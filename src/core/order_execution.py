"""거미줄/RSI 전략 주문 실행 루프 (텔레그램 콜백 + HTTP 웹훅 공용).

기존에 grid_confirm_callback / _internal_execute_grid_handler /
_internal_execute_sgrid_handler / rsitrade_confirm_callback /
_internal_execute_rsitrade_handler / sgridrsi_confirm_callback 에
복붙되어 있던 "주문 발행 루프 + 결과 메시지 전송" 부분을 통합한다.

사전 검증(잔고/세션/예산 재확인 등)과 확인 메시지 빌드는 호출부(콜백/HTTP 핸들러)
책임으로 남기고, 이 모듈은 실제 주문 발행 루프만 담당한다.
"""
import asyncio

from core.exchange_adapter import ExchangeAdapter
from core.parsers import interpolate_range, parse_rsi_range, get_user_rsi_interval
from core.bot_logger import get_logger

_log = get_logger("order_execution")

ORDER_PLACEMENT_SLEEP_SECONDS = 0.2


def _trigger_sync(trigger_sync_fn):
    if trigger_sync_fn is not None:
        asyncio.create_task(trigger_sync_fn())


async def _send_result_message(bot, notify_chat_id, text, log):
    try:
        await bot.send_message(chat_id=notify_chat_id, text=text)
    except Exception as e:
        log.warning("Failed to send strategy execution result message", exc_info=e)


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

    is_sell=False: budget_or_volume은 예산(원화), buy_limit_order로 매수
    is_sell=True : budget_or_volume은 총 매도 수량, create_order(ask)로 매도

    각 주문 발행은 개별 try/except로 감싸 한 건 실패해도 나머지 배치가 계속
    진행되며, group_no는 항상 부여되고 trigger_sync_fn(있으면)을 항상 호출한다.
    """
    log = log or _log
    price_step = (end_price - start_price) / (count - 1) if count > 1 else 0
    success_count = 0
    skipped_count = 0

    for i in range(count):
        target_price = start_price + (price_step * i)
        target_price = (
            ExchangeAdapter.adjust_krx_price_to_tick(target_price)
            if exchange in ("kis", "toss")
            else ExchangeAdapter.adjust_price_to_tick(target_price)
        )

        if is_sell:
            raw_vol = budget_or_volume / count
        else:
            raw_vol = (budget_or_volume / count) / target_price if target_price else 0
        volume = int(raw_vol) if exchange in ("kis", "toss") else round(raw_vol, 4)

        if exchange in ("kis", "toss") and volume <= 0:
            skipped_count += 1
            continue

        try:
            if is_sell:
                res = await exchange_adapter.create_order(user_id, exchange, ticker, "ask", target_price, volume)
            else:
                res = await exchange_adapter.buy_limit_order(user_id, exchange, ticker, target_price, volume)
            if res and 'uuid' in res:
                order_manager.add_order(
                    user_id, exchange, ticker, res['uuid'], target_price, volume,
                    side="ask" if is_sell else "bid",
                    strategy="sgrid" if is_sell else "grid",
                    group_no=group_no,
                )
                success_count += 1
        except Exception as e:
            log.error(f"Grid order placement failed at index {i}", exc_info=e)

        await asyncio.sleep(ORDER_PLACEMENT_SLEEP_SECONDS)

    action_name = "매도" if is_sell else "매수"
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
    """
    log = log or _log
    has_sell = bool(sell_rsi_range) and sell_rsi_range != "-"
    b_start, b_end = parse_rsi_range(buy_rsi_range)
    s_start, s_end = parse_rsi_range(sell_rsi_range) if has_sell else (0, 0)
    interval = get_user_rsi_interval(user)

    success = 0
    skipped_count = 0
    for i in range(count):
        target_rsi = interpolate_range(b_start, b_end, i, count)
        sell_target_rsi = interpolate_range(s_start, s_end, i, count) if has_sell else None
        price = await signal_engine.get_price_by_rsi(
            exchange, ticker, target_rsi,
            side="bid", interval=interval, user_id=user_id,
        )
        if not price:
            await asyncio.sleep(ORDER_PLACEMENT_SLEEP_SECONDS)
            continue
        volume = round(per_order_budgets[i] / price, 4)
        if exchange in ("kis", "toss"):
            volume = int(volume)
            if volume <= 0:
                skipped_count += 1
                await asyncio.sleep(ORDER_PLACEMENT_SLEEP_SECONDS)
                continue

        try:
            res = await exchange_adapter.create_order(user_id, exchange, ticker, "bid", price, volume)
            if res and "uuid" in res:
                order_manager.add_order(
                    user_id, exchange, ticker, res["uuid"], price, volume,
                    side="bid", strategy="rsitrade", target_rsi=target_rsi,
                    linked_to=sell_target_rsi, group_no=group_no,
                )
                success += 1
        except Exception as e:
            log.error(f"RSITrade order placement failed at index {i}", exc_info=e)

        await asyncio.sleep(ORDER_PLACEMENT_SLEEP_SECONDS)

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
    """
    log = log or _log
    s_start, s_end = parse_rsi_range(sell_rsi_range)
    budget_per_order = budget / count
    interval = get_user_rsi_interval(user)

    success = 0
    skipped_count = 0
    for i in range(count):
        target_rsi = interpolate_range(s_start, s_end, i, count)
        price = await signal_engine.get_price_by_rsi(
            exchange, ticker, target_rsi,
            side="ask", interval=interval, user_id=user_id,
        )
        if not price:
            await asyncio.sleep(ORDER_PLACEMENT_SLEEP_SECONDS)
            continue
        volume = round(budget_per_order / price, 4)
        if exchange in ("kis", "toss"):
            volume = int(volume)
            if volume <= 0:
                skipped_count += 1
                await asyncio.sleep(ORDER_PLACEMENT_SLEEP_SECONDS)
                continue

        try:
            res = await exchange_adapter.create_order(user_id, exchange, ticker, "ask", price, volume)
            if res and "uuid" in res:
                order_manager.add_order(
                    user_id, exchange, ticker, res["uuid"], price, volume,
                    side="ask", strategy="sgridrsi", target_rsi=target_rsi,
                    linked_to=None, group_no=group_no,
                )
                success += 1
        except Exception as e:
            log.error(f"sGridRSI order placement failed at index {i}", exc_info=e)

        await asyncio.sleep(ORDER_PLACEMENT_SLEEP_SECONDS)

    result_msg = f"✅ {ticker} RSI 매도 전략 가동 완료! ({success}/{count}건 예약됨, 배치 #{group_no})"
    if skipped_count:
        result_msg += f"\n⚠️ {skipped_count}건은 예산으로 1주도 매도할 수 없어 건너뜀."

    _trigger_sync(trigger_sync_fn)
    await _send_result_message(bot, notify_chat_id, result_msg, log)

    return {"success": success, "skipped_count": skipped_count, "ct": count, "group_no": group_no}
