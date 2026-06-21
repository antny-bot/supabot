from core.exchanges.base import BaseExchange


class RegularSessionExchange(BaseExchange):
    """정규장 시간에만 체결되는 거래소(KIS, Toss) 공통 동작.

    하위 클래스는 session_for(ticker)만 구현하면 개장시간 게이팅과
    장외 예약주문(reserved) 대상 판정을 그대로 물려받는다.
    """

    supports_reserved_orders = True  # main.py/order_execution.py가 거래소 이름 대신 이 capability로 분기

    def session_for(self, ticker=None):
        """(is_open_fn, next_check_fn) 튜플 반환 — 서브클래스가 국내/해외 등으로 분기."""
        raise NotImplementedError

    def is_market_open(self, ticker=None) -> bool:
        is_open_fn, _ = self.session_for(ticker)
        return is_open_fn()

    def next_check_timestamp(self, ticker=None) -> float:
        _, next_check_fn = self.session_for(ticker)
        return next_check_fn()
