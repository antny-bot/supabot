"""매니저 백엔드 연동 내부 webhook API (HMAC 인증 필요).

main.py의 post_init에서 init()으로 의존 객체를 주입한 뒤 라우트로 등록한다.
"""
import asyncio
import hashlib
import hmac
import json as _json
import os
import time

import aiohttp
from aiohttp import web as _web

from core.bot_logger import get_logger
from core.order_execution import execute_grid_orders, execute_rsitrade_orders
from core.parsers import get_dca_weights, get_user_rsi_interval, validate_max_order

_log = get_logger("internal_api")

_exchange_adapter = None
_order_manager = None
_user_manager = None

# 전략 실행은 webhook 응답을 먼저 반환하고 백그라운드에서 진행한다. asyncio는
# 태스크를 weak-ref로만 잡으므로, 참조를 보관하지 않으면 실행 도중 GC되어 주문
# 발행 루프가 중단될 수 있다. 강한 참조를 유지해 완료까지 살아 있도록 한다.
_bg_tasks: set = set()


def _spawn_bg(coro):
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
    return task


def init(exchange_adapter, order_manager, user_manager):
    global _exchange_adapter, _order_manager, _user_manager
    _exchange_adapter = exchange_adapter
    _order_manager = order_manager
    _user_manager = user_manager


async def _verify_webhook_request(request: _web.Request) -> bool:
    """웹훅 요청의 HMAC 서명 및 IP 화이트리스트 검증"""
    # 1. IP 화이트리스팅 검증
    allowed_ips_str = os.environ.get("ALLOWED_WEBHOOK_IPS", "").strip()
    if allowed_ips_str:
        allowed_ips = [ip.strip() for ip in allowed_ips_str.split(",") if ip.strip()]
        client_ip = request.remote
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            client_ip = xff.split(",")[0].strip()
        if client_ip not in allowed_ips and client_ip != "127.0.0.1":
            _log.warning(f"Webhook blocked: IP {client_ip} is not in whitelist")
            return False

    # 2. HMAC 서명 검증
    api_key = os.environ.get("MANAGER_API_KEY", "")
    if not api_key:
        return False

    timestamp = request.headers.get("X-Timestamp")
    signature = request.headers.get("X-Signature")

    if not timestamp or not signature:
        _log.warning("Webhook blocked: Missing X-Timestamp or X-Signature headers")
        return False

    # 시간 오차 검증 (리플레이 공격 방지, 5분 허용)
    try:
        req_time = int(timestamp)
        if abs(int(time.time()) - req_time) > 300:
            _log.warning("Webhook blocked: Timestamp drift too large")
            return False
    except ValueError:
        return False

    # 바디 페이로드 읽기
    body_bytes = await request.read()

    # 예상 서명 계산
    msg = timestamp.encode("utf-8") + body_bytes
    expected_sig = hmac.new(api_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        _log.warning("Webhook blocked: Signature verification failed")
        return False

    return True


async def _internal_notify_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        app = request.app["bot_application"]
        await app.bot.send_message(
            chat_id=data["chat_id"],
            text=data["text"],
            parse_mode=data.get("parse_mode", "HTML"),
        )
    except Exception as e:
        _log.warning("internal notify failed", exc_info=e, extra={"event": "notify_error"})
        return _web.Response(status=500, text=str(e))
    return _web.Response(text="ok")


async def trigger_realtime_sync():
    """매니저의 /api/realtime/trigger를 호출하여 프론트엔드 실시간 갱신을 트리거합니다."""
    manager_url = os.environ.get("MANAGER_BACKEND_URL", "http://localhost:8000")
    api_key = os.environ.get("MANAGER_API_KEY", "")
    if not api_key:
        return
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"X-API-Key": api_key}
            async with session.post(f"{manager_url}/api/realtime/trigger", headers=headers, json={"event": "refresh"}) as resp:
                if resp.status != 200:
                    _log.warning(f"Failed to trigger realtime sync, status: {resp.status}")
    except Exception as e:
        _log.warning("Error triggering realtime sync", exc_info=e)


