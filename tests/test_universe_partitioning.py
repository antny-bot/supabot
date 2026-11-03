"""유니버스 분리(Universe Partitioning) 정책 종합 단위 테스트.

docs/plans/universe_partitioning_policy.md 명세 검증:
1. TOP N 대형주 전담 종목(삼성전자 등)에 개별 전략(RSI, Grid, DCA 등) 주문 등록 시도시 사전 차단
2. TOP N 외 종목(11위 이하 중소형주, 코스닥, 코인)은 개별 전략 정상 허용
3. 수동 주문(manual) 및 손절(stoploss)은 대형주라도 항상 허용
4. TOP N 바스켓 산출 시 exclude_tickers 전달 시 충돌 종목 스킵 및 차순위 종목 자동 편입 검증
"""
import os
import sys
import inspect

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.trading_gate import (
    assert_single_strategy_per_ticker,
    is_top_universe_ticker,
    DEFAULT_TOP_UNIVERSE_TICKERS,
    check_can_place_order,
)
from manager.backend.services.universe_resolver import (
    resolve_strategy_targets,
    DEFAULT_KOSPI_TOP,
)


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


def test_is_top_universe_ticker():
    """TOP N 대형주 판별 로직 검증."""
    assert is_top_universe_ticker("005930") is True   # 삼성전자
    assert is_top_universe_ticker("000660") is True   # SK하이닉스
    assert is_top_universe_ticker("005490") is False  # 11위 POSCO홀딩스
    assert is_top_universe_ticker("KRW-BTC") is False # 비트코인


def test_universe_partitioning_blocks_top_tickers():
    """TOP N 대형주에 개별 전략(RSI, Grid, DCA) 주문 시도시 차단되어야 한다."""
    # 1. 삼성전자(005930)에 rsitrade 시도시 차단
    ok, msg = assert_single_strategy_per_ticker([], ticker="005930", strategy="rsitrade")
    assert ok is False
    assert "TOP N 모으기 전략" in msg
    assert "005930" in msg

    # 2. SK하이닉스(000660)에 grid 시도시 차단
    ok, msg = assert_single_strategy_per_ticker([], ticker="000660", strategy="grid")
    assert ok is False
    assert "TOP N 모으기 전략" in msg

    # 3. LG에너지솔루션(373220)에 dca 시도시 차단
    ok, msg = assert_single_strategy_per_ticker([], ticker="373220", strategy="dca")
    assert ok is False
    assert "TOP N 모으기 전략" in msg


def test_universe_partitioning_allows_non_top_tickers():
    """11위 이하 종목이나 코스닥/코인은 개별 전략으로 정상 허용되어야 한다."""
    # 11위 POSCO홀딩스(005490) rsitrade 허용
    ok, msg = assert_single_strategy_per_ticker([], ticker="005490", strategy="rsitrade")
    assert ok is True
    assert msg is None

    # 14위 카카오(035720) grid 허용
    ok, msg = assert_single_strategy_per_ticker([], ticker="035720", strategy="grid")
    assert ok is True
    assert msg is None

    # 코인 허용
    ok, msg = assert_single_strategy_per_ticker([], ticker="KRW-BTC", strategy="rsitrade")
    assert ok is True


def test_universe_partitioning_exempts_manual_and_stoploss():
    """수동 주문(manual) 및 손절(stoploss)은 대형주라도 항상 허용되어야 한다."""
    # 삼성전자 수동 매수/매도 허용
    ok, msg = assert_single_strategy_per_ticker([], ticker="005930", strategy="manual")
    assert ok is True

    # 삼성전자 손절 허용
    ok, msg = assert_single_strategy_per_ticker([], ticker="005930", strategy="stoploss")
    assert ok is True


def test_resolve_strategy_targets_with_exclude_tickers():
    """TOP N 바스켓 산출 시 exclude_tickers 전달 시 충돌 종목 스킵 및 차순위 자동 편입 검증."""
    async def _run():
        params = {"market": "KOSPI", "rank_start": 1, "rank_end": 10}
        master = [dict(x) for x in DEFAULT_KOSPI_TOP]  # 20개 종목

        # 1. 제외 종목 없을 때: 1위~10위 총 10개
        targets_normal = await resolve_strategy_targets(params, master_items=master)
        assert len(targets_normal) == 10
        assert targets_normal[0]["code"] == "005930"  # 1위 삼성전자
        assert targets_normal[9]["code"] == "012450"  # 10위 한화에어로스페이스

        # 2. 1위 삼성전자(005930)가 개별 전략 운용 중(exclude_tickers)인 경우:
        # 1위 삼성전자가 제외되고, 2위(SK하이닉스)부터 11위(POSCO홀딩스 005490)까지 총 10개가 차순위 편입되어야 함!
        targets_excluded = await resolve_strategy_targets(
            params, master_items=master, exclude_tickers={"005930"}
        )
        assert len(targets_excluded) == 10
        codes = [t["code"] for t in targets_excluded]
        assert "005930" not in codes
        assert targets_excluded[0]["code"] == "000660"  # 2위 SK하이닉스부터 시작
        assert targets_excluded[9]["code"] == "005490"  # 11위 POSCO홀딩스가 차순위로 편입됨!

    _sync_run(_run())


if __name__ == "__main__":
    test_is_top_universe_ticker()
    print("test_is_top_universe_ticker passed")
    test_universe_partitioning_blocks_top_tickers()
    print("test_universe_partitioning_blocks_top_tickers passed")
    test_universe_partitioning_allows_non_top_tickers()
    print("test_universe_partitioning_allows_non_top_tickers passed")
    test_universe_partitioning_exempts_manual_and_stoploss()
    print("test_universe_partitioning_exempts_manual_and_stoploss passed")
    test_resolve_strategy_targets_with_exclude_tickers()
    print("test_resolve_strategy_targets_with_exclude_tickers passed")
    print("\n=== ALL 5 UNIVERSE PARTITIONING TESTS PASSED PERFECTLY! ===")
