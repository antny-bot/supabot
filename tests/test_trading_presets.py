import pytest
from core.trading_presets import (
    BUY_RECOMMENDED_TIME_PRESETS,
    SELL_RECOMMENDED_TIME_PRESETS,
    ALL_RECOMMENDED_TIME_PRESETS,
    get_recommended_times,
    get_recommended_time_by_rank,
    get_presets_by_time,
    format_recommended_time_guide,
)


def test_buy_presets_ranks_and_times():
    assert len(BUY_RECOMMENDED_TIME_PRESETS) == 3

    # 1순위: 15:10 (15:00~15:20) 종가 추세
    p1 = BUY_RECOMMENDED_TIME_PRESETS[0]
    assert p1["rank"] == 1
    assert p1["time"] == "15:10"
    assert "15:00~15:20" in p1["time_range"]
    assert "종가 추세" in p1["reason"]

    # 2순위: 09:40 (09:30~10:00) 변동성 진정
    p2 = BUY_RECOMMENDED_TIME_PRESETS[1]
    assert p2["rank"] == 2
    assert p2["time"] == "09:40"
    assert "09:30~10:00" in p2["time_range"]
    assert "변동성 진정" in p2["reason"]

    # 3순위: 10:30 (10:30 전후) 아시아 장 개장
    p3 = BUY_RECOMMENDED_TIME_PRESETS[2]
    assert p3["rank"] == 3
    assert p3["time"] == "10:30"
    assert "아시아" in p3["reason"]


def test_sell_presets_ranks_and_times():
    assert len(SELL_RECOMMENDED_TIME_PRESETS) == 3

    # 1순위: 09:20 (09:10~09:30) 거래량/고점
    p1 = SELL_RECOMMENDED_TIME_PRESETS[0]
    assert p1["rank"] == 1
    assert p1["time"] == "09:20"
    assert "09:10~09:30" in p1["time_range"]
    assert "고점" in p1["reason"]

    # 2순위: 11:15 (11:00~11:30) 전장 반등
    p2 = SELL_RECOMMENDED_TIME_PRESETS[1]
    assert p2["rank"] == 2
    assert p2["time"] == "11:15"
    assert "11:00~11:30" in p2["time_range"]
    assert "전장 반등" in p2["reason"]

    # 3순위: 15:10 (15:00~15:20) 차익실현 마감
    p3 = SELL_RECOMMENDED_TIME_PRESETS[2]
    assert p3["rank"] == 3
    assert p3["time"] == "15:10"
    assert "차익 실현" in p3["reason"]


def test_helper_functions():
    assert get_recommended_time_by_rank("buy", 1) == "15:10"
    assert get_recommended_time_by_rank("buy", 2) == "09:40"
    assert get_recommended_time_by_rank("buy", 3) == "10:30"

    assert get_recommended_time_by_rank("sell", 1) == "09:20"
    assert get_recommended_time_by_rank("sell", 2) == "11:15"
    assert get_recommended_time_by_rank("sell", 3) == "15:10"

    # get_presets_by_time
    matches_1510 = get_presets_by_time("15:10")
    # 15:10은 매수 1순위이자 매도 3순위
    assert len(matches_1510) == 2
    actions = {m["action"] for m in matches_1510}
    assert "buy" in actions
    assert "sell" in actions

    matches_0920 = get_presets_by_time("09:20")
    assert len(matches_0920) == 1
    assert matches_0920[0]["action"] == "sell"

    guide = format_recommended_time_guide()
    assert "15:10" in guide
    assert "09:40" in guide
    assert "09:20" in guide
    assert "11:15" in guide