async def _internal_execute_grid_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        user_id = str(data["user_id"])
        ex = data["exchange"].lower()
        tk = data["ticker"].upper()
        s_p = float(data["start_price"])
        e_p = float(data["end_price"])
        ct = int(data["count"])
        val = float(data["budget"])

        user = _user_manager.get_user(user_id)
        if not user:
            return _web.Response(status=404, text="User not found")

        ok, error_msg = validate_max_order(user, val / ct)
        if not ok:
            return _web.Response(status=400, text=error_msg)

        app = request.app["bot_application"]
        group_no = _order_manager.get_next_group_no(user_id)

        async def run_grid():
            await execute_grid_orders(
                exchange_adapter=_exchange_adapter, order_manager=_order_manager,
                user_id=user_id, exchange=ex, ticker=tk,
                start_price=s_p, end_price=e_p, count=ct, budget_or_volume=val,
                is_sell=False, group_no=group_no,
                bot=app.bot, notify_chat_id=user_id,
                trigger_sync_fn=trigger_realtime_sync,
            )

        _spawn_bg(run_grid())
        return _web.Response(text="Grid execution started")
    except Exception as e:
        _log.warning("Internal grid execution failed", exc_info=e)
        return _web.Response(status=500, text=str(e))


async def _internal_execute_rsitrade_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        user_id = str(data["user_id"])
        ex = data["exchange"].lower()
        tk = data["ticker"].upper()
        b_rsi = str(data["buy_rsi_range"])
        s_rsi = str(data["sell_rsi_range"])
        ct = int(data["count"])
        bg = float(data["budget"])
        dca_mode = bool(data.get("weighted", False))

        user = _user_manager.get_user(user_id)
        if not user:
            return _web.Response(status=404, text="User not found")

        if not _exchange_adapter.get_exchange(ex).supports_minute_candles() and get_user_rsi_interval(user) != "day":
            return _web.Response(status=400, text="한투/토스는 일봉(day) 기준 RSI만 지원합니다.")

        dca_weights = get_dca_weights(ct) if dca_mode else None
        per_order_budgets = [bg * w for w in dca_weights] if dca_weights else [bg / ct] * ct

        ok, error_msg = validate_max_order(user, max(per_order_budgets))
        if not ok:
            return _web.Response(status=400, text=error_msg)

        min_amt = _exchange_adapter.get_min_order_amount(ex)
        if min(per_order_budgets) < min_amt:
            return _web.Response(status=400, text=f"건당 주문 금액이 거래소 최소 주문 금액({min_amt:,.0f}원)보다 작습니다.")

        app = request.app["bot_application"]
        group_no = _order_manager.get_next_group_no(user_id)

        async def run_rsitrade():
            await execute_rsitrade_orders(
                exchange_adapter=_exchange_adapter, order_manager=_order_manager, signal_engine=request.app["signal_engine"],
                user_id=user_id, exchange=ex, ticker=tk,
                buy_rsi_range=b_rsi, sell_rsi_range=s_rsi,
                count=ct, per_order_budgets=per_order_budgets,
                user=user, group_no=group_no, bot=app.bot, notify_chat_id=user_id,
                trigger_sync_fn=trigger_realtime_sync,
            )

        _spawn_bg(run_rsitrade())
        return _web.Response(text="RSITrade execution started")
    except Exception as e:
        _log.warning("Internal rsitrade execution failed", exc_info=e)
        return _web.Response(status=500, text=str(e))


async def _internal_execute_sgrid_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        user_id = str(data["user_id"])
        ex = data["exchange"].lower()
        tk = data["ticker"].upper()
        s_p = float(data["start_price"])
        e_p = float(data["end_price"])
        ct = int(data["count"])
        total_vol = float(data["total_volume"])

        user = _user_manager.get_user(user_id)
        if not user:
            return _web.Response(status=404, text="User not found")

        if ex == "kis" and int(total_vol) < ct:
            return _web.Response(status=400, text=f"총 수량({int(total_vol)}주)이 주문 개수({ct})보다 작습니다.")

        app = request.app["bot_application"]
        group_no = _order_manager.get_next_group_no(user_id)

        async def run_sgrid():
            await execute_grid_orders(
                exchange_adapter=_exchange_adapter, order_manager=_order_manager,
                user_id=user_id, exchange=ex, ticker=tk,
                start_price=s_p, end_price=e_p, count=ct, budget_or_volume=total_vol,
                is_sell=True, group_no=group_no,
                bot=app.bot, notify_chat_id=user_id,
                trigger_sync_fn=trigger_realtime_sync,
            )

        _spawn_bg(run_sgrid())
        return _web.Response(text="sGrid execution started")
    except Exception as e:
        _log.warning("Internal sgrid execution failed", exc_info=e)
        return _web.Response(status=500, text=str(e))


