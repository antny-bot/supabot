"""주문 생명주기 관리 및 거래소 동기화 엔진 (Order Synchronization & Lifecycle Engine).

미체결 주문 상태 폴링, 부분/전량 체결 감지, 연동 매도(익절) 자동 생성,
손절/트레일링 스톱 실행, 장외 예약/재주문 자동 제출, 고아 주문 방지 및 복구를 전담한다.
"""
import asyncio
from collections import defaultdict
import time

from core.bot_logger import get_logger
from core.trade_log import append_trade
from core.operational_events import append_operational_event
from core.parsers import (
    exchange_display_name,
    get_user_rsi_interval,
    resolve_linked_rsi_target,
    is_strategy_order,
)
from core.user_manager import UserManager
from core import trading_gate

_log = get_logger("order_sync")

_REORDER_FAIL_LIMIT = 5
_reorder_failures: dict = {}

# 상하한가 제한으로 인한 주문 보류(postponed) 경고 중복 전송 방지용 캐시 (uuid -> True)
_limit_warned_orders: dict = {}

# 재주문/예약주문 매칭 시 가격 비교 허용 오차(원). 거래소 틱 단위 보정 잔차를 흡수한다.
_REORDER_PRICE_TOLERANCE = 1.0

_STOPLOSS_PLACE_RETRIES = 3
_STATUS_CHECK_FAIL_LIMIT = 5
_status_check_failures: dict = {}

_exchange_status_semaphores: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(4))
_exchange_user_semaphores: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(1))


def _get_limit_warned_orders() -> dict:
    import main
    return getattr(main, "_limit_warned_orders", _limit_warned_orders)


def _get_status_check_failures() -> dict:
    import main
    return getattr(main, "_status_check_failures", _status_check_failures)


def _get_reorder_failures() -> dict:
    import main
    return getattr(main, "_reorder_failures", _reorder_failures)


def _call_append_trade(**kwargs):
    import main
    fn = getattr(main, "append_trade", append_trade)
    return fn(**kwargs)


def _call_append_operational_event(level, source, message, details=None):
    import main
    fn = getattr(main, "append_operational_event", append_operational_event)
    return fn(level, source, message, details)


async def _call_cancel_and_remove_order(user_id: str, ord_dict: dict) -> bool:
    import main
    fn = getattr(main, "cancel_and_remove_order", cancel_and_remove_order)
    return await fn(user_id, ord_dict)


def _get_app_context():
    """main 모듈의 전역 싱글턴 인스턴스에 접근한다."""
    import main
    return main.order_manager, main.user_manager, main.exchange_adapter, main.signal_engine


async def _find_duplicate_open_order(exchange_adapter, user_id, exchange, ticker, side, price, volume):
    """재주문/예약주문 발행 직전, 이전 사이클의 create_order 응답이 유실됐을 뿐 실제로는
    거래소에 이미 제출된 동일 스펙의 미체결 주문이 있는지 확인한다.
    """
    try:
        open_orders = await exchange_adapter.get_open_orders(user_id, exchange, ticker)
    except Exception:
        return None
    if not open_orders:
        return None
    for o in open_orders:
        if not o.get("uuid"):
            continue
        if o.get("side") != side:
            continue
        if abs(float(o.get("price", 0)) - float(price)) > _REORDER_PRICE_TOLERANCE:
            continue
        if abs(float(o.get("volume", 0)) - float(volume)) > 1e-6:
            continue
        return o
    return None


_TOP_N_AGGRESSIVE_TICKS = 2


def _shift_krx_ticks(price: float, ticks: int) -> float:
    """KRX 호가 단위로 price를 ticks만큼 이동(양수=위, 음수=아래). 호가 구간 경계를 단계마다 재계산한다."""
    from core.exchanges.common import CommonMixin
    p = float(CommonMixin.adjust_krx_price_to_tick(price))
    step = 1 if ticks > 0 else -1
    for _ in range(abs(ticks)):
        if step > 0:
            p += CommonMixin.get_krx_tick_size(p)
        else:
            # 하향 시에는 직전 호가 구간의 틱 크기를 사용 (경계값에서 내려갈 때)
            p -= CommonMixin.get_krx_tick_size(p - 1) if p > 1 else 0
    return float(p)


async def _get_template_order_price_mode(template_id) -> str:
    """전략 템플릿의 order_price_mode 조회. 실패/미설정 시 'limit_current'."""
    if template_id is None:
        return "limit_current"
    try:
        from core.db import get_db, is_db_available
        if not is_db_available():
            return "limit_current"
        res = await get_db().table("strategy_templates").select("params").eq("id", int(template_id)).execute_async()
        if res.data:
            mode = str((res.data[0].get("params") or {}).get("order_price_mode") or "").strip().lower()
            if mode in ("limit_current", "limit_aggressive", "market"):
                return mode
    except Exception as e:
        _log.warning(f"Failed to load order_price_mode for template {template_id}: {e}")
    return "limit_current"


def compute_top_n_order_plan(mode: str, side: str, current_price: float, stored_price: float,
                             upper_limit=None, lower_limit=None) -> tuple[str, float]:
    """TOP N 예약주문 제출 시점의 (ord_type, price) 산출.

    배치 시점 가격(전일 종가 스냅샷)은 낡았으므로 제출 시점 현재가를 기준으로 재산정한다.
    현재가를 알 수 없으면 저장된 가격으로 지정가 제출(기존 동작)한다.
    """
    if not current_price or current_price <= 0:
        return "limit", float(stored_price or 0)
    if mode == "market":
        return "market", float(current_price)
    if mode == "limit_aggressive":
        ticks = _TOP_N_AGGRESSIVE_TICKS if side == "bid" else -_TOP_N_AGGRESSIVE_TICKS
        price = _shift_krx_ticks(current_price, ticks)
    else:
        from core.exchanges.common import CommonMixin
        price = float(CommonMixin.adjust_krx_price_to_tick(current_price))
    if upper_limit is not None and price > float(upper_limit):
        price = float(upper_limit)
    if lower_limit is not None and price < float(lower_limit):
        price = float(lower_limit)
    return "limit", price


