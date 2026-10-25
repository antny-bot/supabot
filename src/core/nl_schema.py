from typing import Literal, Optional
from pydantic import BaseModel, Field


class TradeIntentModel(BaseModel):
    action: Optional[Literal[
        "asset",
        "price",
        "orders",
        "status",
        "config_view",
        "config_set",
        "history",
        "buy",
        "sell",
        "grid",
        "sgrid",
        "rsitrade",
        "gridrsi",
        "sgridrsi",
        "watch",
        "unwatch",
        "cancel",
        "help",
        "rsi",
        "indicators",
        "clarify",
    ]] = Field(default=None, description="파싱된 봇 액션 명령")

    exchange: Optional[Literal["upbit", "bithumb", "kis", "toss"]] = Field(
        default=None, description="대상 거래소 (upbit, bithumb, kis, toss)"
    )

    ticker: Optional[str] = Field(
        default=None, description="코인 심볼(BTC, ETH 등) 또는 6자리 주식코드(005930 등)"
    )

    price: Optional[float] = Field(
        default=None, description="지정가 주문 가격"
    )

    volume: Optional[float] = Field(
        default=None, description="주문 코인/주식 수량"
    )

    amount_krw: Optional[int] = Field(
        default=None, description="주문 원화 금액"
    )

    start_price: Optional[float] = Field(
        default=None, description="그리드 매매 시작 가격"
    )

    end_price: Optional[float] = Field(
        default=None, description="그리드 매매 종료 가격"
    )

    count: Optional[int] = Field(
        default=None, description="분할 횟수 (주문 분할 수)"
    )

    buy_rsi_range: Optional[str] = Field(
        default=None, description="매수 RSI 구간 (예: 25-30)"
    )

    sell_rsi_range: Optional[str] = Field(
        default=None, description="매도 RSI 구간 (예: 65-75)"
    )

    dca_mode: Optional[bool] = Field(
        default=None, description="DCA(물타기) 가중 분할 모드 활성화 여부"
    )

    config_key: Optional[str] = Field(
        default=None, description="설정 변경 키"
    )

    config_value: Optional[str] = Field(
        default=None, description="설정 변경 값"
    )

    question: Optional[str] = Field(
        default=None, description="action이 clarify인 경우 사용자에게 확인할 되묻기 질문"
    )
