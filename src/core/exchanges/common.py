"""Backward compatibility module: forwards to supabot_common.ticks."""
from supabot_common.ticks import (
    get_tick_size as _common_get_tick_size,
    get_krx_tick_size as _common_get_krx_tick_size,
    get_crypto_tick_size,
    adjust_crypto_price_to_tick,
    adjust_krx_price_to_tick as _common_adjust_krx_price_to_tick,
    adjust_us_price_to_tick as _common_adjust_us_price_to_tick,
)


class CommonMixin:
    """거래소 공통 호가 단위 계산 및 상태 정규화 헬퍼 (supabot_common 위임)."""

    @staticmethod
    def get_tick_size(price):
        """업비트/빗썸 호가 단위 계산"""
        return get_crypto_tick_size(price)

    @staticmethod
    def adjust_price_to_tick(price):
        """가격을 호가 단위에 맞게 보정 (내림 처리)"""
        return adjust_crypto_price_to_tick(price)

    @staticmethod
    def get_krx_tick_size(price):
        """KIS/Toss(KRX 상장 주식) 호가 단위 계산"""
        return _common_get_krx_tick_size(price)

    @staticmethod
    def adjust_krx_price_to_tick(price):
        """KIS/Toss 주문 가격을 KRX 호가 단위에 맞게 보정 (내림 처리)"""
        return _common_adjust_krx_price_to_tick(price)

    @staticmethod
    def adjust_us_price_to_tick(price):
        """Toss 해외주식 주문 가격을 센트(0.01) 단위로 보정 (내림 처리)"""
        return _common_adjust_us_price_to_tick(price)

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