def _extract_order_submit_failure_reason(res):
    """거래소 주문 발행 실패 응답에서 사용자/운영자가 볼 수 있는 최소 원인을 뽑아낸다."""
    if not isinstance(res, dict):
        return None
    err = res.get("error")
    if isinstance(err, dict):
        code = str(err.get("code") or "").strip()
        msg = str(err.get("message") or err.get("error_description") or err.get("description") or "").strip()
        if code and msg:
            return f"{code}: {msg}"
        if code:
            return code
        if msg:
            return msg
    for key in ("message", "error_description", "description"):
        val = str(res.get(key) or "").strip()
        if val:
            return val
    return None


def _find_linked_sell_orders(buy_uuid: str) -> list[dict]:
    """주어진 rsitrade 매수 주문에 연동된 모든 익절매도 주문(reorder_of==buy_uuid) 목록을 반환한다."""
    order_manager, _, _, _ = _get_app_context()
    return [o for o in order_manager.orders if o.get("strategy") == "rsitrade_sell" and o.get("reorder_of") == buy_uuid]


def _find_linked_sell_order(buy_uuid: str) -> dict | None:
    """하위 호환성을 위한 단수형 조회 함수."""
    sells = _find_linked_sell_orders(buy_uuid)
    return sells[0] if sells else None


async def _create_linked_sell_order(application, ord, exec_vol, state):
    """rsitrade 매수 체결 시 연동된 익절매도 주문을 생성한다.

    sync_orders의 정상 처리 경로와 startup_recovery의 크래시 복구 경로가 동일 로직을
    공유한다. 부분 체결이 여러 번에 걸쳐 일어나는 경우에도 이미 발행된 매도 주문 수량 합계를
    계산해 아직 매도가 발행되지 않은 추가 체결분에 대해 익절 주문을 정상 발행한다.
    크래시 복구 시에는 이미 체결량만큼 매도 주문이 발행되어 있으면 중복 발행 없이
    매수의 filled_volume만 동기화한다 (멱등성 보장).

    Returns: "created" | "exists" | "no_price" | "zero_volume" | "failed" | "external_sold"
    """
    order_manager, user_manager, exchange_adapter, signal_engine = _get_app_context()
    user_id = ord["user_id"]
    exchange = ord["exchange"]
    ticker = ord["ticker"]
    exec_vol_float = float(exec_vol)

    # 1. 이미 해당 매수 주문에 연동되어 발행된 매도 주문들의 수량 합산
    linked_sells = _find_linked_sell_orders(ord["uuid"])
    existing_sell_vol = sum(float(s.get("volume", 0.0)) for s in linked_sells)

    # 이미 전체 체결량 이상의 매도 주문이 발행되어 있다면 (직전 크래시 후 재동기화 등) 중복 발행 방지
    if existing_sell_vol >= exec_vol_float:
        order_manager.update_order_fill(ord["uuid"], exec_vol_float, state)
        return "exists"

    # 아직 매도 주문이 발행되지 않은 잔여 체결 수량 계산
    needed_sell_vol = exec_vol_float - existing_sell_vol
    if needed_sell_vol <= 0:
        order_manager.update_order_fill(ord["uuid"], exec_vol_float, state)
        return "exists"

    target_rsi = resolve_linked_rsi_target(ord["linked_to"])
    user = user_manager.get_user(user_id) or {"preferences": UserManager.DEFAULT_PREFERENCES}
    sell_price = await signal_engine.get_price_by_rsi(
        exchange,
        ticker,
        target_rsi,
        side="ask",
        interval=get_user_rsi_interval(user),
        user_id=user_id,
    )
    if not sell_price:
        return "no_price"

    ex = exchange_adapter.get_exchange(exchange)
    sell_volume = ex.round_volume(needed_sell_vol)
    if ex.requires_integer_volume() and sell_volume <= 0:
        return "zero_volume"

    s_res = None
    try:
        s_res = await exchange_adapter.create_order(user_id, exchange, ticker, "ask", sell_price, sell_volume)
    except Exception as e:
        _log.warning(f"create_order failed for linked sell: {e}")

    if not (s_res and "uuid" in s_res):
        try:
            balances = await exchange_adapter.get_balances(user_id, exchange)
            avail_vol = 0.0
            if balances:
                for b in balances:
                    b_ticker = b.get("currency") or b.get("ticker") or ""
                    if b_ticker.upper() == ticker.upper() or ticker.endswith(b_ticker) or b_ticker.endswith(ticker):
                        avail_vol = float(b.get("balance", 0.0) or 0.0)
                        break
            if avail_vol < sell_volume:
                order_manager.update_order_fill(ord["uuid"], exec_vol_float, state)
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ [{exchange.upper()}] {ticker} 잔고 부족 (보유: {avail_vol:g}개 / 필요: {sell_volume:g}개)\n"
                         f"외부에서 수동 매도된 것으로 감지되어 익절 주문 생성을 생략하고 추적을 종료합니다.",
                )
                return "external_sold"
        except Exception as bal_err:
            _log.warning(f"Failed to check balance after linked sell failure: {bal_err}")
        return "failed"

    stop_loss_pct = float(user.get("preferences", {}).get("stop_loss_pct", 0) or 0)
    stop_price = (
        ex.adjust_price_to_tick(ord["price"] * (1 - stop_loss_pct / 100), ticker)
        if stop_loss_pct > 0 else None
    )
    order_manager.add_order(user_id, exchange, ticker, s_res["uuid"], sell_price, sell_volume,
                             side="ask", strategy="rsitrade_sell", target_rsi=target_rsi,
                             stop_price=stop_price, group_no=ord.get("group_no"),
                             reorder_of=ord["uuid"], template_id=ord.get("template_id"))
    order_manager.update_order_fill(ord["uuid"], exec_vol_float, state)
    await application.bot.send_message(
        chat_id=user_id,
        text=f"✅ [{ticker}] 매수 체결 및 익절 예약 완료\n"
             f"• 체결: {needed_sell_vol:.4f}개\n"
             f"• 익절가: {sell_price:,.0f}원 (RSI {target_rsi} 목표)",
    )
    return "created"


