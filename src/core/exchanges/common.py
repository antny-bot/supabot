class CommonMixin:
    """거래소 공통 호가 단위 계산 및 상태 정규화 헬퍼."""

    @staticmethod
    def get_tick_size(price):
        """업비트/빗썸 호가 단위 계산"""
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

    @staticmethod
    def adjust_price_to_tick(price):
        """가격을 호가 단위에 맞게 보정 (내림 처리)"""
        tick_size = CommonMixin.get_tick_size(price)
        adjusted = price - (price % tick_size)
        if tick_size >= 1:
            return int(adjusted)
        return round(adjusted, 4)

    @staticmethod
    def get_krx_tick_size(price):
        """KIS/Toss(KRX 상장 주식) 호가 단위 계산 (업비트/빗썸 호가 단위와 다름)"""
        if price >= 500000: return 1000
        if price >= 200000: return 500
        if price >= 50000: return 100
        if price >= 20000: return 50
        if price >= 5000: return 10
        if price >= 2000: return 5
        return 1

    @staticmethod
    def adjust_krx_price_to_tick(price):
        """KIS/Toss 주문 가격을 KRX 호가 단위에 맞게 보정 (내림 처리)"""
        tick_size = CommonMixin.get_krx_tick_size(price)
        adjusted = price - (price % tick_size)
        return int(adjusted)

    @staticmethod
    def adjust_us_price_to_tick(price):
        """Toss 해외주식 주문 가격을 센트(0.01) 단위로 보정 (내림 처리)"""
        adjusted = price - (price % 0.01)
        return round(adjusted, 2)

    @staticmethod
    def _normalize_order_state(state, executed_volume=0):
        state = (state or "").lower()
        if state in ["done", "completed"]:
            return "done"
        if state in ["cancel", "canceled", "cancelled"]:
            return "cancel"
        if executed_volume > 0:
            return "partial"
        return "wait"

    @staticmethod
    def _is_error_response(res):
        if not isinstance(res, dict):
            return False
        if "error" in res:
            return True
        status = str(res.get("status", ""))
        return status.startswith("4") or status.startswith("5")
