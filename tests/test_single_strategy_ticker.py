"""단일 종목 독점 원칙(Single Strategy per Ticker) 및 외부 매도 정합성(Reconciliation) 단위 테스트.

docs/plans/single_strategy_ticker_isolation_and_reconciliation.md 명세 검증:
1. 동일 종목에 다른 전략 주문 등록 시도시 차단 (1차 방어)
2. 동일 전략 패밀리(rsitrade <-> rsitrade_sell 등) 및 수동(manual)/손절(stoploss) 면제 검증
3. DCA 스케줄과의 상호 충돌 방지 검증
4. 외부 매도로 잔고 부족 발생 시 FIFO 기반 최근 매도 주문 취소 및 텔레그램 알림 검증 (2차 방어)
5. 매수 체결 후 익절 매도 생성 시 외부 매도로 잔고 부족 감지 시 external_sold 처리 검증
"""
import os
import sys
import inspect

# Windows 샌드박스 Proactor loopback 소켓 블로킹 방지
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 테스트 실행 시 Supabase 라이브 네트워크 호출 차단
import dotenv
import dotenv.main
dotenv.load_dotenv = lambda *args, **kwargs: False
dotenv.main.load_dotenv = lambda *args, **kwargs: False

os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_KEY"] = ""
os.environ.setdefault("USER_SECRET_KEY", "bW9jay1mZXJuZXQta2V5LWZvci10ZXN0aW5nLTEyMzQ1Ng==")

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

def _sync_run(coro):
    """Windows 샌드박스 Proactor loopback 소켓 블로킹 방지용 순수 코루틴 러너."""
    stack = [coro]
    val = None
    while stack:
        top = stack[-1]
        try:
            nxt = top.send(val)
            val = None
            if inspect.iscoroutine(nxt) or hasattr(nxt, "__await__"):
                if hasattr(nxt, "__await__"):
                    nxt = nxt.__await__()
                stack.append(nxt)
            else:
                val = nxt
        except StopIteration as e:
            stack.pop()
            val = e.value
    return val
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.trading_gate import (
    assert_single_strategy_per_ticker,
    get_strategy_family,
    check_can_place_order,
)
import main


def test_strategy_family_mapping():
    assert get_strategy_family("rsitrade") == "rsi"
    assert get_strategy_family("rsitrade_sell") == "rsi"
    assert get_strategy_family("gridrsi") == "rsi"
    assert get_strategy_family("grid") == "grid"
    assert get_strategy_family("sgrid") == "grid"
    assert get_strategy_family("sgridrsi") == "sgridrsi"
    assert get_strategy_family("dca") == "dca"
    assert get_strategy_family("sdca") == "dca"
    assert get_strategy_family("manual") == "manual"
    assert get_strategy_family("custom_strat") == "custom_strat"


def test_single_strategy_different_family_blocked():
    """동일 종목에 다른 전략 주문이 열려있으면 신규 전략 주문이 차단되어야 한다."""
    open_orders = [
        {"ticker": "005490", "strategy": "rsitrade", "side": "bid", "status": "wait"},
    ]
    # 005490(POSCO홀딩스, 11위)에 grid 주문 시도시 차단
    ok, msg = assert_single_strategy_per_ticker(open_orders, ticker="005490", strategy="grid")
    assert ok is False
    assert "005490" in msg
    assert "rsitrade" in msg
    assert "동일 종목의 복수 전략 동시 운용은 제한됩니다" in msg


def test_single_strategy_same_family_allowed():
    """동일 종목에 동일 전략 패밀리(예: rsitrade와 rsitrade_sell)는 허용되어야 한다."""
    open_orders = [
        {"ticker": "005490", "strategy": "rsitrade", "side": "bid", "status": "wait"},
    ]
    ok, msg = assert_single_strategy_per_ticker(open_orders, ticker="005490", strategy="rsitrade_sell")
    assert ok is True
    assert msg is None

    # grid와 sgrid도 동일 family
    open_grid = [
        {"ticker": "035720", "strategy": "grid", "side": "bid", "status": "wait"},
    ]
    ok_grid, _ = assert_single_strategy_per_ticker(open_grid, ticker="035720", strategy="sgrid")
    assert ok_grid is True


def test_single_strategy_manual_and_stoploss_exempt():
    """수동 주문(manual)과 보호성 손절(stoploss)은 전략 제한 없이 항상 허용되어야 한다."""
    open_orders = [
        {"ticker": "005490", "strategy": "rsitrade", "side": "bid", "status": "wait"},
    ]
    # manual 주문 허용
    ok_m, _ = assert_single_strategy_per_ticker(open_orders, ticker="005490", strategy="manual")
    assert ok_m is True

    # stoploss 주문 허용
    ok_sl, _ = assert_single_strategy_per_ticker(open_orders, ticker="005490", strategy="stoploss")
    assert ok_sl is True


def test_single_strategy_dca_conflict():
    """DCA 스케줄이 등록된 종목에 다른 전략 주문을 시도하거나, 반대의 경우 차단되어야 한다."""
    dca_scheds = [{"ticker": "005490", "side": "bid"}]
    # DCA가 있는 종목에 rsitrade 시도시 차단
    ok, msg = assert_single_strategy_per_ticker([], ticker="005490", strategy="rsitrade", dca_schedules=dca_scheds)
    assert ok is False
    assert "DCA" in msg

    # open_orders에 grid가 있는데 신규 DCA 시도시 차단
    open_orders = [{"ticker": "005490", "strategy": "grid", "status": "wait"}]
    ok_dca, msg_dca = assert_single_strategy_per_ticker(open_orders, ticker="005490", strategy="dca")
    assert ok_dca is False
    assert "grid" in msg_dca