async def reconcile_external_sells_fifo(application, user_id: str, exchange: str, ticker: str, current_balance: float):
    """외부 매도 등으로 인해 거래소 실제 잔고가 봇의 오픈 매도 주문 합계보다 적을 때 FIFO로 최근 매도 주문을 정리한다."""
    order_manager, _, _, _ = _get_app_context()
    user_orders = order_manager.get_user_orders(user_id, exchange)
    open_asks = [
        o for o in user_orders
        if o.get("ticker") == ticker and o.get("side") == "ask" and o.get("status") in ("wait", "partial", "reserved", "pending_reorder")
    ]
    if not open_asks:
        return

    total_ask_volume = sum(float(o.get("volume", 0)) - float(o.get("filled_volume", 0)) for o in open_asks)
    if current_balance >= total_ask_volume:
        return

    sorted_asks = sorted(open_asks, key=lambda x: float(x.get("created_at", 0) or 0))
    remaining_balance = max(0.0, current_balance)
    canceled_orders = []

    for ord_item in sorted_asks:
        ord_rem_vol = float(ord_item.get("volume", 0)) - float(ord_item.get("filled_volume", 0))
        if remaining_balance >= ord_rem_vol:
            remaining_balance -= ord_rem_vol
        else:
            await _call_cancel_and_remove_order(user_id, ord_item)
            canceled_orders.append(ord_item)

    if canceled_orders:
        strat_names = ", ".join(f"[{o.get('strategy', '전략')}]" for o in canceled_orders)
        await application.bot.send_message(
            chat_id=user_id,
            text=f"⚠️ [{exchange.upper()}] {ticker} 외부 매도 감지\n"
                 f"실제 잔고({current_balance:g}개)가 매도 주문 수량({total_ask_volume:g}개)보다 적어 "
                 f"FIFO 원칙에 따라 최근 주문 {strat_names}이 자동 정리되었습니다.",
        )


async def _refund_unfilled_budget(ord_dict: dict, filled_volume: float | None = None) -> None:
    """취소/만료로 종료되는 지정가 DCA 매수 주문의 미체결분 예산을 템플릿에 환원한다 (ORDER_CANCEL_REFUND, 주문 UUID 기준 중복 환원 차단).

    접수 시 차감한 금액(price*volume) 중 체결되지 않은 수량 몫만 되돌린다. 시장가 주문은 대상이 아니다.
    """
    try:
        if ord_dict.get("strategy") != "dca" or ord_dict.get("side") != "bid":
            return
        if ord_dict.get("template_id") is None or ord_dict.get("order_type") == "market":
            return
        vol = float(ord_dict.get("volume") or 0.0)
        filled = float(ord_dict.get("filled_volume") or 0.0) if filled_volume is None else float(filled_volume)
        unfilled = max(0.0, vol - filled)
        refund = round(float(ord_dict.get("price") or 0.0) * unfilled)
        if refund <= 0:
            return
        from core.budget_ledger import record_budget_adjust
        await record_budget_adjust(
            user_id=ord_dict["user_id"],
            template_id=int(ord_dict["template_id"]),
            diff_krw=-float(refund),
            ticker=ord_dict["ticker"],
            qty=unfilled,
            group_no=ord_dict.get("group_no"),
            order_uuid=ord_dict["uuid"],
            description=f"DCA 주문 취소 미체결분 예산 환원: {ord_dict['ticker']} {unfilled:g}주 ({refund:,.0f}원)",
            entry_type="ORDER_CANCEL_REFUND",
        )
    except Exception as e:
        _log.error("Failed to refund unfilled DCA budget for %s: %s", ord_dict.get("uuid"), e)


async def cancel_and_remove_order(user_id: str, ord_dict: dict) -> bool:
    """거래소에 주문 취소를 요청하고, 성공하거나 이미 완료된 주문이면 order_manager에서 제거합니다."""
    order_manager, _, exchange_adapter, _ = _get_app_context()
    exchange = ord_dict["exchange"]
    uuid = ord_dict["uuid"]
    ticker = ord_dict["ticker"]

    try:
        cancel_ok = await exchange_adapter.cancel_order(user_id, exchange, uuid, ticker)
        if cancel_ok:
            filled_so_far = float(ord_dict.get("filled_volume") or 0.0)
            order_manager.remove_order(uuid)
            await _refund_unfilled_budget(ord_dict, filled_so_far)
            return True
    except Exception as e:
        _log.warning(f"Exception during cancel_order for {uuid}", exc_info=e)

    try:
        status_res = await exchange_adapter.get_order_status(user_id, exchange, uuid, ticker)
        if status_res is not None and status_res.get("state") in ("done", "cancel"):
            exec_vol = max(
                float(ord_dict.get("filled_volume") or 0.0),
                float(status_res.get("executed_volume") or 0.0),
            )
            order_manager.remove_order(uuid)
            if status_res.get("state") == "cancel":
                await _refund_unfilled_budget(ord_dict, exec_vol)
            return True
    except Exception as e:
        _log.warning(f"Failed to check order status after cancel failure for {uuid}", exc_info=e)

    return False


