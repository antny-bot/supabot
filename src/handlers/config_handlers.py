"""/config — API 키·환경설정 대화형 핸들러 (ConversationHandler).

ConversationHandler 상태 상수(SET_EXCHANGE 등)는 main.py 소유로 남아있고
여기서는 main.<상수>로 참조한다.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import main
from main import check_details_help
from core.parsers import POLL_INTERVAL_KEYS, parse_config_value, validate_config_update
from core.formatters import build_config_view, format_config_value
from core.operational_events import append_operational_event


# --- /config: API 키 설정 대화형 핸들러 ---
async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_details_help(update, "config"):
        return ConversationHandler.END

    user_id = str(update.effective_chat.id)
    user = main.user_manager.get_user(user_id)

    if not user or not user["is_active"]:
        await update.message.reply_text("👋 먼저 /start 명령어로 등록 및 승인을 완료해 주세요.")
        return ConversationHandler.END

    args = context.args
    if args and args[0].lower() in ["-v", "-view", "--view"]:
        await update.message.reply_text(
            build_config_view(user, active_order_count=len(main.order_manager.orders)),
            parse_mode="HTML",
        )
        return ConversationHandler.END

    # Shorthand: /config <key> <value>  (equivalent to /config set <key> <value>)
    if args and len(args) >= 2 and args[0].lower() not in ("-v", "-view", "--view", "set"):
        args = ["set"] + list(args)
        context.args = args

    if args and args[0].lower() == "set":
        if len(args) < 3:
            await update.message.reply_text("⚠️ 사용법: /config set [항목] [값]\n예: /config set rsi_budget_krw 100만")
            return ConversationHandler.END
        key = args[1].strip().lower()
        raw_value = " ".join(args[2:]).strip()
        if key in POLL_INTERVAL_KEYS:
            await update.message.reply_text("❌ 폴링 설정은 config/.env에서 직접 변경 후 재시작해주세요.")
            return ConversationHandler.END
        try:
            value = parse_config_value(key, raw_value)
            validate_config_update(user, key, value)
        except (ValueError, TypeError) as e:
            await update.message.reply_text(f"❌ 설정 저장 실패: {e}")
            return ConversationHandler.END
        main.user_manager.update_preference(user_id, key, value)
        formatted = format_config_value(key, value)
        await update.message.reply_text(f"✅ {key} 설정을 {formatted}(으)로 저장했습니다.")
        return ConversationHandler.END

    if args:
        await update.message.reply_text("⚠️ 알 수 없는 /config 옵션입니다. 사용법은 /config -h를 확인하세요.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Upbit", callback_data="conf_upbit"),
         InlineKeyboardButton("Bithumb", callback_data="conf_bithumb")],
        [InlineKeyboardButton("한국투자증권", callback_data="conf_kis")],
        [InlineKeyboardButton("Gemini API 키", callback_data="conf_gemini")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        build_config_view(user, active_order_count=len(main.order_manager.orders)),
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    return main.SET_EXCHANGE


async def config_exchange_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    exchange = query.data.split("_")[1]
    if exchange == "gemini":
        await query.edit_message_text("🔑 Gemini API 키를 입력해 주세요. 입력 메시지는 저장 후 삭제됩니다.")
        return main.SET_GEMINI_KEY
    context.user_data["temp_exchange"] = exchange
    if exchange == "kis":
        await query.edit_message_text("🔑 한국투자증권 App Key를 입력해 주세요.")
        return main.SET_KIS_APP
    await query.edit_message_text(f"🔑 {exchange.upper()}의 Access Key를 입력해 주세요.")
    return main.SET_ACCESS


async def set_gemini_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    api_key = update.message.text.strip()
    try: await update.message.delete()
    except: pass
    if not api_key:
        await update.message.reply_text("⚠️ Gemini API 키가 비어 있습니다. /config에서 다시 시도해 주세요.")
        return ConversationHandler.END
    try:
        main.user_manager.update_gemini_api_key(user_id, api_key)
    except ValueError as e:
        await update.message.reply_text(f"❌ 보안 키 설정 오류: {e}")
        return ConversationHandler.END
    await update.message.reply_text("✅ Gemini API 키를 저장했습니다. /config set llm_enabled on으로 자연어 기능을 켤 수 있습니다.")
    return ConversationHandler.END


async def set_access_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["temp_access"] = update.message.text
    try: await update.message.delete()
    except: pass
    await update.message.reply_text("🔒 이제 Secret Key를 입력해 주세요.")
    return main.SET_SECRET


async def set_secret_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    exchange = context.user_data.get("temp_exchange")
    access = context.user_data.get("temp_access")
    secret = update.message.text

    try: await update.message.delete()
    except: pass

    try:
        main.user_manager.update_exchange_keys(user_id, exchange, access, secret)
    except ValueError as e:
        await update.message.reply_text(f"❌ 보안 키 설정 오류: {e}")
        return ConversationHandler.END
    status_msg = await update.message.reply_text(f"⏳ {exchange.upper()} API 키 유효성을 검증하는 중...")

    is_valid = await main.exchange_adapter.validate_api_keys(user_id, exchange)
    main.user_manager.update_api_validation_status(user_id, exchange, is_valid)
    if is_valid:
        await status_msg.edit_text(f"✅ {exchange.upper()} API 키 설정이 완료되었습니다!")
    else:
        append_operational_event("warning", "api_validation", "API key validation failed", exchange)
        await status_msg.edit_text(f"⚠️ {exchange.upper()} API 키 검증에 실패했습니다. 키를 다시 확인해 주세요.")

    return ConversationHandler.END


async def set_kis_app_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["temp_kis_app"] = update.message.text.strip()
    try: await update.message.delete()
    except: pass
    await update.message.reply_text("🔒 한국투자증권 App Secret을 입력해 주세요.")
    return main.SET_KIS_SECRET


async def set_kis_secret_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["temp_kis_secret"] = update.message.text.strip()
    try: await update.message.delete()
    except: pass
    await update.message.reply_text("🏦 계좌번호 앞 8자리를 입력해 주세요. 예: 12345678")
    return main.SET_KIS_ACCOUNT


async def set_kis_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    account_no = update.message.text.strip().replace("-", "")
    if not account_no.isdigit() or len(account_no) != 8:
        await update.message.reply_text("⚠️ 계좌번호 앞 8자리를 숫자로 입력해 주세요. 예: 12345678")
        return main.SET_KIS_ACCOUNT
    context.user_data["temp_kis_account"] = account_no
    try: await update.message.delete()
    except: pass
    await update.message.reply_text("📌 계좌상품코드 2자리를 입력해 주세요. 국내주식 종합계좌는 보통 01입니다.")
    return main.SET_KIS_PRODUCT


async def set_kis_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product_code = update.message.text.strip()
    if not product_code.isdigit() or len(product_code) != 2:
        await update.message.reply_text("⚠️ 계좌상품코드는 숫자 2자리여야 합니다. 예: 01")
        return main.SET_KIS_PRODUCT
    context.user_data["temp_kis_product"] = product_code
    await update.message.reply_text("🧪 투자 환경을 입력해 주세요: paper(모의) 또는 real(실전)")
    return main.SET_KIS_ENV


async def set_kis_env(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    raw_env = update.message.text.strip().lower()
    if raw_env in ["paper", "demo", "mock", "모의", "모의투자"]:
        env = "paper"
    elif raw_env in ["real", "prod", "실전", "실전투자"]:
        env = "real"
    else:
        await update.message.reply_text("⚠️ 투자 환경은 paper(모의) 또는 real(실전)로 입력해 주세요.")
        return main.SET_KIS_ENV

    app_key = context.user_data.get("temp_kis_app", "")
    app_secret = context.user_data.get("temp_kis_secret", "")
    account_no = context.user_data.get("temp_kis_account", "")
    product_code = context.user_data.get("temp_kis_product", "01")

    try:
        main.user_manager.update_kis_keys(user_id, app_key, app_secret, account_no, product_code, env)
    except ValueError as e:
        await update.message.reply_text(f"❌ 보안 키 설정 오류: {e}")
        return ConversationHandler.END
    status_msg = await update.message.reply_text("⏳ 한국투자증권 API 설정을 검증하는 중...")
    is_valid = await main.exchange_adapter.validate_api_keys(user_id, "kis")
    main.user_manager.update_api_validation_status(user_id, "kis", is_valid)
    env_name = "실전" if env == "real" else "모의"
    if is_valid:
        await status_msg.edit_text(f"✅ 한국투자증권 API 설정이 완료되었습니다. ({env_name})")
    else:
        append_operational_event("warning", "api_validation", "KIS API validation failed", env_name)
        await status_msg.edit_text("⚠️ 한국투자증권 API 검증에 실패했습니다. App Key, App Secret, 계좌번호, 환경을 확인해 주세요.")

    for key in ["temp_kis_app", "temp_kis_secret", "temp_kis_account", "temp_kis_product"]:
        context.user_data.pop(key, None)
    return ConversationHandler.END


async def cancel_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ 설정이 취소되었습니다.")
    return ConversationHandler.END
