"""Phase 8 장기: 메트릭 수집 + /diag 운영 모니터링 테스트"""
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def _fresh_metrics():
    from core.metrics import _MetricsCollector
    return _MetricsCollector()


# ── record_order ─────────────────────────────────────────────────────────────

def test_metrics_record_order_counts_ok_and_fail():
    """성공/실패 주문이 정확히 집계되어야 함."""
    m = _fresh_metrics()
    m.record_order("upbit", True)
    m.record_order("upbit", True)
    m.record_order("upbit", False)
    snap = m.snapshot()
    assert snap["orders"]["upbit"]["ok"] == 2
    assert snap["orders"]["upbit"]["fail"] == 1
    assert snap["orders"]["upbit"]["total"] == 3
    assert snap["orders"]["upbit"]["success_rate"] == round(2 / 3 * 100, 1)


def test_metrics_record_order_separate_exchanges():
    """거래소별로 독립적인 카운터를 유지해야 함."""
    m = _fresh_metrics()
    m.record_order("upbit", True)
    m.record_order("bithumb", False)
    snap = m.snapshot()
    assert snap["orders"]["upbit"]["ok"] == 1
    assert snap["orders"]["bithumb"]["fail"] == 1
    assert "upbit" in snap["orders"]
    assert "bithumb" in snap["orders"]


# ── record_latency ────────────────────────────────────────────────────────────

def test_metrics_record_latency_p50_p95():
    """p50/p95 레이턴시가 올바르게 계산되어야 함."""
    m = _fresh_metrics()
    for i in range(1, 21):  # 1ms ~ 20ms, 20개
        m.record_latency("upbit", float(i))
    snap = m.snapshot()
    lat = snap["latencies"]["upbit"]
    assert lat["count"] == 20
    # p50: index = 20//2 = 10 → s[10] = 11.0 (0-indexed, sorted)
    assert lat["p50"] == 11.0
    assert lat["p95"] >= 18.0


def test_metrics_latency_capped_at_100():
    """100개 초과 시 최근 100개만 유지해야 함."""
    m = _fresh_metrics()
    for i in range(150):
        m.record_latency("kis", float(i))
    snap = m.snapshot()
    assert snap["latencies"]["kis"]["count"] == 100


# ── record_poll_ok / record_signal_ok ────────────────────────────────────────

def test_metrics_record_poll_ok_updates_timestamp():
    """record_poll_ok 호출 후 poll_last_ok가 현재 시각으로 갱신되어야 함."""
    m = _fresh_metrics()
    before = time.time()
    m.record_poll_ok()
    snap = m.snapshot()
    assert snap["poll_last_ok"] is not None
    assert snap["poll_last_ok"] >= before


def test_metrics_record_signal_ok_updates_timestamp():
    """record_signal_ok 호출 후 signal_last_ok가 현재 시각으로 갱신되어야 함."""
    m = _fresh_metrics()
    m.record_signal_ok()
    snap = m.snapshot()
    assert snap["signal_last_ok"] is not None


# ── ops_alerts ────────────────────────────────────────────────────────────────

def test_ops_alerts_no_issues_returns_empty():
    """정상 상태에서 ops_alerts는 빈 리스트를 반환해야 함."""
    m = _fresh_metrics()
    for _ in range(10):
        m.record_order("upbit", True)
    m.record_poll_ok()
    m.record_signal_ok()
    assert m.ops_alerts() == []


def test_ops_alerts_high_failure_rate():
    """5건 이상 + 실패율 20% 초과 시 알림이 발생해야 함."""
    m = _fresh_metrics()
    m.record_order("upbit", True)   # 1 ok
    for _ in range(4):
        m.record_order("upbit", False)  # 4 fail → 20% success
    alerts = m.ops_alerts()
    assert any("upbit" in a and "실패율" in a for a in alerts)


def test_ops_alerts_poll_loop_stale():
    """주문 동기화 루프가 5분 이상 응답 없을 때 알림이 발생해야 함."""
    m = _fresh_metrics()
    m._poll_ts = time.time() - 400  # 400초 전 (> 300초 임계)
    alerts = m.ops_alerts()
    assert any("주문 동기화" in a for a in alerts)