def test_check_can_place_order_integrates_single_strategy():
    """check_can_place_order에서도 종목 독점 원칙이 작동해야 한다."""
    user = {"preferences": {}}
    open_orders = [
        {"ticker": "005490", "strategy": "rsitrade", "side": "bid", "price": 70000, "volume": 1, "filled_volume": 0},
    ]
    with patch("core.trading_gate.assert_can_trade", return_value=(True, None)):
        ok, msg = check_can_place_order(
            user, open_orders, new_order_krw=70000, ticker="005490", strategy="grid", side="bid"
        )
        assert ok is False
        assert "이미 'rsitrade' 전략이 운용 중입니다" in msg


def test_reconcile_external_sells_fifo():
    """외부 매도로 실제 잔고가 오픈 매도 주문 합계보다 적을 때 FIFO로 최근 주문을 정리해야 한다."""
    async def _run():
        app_mock = MagicMock()
        app_mock.bot.send_message = AsyncMock()

        # 두 주문: ord1은 10시(오래됨, 1주), ord2는 11시(최신, 1주)
        ord1 = {
            "uuid": "u1", "user_id": "123", "exchange": "toss", "ticker": "005930",
            "side": "ask", "strategy": "rsitrade_sell", "volume": 1, "filled_volume": 0,
            "status": "wait", "created_at": 100.0,
        }
        ord2 = {
            "uuid": "u2", "user_id": "123", "exchange": "toss", "ticker": "005930",
            "side": "ask", "strategy": "grid", "volume": 1, "filled_volume": 0,
            "status": "wait", "created_at": 200.0,
        }

        mock_om = MagicMock()
        mock_om.get_user_orders.return_value = [ord1, ord2]
        mock_ea = MagicMock()
        mock_ea.cancel_order = AsyncMock(return_value=True)
        mock_ea.get_order_status = AsyncMock(return_value={"state": "cancel"})

        mock_cancel = AsyncMock(return_value=True)
        with patch.object(main, "order_manager", mock_om), \
             patch.object(main, "exchange_adapter", mock_ea), \
             patch.object(main, "cancel_and_remove_order", mock_cancel):

            await main.reconcile_external_sells_fifo(app_mock, "123", "toss", "005930", current_balance=1.0)

            # FIFO 원칙: 오래된 ord1(1주)은 보존되고, 최신인 ord2(1주)가 취소되어야 함
            mock_cancel.assert_awaited_once_with("123", ord2)
            # 안내 메시지가 텔레그램으로 발송되었는지 검증
            app_mock.bot.send_message.assert_awaited_once()
            sent_text = app_mock.bot.send_message.call_args[1]["text"]
            assert "외부 매도 감지" in sent_text
            assert "FIFO 원칙" in sent_text
            assert "[grid]" in sent_text

    _sync_run(_run())


def test_create_linked_sell_order_external_sold_handling():
    """매수 체결 후 익절 매도 생성 시 잔고 부족이면 external_sold로 정상 정리되어야 한다."""
    async def _run():
        app_mock = MagicMock()
        app_mock.bot.send_message = AsyncMock()

        ord_bid = {
            "uuid": "bid-uuid", "user_id": "123", "exchange": "toss", "ticker": "005930",
            "side": "bid", "strategy": "rsitrade", "linked_to": "60", "price": 70000,
            "volume": 1, "filled_volume": 0, "group_no": 1,
        }

        mock_om = MagicMock()
        mock_ea = MagicMock()
        mock_ex = MagicMock()
        mock_ex.round_volume.return_value = 1.0
        mock_ex.requires_integer_volume.return_value = True
        mock_ea.get_exchange.return_value = mock_ex

        # 매도 생성 실패 (잔고 부족)
        mock_ea.create_order = AsyncMock(return_value=None)
        # 실제 잔고 0개 조회됨 (외부 매도)
        mock_ea.get_balances = AsyncMock(return_value=[{"ticker": "005930", "balance": 0.0}])

        with patch.object(main, "order_manager", mock_om), \
             patch.object(main, "exchange_adapter", mock_ea), \
             patch.object(main, "signal_engine", MagicMock(get_price_by_rsi=AsyncMock(return_value=75000))), \
             patch.object(main, "_find_linked_sell_order", return_value=None):

            outcome = await main._create_linked_sell_order(app_mock, ord_bid, exec_vol=1.0, state="done")

            assert outcome == "external_sold"
            # order_manager fill 업데이트 확인
            mock_om.update_order_fill.assert_called_once_with("bid-uuid", 1.0, "done")
            # 텔레그램 알림 발송 확인
            app_mock.bot.send_message.assert_awaited_once()
            sent_msg = app_mock.bot.send_message.call_args[1]["text"]
            assert "잔고 부족" in sent_msg
            assert "외부에서 수동 매도된 것으로 감지되어" in sent_msg

    _sync_run(_run())


if __name__ == "__main__":
    test_strategy_family_mapping()
    print("test_strategy_family_mapping passed")
    test_single_strategy_different_family_blocked()
    print("test_single_strategy_different_family_blocked passed")
    test_single_strategy_same_family_allowed()
    print("test_single_strategy_same_family_allowed passed")
    test_single_strategy_manual_and_stoploss_exempt()
    print("test_single_strategy_manual_and_stoploss_exempt passed")
    test_single_strategy_dca_conflict()
    print("test_single_strategy_dca_conflict passed")
    test_check_can_place_order_integrates_single_strategy()
    print("test_check_can_place_order_integrates_single_strategy passed")
    test_reconcile_external_sells_fifo()
    print("test_reconcile_external_sells_fifo passed")
    test_create_linked_sell_order_external_sold_handling()
    print("test_create_linked_sell_order_external_sold_handling passed")
    print("\n=== ALL 8 TESTS PASSED PERFECTLY! ===")
