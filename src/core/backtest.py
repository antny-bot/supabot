"""RSI 분할 매매 전략 가상 백테스트 시뮬레이션 엔진 (F5).

실거래 API(create_order 등)는 절대 호출하지 않으며, 순수 인메모리 가상 체결로 동작합니다.
"""
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from core.indicators import RSIIndicator
from core.parsers import interpolate_range, parse_rsi_range


@dataclass
class BacktestTrade:
    entry_time: Any
    exit_time: Any
    entry_price: float
    exit_price: float
    volume: float
    pnl_krw: float
    pnl_pct: float
    fee_krw: float


@dataclass
class BacktestResult:
    initial_budget: float
    final_balance: float
    total_pnl_krw: float
    total_return_pct: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    mdd_pct: float
    trades: List[BacktestTrade]


def run_rsi_backtest(
    df: pd.DataFrame,
    buy_rsi_range: str,
    sell_rsi_range: str,
    count: int,
    initial_budget: float,
    fee_rate: float = 0.0005,
    slippage_pct: float = 0.0005,
    period: int = 14,
) -> BacktestResult:
    """과거 캔들 DataFrame을 기반으로 RSI 분할 매매 전략을 가상 시뮬레이션합니다.

    Args:
        df: 'close', 'high', 'low' 등을 포함하는 캔들 DataFrame (시간순 정렬)
        buy_rsi_range: 매수 RSI 범위 (예: "25-30")
        sell_rsi_range: 익절 매도 RSI 범위 (예: "65-75")
        count: 분할 레그 수 (예: 5)
        initial_budget: 시뮬레이션 투입 총 자본금 (KRW)
        fee_rate: 편도 거래 수수료율 (기본 0.05%)
        slippage_pct: 슬리피지율 (기본 0.05%)
        period: RSI 계산 기간 (기본 14)
    """
    if df is None or len(df) < period + 10:
        return BacktestResult(
            initial_budget=initial_budget, final_balance=initial_budget,
            total_pnl_krw=0.0, total_return_pct=0.0, win_rate=0.0,
            total_trades=0, winning_trades=0, losing_trades=0, mdd_pct=0.0, trades=[]
        )

    # 1. RSI 계산
    import ta
    rsi_series = ta.momentum.RSIIndicator(close=df["close"].astype(float), window=period).rsi()

    b_start, b_end = parse_rsi_range(buy_rsi_range)
    s_start, s_end = parse_rsi_range(sell_rsi_range)

    per_order_budget = initial_budget / count
    cash = initial_budget
    peak_equity = initial_budget
    max_drawdown = 0.0

    # 가상 포지션 관리: list of active buy legs
    # [{'entry_time': ..., 'entry_price': ..., 'volume': ..., 'sell_target_rsi': ..., 'cost': ...}]
    active_positions = []
    closed_trades: List[BacktestTrade] = []

    # 시뮬레이션 루프
    for i in range(period, len(df)):
        current_time = df.index[i] if not isinstance(df.index, pd.RangeIndex) else i
        current_rsi = float(rsi_series.iloc[i])
        current_price = float(df["close"].iloc[i])

        if pd.isna(current_rsi) or pd.isna(current_price) or current_price <= 0:
            continue

        # 2. 매도 검사 (익절 조건 충족된 포지션 매도)
        remaining_positions = []
        for pos in active_positions:
            if current_rsi >= pos["sell_target_rsi"]:
                # 익절 매도 체결
                exit_price = current_price * (1.0 - slippage_pct)
                gross_proceeds = pos["volume"] * exit_price
                sell_fee = gross_proceeds * fee_rate
                net_proceeds = gross_proceeds - sell_fee

                total_fees = pos["buy_fee"] + sell_fee
                pnl = net_proceeds - pos["cost"]
                pnl_pct = (pnl / pos["cost"]) * 100.0 if pos["cost"] > 0 else 0.0

                cash += net_proceeds
                trade = BacktestTrade(
                    entry_time=pos["entry_time"],
                    exit_time=current_time,
                    entry_price=pos["entry_price"],
                    exit_price=exit_price,
                    volume=pos["volume"],
                    pnl_krw=pnl,
                    pnl_pct=pnl_pct,
                    fee_krw=total_fees,
                )
                closed_trades.append(trade)
            else:
                remaining_positions.append(pos)
        active_positions = remaining_positions

        # 3. 매수 검사 (미보유 중인 레그 중 RSI 진입 조건 만족 시 매수)
        # 각 레그의 target_rsi 범위 판정
        for leg_idx in range(count):
            leg_buy_rsi = interpolate_range(b_start, b_end, leg_idx, count)
            leg_sell_rsi = interpolate_range(s_start, s_end, leg_idx, count)

            # 이미 해당 레그가 진입해 있는지 확인
            already_active = any(p.get("leg_idx") == leg_idx for p in active_positions)
            if not already_active and current_rsi <= leg_buy_rsi and cash >= per_order_budget:
                entry_price = current_price * (1.0 + slippage_pct)
                buy_fee = per_order_budget * fee_rate
                investable = per_order_budget - buy_fee
                volume = investable / entry_price

                cash -= per_order_budget
                active_positions.append({
                    "leg_idx": leg_idx,
                    "entry_time": current_time,
                    "entry_price": entry_price,
                    "volume": volume,
                    "cost": per_order_budget,
                    "buy_fee": buy_fee,
                    "sell_target_rsi": leg_sell_rsi,
                })

        # 4. 자산 평가 및 MDD 계산
        position_value = sum(p["volume"] * current_price for p in active_positions)
        total_equity = cash + position_value
        if total_equity > peak_equity:
            peak_equity = total_equity
        drawdown = ((peak_equity - total_equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    # 시뮬레이션 종료 시 미체결 잔여 포지션 가치 합산
    final_equity = cash + sum(p["volume"] * float(df["close"].iloc[-1]) for p in active_positions)
    total_pnl = final_equity - initial_budget
    total_return_pct = (total_pnl / initial_budget) * 100.0 if initial_budget > 0 else 0.0

    total_trades = len(closed_trades)
    winning_trades = sum(1 for t in closed_trades if t.pnl_krw > 0)
    losing_trades = total_trades - winning_trades
    win_rate = (winning_trades / total_trades * 100.0) if total_trades > 0 else 0.0

    return BacktestResult(
        initial_budget=initial_budget,
        final_balance=final_equity,
        total_pnl_krw=total_pnl,
        total_return_pct=total_return_pct,
        win_rate=win_rate,
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        mdd_pct=max_drawdown,
        trades=closed_trades,
    )