def _cleanup_stale_caches(active_uuids: set):
    """현재 추적 중이지 않은 주문의 limit warning 및 재시도 실패 캐시 정리 (메모리 누수 방지)."""
    lwo = _get_limit_warned_orders()
    for uid in list(lwo.keys()):
        if uid not in active_uuids:
            lwo.pop(uid, None)
    rf = _get_reorder_failures()
    for uid in list(rf.keys()):
        if uid not in active_uuids:
            rf.pop(uid, None)
    scf = _get_status_check_failures()
    for uid in list(scf.keys()):
        if uid not in active_uuids:
            scf.pop(uid, None)


async def _handle_market_closed(ord: dict, ex_obj) -> bool:
    """장외 시간 주문 처리. 장외인 경우 True를 반환해 추가 조회를 건너뜀."""
    order_manager, _, _, _ = _get_app_context()
    ticker = ord["ticker"]
    if not ex_obj.is_market_open(ticker):
        next_check = ex_obj.next_check_timestamp(ticker)
        status = ord.get("status") if ord.get("status") in ("pending_reorder", "reserved") else "market_closed"
        order_manager.update_order_status(ord["uuid"], status)
        order_manager.update_next_check_at(ord["uuid"], next_check)
        return True
    return False


async def _submit_reserved_or_reorder(application, ord: dict, ex_obj, ticker_cache: dict = None) -> bool:
    """예약/재주문 상태의 주문을 거래소에 제출. 처리된 경우 True를 반환."""
    if not (getattr(ex_obj, "supports_reserved_orders", False) and ord.get("status") in ("pending_reorder", "reserved")):
        return False

    order_manager, _, exchange_adapter, _ = _get_app_context()
    ticker = ord["ticker"]
    user_id = ord["user_id"]
    exchange = ord["exchange"]

    remaining = max(float(ord.get("volume", 0)) - float(ord.get("filled_volume", 0)), 0)
    if remaining <= 0:
        order_manager.remove_order(ord["uuid"])
        return True

    if trading_gate.is_trading_halted():
        order_manager.update_next_check_at(ord["uuid"], ex_obj.next_check_timestamp(ticker))
        return True

    if not getattr(ex_obj, "is_order_placement_allowed", lambda t: True)(ticker):
        order_manager.update_next_check_at(ord["uuid"], ex_obj.next_check_timestamp(ticker))
        return True

    vol = int(remaining) if ex_obj.requires_integer_volume() else remaining
    side = ord.get("side", "bid")
    price = ord.get("price")
    submit_ord_type = "limit"

    is_kr_stock = (exchange == "kis") or (exchange == "toss" and not getattr(ex_obj, "is_us_stock", lambda t: False)(ticker))
    if is_kr_stock:
        try:
            cache_key = f"{exchange}:{ticker}:{user_id}"
            ticker_info = ticker_cache.get(cache_key) if ticker_cache is not None else None
            if ticker_info is None:
                ticker_info = await ex_obj.get_ticker(ticker, user_id=user_id)
                if ticker_cache is not None and ticker_info:
                    ticker_cache[cache_key] = ticker_info
            if ticker_info:
                upper_limit = ticker_info.get("upper_limit_price")
                lower_limit = ticker_info.get("lower_limit_price")

                # TOP N 전략: 배치 시점의 낡은 가격 대신 제출 시점 현재가 + 템플릿 order_price_mode로 재산정
                if str(ord.get("strategy", "")).startswith("kospi_top") and ord.get("status") == "reserved":
                    mode = await _get_template_order_price_mode(ord.get("template_id"))
                    try:
                        cur_px = float(ticker_info.get("trade_price") or 0)
                    except (TypeError, ValueError):
                        cur_px = 0.0
                    submit_ord_type, price = compute_top_n_order_plan(
                        mode, side, cur_px, float(price or 0), upper_limit, lower_limit,
                    )
                    _log.info(
                        f"TOP N order plan {ticker}: mode={mode} type={submit_ord_type} "
                        f"stored={ord.get('price')} cur={cur_px} -> price={price}"
                    )

                price_val = float(price) if price is not None else 0.0

                is_limit_exceeded = False
                limit_reason = ""
                if upper_limit is not None and price_val > float(upper_limit):
                    is_limit_exceeded = True
                    limit_reason = f"주문가격이 상한가({float(upper_limit):,.0f}원) 초과입니다."
                elif lower_limit is not None and price_val < float(lower_limit):
                    is_limit_exceeded = True
                    limit_reason = f"주문가격이 하한가({float(lower_limit):,.0f}원) 미만입니다."

                lwo = _get_limit_warned_orders()
                rf = _get_reorder_failures()
                if is_limit_exceeded:
                    order_manager.update_next_check_at(ord["uuid"], ex_obj.next_check_timestamp(ticker))
                    if ord["uuid"] not in lwo:
                        action = "재주문" if ord.get("status") == "pending_reorder" else "예약주문 실행"
                        order_kind = "전략" if is_strategy_order(ord) else "자동 재주문 설정"
                        label = exchange_display_name(exchange)

                        _call_append_operational_event("warning", "sync_orders", f"{exchange} {action} postponed: {limit_reason}", ticker)
                        await application.bot.send_message(
                            chat_id=user_id,
                            text=f"⚠️ [{label}] {ticker} {order_kind} 주문 {action} 실패 (상하한가 제한)\n"
                                 f"• 사유: {limit_reason}\n"
                                 f"다음 정규장 체크 때 다시 시도합니다.",
                        )
                        lwo[ord["uuid"]] = True
                    return True
        except Exception as e:
            _log.warning(f"Error checking price limits for {exchange} {ticker} during sync: {e}")

    lwo = _get_limit_warned_orders()
    rf = _get_reorder_failures()
    dup = None
    if submit_ord_type != "market":
        dup = await _find_duplicate_open_order(exchange_adapter, user_id, exchange, ticker, side, price, vol)
    if dup:
        res = dup
    elif submit_ord_type == "market":
        res = await exchange_adapter.create_order(user_id, exchange, ticker, side, price, vol, ord_type="market")
    else:
        res = await exchange_adapter.create_order(user_id, exchange, ticker, side, price, vol)
    action = "재주문" if ord.get("status") == "pending_reorder" else "예약주문 실행"
    order_kind = "전략" if is_strategy_order(ord) else "자동 재주문 설정"
    label = exchange_display_name(exchange)
    if res and "uuid" in res:
        old_uuid = ord["uuid"]
        rf.pop(old_uuid, None)
        lwo.pop(old_uuid, None)
        if not dup:
            old_price = float(ord.get("price") or 0.0)
            new_price = float(price) if price is not None else old_price
            # 제출에 실제 사용된 가격/주문유형을 기록 (체결 로그가 낡은 스냅샷 가격이 아닌 제출가를 쓰도록)
            ord["price"] = new_price
            if submit_ord_type == "market":
                ord["order_type"] = "market"
            elif (
                str(ord.get("strategy", "")).startswith("kospi_top")
                and side == "bid"
                and ord.get("template_id") is not None
                and old_price > 0
                and new_price > 0
            ):
                diff_krw = (new_price - old_price) * float(vol or 0.0)
                if round(diff_krw) != 0:
                    try:
                        from core.budget_ledger import record_budget_adjust
                        await record_budget_adjust(
                            user_id=user_id,
                            template_id=int(ord["template_id"]),
                            diff_krw=diff_krw,
                            ticker=ticker,
                            qty=float(vol or 0.0),
                            group_no=ord.get("group_no"),
                            order_uuid=res["uuid"],
                            description=(
                                f"TOP N 예약주문 장개시 발주가 정산: {ticker} {float(vol or 0.0):g}주 "
                                f"({old_price:,.0f}원 → {new_price:,.0f}원)"
                            ),
                        )
                    except Exception as adj_err:
                        _log.error("Failed to record TOP N reserve submit budget adjust: %s", adj_err)
        order_manager.replace_order_uuid(old_uuid, res["uuid"])
        await application.bot.send_message(
            chat_id=user_id,
            text=f"✅ [{label}] {ticker} {order_kind} 주문 {action} 완료\n"
                 f"• 가격: {'시장가' if submit_ord_type == 'market' else format(float(ord.get('price', 0)), ',.0f') + '원'}\n"
                 f"• 잔량: {remaining:,.0f}주\n"
                 f"• 새 주문ID: {res['uuid']}",
        )
    else:
        reason = _extract_order_submit_failure_reason(res)
        error_detail = f"\n• 사유: {reason}" if reason else ""
        fails = rf.get(ord["uuid"], 0) + 1
        rf[ord["uuid"]] = fails
        if fails >= _REORDER_FAIL_LIMIT:
            rf.pop(ord["uuid"], None)
            lwo.pop(ord["uuid"], None)
            order_manager.remove_order(ord["uuid"])
            _call_append_operational_event(
                "warning",
                "sync_orders",
                f"{exchange} {action} failed {fails}x, giving up: {reason or ''}",
                details=res,
            )
            await application.bot.send_message(
                chat_id=user_id,
                text=f"🛑 [{label}] {ticker} {order_kind} 주문 {action} {fails}회 연속 실패로 추적을 종료합니다.{error_detail}\n"
                     f"필요 시 수동으로 다시 주문해 주세요.",
            )
        else:
            if ex_obj.is_market_open(ticker):
                retry_ts = time.time() + 60.0
                retry_msg = "잠시 후 다시 시도합니다."
            else:
                retry_ts = ex_obj.next_check_timestamp(ticker)
                retry_msg = "다음 정규장 체크 때 다시 시도합니다."
            order_manager.update_next_check_at(ord["uuid"], retry_ts)
            _call_append_operational_event(
                "warning",
                "sync_orders",
                f"{exchange} strategy {action} failed ({fails}/{_REORDER_FAIL_LIMIT}): {reason or ''}",
                details=res,
            )
            await application.bot.send_message(
                chat_id=user_id,
                text=f"⚠️ [{label}] {ticker} {order_kind} 주문 {action} 실패 ({fails}/{_REORDER_FAIL_LIMIT}){error_detail}\n{retry_msg}",
            )
    return True