def test_ops_alerts_signal_loop_stale():
    """신호 분석 루프가 15분 이상 응답 없을 때 알림이 발생해야 함."""
    m = _fresh_metrics()
    m._signal_ts = time.time() - 1000  # 1000초 전 (> 900초 임계)
    alerts = m.ops_alerts()
    assert any("신호 분석" in a for a in alerts)


def test_ops_alerts_below_threshold_no_alert():
    """4건 이하이면 실패율이 높아도 알림 없음 (샘플 부족)."""
    m = _fresh_metrics()
    for _ in range(4):
        m.record_order("upbit", False)
    alerts = m.ops_alerts()
    assert not any("실패율" in a for a in alerts)


# ── build_diag_view: metrics section ─────────────────────────────────────────

def test_diag_view_includes_metrics_section():
    """build_diag_view에 메트릭 섹션이 포함되어야 함."""
    from core.formatters import build_diag_view
    from core.user_manager import UserManager
    user = {
        "is_active": True, "is_admin": True,
        "preferences": dict(UserManager.DEFAULT_PREFERENCES),
        "exchanges": {}, "llm": {},
    }
    snap = {
        "orders": {"upbit": {"ok": 5, "fail": 1, "total": 6, "success_rate": 83.3}},
        "latencies": {"upbit": {"p50": 120.0, "p95": 350.0, "count": 10}},
        "poll_last_ok": time.time() - 30,
        "signal_last_ok": time.time() - 60,
    }
    view = build_diag_view(user, metrics_snapshot=snap)
    assert "메트릭" in view
    assert "upbit" in view
    assert "p50" in view


def test_diag_view_metrics_section_with_empty_snapshot():
    """메트릭 snapshot이 없을 때도 '메트릭 수집 없음' 등으로 안전하게 표시되어야 함."""
    from core.formatters import build_diag_view
    from core.user_manager import UserManager
    user = {
        "is_active": True, "is_admin": True,
        "preferences": dict(UserManager.DEFAULT_PREFERENCES),
        "exchanges": {}, "llm": {},
    }
    view = build_diag_view(user, metrics_snapshot=None)
    assert "메트릭" in view


# ── exchange_adapter records latency ─────────────────────────────────────────

def test_exchange_adapter_records_upbit_latency():
    """_run_upbit_cli 호출 시 upbit 레이턴시가 metrics에 기록되어야 함."""
    import asyncio
    from unittest.mock import AsyncMock as _AsyncMock, MagicMock, patch
    from core.exchange_adapter import ExchangeAdapter

    class _DummyUsers:
        def get_user(self, _):
            return {"exchanges": {"upbit": {"access_key": "k", "secret_key": "s"}}}

    adapter = ExchangeAdapter(_DummyUsers())

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.communicate = _AsyncMock(return_value=(b'[{"trade_price": 50000000}]', b''))

    with patch("core.exchanges.upbit.metrics") as mock_metrics:
        with patch("asyncio.create_subprocess_exec", new_callable=_AsyncMock) as mock_exec:
            mock_exec.return_value = mock_process
            asyncio.run(adapter._run_upbit_cli("candles", "list-days"))
        mock_metrics.record_latency.assert_called_once()
        call_args = mock_metrics.record_latency.call_args[0]
        assert call_args[0] == "upbit"
        assert isinstance(call_args[1], float)


def test_exchange_adapter_records_order_outcome():
    """create_order 성공 시 주문 성공 카운터가 증가해야 함."""
    import asyncio
    from core.exchange_adapter import ExchangeAdapter
    from core.metrics import metrics as global_metrics

    class _DummyUsers:
        def get_user(self, _):
            return {"exchanges": {"upbit": {"access_key": "k", "secret_key": "s"}}}

    adapter = ExchangeAdapter(_DummyUsers())

    async def fake_cli(resource, command, args=None, keys=None):
        return {"uuid": "test-order-uuid"}

    adapter._run_upbit_cli = fake_cli

    before_ok = global_metrics.snapshot()["orders"].get("upbit", {}).get("ok", 0)
    asyncio.run(adapter.create_order("user1", "upbit", "KRW-BTC", "bid", 50_000_000, 0.001))
    after_ok = global_metrics.snapshot()["orders"].get("upbit", {}).get("ok", 0)

    assert after_ok == before_ok + 1
