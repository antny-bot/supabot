class BaseExchange:
    """거래소 공통 동작의 기본 구현. 암호화폐 거래소(Upbit/Bithumb) 동작을 기본값으로 하고,
    KIS/Toss 등 주식 거래소는 다른 부분만 오버라이드한다.

    각 인스턴스는 adapter(ExchangeAdapter)를 들고 있다가 실제 HTTP/세션/토큰 호출은
    adapter에 위임한다 — 세션·캐시·토큰은 거래소 종류와 무관하게 adapter가 단일 소유한다.
    """

    name = "base"

    def __init__(self, adapter):
        self.adapter = adapter

    # ── 거래/조회 (하위 클래스가 구현) ──────────────────────────────────────────
    async def get_balances(self, user_id, client):
        raise NotImplementedError

    async def create_order(self, user_id, client, ticker, side, price, volume, ord_type="limit"):
        raise NotImplementedError

    async def cancel_order(self, user_id, client, order_id, ticker=None):
        raise NotImplementedError

    async def get_order_status(self, user_id, client, order_id, ticker=None):
        raise NotImplementedError

    async def get_candles(self, ticker, interval, count, user_id=None):
        raise NotImplementedError

    async def get_ticker(self, ticker, user_id=None):
        raise NotImplementedError

    async def get_order_history(self, user_id, client, ticker=None):
        raise NotImplementedError

    async def get_krw_ticker_prices(self):
        return {}

    # ── capability — 기본값은 "코인 거래소" 동작 ────────────────────────────────
    def min_order_amount(self) -> float:
        return 5000

    def supports_minute_candles(self) -> bool:
        return True

    def is_market_open(self, ticker=None) -> bool:
        return True

    def next_check_timestamp(self, ticker=None) -> float:
        return 0.0

    def requires_numeric_ticker(self) -> bool:
        """한글 종목명이 아닌 코드/마켓 심볼로만 주문 가능한지 여부 (KIS/Toss=True)."""
        return False

    def round_volume(self, raw: float):
        """주문 수량을 거래소 단위에 맞게 보정 (코인=소수 4자리, 주식=정수)."""
        return round(raw, 4)

    def requires_integer_volume(self) -> bool:
        """주문 수량이 정수(주식) 단위여야 하는지 여부 (코인=False, KIS/Toss=True).

        round_volume()이 0으로 떨어지면 주문 자체가 불가능한 거래소를 구분해
        호출부가 "0주 주문"을 건너뛸지 판단하는 데 쓴다.
        """
        return False

    def format_volume(self, volume) -> str:
        """표시용 수량 문자열 (코인='개', 주식='주')."""
        return f"{float(volume):.4f}개"

    def get_tick_size(self, price):
        if price >= 2000000: return 1000
        if price >= 1000000: return 500
        if price >= 500000: return 100
        if price >= 100000: return 50
        if price >= 10000: return 10
        if price >= 1000: return 5
        if price >= 100: return 1
        if price >= 10: return 0.1
        if price >= 1: return 0.01
        if price >= 0.1: return 0.001
        return 0.0001

    def adjust_price_to_tick(self, price, ticker=None):
        """가격을 호가 단위에 맞게 보정 (내림 처리). 기본은 코인 틱 단위."""
        tick_size = self.get_tick_size(price)
        adjusted = price - (price % tick_size)
        if tick_size >= 1:
            return int(adjusted)
        return round(adjusted, 4)

    def env_label(self, client=None):
        """KIS 모의/실전처럼 거래소 환경을 나타내는 라벨. 없으면 None."""
        return None

    def required_credential_fields(self) -> list:
        """API 키 설정 여부 판단에 필요한 필드 목록 (기본: 코인 거래소 access/secret)."""
        return ["access_key", "secret_key"]