async def _apply_stop_loss(application, ord: dict, state: str, price_cache: dict) -> bool:
    """손절(Stop-Loss) 조건 평가 및 실행. 손절 주문이 발행된 경우 True 반환."""
    if not (ord.get("strategy") == "rsitrade_sell" and ord.get("stop_price") and state == "wait"):
        return False

    order_manager, _, exchange_adapter, _ = _get_app_context()
    exchange = ord["exchange"]
    ticker = ord["ticker"]
    user_id = ord["user_id"]

    cache_key = (exchange, ticker)
    if cache_key not in price_cache:
        from core.websocket_client import ticker_engine
        ws_price = ticker_engine.get_price(exchange, ticker) if ticker_engine else None
        if ws_price and ws_price > 0:
            price_cache[cache_key] = float(ws_price)
        else:
            tkr = await exchange_adapter.get_ticker(exchange, ticker, user_id)
            price_cache[cache_key] = float(tkr.get("trade_price", 0)) if tkr else 0.0
    current_price = price_cache.get(cache_key, 0.0)

    if ord.get("trailing_stop_pct") is not None and current_price > 0:
        trailing_pct = float(ord["trailing_stop_pct"])
        expected_stop_price = current_price * (1 - trailing_pct / 100)
        expected_stop_price = exchange_adapter.get_exchange(exchange).adjust_price_to_tick(expected_stop_price, ticker)
        if expected_stop_price > float(ord["stop_price"]):
            order_manager.update_order_stop_price(ord["uuid"], expected_stop_price)
            ord["stop_price"] = expected_stop_price
            _log.info(f"Trailing stop updated for {ticker}: stop_price -> {expected_stop_price:,.0f}원 (현재가: {current_price:,.0f}원)")

    if current_price and current_price < float(ord["stop_price"]):
        cancel_ok = await exchange_adapter.cancel_order(user_id, exchange, ord["uuid"], ticker)
        if cancel_ok:
            remaining = float(ord["volume"]) - float(ord["filled_volume"])
            sl_price = exchange_adapter.get_exchange(exchange).adjust_price_to_tick(current_price * 0.999, ticker)
            sl_res = None
            for _sl_attempt in range(_STOPLOSS_PLACE_RETRIES):
                sl_res = await exchange_adapter.create_order(
                    user_id, exchange, ticker, "ask", sl_price, remaining
                )
                if sl_res and "uuid" in sl_res:
                    break
                await asyncio.sleep(0.3)
            order_manager.remove_order(ord["uuid"])
            if sl_res and "uuid" in sl_res:
                order_manager.add_order(
                    user_id, exchange, ticker, sl_res["uuid"],
                    sl_price, remaining, side="ask", strategy="stoploss",
                )
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"🛑 [{ticker}] 손절 실행\n"
                         f"• 현재가: {current_price:,.0f}원\n"
                         f"• 손절 기준가: {float(ord['stop_price']):,.0f}원\n"
                         f"• 손절 주문이 제출되었습니다.",
                )
            else:
                _call_append_operational_event(
                    "error", "sync_orders",
                    f"{exchange} stop-loss order placement failed after retries (position unprotected)",
                    ticker,
                )
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"🚨 [{ticker}] 손절 주문 발행 실패\n"
                         f"• 현재가: {current_price:,.0f}원\n"
                         f"• 손절 기준가: {float(ord['stop_price']):,.0f}원\n"
                         f"• 기존 익절 주문은 취소되었으나 손절 매도가 접수되지 않았습니다.\n"
                         f"• ⚠️ 잔량이 무방비 상태입니다. 즉시 수동으로 매도해 주세요.",
                )
        return True

    return False


