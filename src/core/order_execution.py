"""거미줄/RSI 전략 주문 실행 루프 (텔레그램 콜백 + HTTP 웹훅 공용).

기존에 grid_confirm_callback / _internal_execute_grid_handler /
_internal_execute_sgrid_handler / rsitrade_confirm_callback /
_internal_execute_rsitrade_handler / sgridrsi_confirm_callback 에
복붙되어 있던 "주문 발행 루프 + 결과 메시지 전송" 부분을 통합한다.

사전 검증(잔고/세션/예산 재확인 등)과 확인 메시지 빌드는 호출부(콜백/HTTP 핸들러)
책임으로 남기고, 이 모듈은 실제 주문 발행 루프만 담당한다.
"""
import asyncio
import uuid as _uuid

from core.parsers import interpolate_range, parse_rsi_range, get_user_rsi_interval
from core.bot_logger import get_logger

_log = get_logger("order_execution")

ORDER_PLACEMENT_SLEEP_SECONDS = 0.2

# fire-and-forget 태스크 강한 참조 보관 (asyncio weak-ref GC로 유실 방지).
_bg_tasks: set = set()


def _trigger_sync(trigger_sync_fn):
    if trigger_sync_fn is not None:
        task = asyncio.create_task(trigger_sync_fn())
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)


async def _send_result_message(bot, notify_chat_id, text, log):
    try:
        await bot.send_message(chat_id=notify_chat_id, text=text)
    except Exception as e:
        log.warning("Failed to send strategy execution result message", exc_info=e)


async def _execute_order_batch(
    *, exchange_adapter, order_manager, user_id, exchange, ticker,
    group_no, count, leg_fn, is_reserved, log,
):
    """grid/rsitrade/sgridrsi가 공유하는 주문 발행 루프.

    leg_fn(i)는 다음 중 하나를 반환한다:
    - None: 이번 회차는 조용히 건너뜀 (예: 가격 조회 실패 — skipped_count 미증가)
    - {"skip": True}: 건너뛰되 사용자에게 보고할 스킵 (예: 예산 부족으로 0주/0개) — skipped_count 증가
    - {"price", "volume", "side", "strategy", "target_rsi"?, "linked_to"?}: 실제 주문 발행

    is_reserved=True면 실거래소 API를 호출하지 않고 "reserved:" 접두 가짜 uuid로
    order_manager에만 등록한다(장외 예약주문). (success_count, skipped_count) 반환.
    """
    success, skipped = 0, 0
    for i in range(count):
        leg = await leg_fn(i)
        if leg is None:
            await asyncio.sleep(ORDER_PLACEMENT_SLEEP_SECONDS)
            continue
        if leg.get("skip"):
            skipped += 1
            await asyncio.sleep(ORDER_PLACEMENT_SLEEP_SECONDS)
            continue

        try:
            if is_reserved:
                res = {"uuid": f"reserved:{_uuid.uuid4().hex}"}
            else:
                res = await exchange_adapter.create_order(
                    user_id, exchange, ticker, leg["side"], leg["price"], leg["volume"],
                )
        except Exception as e:
            log.error(f"Order placement failed at index {i}", exc_info=e)
            res = None

        # create_order는 성공했는데 add_order(추적 등록)가 실패하면 거래소에는 실주문이
        # 걸려 있으나 order_manager가 추적하지 못하는 "고아 주문"이 된다(체결 감시·취소 누락).
        # 발행과 등록을 분리해, 등록 실패 시 uuid를 CRITICAL로 남겨 수동 복구를 가능하게 한다.
        if res and "uuid" in res:
            try:
                order_manager.add_order(
                    user_id, exchange, ticker, res["uuid"], leg["price"], leg["volume"],
                    side=leg["side"], strategy=leg["strategy"],
                    target_rsi=leg.get("target_rsi"), linked_to=leg.get("linked_to"),
                    group_no=group_no, status="reserved" if is_reserved else "wait",
                )
                success += 1
            except Exception as e:
                log.critical(
                    "ORPHAN ORDER: 거래소 주문은 발행됐으나 추적 등록 실패 — 수동 확인 필요",
                    exc_info=e,
                    extra={
                        "event": "orphan_order", "user_id": str(user_id),
                        "exchange": exchange, "ticker": ticker, "uuid": res["uuid"],
                        "side": leg["side"], "price": leg["price"], "volume": leg["volume"],
                    },
                )

        await asyncio.sleep(ORDER_PLACEMENT_SLEEP_SECONDS)

    return success, skipped


