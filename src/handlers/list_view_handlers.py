"""/orders,/status,/history,/report,/asset 공용 펼치기·페이지네이션 인라인 버튼 디스패처.

콜백 데이터 포맷: ``lv|<kind>|<token>|<action>[|<extra>]``
- kind: orders | status | history | report | asset
- action: toggle(orders/status/asset) | prev/next(history/report)
- extra: asset에서만 거래소 코드(upbit/bithumb/kis/toss)

orders/status는 로컬 order_manager 데이터라 클릭마다 라이브 재조회한다.
history/report/asset은 거래소 API/DB 조회 비용이 있어 명령어 실행 시점에
`core.list_view_tokens`의 토큰에 스냅샷을 저장하고, 버튼 클릭은 그 스냅샷의
다른 페이지/섹션만 다시 그린다(재조회 없음).

각 kind의 `_build_*` 함수는 최초 명령어 실행과 버튼 클릭 양쪽에서 공유되어
렌더링 로직이 중복되지 않는다.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

import main
from core.parsers import exchange_display_name, is_us_stock_ticker
from core.stock_resolver import kr_stock_display
from core.formatters import build_report_view_page

HISTORY_PAGE_SIZE = 5


# ── /orders ──────────────────────────────────────────────────────────────────

_ORDERS_STATUS_NAMES = {"wait": "대기", "partial": "부분체결", "pending_reorder": "재주문대기", "market_closed": "장외대기", "reserved": "예약"}


def _format_order_line(o, with_group_tag: bool) -> str:
    group_tag = f" [<b>#{o['group_no']}</b>]" if with_group_tag and o.get("group_no") else ""
    side_str = "매수" if o["side"] == "bid" else "매도"
    status_str = _ORDERS_STATUS_NAMES.get(o.get("status"), "")
    status_tag = f" — {status_str}" if status_str else ""
    line = f"📌 <b>[{exchange_display_name(o['exchange'])}]</b> {kr_stock_display(o['exchange'], o['ticker'])}{group_tag}\n"
    if is_us_stock_ticker(o['exchange'], o['ticker']):
        line += f"   └ ${o['price']:,.2f} ({side_str}, {o['volume']:.0f}주){status_tag}\n"
    else:
        line += f"   └ {o['price']:,.0f}원 ({side_str}, {o['volume']:.4f}개){status_tag}\n"
    return line


def _status_breakdown(orders) -> str:
    counts = {}
    for o in orders:
        name = _ORDERS_STATUS_NAMES.get(o.get("status"), o.get("status") or "")
        if not name:
            continue
        counts[name] = counts.get(name, 0) + 1
    return " · ".join(f"{name} {c}" for name, c in counts.items())


def _group_orders_by_batch(orders):
    groups = {}
    ungrouped = []
    for o in orders:
        gno = o.get("group_no")
        if gno:
            groups.setdefault(gno, []).append(o)
        else:
            ungrouped.append(o)
    return sorted(groups.items()), ungrouped


def build_orders_message(user_id, exchange, expanded: bool, token=None):
    orders = main.order_manager.get_user_orders(user_id, exchange)
    if not orders:
        if token:
            main.discard_list_view(token)
        return "⏳ 봇이 추적 중인 거래소 미체결 주문은 없습니다.\nRSI/거미줄 전략 대기 상태는 /status에서 확인하세요.", None

    groups, ungrouped = _group_orders_by_batch(orders)

    msg = "⏳ <b>현재 추적 중인 미체결 주문</b>\n\n"
    if expanded or not groups:
        for o in orders:
            msg += _format_order_line(o, with_group_tag=True)
    else:
        for o in ungrouped:
            msg += _format_order_line(o, with_group_tag=False)
        for gno, g_orders in groups:
            tickers = sorted(set((o["exchange"], o["ticker"]) for o in g_orders))
            label_ex, label_tk = tickers[0]
            extra_note = f" 외 {len(tickers) - 1}종목" if len(tickers) > 1 else ""
            msg += (
                f"📦 <b>[#{gno} 배치]</b> [{exchange_display_name(label_ex)}] "
                f"{kr_stock_display(label_ex, label_tk)}{extra_note} — {len(g_orders)}건 ({_status_breakdown(g_orders)})\n"
            )

    msg += "\n배치 번호로 취소: <code>/cancelno [번호]</code>"

    markup = None
    if groups and token:
        label = "🔼 그룹으로 접기" if expanded else "🔽 전체 펼치기"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"lv|orders|{token}|toggle")]])
    return msg, markup


async def _render_orders(entry, token, action, extra):
    if action == "toggle":
        expanded = not entry["state"].get("expanded", False)
        entry["state"]["expanded"] = expanded
        main.update_list_view_state(token, expanded=expanded)
    user_id = entry["user_id"]
    exchange = entry["state"]["exchange"]
    return build_orders_message(user_id, exchange, entry["state"].get("expanded", False), token)


# ── /status ──────────────────────────────────────────────────────────────────

_STATUS_NAMES = {
    "wait": "대기", "partial": "부분체결", "market_closed": "장외 대기",
    "pending_reorder": "다음 정규장 재주문 예정", "reserved": "장외 예약 (개장 시 자동 제출)",
    "done": "완료", "cancel": "취소",
}


def build_status_message(orders, expanded: bool, token=None):
    if not orders:
        return "📊 현재 가동 중인 트레이딩 전략이 없습니다.\n거래소 실제 미체결 주문은 /orders에서 확인하세요.", None

    msg = "📊 트레이딩 전략 통합 대시보드\n\n"
    any_truncatable = False

    for ex in ["upbit", "bithumb", "kis", "toss"]:
        ex_orders = [o for o in orders if o['exchange'] == ex]
        if not ex_orders:
            continue

        msg += f"🏛️ <b>{ex.upper()}</b>\n"

        tickers = sorted(list(set([o['ticker'] for o in ex_orders])))
        for tk in tickers:
            tk_orders = [o for o in ex_orders if o['ticker'] == tk]

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

                shown = g_orders if expanded else g_orders[:3]
                for i, o in enumerate(shown):
                    side_str = "매수" if o['side'] == 'bid' else "매도"
                    if o['target_rsi']:
                        target = f"RSI {o['target_rsi']}"
                    elif is_us_stock_ticker(o['exchange'], tk):
                        target = f"${o['price']:,.2f}"
                    else:
                        target = f"{o['price']:,.0f}원"
                    state_text = _STATUS_NAMES.get(o.get("status"), o.get("status", "대기"))
                    msg += f"  ▫️ {i + 1}. {side_str}[{state_text}]: {target}\n"
                if len(g_orders) > 3:
                    any_truncatable = True
                    if not expanded:
                        msg += "  ▫️ ... 그 외 생략\n"
        msg += "\n"

    msg += "ℹ️ 체결 및 외부 취소 시 실시간 알림이 전송됩니다.\n"
    msg += "📊 더 상세한 내역과 리포트는 [웹 대시보드]에서 확인하실 수 있습니다."

    markup = None
    if any_truncatable and token:
        label = "🔼 접기" if expanded else "🔽 생략된 항목 보기"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f"lv|status|{token}|toggle")]])
    return msg, markup


async def _render_status(entry, token, action, extra):
    if action == "toggle":
        expanded = not entry["state"].get("expanded", False)
        entry["state"]["expanded"] = expanded
        main.update_list_view_state(token, expanded=expanded)
    user_id = entry["user_id"]
    orders = main.order_manager.get_user_orders(user_id)
    return build_status_message(orders, entry["state"].get("expanded", False), token)


# ── /history ─────────────────────────────────────────────────────────────────

def build_history_message(exchange, ticker, history, page: int, token=None, page_size: int = HISTORY_PAGE_SIZE):
    """반환: (text, markup, clamped_page)"""
    total = len(history)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    page_items = history[page * page_size: (page + 1) * page_size]

    msg = f"📜 <b>[{exchange_display_name(exchange)}] 최근 체결 내역</b>"
    if total_pages > 1:
        msg += f" ({page * page_size + 1}-{page * page_size + len(page_items)}/{total}건)"
    else:
        msg += f" ({total}건)"
    msg += "\n\n"

    for ord in page_items:
        side = "🔴 매수" if ord.get('side', '').lower() in ['bid', 'buy'] else "🔵 매도"
        tk = ord.get('market', ticker)
        price = float(ord.get('price', 0))
        vol = float(ord.get('volume', 0))
        date = ord.get('created_at', '').split('T')[0]
        is_usd = is_us_stock_ticker(exchange, tk)

        msg += f"- {date} | {side} | {kr_stock_display(exchange, tk)}\n"
        if is_usd:
            msg += f"  └ ${price:,.2f} | {vol:.0f}주\n"
        else:
            msg += f"  └ {price:,.0f}원 | {vol:.4f}개\n"

    markup = None
    if total_pages > 1 and token:
        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("◀️ 이전", callback_data=f"lv|history|{token}|prev"))
        if page < total_pages - 1:
            buttons.append(InlineKeyboardButton("▶️ 다음", callback_data=f"lv|history|{token}|next"))
        if buttons:
            markup = InlineKeyboardMarkup([buttons])
    return msg, markup, page


async def _render_history(entry, token, action, extra):
    page = entry["state"].get("page", 0)
    if action == "prev":
        page -= 1
    elif action == "next":
        page += 1
    snapshot = entry["snapshot"]
    text, markup, page = build_history_message(snapshot["exchange"], snapshot["ticker"], snapshot["history"], page, token)
    entry["state"]["page"] = page
    main.update_list_view_state(token, page=page)
    return text, markup


# ── /report ──────────────────────────────────────────────────────────────────

async def _render_report(entry, token, action, extra):
    page = entry["state"].get("page", 0)
    if action == "prev":
        page -= 1
    elif action == "next":
        page += 1
    snapshot = entry["snapshot"]
    text, page, total_pages = build_report_view_page(snapshot["trades"], snapshot["period"], page)
    entry["state"]["page"] = page
    main.update_list_view_state(token, page=page)

    markup = None
    if total_pages > 1:
        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("◀️ 이전", callback_data=f"lv|report|{token}|prev"))
        if page < total_pages - 1:
            buttons.append(InlineKeyboardButton("▶️ 다음", callback_data=f"lv|report|{token}|next"))
        if buttons:
            markup = InlineKeyboardMarkup([buttons])
    return text, markup


# ── /asset ───────────────────────────────────────────────────────────────────

def _render_asset_kis_toss_section(ex, balances, expanded: bool):
    ex_env_label = main.exchange_adapter.get_exchange(ex).env_label(balances)
    env_label = f" ({ex_env_label})" if ex_env_label else ""
    text = f"🏛️ <b>{exchange_display_name(ex)}</b>{env_label}\n"
    cash = float(balances.get("cash", 0))
    ex_eval = float(balances.get("total_eval", 0))
    text += f"- 💵 예수금: {cash:,.0f}원\n"

    stocks = sorted(balances.get("stocks", []), key=lambda s: float(s.get("value", 0)), reverse=True)
    shown = stocks if expanded else stocks[:5]
    rest = [] if expanded else stocks[5:]
    for stock in shown:
        value = float(stock.get("value", 0))
        name = stock.get('name') or stock.get('code')
        currency = stock.get("currency", "KRW")
        qty = stock.get('quantity', 0)
        if currency == "KRW":
            text += f"- 📈 {name} ({qty:,.0f}주)\n"
            text += f"   └ {value:,.0f}원\n"
        else:
            text += f"- 📈 {name} ({qty:,.2f}주, {currency})\n"
            text += f"   └ {value:,.2f} {currency}\n"
    others_count = len(rest)
    others_value = sum(float(s.get("value", 0)) for s in rest if s.get("currency", "KRW") == "KRW")
    if others_count > 0:
        text += f"- 📦 기타 {others_count}개 종목: {others_value:,.0f}원\n"
    elif expanded and len(stocks) > 5:
        text += "ℹ️ 잔고는 조회 시점 기준입니다. 최신 정보는 /asset 재실행\n"
    text += f"   └ 계좌 평가액: {ex_eval:,.0f}원\n\n"
    return text, ex_eval, len(stocks) - 5 if len(stocks) > 5 else 0


def _render_asset_coin_section(ex, balances, ticker_prices, expanded: bool):
    text = f"🏛️ <b>{ex.upper()}</b>\n"
    ex_eval = 0
    cash_krw = 0.0
    coin_items = []

    for b in balances:
        qty = float(b['balance']) + float(b['locked'])
        if qty <= 0:
            continue
        currency = b['currency']
        if currency == "KRW":
            ex_eval += qty
            cash_krw += qty
        else:
            price = ticker_prices.get(currency, 0)
            value = qty * price
            ex_eval += value
            coin_items.append({"currency": currency, "qty": qty, "value": value})

    text += f"- 💵 KRW: {cash_krw:,.0f}원\n"

    coin_items.sort(key=lambda x: x["value"], reverse=True)
    shown = coin_items if expanded else coin_items[:5]
    rest = [] if expanded else coin_items[5:]
    for item in shown:
        text += f"- 🪙 {item['currency']} ({item['qty']:.4f}개)\n"
        if item['value'] > 0:
            text += f"   └ {item['value']:,.0f}원\n"
    others_count = len(rest)
    others_value = sum(i["value"] for i in rest)
    if others_count > 0:
        text += f"- 📦 기타 {others_count}개 종목: {others_value:,.0f}원\n"
    elif expanded and len(coin_items) > 5:
        text += "ℹ️ 잔고는 조회 시점 기준입니다. 최신 정보는 /asset 재실행\n"
    text += f"   └ 거래소 평가액: {ex_eval:,.0f}원\n\n"
    return text, ex_eval, len(coin_items) - 5 if len(coin_items) > 5 else 0


def build_asset_message(snapshot, expanded_exchanges, token=None):
    full_msg = "💰 <b>통합 자산 현황</b>\n\n"
    total_eval_krw = 0
    others_counts = {}

    for ex in snapshot["exchanges"]:
        balances = snapshot["balances"].get(ex)
        if balances is None:
            full_msg += f"❌ <b>{exchange_display_name(ex)}</b>: API 키가 설정되지 않았거나 오류 발생\n\n"
            continue
        expanded = ex in expanded_exchanges
        if ex in ("kis", "toss"):
            text, eval_krw, others = _render_asset_kis_toss_section(ex, balances, expanded)
        else:
            text, eval_krw, others = _render_asset_coin_section(ex, balances, snapshot["ticker_prices"].get(ex, {}), expanded)
        full_msg += text
        total_eval_krw += eval_krw
        if not expanded:
            others_counts[ex] = others

    full_msg += f"💳 <b>총 합계 자산: {total_eval_krw:,.0f}원</b>"

    markup = None
    if token:
        rows = []
        for ex, count in others_counts.items():
            if count > 0:
                rows.append([InlineKeyboardButton(f"🔽 {exchange_display_name(ex)} 기타 {count}개 보기", callback_data=f"lv|asset|{token}|toggle|{ex}")])
        for ex in expanded_exchanges:
            rows.append([InlineKeyboardButton(f"🔼 {exchange_display_name(ex)} 접기", callback_data=f"lv|asset|{token}|toggle|{ex}")])
        if rows:
            markup = InlineKeyboardMarkup(rows)
    return full_msg, markup


async def _render_asset(entry, token, action, extra):
    expanded_exchanges = set(entry["state"].get("expanded_exchanges", []))
    if action == "toggle" and extra:
        if extra in expanded_exchanges:
            expanded_exchanges.discard(extra)
        else:
            expanded_exchanges.add(extra)
        entry["state"]["expanded_exchanges"] = sorted(expanded_exchanges)
        main.update_list_view_state(token, expanded_exchanges=sorted(expanded_exchanges))
    return build_asset_message(entry["snapshot"], expanded_exchanges, token)


# ── 디스패처 ──────────────────────────────────────────────────────────────────

_RENDERERS = {
    "orders": _render_orders,
    "status": _render_status,
    "history": _render_history,
    "report": _render_report,
    "asset": _render_asset,
}


async def list_view_callback(update, context):
    query = update.callback_query
    parts = query.data.split("|")
    kind = parts[1] if len(parts) > 1 else None
    token = parts[2] if len(parts) > 2 else None
    action = parts[3] if len(parts) > 3 else None
    extra = parts[4] if len(parts) > 4 else None

    user_id = str(query.from_user.id)
    entry, error = main.peek_list_view(token, user_id)
    if error:
        await query.answer()
        try:
            await query.edit_message_text(f"⚠️ {error}")
        except BadRequest:
            pass
        return

    await query.answer()
    renderer = _RENDERERS.get(kind)
    if renderer is None:
        return
    text, markup = await renderer(entry, token, action, extra)
    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
