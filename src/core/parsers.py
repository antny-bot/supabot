from datetime import datetime, time as dt_time, timedelta, timezone

KST = timezone(timedelta(hours=9))

RSI_INTERVAL_ALIASES = {
    "day": "day",
    "daily": "day",
    "d": "day",
    "1d": "day",
}
RSI_MINUTE_INTERVALS = {"1", "3", "5", "10", "15", "30", "60", "240"}
POLL_INTERVAL_KEYS = {"poll_active_interval", "poll_no_order_interval", "signal_analysis_interval"}
ADMIN_ONLY_KEYS = POLL_INTERVAL_KEYS


def normalize_exchange(value):
    text = str(value).strip().lower()
    if text in ["upbit", "업비트"]:
        return "upbit"
    if text in ["bithumb", "빗썸"]:
        return "bithumb"
    if text in ["kis", "한투", "한국투자", "한국투자증권"]:
        return "kis"
    return None


def is_exchange_token(value, exchange):
    return normalize_exchange(value) == exchange


def exchange_display_name(exchange):
    return {
        "upbit": "UPBIT",
        "bithumb": "BITHUMB",
        "kis": "한국투자증권",
    }.get(exchange, exchange.upper())


def parse_exchange_and_ticker(args, default_exchange):
    if not args:
        return default_exchange, None

    exchange = default_exchange
    raw_ticker = None

    arg0_exchange = normalize_exchange(args[0])
    if arg0_exchange:
        exchange = arg0_exchange
        raw_ticker = args[1].upper() if len(args) > 1 else None
    else:
        raw_ticker = args[0].upper()

    if raw_ticker:
        if exchange in ["upbit", "bithumb"] and "-" not in raw_ticker:
            raw_ticker = f"KRW-{raw_ticker}"
        elif exchange == "kis":
            raw_ticker = raw_ticker.replace("KRW-", "")

    return exchange, raw_ticker


def parse_number(value):
    text = str(value).replace(",", "").strip()
    multipliers = [("억", 100000000), ("만", 10000), ("천", 1000)]
    for suffix, multiplier in multipliers:
        if text.endswith(suffix):
            return float(text[:-len(suffix)]) * multiplier
    return float(text)


def parse_rsi_range(rsi_range):
    start, end = map(float, str(rsi_range).split("-"))
    if not (0 <= start <= 100 and 0 <= end <= 100 and start <= end):
        raise ValueError("RSI 범위는 0-100 사이의 오름차순이어야 합니다.")
    return start, end


def parse_optional_krw(value):
    if str(value).strip().lower() in ["off", "none", "unset", "미설정", "해제", "0"]:
        return None
    amount = parse_number(value)
    if amount <= 0:
        raise ValueError("금액은 0보다 커야 합니다.")
    return amount


def parse_rsi_interval(value):
    text = str(value).strip().lower()
    if text in RSI_INTERVAL_ALIASES:
        return RSI_INTERVAL_ALIASES[text]
    if text in RSI_MINUTE_INTERVALS:
        return text
    raise ValueError("RSI 캔들 기준은 day 또는 1,3,5,10,15,30,60,240 분봉 중 하나여야 합니다.")


def has_gemini_key(user):
    return bool(user.get("llm", {}).get("gemini_api_key"))


def get_user_rsi_interval(user):
    return user.get("preferences", {}).get("rsi_interval", "day")


def is_strategy_order(order):
    return (
        str(order.get("strategy", "")).startswith("rsitrade")
        or str(order.get("strategy", "")).startswith("grid")
    )


def _as_kst_now(now=None):
    if now is None:
        return datetime.now(KST).replace(tzinfo=None)
    if getattr(now, "tzinfo", None):
        return now.astimezone(KST).replace(tzinfo=None)
    return now


def is_kis_regular_session(now=None):
    now = _as_kst_now(now)
    if now.weekday() >= 5:
        return False
    return dt_time(9, 0) <= now.time() <= dt_time(15, 35)


def next_kis_regular_session(now=None):
    now = _as_kst_now(now)
    if now.weekday() < 5 and now.time() < dt_time(9, 0):
        return now.replace(hour=9, minute=0, second=0, microsecond=0)
    next_day = now + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    return next_day.replace(hour=9, minute=0, second=0, microsecond=0)


def kis_next_check_timestamp(now=None):
    return next_kis_regular_session(now).replace(tzinfo=KST).timestamp()


def _format_seconds(seconds: int) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}초"
    m, s = divmod(seconds, 60)
    return f"{m}분" if s == 0 else f"{m}분 {s}초"