async def _process_order_fill(application, ord: dict, res: dict, ex_obj) -> None:
    """체결 감지 및 완료/취소 상태 처리."""
    order_manager, _, _, _ = _get_app_context()
    state = res['state']
    exec_vol = float(res.get('executed_volume', 0.0))
    user_id = ord['user_id']
    exchange = ord['exchange']
    ticker = ord['ticker']
    keep_order_for_retry = False
    current_filled = float(ord.get('filled_volume', 0.0))

    if exec_vol > current_filled:
        if ord['side'] == 'bid' and ord['strategy'] == 'rsitrade' and ord['linked_to']:
            outcome = await _create_linked_sell_order(application, ord, exec_vol, state)
            if outcome == "zero_volume":
                keep_order_for_retry = True
                return
            if outcome in ("no_price", "failed"):
                keep_order_for_retry = True
            elif outcome == "external_sold":
                keep_order_for_retry = False
        else:
            # 시장가 매수(DCA/SDCA 등)로 인해 발주 시점 추정 수량(volume)과 실제 거래소 체결 수량(exec_vol)이
            # 다를 수 있으므로, 시장가 주문에 한해 완료(done) 시점에 실제 체결 수량으로 주문 volume을 보정하여 일치시킨다.
            ord_vol = float(ord.get("volume") or 0.0)
            ord_type = ord.get("order_type")
            if ord_type is not None:
                is_market_order = ord_type == "market" or ord_vol <= 0
            else:
                is_market_order = ord_vol <= 0 or ord.get("strategy") in ("dca", "sdca")
            is_top_n = str(ord.get("strategy", "")).startswith("kospi_top")
            if state == "done" and exec_vol > 0 and is_market_order and (ord.get("strategy") in ("dca", "sdca") or is_top_n):
                est_ord_price = float(ord.get("price") or 0.0)
                exec_funds = float(res.get("executed_funds") or res.get("total_amount") or 0.0)
                if exec_funds <= 0 and float(res.get("price") or 0.0) > 0:
                    exec_funds = float(res["price"]) * exec_vol
                if is_top_n and exec_funds > 0 and exec_vol > 0:
                    ord["price"] = round(exec_funds / exec_vol, 4)
                order_manager.update_order(ord['uuid'], volume=exec_vol, filled_volume=exec_vol, status=state)
                # 시장가 매수(DCA / TOP N) 체결 완료 시 실제 소요 금액과 당초 주문 차감액 차이 정산 (BUY_ORDER_ADJUST)
                if (ord.get("strategy") == "dca" or is_top_n) and ord.get("side") == "bid" and ord.get("template_id") is not None:
                    try:
                        est_cost = float(round(est_ord_price * ord_vol)) if ord_vol > 0 else est_ord_price
                        diff_krw = exec_funds - est_cost if exec_funds > 0 and est_cost > 0 else 0.0
                        if round(diff_krw) != 0:
                            from core.budget_ledger import record_budget_adjust
                            await record_budget_adjust(
                                user_id=user_id,
                                template_id=int(ord["template_id"]),
                                diff_krw=diff_krw,
                                ticker=ticker,
                                qty=exec_vol,
                                group_no=ord.get("group_no"),
                                order_uuid=ord["uuid"],
                            )
                    except Exception as adj_err:
                        _log.error("Failed to record budget adjust in order_sync: %s", adj_err)
            else:
                order_manager.update_order_fill(ord['uuid'], exec_vol, state)
            if state == "done":
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ [{exchange.upper()}] {ticker} 주문 완료\n"
                         f"• {'매수' if ord['side']=='bid' else '매도'} 전량 체결되었습니다.",
                )

    if state in ["done", "cancel"] and not keep_order_for_retry:
        if state == "cancel":
            strategy_name = str(ord.get("strategy", ""))
            if (
                getattr(ex_obj, "supports_reserved_orders", False)
                and (is_strategy_order(ord) or ord.get("auto_reorder"))
                and not strategy_name.startswith("kospi_top")
            ):
                next_check = ex_obj.next_check_timestamp(ticker)
                order_manager.mark_reorder_pending(ord['uuid'], next_check)
                order_kind = "전략" if is_strategy_order(ord) else "자동 재주문 설정"
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"⏳ [{exchange_display_name(exchange)}] {ticker} {order_kind} 주문이 만료/취소되어 다음 정규장 재주문 예정입니다.",
                )
                return
            if exec_vol > 0:
                extra_kw = {}
                if ord.get("group_no") is not None:
                    extra_kw["group_no"] = ord["group_no"]
                if ord.get("template_id") is not None:
                    extra_kw["template_id"] = ord["template_id"]
                _call_append_trade(
                    user_id=user_id,
                    exchange=exchange,
                    ticker=ticker,
                    side=ord["side"],
                    price=ord["price"],
                    volume=float(exec_vol),
                    strategy=ord.get("strategy", "manual"),
                    uuid=ord["uuid"],
                    fee_amount=float(res.get("fee_amount") or 0),
                    **extra_kw,
                )
            await _refund_unfilled_budget(ord, max(current_filled, exec_vol))
            await application.bot.send_message(
                chat_id=user_id,
                text=f"🛑 [{exchange_display_name(exchange)}] {ticker} 외부 개입 감지\n"
                     f"• 주문이 거래소에서 취소되었습니다. 추적을 중단합니다.",
            )
        if state == "done":
            extra_kw = {}
            if ord.get("group_no") is not None:
                extra_kw["group_no"] = ord["group_no"]
            if ord.get("template_id") is not None:
                extra_kw["template_id"] = ord["template_id"]
            _call_append_trade(
                user_id=user_id,
                exchange=exchange,
                ticker=ticker,
                side=ord["side"],
                price=ord["price"],
                volume=float(exec_vol) if exec_vol else float(ord.get("filled_volume", ord["volume"])),
                strategy=ord.get("strategy", "manual"),
                uuid=ord["uuid"],
                fee_amount=float(res.get("fee_amount") or 0),
                **extra_kw,
            )
        order_manager.remove_order(ord['uuid'])
    elif state != ord.get("status"):
        order_manager.update_order_status(ord['uuid'], state)