async def execute_grid_orders(
    *,
    exchange_adapter,
    order_manager,
    user_id: str,
    exchange: str,
    ticker: str,
    start_price: float,
    end_price: float,
    count: int,
    budget_or_volume: float,
    is_sell: bool,
    group_no: int,
    bot,
    notify_chat_id: str,
    trigger_sync_fn=None,
    log=None,
) -> dict:
    """가격 범위 분할 매수(grid)/매도(sgrid) 주문 발행 루프.

    is_sell=False: budget_or_volume은 예산(원화), bid로 매수
    is_sell=True : budget_or_volume은 총 매도 수량, ask로 매도

    장외 시간(KIS/Toss 정규장 외)이면 실거래소에 주문을 내지 않고
    status="reserved" 배치로 등록해 장 개장 시 sync_orders가 자동 제출한다.
    """
    log = log or _log
    ex = exchange_adapter.get_exchange(exchange)
    is_reserved = getattr(ex, "supports_reserved_orders", False) and not ex.is_market_open(ticker)
    price_step = (end_price - start_price) / (count - 1) if count > 1 else 0

    async def leg_fn(i):
        target_price = start_price + (price_step * i)
        target_price = ex.adjust_price_to_tick(target_price, ticker)

        if is_sell:
            raw_vol = budget_or_volume / count
        else:
            # 수수료 버퍼 0.1%(×0.999)를 적용하여 잔고 부족(Insufficient Balance) 오류를 방지함
            effective_budget = (budget_or_volume / count) * 0.999
            raw_vol = effective_budget / target_price if target_price else 0
        volume = ex.round_volume(raw_vol)

        if ex.requires_integer_volume() and volume <= 0:
            return {"skip": True}

        return {
            "price": target_price, "volume": volume,
            "side": "ask" if is_sell else "bid",
            "strategy": "sgrid" if is_sell else "grid",
        }

    success_count, skipped_count = await _execute_order_batch(
        exchange_adapter=exchange_adapter, order_manager=order_manager,
        user_id=user_id, exchange=exchange, ticker=ticker,
        group_no=group_no, count=count, leg_fn=leg_fn, is_reserved=is_reserved, log=log,
    )

    action_name = "매도" if is_sell else "매수"
    if is_reserved:
        result_msg = f"⏳ `{ticker}` 거미줄 {action_name} 예약 등록 완료! ({success_count}/{count}건)\n장 개장 시 자동으로 실제 주문이 제출됩니다."
    else:
        result_msg = f"✅ `{ticker}` 거미줄 {action_name} 완료! ({success_count}/{count}건 성공)\n백그라운드에서 체결을 감시합니다."
    if skipped_count:
        result_msg += f"\n⚠️ {skipped_count}건은 수량 부족(0주)으로 건너뜀."
    if success_count:
        result_msg += f"\n배치 #{group_no}"

    _trigger_sync(trigger_sync_fn)
    await _send_result_message(bot, notify_chat_id, result_msg, log)

    return {"success_count": success_count, "skipped_count": skipped_count, "ct": count, "group_no": group_no}