def interpolate_range(start, end, index, count):
    if count <= 1:
        return start
    return start + ((end - start) / (count - 1) * index)


def resolve_linked_rsi_target(linked_to):
    if linked_to is None:
        return None
    text = str(linked_to)
    if "-" in text:
        start, _ = parse_rsi_range(text)
        return start
    return float(text)


def _volume_unit(ticker):
    text = str(ticker or "").replace("KRW-", "")
    return "주" if text.isdigit() else text


def _format_preview_volume(ticker, volume):
    unit = _volume_unit(ticker)
    if unit == "주":
        return f"{int(volume)}주"
    return f"{volume:.4f} {unit}"


def parse_config_value(key, raw_value):
    key = key.strip().lower()
    if key == "default_exchange":
        exchange = normalize_exchange(raw_value)
        if not exchange:
            raise ValueError("기본 거래소는 upbit, bithumb, kis, 업비트, 빗썸, 한투 중 하나여야 합니다.")
        return exchange
    if key == "asset_min_display_krw":
        amount = parse_number(raw_value)
        if amount < 0:
            raise ValueError("최소 표시 금액은 0 이상이어야 합니다.")
        return amount
    if key in ["rsi_buy_range", "rsi_sell_range"]:
        parse_rsi_range(raw_value)
        return str(raw_value)
    if key == "rsi_interval":
        return parse_rsi_interval(raw_value)
    if key == "rsi_order_count":
        count = int(raw_value)
        if count <= 0:
            raise ValueError("분할 주문 수는 1 이상이어야 합니다.")
        return count
    if key == "rsi_budget_krw":
        return parse_optional_krw(raw_value)
    if key == "signal_alerts":
        text = str(raw_value).strip().lower()
        if text in ["on", "true", "1", "yes", "y", "켜기"]:
            return True
        if text in ["off", "false", "0", "no", "n", "끄기"]:
            return False
        raise ValueError("signal_alerts 값은 on 또는 off여야 합니다.")
    if key == "llm_enabled":
        text = str(raw_value).strip().lower()
        if text in ["on", "true", "1", "yes", "y", "켜기"]:
            return True
        if text in ["off", "false", "0", "no", "n", "끄기"]:
            return False
        raise ValueError("llm_enabled 값은 on 또는 off여야 합니다.")
    if key == "llm_model":
        model = str(raw_value).strip()
        if not model.startswith("gemini-"):
            raise ValueError("llm_model은 gemini- 로 시작하는 모델명이어야 합니다.")
        return model
    if key == "signal_rsi_threshold":
        threshold = float(raw_value)
        if not 0 <= threshold <= 100:
            raise ValueError("RSI 기준은 0-100 사이여야 합니다.")
        return threshold
    if key == "signal_bb_alert":
        text = str(raw_value).strip().lower()
        if text in ["on", "true", "1", "yes", "y", "켜기"]:
            return True
        if text in ["off", "false", "0", "no", "n", "끄기"]:
            return False
        raise ValueError("signal_bb_alert 값은 on 또는 off여야 합니다.")
    if key == "max_order_krw":
        return parse_optional_krw(raw_value)
    if key == "stop_loss_pct":
        text = str(raw_value).strip().lower()
        if text in ["off", "none", "unset", "미설정", "해제", "0"]:
            return None
        pct = float(text.rstrip("%"))
        if not 0 < pct <= 100:
            raise ValueError("손절 비율은 0 초과 100 이하의 숫자여야 합니다 (예: 3 또는 3%).")
        return pct
    if key in POLL_INTERVAL_KEYS:
        try:
            val = int(raw_value)
        except (ValueError, TypeError):
            raise ValueError("폴링 주기는 정수(초)로 입력해야 합니다.")
        if val < 10:
            raise ValueError("폴링 주기는 최소 10초 이상이어야 합니다.")
        return val
    raise ValueError("지원하지 않는 설정 항목입니다. `/config -h`로 항목 목록을 확인하세요.")


def validate_max_order(user, order_krw):
    max_order_krw = user.get("preferences", {}).get("max_order_krw")
    if max_order_krw is None:
        return True, None
    if order_krw > float(max_order_krw):
        return False, f"❌ 단일 주문 금액 {order_krw:,.0f}원이 설정된 최대 주문 금액 {float(max_order_krw):,.0f}원을 초과합니다."
    return True, None


def validate_config_update(user, key, value):
    if key == "llm_enabled" and value and not has_gemini_key(user):
        raise ValueError("Gemini API 키를 먼저 /config에서 설정해야 llm_enabled를 켤 수 있습니다.")
    return True
