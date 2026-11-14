"""호가 단위(Tick Size) 및 가격 보정 공통 유틸리티."""


def get_krx_tick_size(price: float) -> int:
    """한국거래소(KRX) 주식 호가 단위 계산 (KIS / Toss 국내)."""
    p = float(price)
    if p >= 500000:
        return 1000
    if p >= 200000:
        return 500
    if p >= 50000:
        return 100
    if p >= 20000:
        return 50
    if p >= 5000:
        return 10
    if p >= 2000:
        return 5
    return 1


def adjust_krx_price_to_tick(price: float) -> int:
    """KRX 주문 가격을 호가 단위에 맞게 보정 (내림 처리)."""
    tick = get_krx_tick_size(price)
    adjusted = price - (price % tick)
    return int(adjusted)


def get_crypto_tick_size(price: float) -> float:
    """가상자산(Upbit / Bithumb) 호가 단위 계산."""
    p = float(price)
    if p >= 2000000:
        return 1000
    if p >= 1000000:
        return 500
    if p >= 500000:
        return 100
    if p >= 100000:
        return 50
    if p >= 10000:
        return 10
    if p >= 1000:
        return 5
    if p >= 100:
        return 1
    if p >= 10:
        return 0.1
    if p >= 1:
        return 0.01
    if p >= 0.1:
        return 0.001
    return 0.0001


def adjust_crypto_price_to_tick(price: float) -> float | int:
    """가상자산 주문 가격을 호가 단위에 맞게 보정 (내림 처리)."""
    tick = get_crypto_tick_size(price)
    adjusted = price - (price % tick)
    if tick >= 1:
        return int(adjusted)
    return round(adjusted, 4)


def adjust_us_price_to_tick(price: float) -> float:
    """Toss 해외주식 주문 가격을 센트(0.01) 단위로 보정 (내림 처리)."""
    adjusted = price - (price % 0.01)
    return round(adjusted, 2)


def get_tick_size(price: float, exchange: str = "base") -> float:
    """거래소 및 가격에 따른 통합 호가 단위 산출."""
    ex = str(exchange or "base").lower()
    if ex in ("kis", "toss"):
        return float(get_krx_tick_size(price))
    return float(get_crypto_tick_size(price))
