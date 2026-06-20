"""Phase 9 중기: KIS 시장가 주문 + Grid/SGrid KIS 지원 테스트"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


# ── KIS 시장가 주문 (_create_kis_order) ──────────────────────────────────────

def test_kis_market_order_uses_ord_dvsn_01():
    """시장가 주문 시 ORD_DVSN=01, ORD_UNPR=0이 API에 전달되어야 함."""
    from core.exchange_adapter import ExchangeAdapter

    class _DummyUsers:
        def get_user(self, _):
            return {"exchanges": {"kis": {
                "app_key": "k", "app_secret": "s",
                "account_no": "12345678", "product_code": "01", "env": "paper"
            }}}

    adapter = ExchangeAdapter(_DummyUsers())
    captured = {}

    async def fake_request_kis(user_id, method, path, tr_id, body=None, params=None):
        captured["body"] = body
        return {"rt_cd": "0", "output": {"ODNO": "0001", "KRX_FWDG_ORD_ORGNO": "ORG"}}

    adapter._request_kis = fake_request_kis
    keys = {"account_no": "12345678", "product_code": "01", "env": "paper",
            "app_key": "k", "app_secret": "s"}
    asyncio.run(adapter._create_kis_order("user1", keys, "005930", "bid", price=0, volume=10, ord_type="market"))

    assert captured["body"]["ORD_DVSN"] == "01"
    assert captured["body"]["ORD_UNPR"] == "0"


def test_kis_limit_order_uses_ord_dvsn_00():
    """지정가 주문 시 ORD_DVSN=00, ORD_UNPR=가격이 API에 전달되어야 함."""
    from core.exchange_adapter import ExchangeAdapter

    class _DummyUsers:
        def get_user(self, _):
            return {"exchanges": {"kis": {
                "app_key": "k", "app_secret": "s",
                "account_no": "12345678", "product_code": "01", "env": "paper"
            }}}

    adapter = ExchangeAdapter(_DummyUsers())
    captured = {}

    async def fake_request_kis(user_id, method, path, tr_id, body=None, params=None):
        captured["body"] = body
        return {"rt_cd": "0", "output": {"ODNO": "0002", "KRX_FWDG_ORD_ORGNO": "ORG"}}

    adapter._request_kis = fake_request_kis
    keys = {"account_no": "12345678", "product_code": "01", "env": "paper",
            "app_key": "k", "app_secret": "s"}
    asyncio.run(adapter._create_kis_order("user1", keys, "005930", "bid", price=65000, volume=5, ord_type="limit"))

    assert captured["body"]["ORD_DVSN"] == "00"
    assert captured["body"]["ORD_UNPR"] == "65000"


def test_create_order_passes_ord_type_to_kis():
    """create_order()의 ord_type이 _create_kis_order에 전달되는지 확인."""
    from core.exchange_adapter import ExchangeAdapter

    class _DummyUsers:
        def get_user(self, _):
            return {"exchanges": {"kis": {
                "app_key": "k", "app_secret": "s",
                "account_no": "12345678", "product_code": "01", "env": "paper"
            }}}

    adapter = ExchangeAdapter(_DummyUsers())
    captured_ord_type = {}

    async def fake_create_kis(user_id, keys, ticker, side, price, volume, ord_type="limit"):
        captured_ord_type["ord_type"] = ord_type
        return {"uuid": "test-uuid"}

    adapter._create_kis_order = fake_create_kis
    asyncio.run(adapter.create_order("user1", "kis", "005930", "bid", 0, 10, ord_type="market"))
    assert captured_ord_type["ord_type"] == "market"


# ── 시장가 manual order token ────────────────────────────────────────────────

def test_manual_order_token_stores_ord_type():
    """create_manual_order_token이 ord_type을 저장해야 함."""
    import main
    token = main.create_manual_order_token("u1", "kis", "bid", "005930", 0.0, 10, ord_type="market")
    pending = main._pending_manual_orders[token]
    assert pending["ord_type"] == "market"
    main._pending_manual_orders.pop(token, None)


def test_manual_order_token_default_ord_type_is_limit():
    """기본 ord_type은 limit이어야 함."""
    import main
    token = main.create_manual_order_token("u2", "upbit", "bid", "KRW-BTC", 50_000_000, 0.001)
    pending = main._pending_manual_orders[token]
    assert pending.get("ord_type", "limit") == "limit"
    main._pending_manual_orders.pop(token, None)


# ── Grid/SGrid KIS 지원 ──────────────────────────────────────────────────────

def _patch_kis_market_open(monkeypatch, is_open):
    import core.exchanges.kis as kis_module
    monkeypatch.setattr(kis_module, "is_kis_regular_session", lambda: is_open)


def _patch_auth_kis(monkeypatch):
    import main
    from core.user_manager import UserManager
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    prefs["default_exchange"] = "kis"
    user = {
        "is_active": True,
        "is_admin": False,
        "preferences": prefs,
        "exchanges": {"kis": {"env": "paper"}},
        "llm": {"gemini_api_key": ""},
    }
    mock_um = MagicMock()
    mock_um.get_user.return_value = user
    monkeypatch.setattr(main, "user_manager", mock_um)


def _make_update_simple(args_text=""):
    update = MagicMock()
    update.effective_chat.id = 999
    update.message.text = f"/grid {args_text}"
    update.message.reply_text = AsyncMock()
    return update


async def test_grid_command_kis_rejected_outside_market_hours(monkeypatch):
    """정규장 외 시간에는 KIS grid 주문을 거부해야 함."""
    import main
    from handlers import strategy_handlers
    _patch_auth_kis(monkeypatch)
    _patch_kis_market_open(monkeypatch, False)

    update = _make_update_simple()
    context = MagicMock()
    context.args = ["한투", "005930", "60000", "65000", "3", "300000"]

    await strategy_handlers.grid_command(update, context)

    call_text = update.message.reply_text.call_args[0][0]
    assert "정규장" in call_text


async def test_grid_command_kis_allowed_during_market_hours(monkeypatch):
    """정규장 시간에는 KIS grid 확인 메시지를 정상 전송해야 함."""
    import main
    from handlers import strategy_handlers
    _patch_auth_kis(monkeypatch)
    _patch_kis_market_open(monkeypatch, True)

    update = _make_update_simple()
    context = MagicMock()
    context.args = ["한투", "005930", "60000", "65000", "3", "300000"]

    await strategy_handlers.grid_command(update, context)

    call_text = update.message.reply_text.call_args[0][0]
    assert "거미줄 매수 주문 확인" in call_text


async def test_sgrid_command_kis_rejected_outside_market_hours(monkeypatch):
    """정규장 외 시간에는 KIS sgrid 주문을 거부해야 함."""
    import main
    from handlers import strategy_handlers
    _patch_auth_kis(monkeypatch)
    _patch_kis_market_open(monkeypatch, False)

    update = _make_update_simple()
    context = MagicMock()
    context.args = ["한투", "005930", "60000", "65000", "3", "30"]

    await strategy_handlers.sgrid_command(update, context)

    call_text = update.message.reply_text.call_args[0][0]
    assert "정규장" in call_text


async def test_sgrid_command_kis_insufficient_volume(monkeypatch):
    """총 수량이 주문 개수보다 작을 때 오류를 반환해야 함."""
    import main
    from handlers import strategy_handlers
    _patch_auth_kis(monkeypatch)
    _patch_kis_market_open(monkeypatch, True)

    update = _make_update_simple()
    context = MagicMock()
    # 총 수량 2주, 주문 개수 5 → 주문당 0주
    context.args = ["한투", "005930", "60000", "65000", "5", "2"]

    await strategy_handlers.sgrid_command(update, context)

    call_text = update.message.reply_text.call_args[0][0]
    assert "0주" in call_text


# ── build_manual_order_confirm_message 시장가 표시 ───────────────────────────

def test_confirm_message_shows_market_price_label():
    """시장가 주문 확인 메시지에 '시장가'가 표시되어야 함."""
    from core.formatters import build_manual_order_confirm_message
    user = {"exchanges": {"kis": {"env": "paper"}}}
    msg = build_manual_order_confirm_message("kis", "005930", "bid", 0, 10, user, ord_type="market")
    assert "시장가" in msg
    assert "주문금액" not in msg


def test_confirm_message_shows_price_for_limit_order():
    """지정가 주문 확인 메시지에 가격과 주문금액이 표시되어야 함."""
    from core.formatters import build_manual_order_confirm_message
    user = {"exchanges": {"kis": {"env": "paper"}}}
    msg = build_manual_order_confirm_message("kis", "005930", "bid", 65000, 10, user, ord_type="limit")
    assert "65,000원" in msg
    assert "주문금액" in msg
