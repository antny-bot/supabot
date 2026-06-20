import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import core.trading_gate as tg
from core.user_manager import UserManager
from core.order_manager import OrderManager
import main


def _reset_gate(monkeypatch, tmp_path):
    """DB 미사용 환경에서 파일 폴백 경로를 격리하고 인메모리 캐시를 초기화한다."""
    monkeypatch.setattr(tg, "_HALT_FLAG_FILE", str(tmp_path / "trading_halt.flag"))
    monkeypatch.setattr(tg, "_halt_cache", None)


def test_halt_and_resume_roundtrip(monkeypatch, tmp_path):
    _reset_gate(monkeypatch, tmp_path)
    assert tg.is_trading_halted() is False
    ok, msg = tg.assert_can_trade()
    assert ok is True and msg is None

    tg.set_trading_halt(True, by_user_id="admin")
    assert tg.is_trading_halted() is True
    ok, msg = tg.assert_can_trade()
    assert ok is False and "중지" in msg

    tg.set_trading_halt(False, by_user_id="admin")
    assert tg.is_trading_halted() is False


def test_check_can_place_order_blocked_when_halted(monkeypatch, tmp_path):
    _reset_gate(monkeypatch, tmp_path)
    tg.set_trading_halt(True)
    user = {"preferences": dict(UserManager.DEFAULT_PREFERENCES)}
    ok, msg = tg.check_can_place_order(user, [], 1000)
    assert ok is False


def test_exposure_cap_blocks_over_limit(monkeypatch, tmp_path):
    _reset_gate(monkeypatch, tmp_path)
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    prefs["max_open_exposure_krw"] = 1_000_000
    user = {"preferences": prefs}
    open_orders = [
        {"exchange": "upbit", "ticker": "KRW-BTC", "price": 100_000, "volume": 8, "filled_volume": 0},
    ]  # 현재 노출 800,000원
    # 신규 300,000원 → 합계 1,100,000 > 1,000,000 → 차단
    ok, msg = tg.check_can_place_order(user, open_orders, 300_000)
    assert ok is False and "초과" in msg
    # 신규 100,000원 → 합계 900,000 → 통과
    ok2, _ = tg.check_can_place_order(user, open_orders, 100_000)
    assert ok2 is True


def test_exposure_cap_unset_passes(monkeypatch, tmp_path):
    _reset_gate(monkeypatch, tmp_path)
    user = {"preferences": dict(UserManager.DEFAULT_PREFERENCES)}  # cap None
    ok, _ = tg.check_can_place_order(user, [], 9_999_999_999)
    assert ok is True


def test_usd_order_skips_exposure(monkeypatch, tmp_path):
    _reset_gate(monkeypatch, tmp_path)
    prefs = dict(UserManager.DEFAULT_PREFERENCES)
    prefs["max_open_exposure_krw"] = 1000
    user = {"preferences": prefs}
    ok, _ = tg.check_can_place_order(user, [], 5000, is_usd=True)
    assert ok is True


async def test_sync_orders_skips_kis_reorder_when_halted(monkeypatch, tmp_path):
    """중지 상태에서는 KIS pending_reorder 재주문을 보류하고 next_check만 갱신한다."""
    _reset_gate(monkeypatch, tmp_path)
    tg.set_trading_halt(True)

    om = OrderManager(str(tmp_path / "orders.json"))
    om.add_order("123", "kis", "005930", "uuid-1", 70000, 10, side="bid", strategy="rsitrade")
    om.update_order_fill("uuid-1", 0, "pending_reorder")
    om.mark_reorder_pending("uuid-1", 0.0)  # next_check 과거로 두어 게이트 통과
    monkeypatch.setattr(main, "order_manager", om)
    monkeypatch.setattr(main, "kis_next_check_timestamp", lambda: 9_999_999.0)

    mock_adapter = MagicMock()
    mock_adapter.create_order = AsyncMock()
    mock_adapter.get_order_status = AsyncMock()
    mock_adapter.get_exchange = lambda exchange: MagicMock(is_market_open=lambda: True)
    monkeypatch.setattr(main, "exchange_adapter", mock_adapter)

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    await main.sync_orders(app)

    mock_adapter.create_order.assert_not_called()
    assert om.orders[0]["next_check_at"] == 9_999_999.0

    tg.set_trading_halt(False)
