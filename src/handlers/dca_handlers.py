"""/dca, /sdca — 정기 분할 매수/매도(DCA) 전략 커맨드 및 콜백 핸들러.

strategy_handlers.py에서 모듈화 분리됨.
"""
from datetime import datetime, timezone, timedelta
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import main
from main import check_auth, check_details_help, resolve_ticker_for_command
from core.parsers import (
    parse_exchange_and_ticker, is_exchange_token, parse_number,
    exchange_display_name, is_us_stock_ticker, KST,
)
from core.strategy_tokens import create_strategy_token, pop_valid_strategy_token, discard_strategy_token
from core import trading_gate
from core.dca_manager import format_dca_schedule, format_cash_health_section

logger = logging.getLogger(__name__)

# --- /dca, /sdca: 정기 매수/매도(DCA) 전략 핸들러 ---

_SIDE_ALIASES = {
    "매수": "bid", "buy": "bid", "bid": "bid",
    "매도": "ask", "sell": "ask", "ask": "ask",
}


def _format_dca_amount_text(exchange: str, ticker: str, amount_type: str, amount: float) -> str:
    is_usd = is_us_stock_ticker(exchange, ticker)
    if amount_type == "volume":
        if exchange in ("kis", "toss"):
            return f"{int(amount):,}주"
        return f"{amount:g}개"
    if is_usd:
        return f"${amount:,.2f}"
    return f"{amount:,.0f}원"


def build_dca_list_message(user_id: str, cash_reports: list[dict] | None = None) -> tuple[str, InlineKeyboardMarkup | None]:
    from datetime import datetime
    from core.parsers import KST
    from core.dca_manager import format_dca_schedule, format_cash_health_section

    dca_mgr = getattr(main, "dca_manager", None)
    schedules = dca_mgr.get_user_schedules(user_id, active_only=True) if dca_mgr else []
    if not schedules:
        msg = (
            "📅 <b>등록된 정기 매수/매도 전략이 없습니다.</b>\n\n"
            "<b>사용 예시:</b>\n"
            "• <code>/dca BTC 매일 5만</code> (매일 09:05 5만원 매수)\n"
            "• <code>/dca 한투 005930 매주월 1주 09:10</code> (매주 월요일 1주 매수)\n"
            "• <code>/dca ETH 월수금 3만 10:00 20회</code> (월·수·금 3만원 매수, 총 20회)\n"
            "• <code>/dca 매도 BTC 매월15일 0.01개</code> (매월 15일 0.01개 매도)"
        )
        return msg, None

    lines = [f"📅 <b>가동 중인 정기 매수/매도 전략 ({len(schedules)}건)</b>\n"]
    buttons = []
    for idx, s in enumerate(schedules, start=1):
        side_str = "매수" if s.get("side") == "bid" else "매도"
        ex_str = exchange_display_name(s["exchange"])
        tk = s["ticker"]
        sched_str = format_dca_schedule(s)
        amt_str = _format_dca_amount_text(s["exchange"], tk, s.get("amount_type", "budget"), float(s["amount"]))
        run_cnt = int(s.get("run_count") or 0)
        max_runs = s.get("max_runs")
        run_str = f"{run_cnt}/{max_runs}회" if max_runs else f"누적 {run_cnt}회 (무기한)"
        next_ts = float(s.get("next_run_at") or 0)
        next_str = datetime.fromtimestamp(next_ts, tz=KST).strftime("%Y-%m-%d %H:%M") if next_ts > 0 else "-"
        gno = s.get("group_no")
        group_tag = f" [<b>#{gno}</b>]" if gno else ""

        lines.append(
            f"<b>{idx}. [{ex_str}] {tk} ({side_str})</b>{group_tag}  <code>{s['id']}</code>\n"
            f"  ├ 주기: {sched_str}\n"
            f"  ├ 1회 규모: {amt_str} | 진행: {run_str}\n"
            f"  └ 다음 실행: {next_str} (KST)"
        )
        btn_tag = f"#{gno}" if gno else f"{idx}번"
        buttons.append([
            InlineKeyboardButton(
                f"🛑 {btn_tag} 중지 ({tk} {side_str})",
                callback_data=f"dcadel|{s['id']}",
            )
        ])

    if cash_reports:
        lines.append("\n" + format_cash_health_section(cash_reports, html=True))

    lines.append("\n💡 중지 명령어: <code>/dca stop [#배치번호 또는 ID]</code> | 배치 리포트: <code>/report #[번호]</code>")
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def build_dca_confirm_summary(payload: dict) -> str:
    from datetime import datetime
    from core.parsers import KST
    from core.dca_manager import format_dca_schedule, compute_next_run_at

    exchange = payload["exchange"]
    ticker = payload["ticker"]
    side = payload["side"]
    action_label = "매수" if side == "bid" else "매도"
    sched_text = format_dca_schedule(payload)
    amt_type = payload["amount_type"]
    amt_label = "1회 수량" if amt_type == "volume" else "1회 예산"
    amt_text = _format_dca_amount_text(exchange, ticker, amt_type, float(payload["amount"]))
    max_runs = payload.get("max_runs")
    runs_text = f"총 {max_runs}회 실행 후 자동 종료" if max_runs else "무기한 반복 (수동 중지 전까지)"
    next_ts = compute_next_run_at(
        frequency=payload["frequency"],
        exec_time=payload["exec_time"],
        days_of_week=payload.get("days_of_week"),
        day_of_month=payload.get("day_of_month"),
    )
    next_dt_str = datetime.fromtimestamp(next_ts, tz=KST).strftime("%Y-%m-%d %H:%M")

    market_note = ""
    if exchange in ("kis", "toss"):
        market_note = "\nℹ️ 주식 휴장일·장외 시간 도래 시 다음 정규장 개장 시각에 자동 실행됩니다."

    return (
        f"📅 정기 {action_label} 전략 확인\n\n"
        f"전략 설정\n"
        f"- 거래소: {exchange_display_name(exchange)}\n"
        f"- 종목: {ticker}\n"
        f"- 구분: 정기 {action_label}\n"
        f"- 주기: {sched_text}\n"
        f"- {amt_label}: {amt_text}\n"
        f"- 주문 방식: 실행 시점 현재가 기준 지정가 (슬리피지 버퍼 적용)\n"
        f"- 반복 조건: {runs_text}\n"
        f"- 첫 실행 예정: {next_dt_str} (KST)"
        f"{market_note}\n\n"
        f"위 내용으로 정기 {action_label} 전략을 등록할까요?"
    )