async def _handle_cancel_requested(application, ord: dict, ex_obj) -> None:
    """Manager가 요청한 취소를 수행한다."""
    order_manager, _, exchange_adapter, _ = _get_app_context()
    uuid = ord["uuid"]
    if str(uuid).startswith("reserved:"):
        order_manager.remove_order(uuid)
        return

    user_id = ord["user_id"]
    exchange = ord["exchange"]
    ticker = ord["ticker"]

    exec_vol = float(ord.get("filled_volume") or 0.0)
    fee_amount = 0.0
    try:
        res = await exchange_adapter.get_order_status(user_id, exchange, uuid, ticker)
    except Exception as e:
        _log.warning(f"Failed to query status before cancel for {uuid}", exc_info=e)
        res = None

    if res:
        if res.get("state") == "done":
            await _process_order_fill(application, ord, res, ex_obj)
            return
        exec_vol = max(exec_vol, float(res.get("executed_volume") or 0.0))
        fee_amount = float(res.get("fee_amount") or 0.0)

    ord["filled_volume"] = max(float(ord.get("filled_volume") or 0.0), exec_vol)
    if not await _call_cancel_and_remove_order(user_id, ord):
        return

    if exec_vol > 0:
        extra_kw = {}
        if ord.get("group_no") is not None:
            extra_kw["group_no"] = ord["group_no"]
        if ord.get("template_id") is not None:
            extra_kw["template_id"] = ord["template_id"]
        _call_append_trade(
            user_id=user_id,
            exchange=exchange,
            ticker=ticker,
            side=ord["side"],
            price=ord["price"],
            volume=exec_vol,
            strategy=ord.get("strategy", "manual"),
            uuid=uuid,
            fee_amount=fee_amount,
            **extra_kw,
        )


