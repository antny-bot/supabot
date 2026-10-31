"""다중 시나리오 역테스트 & 수익률 비교 엔진 (backtest_engine.py).

단 1회의 일자별 마스터 스냅샷 로드 후 최대 6개 시나리오 + 벤치마크를 step_single_day 순수 함수로
고속 시뮬레이션(0.5초 이내)하여 수익률, 리스크(MDD), 알파, 가상 원장 및 리더보드를 산출한다.
"""
import copy
import math
from datetime import datetime, timedelta, timezone
import logging

from . import universe_resolver
from . import budget_manager
from .progression_manager import step_single_day

logger = logging.getLogger("backtest_engine")
KST = timezone(timedelta(hours=9))


def compute_xirr(cash_flows: list[tuple[datetime, float]]) -> float:
    """적립식 불규칙 현금흐름 내부수익률(XIRR) 산출 (뉴턴-랩슨 근사)."""
    if len(cash_flows) < 2:
        return 0.0

    dates = [cf[0] for cf in cash_flows]
    amounts = [cf[1] for cf in cash_flows]
    d0 = dates[0]

    # 연 단위 시간 경과
    years = [(d - d0).total_days() / 365.0 for d in dates]

    # r = 0.1 초기값
    r = 0.1
    for _ in range(50):
        # f(r) = sum(cf_i / (1 + r)^t_i)
        f_val = 0.0
        df_val = 0.0
        for amt, t in zip(amounts, years):
            denom = math.pow(1.0 + r, t) if (1.0 + r) > 0 else 1.0
            f_val += amt / denom
            if t > 0 and (1.0 + r) > 0:
                df_val -= t * amt / (denom * (1.0 + r))

        if abs(f_val) < 1e-4:
            break
        if abs(df_val) < 1e-9:
            break
        r_new = r - f_val / df_val
        if r_new <= -0.999:
            r = -0.5
            break
        r = r_new

    return r * 100.0


