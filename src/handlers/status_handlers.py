"""/status — 전략 대시보드."""
from telegram import Update
from telegram.ext import ContextTypes

import main
from main import check_auth, check_details_help
from core.parsers import is_us_stock_ticker


@check_auth
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    if await check_details_help(update, "status"): return
    user_id = str(update.effective_chat.id)
    orders = main.order_manager.get_user_orders(user_id)

    if not orders:
        await update.message.reply_text("📊 현재 가동 중인 트레이딩 전략이 없습니다.\n거래소 실제 미체결 주문은 /orders에서 확인하세요.")
        return

    msg = "📊 트레이딩 전략 통합 대시보드\n\n"

    # 거래소별 그룹화
    status_names = {
        "wait": "대기",
        "partial": "부분체결",
        "market_closed": "장외 대기",
        "pending_reorder": "다음 정규장 재주문 예정",
        "done": "완료",
        "cancel": "취소",
    }
    for ex in ["upbit", "bithumb", "kis", "toss"]:
        ex_orders = [o for o in orders if o['exchange'] == ex]
        if not ex_orders: continue

        msg += f"🏛️ <b>{ex.upper()}</b>\n"

        tickers = sorted(list(set([o['ticker'] for o in ex_orders])))
        for tk in tickers:
            tk_orders = [o for o in ex_orders if o['ticker'] == tk]

            # group_no별 서브그룹 생성: None인 것은 하나로 묶어 먼저 표시
            display_groups = []
            ungrouped = [o for o in tk_orders if not o.get("group_no")]
            if ungrouped:
                display_groups.append((None, ungrouped))
            for gno in sorted(set(o["group_no"] for o in tk_orders if o.get("group_no"))):
                display_groups.append((gno, [o for o in tk_orders if o.get("group_no") == gno]))

            for group_label, g_orders in display_groups:
                total = len(g_orders)
                is_rsi = any(o['strategy'].startswith('rsitrade') for o in g_orders)
                strategy_name = "RSI 순환 매매" if is_rsi else "거미줄 분할 매매"

                if is_rsi:
                    filled = len([o for o in g_orders if o['strategy'] == 'rsitrade_sell'])
                else:
                    filled = len([o for o in g_orders if o['status'] == 'done'])

                prog_bar = "🔵" * filled + "⚪" * (total - filled)
                group_tag = f" [<b>#{group_label}</b>]" if group_label is not None else ""

                msg += f"• <b>{tk}</b> ({strategy_name}){group_tag}\n"
                if is_rsi and filled > 0:
                    msg += f"  └ 진행: {prog_bar} ({total}건 추적, {filled}건 매수완료·매도대기)\n"
                else:
                    msg += f"  └ 진행: {prog_bar} ({total}건 추적)\n"

                for i, o in enumerate(g_orders[:3]):
                    side_str = "매수" if o['side'] == 'bid' else "매도"
                    if o['target_rsi']:
                        target = f"RSI {o['target_rsi']}"
                    elif is_us_stock_ticker(o['exchange'], tk):
                        target = f"${o['price']:,.2f}"
                    else:
                        target = f"{o['price']:,.0f}원"
                    state_text = status_names.get(o.get("status"), o.get("status", "대기"))
                    msg += f"  ▫️ {i+1}. {side_str}[{state_text}]: {target}\n"
                if len(g_orders) > 3: msg += "  ▫️ ... 그 외 생략\n"
        msg += "\n"

    msg += "ℹ️ 체결 및 외부 취소 시 실시간 알림이 전송됩니다.\n"
    msg += "📊 더 상세한 내역과 리포트는 [웹 대시보드]에서 확인하실 수 있습니다."
    await update.message.reply_text(msg, parse_mode="HTML")