async def _handle_dca_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user, default_side: str = "bid"):
    from core.dca_manager import (
        DEFAULT_DCA_EXEC_TIME,
        parse_dca_schedule,
        parse_dca_amount,
        parse_dca_time,
        parse_dca_max_runs,
        is_dca_time_token,
        is_dca_max_runs_token,
    )

    user_id = str(update.effective_chat.id)
    args = list(context.args or [])

    # 1. 인자가 없거나 list 조회인 경우
    if not args or args[0].lower() in ("list", "목록", "조회", "status"):
        from core.dca_manager import analyze_user_cash_sufficiency
        dca_mgr = getattr(main, "dca_manager", None)
        cash_reports = await analyze_user_cash_sufficiency(
            user_id, dca_mgr, getattr(main, "order_manager", None), getattr(main, "exchange_adapter", None)
        )
        msg, markup = build_dca_list_message(user_id, cash_reports=cash_reports)
        await update.message.reply_text(msg, reply_markup=markup, parse_mode="HTML")
        return

    # 2. 중지/삭제 명령 처리 (/dca stop [id|번호], /dca clear)
    sub = args[0].lower()
    if sub in ("stop", "del", "delete", "cancel", "remove", "중지", "삭제", "취소"):
        if len(args) < 2:
            await update.message.reply_text("⚠️ 중지할 정기 전략 ID 또는 번호를 입력해 주세요. 예: `/dca stop 1`")
            return
        target_token = args[1].strip()
        dca_mgr = getattr(main, "dca_manager", None)
        if not dca_mgr:
            await update.message.reply_text("⚠️ 정기 전략 관리자가 초기화되지 않았습니다.")
            return
        schedules = dca_mgr.get_user_schedules(user_id, active_only=True)
        target_id = target_token
        if target_token.startswith("#") and target_token[1:].isdigit():
            by_gno = dca_mgr.get_schedule_by_group_no(user_id, int(target_token[1:]))
            if by_gno:
                target_id = by_gno["id"]
        elif target_token.isdigit():
            by_gno = dca_mgr.get_schedule_by_group_no(user_id, int(target_token))
            idx = int(target_token) - 1
            if 0 <= idx < len(schedules):
                target_id = schedules[idx]["id"]
            elif by_gno:
                target_id = by_gno["id"]
        removed = dca_mgr.remove_schedule(target_id, user_id=user_id)
        if removed:
            await update.message.reply_text(f"🛑 정기 전략(`{target_id}`)이 중지 및 삭제되었습니다.")
        else:
            await update.message.reply_text(f"⚠️ `{target_token}`에 해당하는 정기 전략을 찾을 수 없습니다. `/dca`로 목록을 확인하세요.")
        return

    if sub in ("clear", "모두중지", "전체삭제"):
        dca_mgr = getattr(main, "dca_manager", None)
        count = dca_mgr.clear_user_schedules(user_id) if dca_mgr else 0
        await update.message.reply_text(f"🛑 총 {count}건의 정기 매수/매도 전략을 모두 중지했습니다.")
        return

    # 3. 신규 정기 전략 등록
    ok, halt_msg = trading_gate.assert_can_trade()
    if not ok:
        await update.message.reply_text(halt_msg)
        return

    # 첫 토큰이 매수/매도 방향인지 확인
    side = default_side
    if args[0].lower() in _SIDE_ALIASES:
        side = _SIDE_ALIASES[args[0].lower()]
        args = args[1:]

    if len(args) < 3:
        await update.message.reply_text(
            "⚠️ 사용법: /dca [매수|매도] [거래소] [종목] [주기] [금액|수량] [시각(선택)] [횟수(선택)]\n"
            "예시:\n"
            "• /dca BTC 매일 5만\n"
            "• /dca 한투 005930 매주월 1주 09:10\n"
            "• /dca ETH 월수금 3만 10:00 20회\n"
            "• /dca 매도 BTC 매월15일 0.01개"
        )
        return

    default_exchange = user["preferences"].get("default_exchange", "upbit")
    exchange, ticker = await resolve_ticker_for_command(
        update, user_id, args, default_exchange, "/dca kis 005930 매주월 1주"
    )
    if ticker is None:
        return

    offset = 2 if is_exchange_token(args[0], exchange) else 1
    rem = args[offset:]
    if len(rem) < 2:
        await update.message.reply_text(
            "⚠️ 주기와 주문 금액(또는 수량)을 모두 입력해 주세요.\n"
            "예: /dca BTC 매일 5만"
        )
        return

    raw_schedule = rem[0]
    raw_amount = rem[1]
    optional_tokens = rem[2:]

    try:
        sched_info = parse_dca_schedule(raw_schedule)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return

    try:
        amount_type, amount = parse_dca_amount(raw_amount)
    except ValueError as e:
        await update.message.reply_text(f"⚠️ {e}")
        return

    exec_time = DEFAULT_DCA_EXEC_TIME
    max_runs = None
    for tok in optional_tokens:
        if is_dca_time_token(tok):
            exec_time = parse_dca_time(tok)
        elif is_dca_max_runs_token(tok) or tok.isdigit():
            try:
                max_runs = parse_dca_max_runs(tok)
            except ValueError as e:
                await update.message.reply_text(f"⚠️ {e}")
                return
        else:
            await update.message.reply_text(
                f"⚠️ 알 수 없는 옵션입니다: `{tok}`\n"
                "실행 시각은 `09:05` 형식, 총 횟수는 `10회` 형식으로 입력해 주세요."
            )
            return

    ex_obj = main.exchange_adapter.get_exchange(exchange)
    is_usd = is_us_stock_ticker(exchange, ticker)

    if amount_type == "volume":
        if ex_obj.requires_integer_volume() and int(amount) < 1:
            await update.message.reply_text("⚠️ 주식 주문 수량은 최소 1주 이상이어야 합니다.")
            return
    else:
        min_amt = main.exchange_adapter.get_min_order_amount(exchange)
        if not is_usd and amount < min_amt:
            await update.message.reply_text(f"❌ 1회 예산이 너무 적습니다. 최소 {min_amt:,.0f}원 이상이어야 합니다.")
            return
        if side == "bid":
            ok, err_msg = validate_max_order(user, amount, is_usd=is_usd)
            if not ok:
                await update.message.reply_text(err_msg)
                return

    payload = {
        "exchange": exchange,
        "ticker": ticker,
        "side": side,
        "frequency": sched_info["frequency"],
        "days_of_week": sched_info["days_of_week"],
        "day_of_month": sched_info["day_of_month"],
        "exec_time": exec_time,
        "amount_type": amount_type,
        "amount": amount,
        "max_runs": max_runs,
    }
    token = create_strategy_token(user_id, "dcarun", payload)
    action_label = "매수" if side == "bid" else "매도"
    keyboard = [[
        InlineKeyboardButton(f"✅ 정기 {action_label} 시작", callback_data=f"dcarun|{token}"),
        InlineKeyboardButton("❌ 취소", callback_data=f"grid_cancel|{token}"),
    ]]
    summary = build_dca_confirm_summary(payload)
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))