async def _internal_cancel_order_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        user_id = data["user_id"]
        exchange = data["exchange"]
        uuid = data["uuid"]
        ticker = data["ticker"]
        ok = await _exchange_adapter.cancel_order(user_id, exchange, uuid, ticker)
        if ok:
            _order_manager.remove_order(uuid)
        return _web.Response(text=_json.dumps({"ok": bool(ok)}), content_type="application/json")
    except Exception as e:
        _log.warning("internal cancel_order failed", exc_info=e, extra={"event": "cancel_order_error"})
        return _web.Response(status=500, text=str(e))


async def _internal_sync_order_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        user_id = data["user_id"]
        exchange = data["exchange"]
        uuid = data["uuid"]
        ticker = data["ticker"]
        status_info = await _exchange_adapter.get_order_status(user_id, exchange, uuid, ticker)
        if status_info:
            state = status_info["state"]
            executed = float(status_info["executed_volume"])
            _order_manager.update_order_fill(uuid, executed, state)
            await trigger_realtime_sync()
            return _web.Response(
                text=_json.dumps({"ok": True, "source": "exchange", "state": state, "executed": executed}),
                content_type="application/json"
            )
        else:
            return _web.Response(
                text=_json.dumps({"ok": False, "error": "거래소에서 주문 정보를 찾을 수 없습니다."}),
                content_type="application/json"
            )
    except Exception as e:
        _log.warning("internal sync_order failed", exc_info=e, extra={"event": "sync_order_error"})
        return _web.Response(status=500, text=str(e))


async def _internal_force_update_order_handler(request: _web.Request) -> _web.Response:
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        uuid = data["uuid"]
        state = data["state"]
        executed = float(data.get("filled_volume", 0.0))
        _order_manager.update_order_fill(uuid, executed, state)
        await trigger_realtime_sync()
        return _web.Response(text=_json.dumps({"ok": True}), content_type="application/json")
    except Exception as e:
        _log.warning("internal force_update_order failed", exc_info=e, extra={"event": "force_update_order_error"})
        return _web.Response(status=500, text=str(e))


async def _internal_get_prices_handler(request: _web.Request) -> _web.Response:
    """매니저 리포트용 실시간 현재가 조회 (KIS/Toss는 봇 프로세스 내 자격증명이 필요해
    매니저가 직접 호출할 수 없으므로, 이 webhook을 통해서만 조회 가능하다)."""
    if not await _verify_webhook_request(request):
        return _web.Response(status=401)
    try:
        data = await request.json()
        items = data.get("requests") or []

        async def _fetch_one(item):
            user_id = str(item["user_id"])
            exchange = item["exchange"]
            ticker = item["ticker"]
            try:
                ticker_data = await _exchange_adapter.get_ticker(exchange, ticker, user_id=user_id)
            except Exception as e:
                _log.warning("internal get_prices ticker fetch failed", exc_info=e, extra={"event": "get_prices_error"})
                ticker_data = None
            price = float(ticker_data["trade_price"]) if ticker_data and ticker_data.get("trade_price") else 0.0
            return {"user_id": user_id, "exchange": exchange, "ticker": ticker, "price": price}

        results = await asyncio.gather(*[_fetch_one(item) for item in items])
        return _web.Response(text=_json.dumps({"prices": results}), content_type="application/json")
    except Exception as e:
        _log.warning("internal get_prices failed", exc_info=e, extra={"event": "get_prices_error"})
        return _web.Response(status=500, text=str(e))
