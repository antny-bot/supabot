"""주문 계획 및 분할 주문 생성 모듈 (order_planner.py).

단일 종목 전략(grid, sgrid, rsitrade)에 대해 호가 단위(Tick Size) 보정,
수수료 버퍼(0.999) 반영 및 수량 계산을 전담하여 Supabase orders 테이블에
저장할 status='reserved' 주문 명세를 생성한다.
"""
import uuid
import math
from supabot_common.ticks import get_tick_size


def adjust_price_to_tick(price: float, exchange: str = "base") -> float:
    """호가 단위(Tick Size)에 맞게 내림 보정."""
    tick = get_tick_size(price, exchange)
    adjusted = price - (price % tick)
    if tick >= 1:
        return float(int(adjusted))
    return round(adjusted, 4)


def round_volume(raw_vol: float, exchange: str = "base") -> float:
    """거래소 특성에 맞게 수량 보정 (주식: 정수, 암호화폐: 소수 4자리)."""
    if exchange.lower() in ("kis", "toss"):
        return float(int(raw_vol))
    return round(raw_vol, 4)


def plan_grid_orders(
    user_id: str,
    exchange: str,
    ticker: str,
    start_price: float,
    end_price: float,
    count: int,
    budget_or_volume: float,
    is_sell: bool,
    group_no: int,
    template_id: int | None = None,
) -> list[dict]:
    """가격 범위 분할 매수(grid) 또는 매도(sgrid)의 status='reserved' 주문 목록 생성."""
    if count <= 0 or budget_or_volume <= 0:
        return []

    price_step = (end_price - start_price) / (count - 1) if count > 1 else 0.0
    orders = []

    for i in range(count):
        raw_price = start_price + (price_step * i)
        target_price = adjust_price_to_tick(raw_price, exchange)

        if is_sell:
            raw_vol = budget_or_volume / count
        else:
            # 매수 시 수수료 버퍼 0.1%(0.999) 반영하여 잔고 부족 방지
            effective_budget = (budget_or_volume / count) * 0.999
            raw_vol = effective_budget / target_price if target_price > 0 else 0.0

        volume = round_volume(raw_vol, exchange)
        if volume <= 0:
            continue

        order_dict = {
            "uuid": f"reserved:{uuid.uuid4().hex}",
            "user_id": str(user_id),
            "exchange": exchange,
            "ticker": ticker,
            "price": target_price,
            "volume": volume,
            "filled_volume": 0.0,
            "side": "ask" if is_sell else "bid",
            "strategy": "sgrid" if is_sell else "grid",
            "status": "reserved",
            "group_no": group_no,
        }
        if template_id is not None:
            order_dict["template_id"] = template_id

        orders.append(order_dict)

    return orders


def plan_rsitrade_orders(
    user_id: str,
    exchange: str,
    ticker: str,
    start_rsi: float,
    end_rsi: float,
    count: int,
    total_budget: float,
    current_price: float,
    current_rsi: float,
    group_no: int,
    template_id: int | None = None,
) -> list[dict]:
    """목표 RSI 구간 등간격 분할 매수 주문 생성 (가격 역산 추정)."""
    if count <= 0 or total_budget <= 0 or current_rsi <= 0 or current_price <= 0:
        return []

    rsi_step = (end_rsi - start_rsi) / (count - 1) if count > 1 else 0.0
    orders = []

    for i in range(count):
        target_rsi = start_rsi + (rsi_step * i)
        # 단순 선형 비례 가격 역산 근사: price_est = current_price * (target_rsi / current_rsi)
        ratio = max(0.01, target_rsi / current_rsi)
        raw_price = current_price * ratio
        target_price = adjust_price_to_tick(raw_price, exchange)

        effective_budget = (total_budget / count) * 0.999
        raw_vol = effective_budget / target_price if target_price > 0 else 0.0
        volume = round_volume(raw_vol, exchange)
        if volume <= 0:
            continue

        order_dict = {
            "uuid": f"reserved:{uuid.uuid4().hex}",
            "user_id": str(user_id),
            "exchange": exchange,
            "ticker": ticker,
            "price": target_price,
            "volume": volume,
            "filled_volume": 0.0,
            "side": "bid",
            "strategy": "rsitrade",
            "status": "reserved",
            "target_rsi": target_rsi,
            "group_no": group_no,
        }
        if template_id is not None:
            order_dict["template_id"] = template_id

        orders.append(order_dict)

    return orders