@check_auth
async def dca_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """정기 매수/매도(DCA) 전략 등록 및 목록 관리"""
    if await check_details_help(update, "dca"):
        return
    await _handle_dca_command(update, context, user, default_side="bid")


@check_auth
async def sdca_command(update: Update, context: ContextTypes.DEFAULT_TYPE, user):
    """정기 매도(SDCA) 전략 등록 단축 명령어"""
    if await check_details_help(update, "dca"):
        return
    await _handle_dca_command(update, context, user, default_side="ask")


async def dca_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime
    from core.parsers import KST
    from core.dca_manager import format_dca_schedule

    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    token = query.data.split("|", 1)[1] if "|" in query.data else None
    payload, error = pop_valid_strategy_token(token, user_id)
    if error:
        await query.edit_message_text(f"⚠️ {error}")
        return

    user = main.user_manager.get_user(user_id)
    if not user:
        await query.edit_message_text("❌ 사용자 설정을 찾을 수 없어 등록을 중단합니다.")
        return

    gate_ok, gate_msg = trading_gate.assert_can_trade()
    if not gate_ok:
        await query.edit_message_text(gate_msg)
        return

    dca_mgr = getattr(main, "dca_manager", None)
    if not dca_mgr:
        await query.edit_message_text("❌ 정기 전략 관리자가 초기화되지 않았습니다.")
        return

    om = getattr(main, "order_manager", None)
    open_orders = om.get_user_orders(user_id) if om else []
    dca_scheds = dca_mgr.get_schedules(user_id) if dca_mgr else []
    strat_ok, strat_msg = trading_gate.assert_single_strategy_per_ticker(
        open_orders, ticker=payload["ticker"], strategy="dca", dca_schedules=dca_scheds,
    )
    if not strat_ok:
        await query.edit_message_text(strat_msg)
        return
    group_no = dca_mgr.get_next_group_no(user_id, order_manager=om)
    sched = dca_mgr.add_schedule(
        user_id=user_id,
        exchange=payload["exchange"],
        ticker=payload["ticker"],
        side=payload["side"],
        frequency=payload["frequency"],
        days_of_week=payload.get("days_of_week"),
        day_of_month=payload.get("day_of_month"),
        exec_time=payload["exec_time"],
        amount_type=payload["amount_type"],
        amount=float(payload["amount"]),
        max_runs=payload.get("max_runs"),
        group_no=group_no,
    )

    action_label = "매수" if sched["side"] == "bid" else "매도"
    amt_str = _format_dca_amount_text(sched["exchange"], sched["ticker"], sched["amount_type"], sched["amount"])
    next_dt = datetime.fromtimestamp(sched["next_run_at"], tz=KST).strftime("%Y-%m-%d %H:%M")
    runs_str = f"총 {sched['max_runs']}회" if sched.get("max_runs") else "무기한"

    await query.edit_message_text(
        f"✅ [{exchange_display_name(sched['exchange'])}] {sched['ticker']} 정기 {action_label} 등록 완료!\n\n"
        f"• 배치: #{sched['group_no']} (ID: {sched['id']})\n"
        f"• 주기: {format_dca_schedule(sched)}\n"
        f"• 1회 규모: {amt_str} ({runs_str})\n"
        f"• 첫 실행: {next_dt} (KST)\n\n"
        f"📋 조회 및 중지: /dca | 배치 리포트: /report #{sched['group_no']}"
    )


async def dca_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    sched_id = query.data.split("|", 1)[1] if "|" in query.data else ""
    dca_mgr = getattr(main, "dca_manager", None)
    if not dca_mgr:
        await query.edit_message_text("⚠️ 정기 전략 관리자가 초기화되지 않았습니다.")
        return

    removed = dca_mgr.remove_schedule(sched_id, user_id=user_id)
    if not removed:
        await query.edit_message_text("⚠️ 이미 삭제되었거나 존재하지 않는 전략입니다.")
        return

    msg, markup = build_dca_list_message(user_id)
    header = f"🛑 정기 전략(<code>{sched_id}</code>)을 중지했습니다.\n\n"
    await query.edit_message_text(header + msg, reply_markup=markup, parse_mode="HTML")


_DCA_SIDE_MAP = _SIDE_ALIASES
