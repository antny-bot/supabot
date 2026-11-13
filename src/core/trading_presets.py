"""trading_presets.py — 매수/매도 권장 실행 시각 프리셋 모듈.

국내 증시 및 가상자산 시장의 일중 유동성·변동성 패턴을 반영한 추천 프리셋:
- 매수 추천 시각:
    1순위: 15:10 (15:00~15:20) - 종가 추세 형성 (오버나잇 리스크 최소화 및 안정 진입)
    2순위: 09:40 (09:30~10:00) - 시초가 변동성 진정 (장초반 갭/휩소 회피 및 지지선 확인)
    3순위: 10:30 (10:30 전후) - 아시아 장 개장 (중화권 등 아시아 주요 증시 개장 방향성 반영)

- 매도 추천 시각:
    1순위: 09:20 (09:10~09:30) - 거래량 폭발 & 당일 고점 형성 (장초반 수급 집중 구간 익절)
    2순위: 11:15 (11:00~11:30) - 전장 반등 타이밍 (오전 눌림목 후 전장 마감 전 반등 파동)
    3순위: 15:10 (15:00~15:20) - 당일 차익 실현 마무리 (장마감 전 당일 수익 확정 및 정리)
"""

from typing import Literal, TypedDict


class TradingTimePreset(TypedDict):
    rank: int
    time: str
    time_range: str
    action: Literal["buy", "sell"]
    label: str
    reason: str
    description: str


BUY_RECOMMENDED_TIME_PRESETS: list[TradingTimePreset] = [
    {
        "rank": 1,
        "time": "15:10",
        "time_range": "15:00~15:20",
        "action": "buy",
        "label": "15:10 (1순위: 종가추세)",
        "reason": "종가 추세 형성",
        "description": "당일 장세의 종가 방향성이 잡히고 오버나잇 리스크를 줄이며 안정적으로 진입하는 최적 시각",
    },
    {
        "rank": 2,
        "time": "09:40",
        "time_range": "09:30~10:00",
        "action": "buy",
        "label": "09:40 (2순위: 변동성진정)",
        "reason": "시초가 변동성 진정",
        "description": "개장 직후 30분의 과도한 갭과 휩소 변동성이 진정되고 당일 지지선이 확인되는 시각",
    },
    {
        "rank": 3,
        "time": "10:30",
        "time_range": "10:30 전후",
        "action": "buy",
        "label": "10:30 (3순위: 아시아장)",
        "reason": "아시아 장 개장",
        "description": "중국·홍콩 등 아시아 주요 증시가 개장하며 장중 수급 방향성이 2차로 확인되는 시각",
    },
]

SELL_RECOMMENDED_TIME_PRESETS: list[TradingTimePreset] = [
    {
        "rank": 1,
        "time": "09:20",
        "time_range": "09:10~09:30",
        "action": "sell",
        "label": "09:20 (1순위: 고점형성)",
        "reason": "거래량 폭발 & 당일 고점 형성",
        "description": "개장 직후 거래량이 가장 활발히 터지며 당일 장중 고점이 빈출되는 익절 최적 시각",
    },
    {
        "rank": 2,
        "time": "11:15",
        "time_range": "11:00~11:30",
        "action": "sell",
        "label": "11:15 (2순위: 전장반등)",
        "reason": "전장 반등 타이밍",
        "description": "오전 눌림목 이후 전장 마감(오전장 후반) 전 기술적 반등 파동을 노려 차익 실현하는 시각",
    },
    {
        "rank": 3,
        "time": "15:10",
        "time_range": "15:00~15:20",
        "action": "sell",
        "label": "15:10 (3순위: 당일마감)",
        "reason": "당일 차익 실현 마무리",
        "description": "장 마감 직전 오버나잇 변동성을 피하고 당일 수익을 확실하게 확정·정리하는 시각",
    },
]

ALL_RECOMMENDED_TIME_PRESETS: list[TradingTimePreset] = (
    BUY_RECOMMENDED_TIME_PRESETS + SELL_RECOMMENDED_TIME_PRESETS
)


def get_recommended_times(action: Literal["buy", "sell", "all"] = "buy") -> list[TradingTimePreset]:
    """액션 유형(buy / sell / all)에 따른 추천 시각 프리셋 목록을 반환한다."""
    if action == "buy":
        return list(BUY_RECOMMENDED_TIME_PRESETS)
    if action == "sell":
        return list(SELL_RECOMMENDED_TIME_PRESETS)
    return list(ALL_RECOMMENDED_TIME_PRESETS)


def get_recommended_time_by_rank(action: Literal["buy", "sell"] = "buy", rank: int = 1) -> str:
    """순위(1~3)에 해당하는 추천 시각(HH:MM)을 반환한다. (기본값: 1순위)"""
    presets = BUY_RECOMMENDED_TIME_PRESETS if action == "buy" else SELL_RECOMMENDED_TIME_PRESETS
    for p in presets:
        if p["rank"] == rank:
            return p["time"]
    return presets[0]["time"] if presets else "15:10"


def get_presets_by_time(time_str: str) -> list[TradingTimePreset]:
    """지정된 시간(HH:MM)과 일치하는 매수/매도 추천 프리셋 목록을 반환한다."""
    cleaned = (time_str or "").strip()
    return [p for p in ALL_RECOMMENDED_TIME_PRESETS if p["time"] == cleaned]


def format_recommended_time_guide() -> str:
    """텔레그램이나 도움말에서 출력 가능한 권장 시각 안내 요약 문자열을 반환한다."""
    lines = [
        "⏰ <b>매수/매도 권장 실행 시각 프리셋</b>",
        "",
        "🟢 <b>매수 추천 시각</b>:",
        " • <b>1순위 [15:10]</b> (15:00~15:20): 종가 추세 형성 (오버나잇 리스크 최소화)",
        " • <b>2순위 [09:40]</b> (09:30~10:00): 시초가 변동성 진정 (초반 갭/휩소 회피)",
        " • <b>3순위 [10:30]</b> (10:30 전후): 아시아 장 개장 (수급 방향성 2차 확인)",
        "",
        "🔴 <b>매도 추천 시각</b>:",
        " • <b>1순위 [09:20]</b> (09:10~09:30): 거래량 폭발 & 고점 형성 (당일 최고가 빈출)",
        " • <b>2순위 [11:15]</b> (11:00~11:30): 전장 반등 노림 (오전 눌림목 후 반등 파동)",
        " • <b>3순위 [15:10]</b> (15:00~15:20): 당일 차익실현 마무리 (장마감 전 확정)",
    ]
    return "\n".join(lines)
