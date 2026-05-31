"""Phase 9 단기: KIS 분봉 한계 명확화 + 캔들 캐싱 테스트"""
import asyncio
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.exchange_adapter import ExchangeAdapter
from core.signal_engine import SignalEngine


# ── 캔들 캐싱 ──────────────────────────────────────────────────────────

class _DummyUsers:
    def get_user(self, _):
        return {"exchanges": {"kis": {"app_key": "k", "app_secret": "s", "account_no": "12345678", "product_code": "01", "env": "paper"}}}


def _make_adapter():
    adapter = ExchangeAdapter(_DummyUsers())
    return adapter


def test_candle_cache_hit_skips_api_call():
    """같은 파라미터 두 번째 호출 시 API를 호출하지 않고 캐시 값을 반환."""
    adapter = _make_adapter()
    call_count = [0]

    async def fake_cli(resource, command, args=None, keys=None):
        call_count[0] += 1
        return [{"trade_price": 50_000_000}]

    adapter._run_upbit_cli = fake_cli
    asyncio.run(adapter.get_candles("upbit", "KRW-BTC", interval="day", count=10))
    asyncio.run(adapter.get_candles("upbit", "KRW-BTC", interval="day", count=10))

    assert call_count[0] == 1  # 두 번째 호출은 캐시에서


def test_candle_cache_miss_on_different_interval():
    """interval이 다르면 별개 캐시 엔트리 — 각각 API 호출."""
    adapter = _make_adapter()
    call_count = [0]

    async def fake_cli(resource, command, args=None, keys=None):
        call_count[0] += 1
        return [{"trade_price": 50_000_000}]

    adapter._run_upbit_cli = fake_cli
    asyncio.run(adapter.get_candles("upbit", "KRW-BTC", interval="day", count=10))
    asyncio.run(adapter.get_candles("upbit", "KRW-BTC", interval="60", count=10))

    assert call_count[0] == 2  # interval 다름 → 캐시 미스


def test_candle_cache_expires_after_ttl():
    """TTL 만료 후에는 API를 다시 호출."""
    adapter = _make_adapter()
    call_count = [0]

    async def fake_cli(resource, command, args=None, keys=None):
        call_count[0] += 1
        return [{"trade_price": 50_000_000}]

    adapter._run_upbit_cli = fake_cli
    asyncio.run(adapter.get_candles("upbit", "KRW-BTC", interval="60", count=10))
    # 캐시 항목을 강제로 만료
    key = ("upbit", "KRW-BTC", "60", 10)
    fetched_at, cached = adapter._candle_cache[key]
    adapter._candle_cache[key] = (fetched_at - 61, cached)  # TTL=60s 초과

    asyncio.run(adapter.get_candles("upbit", "KRW-BTC", interval="60", count=10))

    assert call_count[0] == 2  # 만료 후 재호출


def test_failed_candle_fetch_not_cached():
    """None 반환(실패) 결과는 캐시에 저장하지 않음."""
    adapter = _make_adapter()
    call_count = [0]

    async def fake_cli(resource, command, args=None, keys=None):
        call_count[0] += 1
        return None

    adapter._run_upbit_cli = fake_cli
    asyncio.run(adapter.get_candles("upbit", "KRW-BTC", interval="day", count=10))
    asyncio.run(adapter.get_candles("upbit", "KRW-BTC", interval="day", count=10))

    assert call_count[0] == 2  # 실패 결과는 캐시 안 함


# ── KIS 분봉 폴백 ────────────────────────────────────────────────────────

def test_signal_engine_falls_back_to_day_for_kis_minute_interval():
    """get_rsi() 호출 시 KIS + 분봉 조합이면 일봉으로 자동 폴백."""
    calls = []

    class MockAdapter:
        async def get_candles(self, exchange, ticker, interval, count, user_id=None):
            calls.append(interval)
            return None  # 실제 데이터 불필요 (폴백 경로만 검증)

        @staticmethod
        def adjust_price_to_tick(p):
            return int(p)

    engine = SignalEngine(MagicMock(), MockAdapter())
    asyncio.run(engine.get_rsi("kis", "005930", interval="60", user_id="1"))

    assert len(calls) == 1
    assert calls[0] == "day"  # 분봉 요청이 일봉으로 폴백되어야 함


def test_signal_engine_keeps_day_for_kis_day_interval():
    """KIS + 일봉은 그대로 통과."""
    calls = []

    class MockAdapter:
        async def get_candles(self, exchange, ticker, interval, count, user_id=None):
            calls.append(interval)
            return None

        @staticmethod
        def adjust_price_to_tick(p):
            return int(p)

    engine = SignalEngine(MagicMock(), MockAdapter())
    asyncio.run(engine.get_rsi("kis", "005930", interval="day", user_id="1"))

    assert calls[0] == "day"


def test_kis_rsi_minute_error_constant_is_defined():
    """_KIS_RSI_MINUTE_ERROR 상수가 main.py에 존재하고 KIS 관련 안내 포함."""
    import main
    assert hasattr(main, "_KIS_RSI_MINUTE_ERROR")
    assert "한국투자증권" in main._KIS_RSI_MINUTE_ERROR
    assert "rsi_interval day" in main._KIS_RSI_MINUTE_ERROR