async def execute_rsitrade_orders(
    *,
    exchange_adapter,
    order_manager,
    signal_engine,
    user_id: str,
    exchange: str,
    ticker: str,
    buy_rsi_range: str,
    sell_rsi_range: str,
    count: int,
    per_order_budgets: list,
    user: dict,
    group_no: int,
    bot,
    notify_chat_id: str,
    trigger_sync_fn=None,
    log=None,
) -> dict:
    """RSI 역산 기반 분할 매수(rsitrade) 주문 발행 루프.

    has_sell=False (sell_rsi_range가 비었거나 "-")인 경우 linked_to=None으로
    매수 전용 주문을 생성한다 (sgridrsi와 무관한 단순 매수 사이클).
    per_order_budgets는 호출부에서 DCA 가중 분배 또는 균등 분배로 미리 계산해
    전달한다 (가중치 계산 로직은 호출부 책임 — 이 함수는 분배 결과만 사용).

    가격은 RSI 역산(과거 캔들 기준)으로 장외에도 계산 가능하지만, KIS/Toss는
    정규장 외 실거래소 주문 제출이 불가능하므로 grid와 동일하게 장외에는
    reserved 배치로 등록한다(장 개장 시 sync_orders가 자동 제출).
    """
    log = log or _log
    ex = exchange_adapter.get_exchange(exchange)
    is_reserved = getattr(ex, "supports_reserved_orders", False) and not ex.is_market_open(ticker)
    has_sell = bool(sell_rsi_range) and sell_rsi_range != "-"
    b_start, b_end = parse_rsi_range(buy_rsi_range)
    s_start, s_end = parse_rsi_range(sell_rsi_range) if has_sell else (0, 0)
    interval = get_user_rsi_interval(user)

    async def leg_fn(i):
        target_rsi = interpolate_range(b_start, b_end, i, count)
        sell_target_rsi = interpolate_range(s_start, s_end, i, count) if has_sell else None
        price = await signal_engine.get_price_by_rsi(
            exchange, ticker, target_rsi,
            side="bid", interval=interval, user_id=user_id,
        )
        if not price:
            return None
        volume = ex.round_volume(per_order_budgets[i] / price)
        if ex.requires_integer_volume() and volume <= 0:
            return {"skip": True}
        return {
            "price": price, "volume": volume, "side": "bid", "strategy": "rsitrade",
            "target_rsi": target_rsi, "linked_to": sell_target_rsi,
        }

    success, skipped_count = await _execute_order_batch(
        exchange_adapter=exchange_adapter, order_manager=order_manager,
        user_id=user_id, exchange=exchange, ticker=ticker,
        group_no=group_no, count=count, leg_fn=leg_fn, is_reserved=is_reserved, log=log,
    )

    if is_reserved:
        result_msg = f"⏳ `{ticker}` RSI 순환 매매 예약 등록 완료! ({success}/{count}건)\n장 개장 시 자동으로 실제 주문이 제출됩니다."
    else:
        result_msg = f"✅ `{ticker}` RSI 순환 매매 전략 가동 완료! ({success}/{count}건 예약됨)\n백그라운드에서 RSI 체결을 감시합니다."
    if skipped_count:
        result_msg += f"\n⚠️ {skipped_count}건은 예산으로 1주도 매수할 수 없어 건너뜀."
    if success:
        result_msg += f"\n배치 #{group_no}"

    _trigger_sync(trigger_sync_fn)
    await _send_result_message(bot, notify_chat_id, result_msg, log)

    return {"success": success, "skipped_count": skipped_count, "ct": count, "group_no": group_no}


async def execute_sgridrsi_orders(
    *,
    exchange_adapter,
    order_manager,
    signal_engine,
    user_id: str,
    exchange: str,
    ticker: str,
    sell_rsi_range: str,
    count: int,
    budget: float,
    user: dict,
    group_no: int,
    bot,
    notify_chat_id: str,
    trigger_sync_fn=None,
    log=None,
) -> dict:
    """RSI 역산 기반 분할 매도(sgridrsi) 주문 발행 루프 (보유 코인 직접 매도).

    HTTP 웹훅 대응 핸들러는 현재 없으나(/internal/execute_sgridrsi 미존재),
    향후 추가 시 그대로 재사용 가능하도록 동일 패턴으로 통합해둔다.

    KIS/Toss 정규장 외에는 grid와 동일하게 reserved 배치로 등록한다
    (장 개장 시 sync_orders가 자동 제출).
    """
    log = log or _log
    ex = exchange_adapter.get_exchange(exchange)
    is_reserved = getattr(ex, "supports_reserved_orders", False) and not ex.is_market_open(ticker)
    s_start, s_end = parse_rsi_range(sell_rsi_range)
    budget_per_order = budget / count
    interval = get_user_rsi_interval(user)

    async def leg_fn(i):
        target_rsi = interpolate_range(s_start, s_end, i, count)
        price = await signal_engine.get_price_by_rsi(
            exchange, ticker, target_rsi,
            side="ask", interval=interval, user_id=user_id,
        )
        if not price:
            return None
        volume = ex.round_volume(budget_per_order / price)
        if ex.requires_integer_volume() and volume <= 0:
            return {"skip": True}
        return {
            "price": price, "volume": volume, "side": "ask", "strategy": "sgridrsi",
            "target_rsi": target_rsi, "linked_to": None,
        }

    success, skipped_count = await _execute_order_batch(
        exchange_adapter=exchange_adapter, order_manager=order_manager,
        user_id=user_id, exchange=exchange, ticker=ticker,
        group_no=group_no, count=count, leg_fn=leg_fn, is_reserved=is_reserved, log=log,
    )

    if is_reserved:
        result_msg = f"⏳ {ticker} RSI 매도 예약 등록 완료! ({success}/{count}건, 배치 #{group_no})\n장 개장 시 자동으로 실제 주문이 제출됩니다."
    else:
        result_msg = f"✅ {ticker} RSI 매도 전략 가동 완료! ({success}/{count}건 예약됨, 배치 #{group_no})"
    if skipped_count:
        result_msg += f"\n⚠️ {skipped_count}건은 예산으로 1주도 매도할 수 없어 건너뜀."

    _trigger_sync(trigger_sync_fn)
    await _send_result_message(bot, notify_chat_id, result_msg, log)

    return {"success": success, "skipped_count": skipped_count, "ct": count, "group_no": group_no}