async def sync_orders(application):
    """현재 추적 중인 주문들의 상태를 거래소와 동기화하고 자동 대응 수행."""
    import main
    from internal_api import trigger_realtime_sync

    order_manager, _, exchange_adapter, _ = _get_app_context()
    active_uuids = {o["uuid"] for o in order_manager.orders}
    _cleanup_stale_caches(active_uuids)

    initial_state = [(o['uuid'], o.get('status'), o.get('filled_volume'), o.get('stop_price')) for o in order_manager.orders]
    all_orders = list(order_manager.orders)
    price_cache = {}
    ticker_cache = {}
    now_ts = time.time()

    orders_to_query = []
    for ord in all_orders:
        if not order_manager.has_order(ord["uuid"]):
            continue
        if float(ord.get("next_check_at") or 0) > now_ts:
            continue

        user_id = ord['user_id']
        exchange = ord['exchange']
        ticker = ord['ticker']
        ex_obj = exchange_adapter.get_exchange(exchange)

        if ord.get("status") == "cancel_requested":
            await _handle_cancel_requested(application, ord, ex_obj)
            continue

        if exchange == "toss" and str(ticker).isdigit():
            await exchange_adapter.ensure_toss_kr_calendar(user_id)

        if await _handle_market_closed(ord, ex_obj):
            continue

        if await _submit_reserved_or_reorder(application, ord, ex_obj, ticker_cache=ticker_cache):
            continue

        orders_to_query.append((ord, ex_obj))

    async def _fetch_status(item):
        o, ex = item
        user_sem = _exchange_user_semaphores[f"{o['exchange']}:{o['user_id']}"]
        global_sem = _exchange_status_semaphores[o['exchange']]
        async with global_sem:
            async with user_sem:
                if not order_manager.has_order(o['uuid']):
                    return o, ex, None
                res = await exchange_adapter.get_order_status(o['user_id'], o['exchange'], o['uuid'], o['ticker'])
                return o, ex, res

    status_results = []
    if orders_to_query:
        status_results = await asyncio.gather(*[_fetch_status(item) for item in orders_to_query])

    for ord, ex_obj, res in status_results:
        if not order_manager.has_order(ord["uuid"]):
            continue

        user_id = ord['user_id']
        exchange = ord['exchange']
        ticker = ord['ticker']

        if not res:
            if getattr(ex_obj, "supports_reserved_orders", False):
                scf = _get_status_check_failures()
                fails = scf.get(ord["uuid"], 0) + 1
                if fails < _STATUS_CHECK_FAIL_LIMIT:
                    scf[ord["uuid"]] = fails
                    _call_append_operational_event(
                        "warning", "sync_orders",
                        f"{exchange} order status check failed ({fails}/{_STATUS_CHECK_FAIL_LIMIT}), retrying",
                        ticker,
                    )
                else:
                    scf.pop(ord["uuid"], None)
                    strategy_name = str(ord.get("strategy", ""))
                    if (is_strategy_order(ord) or ord.get("auto_reorder")) and not strategy_name.startswith("kospi_top"):
                        order_manager.mark_reorder_pending(ord["uuid"], ex_obj.next_check_timestamp(ticker))
                        order_kind = "전략" if is_strategy_order(ord) else "자동 재주문 설정"
                        await application.bot.send_message(
                            chat_id=user_id,
                            text=f"⏳ [{exchange_display_name(exchange)}] {ticker} {order_kind} 주문 확인이 불가하여 다음 정규장 재주문 대기로 전환합니다.",
                        )
                    else:
                        order_manager.remove_order(ord["uuid"])
                        await application.bot.send_message(
                            chat_id=user_id,
                            text=f"🛑 [{exchange_display_name(exchange)}] {ticker} 주문 확인이 불가하여 추적을 종료합니다.\n자동 재주문은 하지 않습니다.",
                        )
            else:
                _call_append_operational_event("warning", "sync_orders", f"{exchange} get_order_status returned no result", ticker)
            continue

        _get_status_check_failures().pop(ord["uuid"], None)
        state = res['state']

        if await _apply_stop_loss(application, ord, state, price_cache):
            continue

        await _process_order_fill(application, ord, res, ex_obj)

    final_state = [(o['uuid'], o.get('status'), o.get('filled_volume'), o.get('stop_price')) for o in order_manager.orders]
    if initial_state != final_state:
        main._spawn_bg(trigger_realtime_sync())


async def startup_recovery(application):
    """봇 시작 시 rsitrade 매수 체결 후 연동 익절매도 발행이 누락된 주문을 복구한다."""
    order_manager, _, exchange_adapter, _ = _get_app_context()
    _log.info("Startup recovery started", extra={"event": "startup_recovery_start"})
    targets = [
        ord for ord in list(order_manager.orders)
        if ord.get('side') == 'bid' and ord.get('strategy') == 'rsitrade' and ord.get('linked_to')
    ]
    recovered_count = 0

    for ord in targets:
        if not order_manager.has_order(ord["uuid"]):
            continue
        try:
            res = await exchange_adapter.get_order_status(ord['user_id'], ord['exchange'], ord['uuid'], ord.get("ticker"))
        except Exception as e:
            _log.warning("Startup recovery: order status check failed", exc_info=e,
                         extra={"event": "startup_recovery_status_error", "uuid": ord['uuid']})
            continue
        if not res:
            continue
        exec_vol = float(res.get('executed_volume', 0) or 0)
        if exec_vol <= float(ord.get('filled_volume', 0)):
            continue
        outcome = await _create_linked_sell_order(application, ord, exec_vol, res['state'])
        if outcome == "created":
            recovered_count += 1
            _log.info("Startup recovery: linked sell order created", extra={"event": "startup_recovery_recovered", "uuid": ord['uuid']})

    if recovered_count > 0:
        _log.info("Startup recovery complete", extra={"event": "startup_recovery_done", "recovered": recovered_count})
