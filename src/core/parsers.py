import re
from datetime import datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo

import holidays as _holidays_lib

KST = timezone(timedelta(hours=9))
US_ET = ZoneInfo("America/New_York")

_KR_HOLIDAYS = _holidays_lib.country_holidays("KR")
try:
    _US_MARKET_HOLIDAYS = _holidays_lib.financial_holidays("NYSE")
except NotImplementedError:
    _US_MARKET_HOLIDAYS = _holidays_lib.country_holidays("US")

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
    if text in ["toss", "토스", "토스증권", "tossinvest"]:
        return "toss"
    return None


def is_exchange_token(value, exchange):
    return normalize_exchange(value) == exchange


def exchange_display_name(exchange):
    return {
        "upbit": "UPBIT",
        "bithumb": "BITHUMB",
        "kis": "한국투자증권",
        "toss": "토스증권",
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
        elif exchange in ["kis", "toss"]:
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
    strategy = str(order.get("strategy", ""))
    return (
        strategy.startswith("rsitrade")
        or strategy.startswith("grid")
        or strategy.startswith("sgrid")
    )


def _as_tz_now(now, tz):
    if now is None:
        return datetime.now(tz).replace(tzinfo=None)
    if getattr(now, "tzinfo", None):
        return now.astimezone(tz).replace(tzinfo=None)
    return now


def _is_regular_session(now, tz, open_t, close_t, holiday_cal):
    local = _as_tz_now(now, tz)
    if local.weekday() >= 5 or local.date() in holiday_cal:
        return False
    return open_t <= local.time() <= close_t


def _next_regular_session(now, tz, open_t, close_t, holiday_cal):
    local = _as_tz_now(now, tz)
    if local.weekday() < 5 and local.date() not in holiday_cal and local.time() < open_t:
        return local.replace(hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0)
    next_day = local + timedelta(days=1)
    while next_day.weekday() >= 5 or next_day.date() in holiday_cal:
        next_day += timedelta(days=1)
    return next_day.replace(hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0)


def is_kis_regular_session(now=None):
    return _is_regular_session(now, KST, dt_time(9, 0), dt_time(15, 35), _KR_HOLIDAYS)


def next_kis_regular_session(now=None):
    return _next_regular_session(now, KST, dt_time(9, 0), dt_time(15, 35), _KR_HOLIDAYS)


def kis_next_check_timestamp(now=None):
    return next_kis_regular_session(now).replace(tzinfo=KST).timestamp()


def is_us_regular_session(now=None):
    return _is_regular_session(now, US_ET, dt_time(9, 30), dt_time(16, 0), _US_MARKET_HOLIDAYS)


def next_us_regular_session(now=None):
    return _next_regular_session(now, US_ET, dt_time(9, 30), dt_time(16, 0), _US_MARKET_HOLIDAYS)


def us_next_check_timestamp(now=None):
    return next_us_regular_session(now).replace(tzinfo=US_ET).timestamp()


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


def get_dca_weights(count: int) -> list:
    """선형 역수 가중치: index 0(낮은 RSI)에 가장 높은 비중."""
    total = count * (count + 1) / 2
    return [(count - i) / total for i in range(count)]


def resolve_linked_rsi_target(linked_to):
    if linked_to is None:
        return None
    text = str(linked_to)
    if "-" in text:
        start, _ = parse_rsi_range(text)
        return start
    return float(text)


def is_us_stock_ticker(exchange, ticker):
    """토스증권 해외(미국) 주식 종목코드 여부 (알파벳 티커, 예: AAPL). KIS는 해외주문 미지원."""
    text = str(ticker or "").replace("KRW-", "")
    return exchange == "toss" and text.isalpha()


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
            raise ValueError("기본 거래소는 upbit, bithumb, kis, toss, 업비트, 빗썸, 한투, 토스증권 중 하나여야 합니다.")
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
    if key == "max_open_exposure_krw":
        return parse_optional_krw(raw_value)
    if key == "stop_loss_pct":
        text = str(raw_value).strip().lower()
        if text in ["off", "none", "unset", "미설정", "해제", "0"]:
            return None
        pct = float(text.rstrip("%"))
        if not 0 < pct <= 100:
            raise ValueError("손절 비율은 0 초과 100 이하의 숫자여야 합니다 (예: 3 또는 3%).")
        return pct
    if key in ["quiet_hours_start", "quiet_hours_end"]:
        text = str(raw_value).strip().lower()
        if text in ["off", "none", "unset", "미설정", "해제"]:
            return None
        if not re.match(r"^\d{2}:\d{2}$", text):
            raise ValueError("시간은 HH:MM 형식 (24시간) 또는 off로 입력하세요. 예: 22:00")
        h, m = text.split(":")
        if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
            raise ValueError("유효하지 않은 시간입니다. 예: 22:00, 08:30")
        return text
    if key in POLL_INTERVAL_KEYS:
        try:
            val = int(raw_value)
        except (ValueError, TypeError):
            raise ValueError("폴링 주기는 정수(초)로 입력해야 합니다.")
        if val < 10:
            raise ValueError("폴링 주기는 최소 10초 이상이어야 합니다.")
        return val
    raise ValueError("지원하지 않는 설정 항목입니다. `/config -h`로 항목 목록을 확인하세요.")


def validate_max_order(user, order_krw, is_usd=False):
    """max_order_krw는 원화 기준 캡. USD(토스 해외주식) 주문은 통화가 달라 비교할 수 없으므로 검증을 건너뜀."""
    if is_usd:
        return True, None
    max_order_krw = user.get("preferences", {}).get("max_order_krw")
    if max_order_krw is None:
        return True, None
    if order_krw > float(max_order_krw):
        return False, f"❌ 단일 주문 금액 {order_krw:,.0f}원이 설정된 최대 주문 금액 {float(max_order_krw):,.0f}원을 초과합니다."
    return True, None


def compute_open_exposure_krw(orders):
    """미체결 원화 주문들의 잔여 노출 합계(price × 미체결수량). USD(해외주식) 주문은 제외.

    토스 해외주식 등 통화가 KRW가 아닌 주문은 max_open_exposure_krw(원화 기준 캡)와
    비교할 수 없으므로 합산에서 제외한다.
    """
    total = 0.0
    for o in orders:
        if is_us_stock_ticker(o.get("exchange"), o.get("ticker")):
            continue
        remaining = max(float(o.get("volume", 0)) - float(o.get("filled_volume", 0)), 0)
        total += float(o.get("price", 0)) * remaining
    return total


def validate_total_exposure(user, current_open_krw, new_order_krw, is_usd=False):
    """신규 주문 추가 시 총 미체결 노출이 max_open_exposure_krw를 초과하는지 검증.

    max_order_krw와 동일하게 USD 주문은 통화가 달라 검증을 건너뛰고, 캡 미설정(None)이면 통과.
    """
    if is_usd:
        return True, None
    cap = user.get("preferences", {}).get("max_open_exposure_krw")
    if cap is None:
        return True, None
    projected = float(current_open_krw) + float(new_order_krw)
    if projected > float(cap):
        return False, (
            f"❌ 총 미체결 노출 {projected:,.0f}원이 설정된 최대 노출 한도 "
            f"{float(cap):,.0f}원을 초과합니다. (현재 미체결 {float(current_open_krw):,.0f}원)"
        )
    return True, None


def validate_config_update(user, key, value):
    if key == "llm_enabled" and value and not has_gemini_key(user):
        raise ValueError("Gemini API 키를 먼저 /config에서 설정해야 llm_enabled를 켤 수 있습니다.")
    return True