async def run_multi_scenario_backtest(
    start_date: str,
    end_date: str,
    scenarios: list[dict],
    include_benchmark: bool = True,
) -> dict:
    """다중 시나리오 역테스트 실행 및 비교 분석 결과 반환."""
    if not scenarios:
        raise ValueError("최소 1개 이상의 시나리오가 필요합니다.")

    # 대표 시장 결정
    market = scenarios[0].get("market", "KOSPI")

    # 1. 대상 기간의 일별 마스터 TOP 50 스냅샷 맵 1회 로드 (DB 캐싱 & 백필)
    daily_snapshots_map = await universe_resolver.backfill_historical_master_top(
        market=market,
        start_date=start_date,
        end_date=end_date,
        max_n=50,
    )
    sorted_dates = sorted(daily_snapshots_map.keys())
    if not sorted_dates:
        raise ValueError(f"{start_date} ~ {end_date} 기간에 해당하는 영업일 데이터가 없습니다.")

    # 2. 각 시나리오별 시뮬레이션 실행
    scenario_results = []
    daily_comparison_points = {d: {"date": d} for d in sorted_dates}

    total_days = max(1, (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days)
    years_elapsed = max(0.01, total_days / 365.25)

    for sc_idx, sc_cfg in enumerate(scenarios):
        sc_name = sc_cfg.get("name", f"시나리오 {chr(65 + sc_idx)}")
        sim_state = {
            "market": sc_cfg.get("market", market),
            "rank_start": int(sc_cfg.get("rank_start", 1)),
            "rank_end": int(sc_cfg.get("rank_end", sc_cfg.get("top_n", 10))),
            "upper_exit_mode": sc_cfg.get("upper_exit_mode", "sell_on_any_exit"),
            "exit_rank_buffer": int(sc_cfg.get("exit_rank_buffer", 2)),
            "exit_confirm_days": int(sc_cfg.get("exit_confirm_days", 2)),
            "sell_split_days": int(sc_cfg.get("sell_split_days", 5)),
            "cycle_alloc_mode": sc_cfg.get("cycle_alloc_mode", "one_share"),
            "cycle_target_krw": float(sc_cfg.get("cycle_target_krw", 300000.0)),
            "sell_proceeds_mode": sc_cfg.get("sell_proceeds_mode", "keep_cash"),
            "budget_mode": sc_cfg.get("budget_mode", "monthly"),
            "monthly_budget": float(sc_cfg.get("monthly_budget", 3000000.0)),
            "daily_fixed_budget": float(sc_cfg.get("daily_fixed_budget", 150000.0)),
            "custom_tickers": sc_cfg.get("custom_tickers"),
            "budget_epoch": 1,
            "plan_revision_no": 1,
            "carryover_budget": float(sc_cfg.get("initial_carryover", 0.0)),
            "monthly_spent": 0.0,
            "cycle_no": 1,
            "current_cycle_bought": [],
            "skipped_untradable": [],
            "exit_candidate_streaks": {},
            "exit_progress": {},
            "holdings": {},
            "last_group_no": 0,
            "is_holding": False,
        }

        timeline_events = {e["date"]: e for e in sc_cfg.get("timeline_events", []) if "date" in e}

        total_invested = float(sc_cfg.get("initial_carryover", 0.0))
        cash_flows = [(datetime.strptime(sorted_dates[0], "%Y-%m-%d"), -total_invested)] if total_invested > 0 else []

        equity_curve = []
        simulated_ledger = []
        peak_equity = 0.0
        max_drawdown = 0.0
        total_fee_tax = 0.0
        cycle_durations = []
        cycle_start_date = sorted_dates[0]
        cur_cycle_tracked = 1

        # 일자별 타임라인 시뮬레이션
        for d_str in sorted_dates:
            d_dt = datetime.strptime(d_str, "%Y-%m-%d")
            master_items = daily_snapshots_map[d_str]
            price_map = {item["code"]: float(item["price"]) for item in master_items}

            # 2-1. 타임라인 이벤트 적용
            if d_str in timeline_events:
                ev = timeline_events[d_str]
                ev_type = ev.get("type")
                if ev_type == "HOLDING_TOGGLE":
                    sim_state["is_holding"] = bool(ev.get("is_holding", True))
                elif ev_type == "MANUAL_TOPUP":
                    topup = float(ev.get("amount", 0.0))
                    sim_state["carryover_budget"] += topup
                    total_invested += topup
                    cash_flows.append((d_dt, -topup))
                    simulated_ledger.append({
                        "date": d_str,
                        "type": "MANUAL_TOPUP",
                        "delta": topup,
                        "balance": sim_state["carryover_budget"],
                        "desc": f"특별 추경 투입: {ev.get('memo', '')}",
                    })
                elif ev_type == "PLAN_CHANGE":
                    if "monthly_budget" in ev:
                        sim_state["monthly_budget"] = float(ev["monthly_budget"])
                    if "budget_mode" in ev:
                        sim_state["budget_mode"] = str(ev["budget_mode"])
                    if "daily_fixed_budget" in ev:
                        sim_state["daily_fixed_budget"] = float(ev["daily_fixed_budget"])
                elif ev_type == "BUDGET_RESET":
                    sim_state["budget_epoch"] += 1
                    sim_state["carryover_budget"] = float(ev.get("initial_carryover", 0.0))
                    sim_state["monthly_spent"] = 0.0
                    if ev.get("reset_cycle", True):
                        sim_state["cycle_no"] = 1
                        sim_state["current_cycle_bought"] = []

            # 2-2. 일일 예산 충전 (Holding 중이 아닐 때)
            if not sim_state["is_holding"]:
                rem_days = budget_manager.calculate_remaining_trading_days(d_str)
                allowance = budget_manager.compute_daily_allowance(
                    budget_mode=sim_state["budget_mode"],
                    monthly_budget=sim_state["monthly_budget"],
                    daily_fixed_budget=sim_state["daily_fixed_budget"],
                    monthly_spent=sim_state["monthly_spent"],
                    carryover_budget=sim_state["carryover_budget"],
                    remaining_trading_days=rem_days,
                )
                sim_state["carryover_budget"] += allowance
                total_invested += allowance
                cash_flows.append((d_dt, -allowance))
                simulated_ledger.append({
                    "date": d_str,
                    "type": "DAILY_CREDIT",
                    "delta": allowance,
                    "balance": sim_state["carryover_budget"],
                    "desc": f"일일 예산 충전 (+{allowance:,.0f}원)",
                })

            # 2-3. 타겟 리스트 슬라이싱
            targets = []
            if sim_state.get("custom_tickers"):
                t_set = set(sim_state["custom_tickers"])
                targets = [it for it in master_items if it["code"] in t_set]
            else:
                s_idx = max(0, sim_state["rank_start"] - 1)
                e_idx = max(s_idx + 1, sim_state["rank_end"])
                targets = master_items[s_idx:e_idx]

            # 2-4. 순수 상태 전이 실행 (step_single_day)
            if not sim_state["is_holding"]:
                sim_state, buys, sells = step_single_day(
                    state=sim_state,
                    date_str=d_str,
                    target_list=targets,
                    master_items=master_items,
                    price_map=price_map,
                    is_dry_run=True,
                )
                # 수수료 및 거래세 (매수 0.015%, 매도 0.165%)
                for b in buys:
                    fee = b["cost"] * 0.00015
                    total_fee_tax += fee
                    simulated_ledger.append({
                        "date": d_str,
                        "type": "BUY_ORDER_SPEND",
                        "delta": -b["cost"],
                        "balance": sim_state["carryover_budget"],
                        "desc": f"{b.get('rank', '')}위 {b['ticker']} {b['volume']:g}주 매수 (-{b['cost']:,.0f}원)",
                    })
                for s in sells:
                    sell_amt = s["volume"] * s["price"]
                    tax = sell_amt * 0.00165
                    total_fee_tax += tax
                    # recycle_to_budget 모드면 가용 예산 재투입
                    if sim_state["sell_proceeds_mode"] == "recycle_to_budget":
                        sim_state["carryover_budget"] += sell_amt
                        simulated_ledger.append({
                            "date": d_str,
                            "type": "SELL_PROCEEDS_RECYCLE",
                            "delta": sell_amt,
                            "balance": sim_state["carryover_budget"],
                            "desc": f"이탈 종목({s['ticker']}) 매도 대금 재투입 (+{sell_amt:,.0f}원)",
                        })

                # 사이클 완주 추적
                if sim_state["cycle_no"] > cur_cycle_tracked:
                    duration = (d_dt - datetime.strptime(cycle_start_date, "%Y-%m-%d")).days
                    cycle_durations.append(max(1, duration))
                    cycle_start_date = d_str
                    cur_cycle_tracked = sim_state["cycle_no"]

            # 2-5. 당일 마감 총 평가 자산 (주식 평가액 + 가용 잔여 현금)
            stock_equity = 0.0
            for code, h in sim_state.get("holdings", {}).items():
                p = price_map.get(code, h.get("avg_price", 0.0))
                stock_equity += h.get("qty", 0.0) * p

            total_equity = stock_equity + sim_state["carryover_budget"]
            peak_equity = max(peak_equity, total_equity)
            drawdown = ((peak_equity - total_equity) / peak_equity * 100.0) if peak_equity > 0 else 0.0
            max_drawdown = max(max_drawdown, drawdown)

            cumulative_return = ((total_equity - total_invested) / total_invested * 100.0) if total_invested > 0 else 0.0

            point = {
                "date": d_str,
                "total_invested": total_invested,
                "stock_equity": stock_equity,
                "cash": sim_state["carryover_budget"],
                "total_equity": total_equity,
                "return_pct": cumulative_return,
                "drawdown_pct": drawdown,
            }
            equity_curve.append(point)
            daily_comparison_points[d_str][f"sc_{sc_idx}_return"] = round(cumulative_return, 2)
            daily_comparison_points[d_str][f"sc_{sc_idx}_equity"] = round(total_equity)

        # 최종 성과 지표 산출
        final_equity = equity_curve[-1]["total_equity"] if equity_curve else 0.0
        net_profit = final_equity - total_invested
        roi = ((final_equity - total_invested) / total_invested * 100.0) if total_invested > 0 else 0.0

        # CAGR = (final / invested) ^ (1 / years) - 1
        if total_invested > 0 and final_equity > 0:
            try:
                cagr = (math.pow(final_equity / total_invested, 1.0 / years_elapsed) - 1.0) * 100.0
            except Exception:
                cagr = 0.0
        else:
            cagr = 0.0

        # IRR (XIRR)
        final_dt = datetime.strptime(sorted_dates[-1], "%Y-%m-%d")
        cash_flows.append((final_dt, final_equity))
        try:
            irr = compute_xirr(cash_flows)
        except Exception:
            irr = cagr

        calmar = abs(roi / max_drawdown) if max_drawdown > 0 else 0.0
        avg_cycle_days = round(sum(cycle_durations) / len(cycle_durations), 1) if cycle_durations else 0.0

        # 종목별 기여도 Top / Bottom
        stock_contributions = []
        for code, h in sim_state.get("holdings", {}).items():
            cost = h.get("total_cost", 0.0)
            cur_p = price_map.get(code, h.get("avg_price", 0.0))
            cur_val = h.get("qty", 0.0) * cur_p
            pnl = cur_val - cost
            ret = (pnl / cost * 100.0) if cost > 0 else 0.0
            stock_contributions.append({
                "code": code,
                "qty": h.get("qty", 0.0),
                "cost": cost,
                "value": cur_val,
                "pnl": pnl,
                "return_pct": round(ret, 2),
            })
        stock_contributions.sort(key=lambda x: x["pnl"], reverse=True)

        scenario_results.append({
            "scenario_index": sc_idx,
            "name": sc_name,
            "config": sc_cfg,
            "total_invested": total_invested,
            "final_equity": final_equity,
            "net_profit": net_profit,
            "roi": round(roi, 2),
            "cagr": round(cagr, 2),
            "irr": round(irr, 2),
            "mdd": round(max_drawdown, 2),
            "calmar": round(calmar, 2),
            "cycles_completed": sim_state["cycle_no"] - 1,
            "avg_cycle_days": avg_cycle_days,
            "total_fee_tax": round(total_fee_tax),
            "equity_curve": equity_curve,
            "simulated_ledger": simulated_ledger[-100:],  # 최근 100건
            "stock_contributions": stock_contributions,
        })

    # 3. 벤치마크 (단순 지수/1위 종목 적립식 DCA) 산출
    bench_name = f"{market} 벤치마크 (적립식)"
    bench_cash_invested = 0.0
    bench_qty = 0.0
    bench_curve = []
    
    # 1위 종목 가격 기준 적립식 시뮬레이션
    for d_str in sorted_dates:
        m_items = daily_snapshots_map[d_str]
        top1_price = float(m_items[0]["price"]) if m_items else 1000.0
        # 일일 15만 원 적립 기준
        d_invest = 150000.0
        bench_cash_invested += d_invest
        bench_qty += d_invest / top1_price
        bench_equity = bench_qty * top1_price
        bench_ret = ((bench_equity - bench_cash_invested) / bench_cash_invested * 100.0) if bench_cash_invested > 0 else 0.0
        
        bench_curve.append({
            "date": d_str,
            "total_invested": bench_cash_invested,
            "total_equity": bench_equity,
            "return_pct": round(bench_ret, 2),
        })
        daily_comparison_points[d_str]["benchmark_return"] = round(bench_ret, 2)
        daily_comparison_points[d_str]["benchmark_equity"] = round(bench_equity)

    bench_final_equity = bench_curve[-1]["total_equity"] if bench_curve else 0.0
    bench_roi = ((bench_final_equity - bench_cash_invested) / bench_cash_invested * 100.0) if bench_cash_invested > 0 else 0.0

    # 4. 리더보드 순위 및 배지 산출
    best_roi_idx = max(range(len(scenario_results)), key=lambda i: scenario_results[i]["roi"])
    lowest_mdd_idx = min(range(len(scenario_results)), key=lambda i: scenario_results[i]["mdd"])
    best_calmar_idx = max(range(len(scenario_results)), key=lambda i: scenario_results[i]["calmar"])

    leaderboard = []
    for sc in scenario_results:
        idx = sc["scenario_index"]
        alpha = round(sc["roi"] - bench_roi, 2)
        sc["alpha"] = alpha
        
        badges = []
        if idx == best_roi_idx:
            badges.append("🏆 Best Return")
        if idx == lowest_mdd_idx:
            badges.append("🛡️ Lowest MDD")
        if idx == best_calmar_idx:
            badges.append("⚡ Best Efficiency")

        leaderboard.append({
            "rank": 0,  # 아래에서 정렬 후 할당
            "scenario_index": idx,
            "name": sc["name"],
            "badges": badges,
            "roi": sc["roi"],
            "cagr": sc["cagr"],
            "irr": sc["irr"],
            "mdd": sc["mdd"],
            "calmar": sc["calmar"],
            "alpha": alpha,
            "total_invested": sc["total_invested"],
            "final_equity": sc["final_equity"],
            "net_profit": sc["net_profit"],
            "cycles_completed": sc["cycles_completed"],
            "avg_cycle_days": sc["avg_cycle_days"],
            "total_fee_tax": sc["total_fee_tax"],
        })

    # ROI 기준 리더보드 정렬
    leaderboard.sort(key=lambda x: x["roi"], reverse=True)
    for r_idx, lb in enumerate(leaderboard):
        lb["rank"] = r_idx + 1

    comparison_series = [daily_comparison_points[d] for d in sorted_dates]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "trading_days_count": len(sorted_dates),
        "leaderboard": leaderboard,
        "comparison_series": comparison_series,
        "benchmark": {
            "name": bench_name,
            "roi": round(bench_roi, 2),
            "final_equity": round(bench_final_equity),
            "total_invested": round(bench_cash_invested),
        },
        "scenario_details": {sc["scenario_index"]: sc for sc in scenario_results},
    }
