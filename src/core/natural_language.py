import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone


KST = timezone(timedelta(hours=9))
NL_UNMATCHED_LOG_PATH = os.getenv("NL_UNMATCHED_LOG_PATH", "data/nl_unmatched.jsonl")
NL_PREPROCESS_HIT_PATH = os.getenv("NL_PREPROCESS_HIT_PATH", "data/nl_preprocess_hits.json")
NL_UNMATCHED_LOG_MAX_LINES = 500

RSI_SPLIT_HINTS = ("거미줄", "분할", "나눠", "나누", "쪼개")
ORDER_STATUS_HINTS = (
    "주문대기",
    "대기중인주문",
    "대기중주문",
    "대기주문",
    "예약된주문",
    "예약주문",
    "추적중인주문",
    "추적중주문",
    "전략주문",
    "걸어둔주문",
)
OPEN_ORDER_HINTS = ("미체결", "오픈오더", "openorder", "openorders")
ORDER_CHANGE_HINTS = (
    "취소",
    "중지",
    "없애",
    "삭제",
    "사줘",
    "매수",
    "팔아",
    "매도",
    "설정해",
    "변경",
    "바꿔",
    "켜줘",
    "꺼줘",
)
ASSET_HINTS = ("잔고", "보유자산", "자산", "평가금액", "계좌현황")
PRICE_HINTS = ("시세", "가격", "현재가", "얼마")
HISTORY_HINTS = ("최근체결", "체결내역", "거래내역", "매매기록", "거래기록")
CONFIG_VIEW_HINTS = ("설정보여", "현재설정", "설정확인", "api등록상태", "자연어켜져")
HELP_HINTS = ("뭐할수", "사용법", "명령어", "도움말", "help")
AMBIGUOUS_VIEW_HINTS = ("봐줘", "보여줘", "확인해줘")
TICKER_ALIASES = {
    "비트": "BTC",
    "비트코인": "BTC",
    "이더": "ETH",
    "이더리움": "ETH",
    "리플": "XRP",
    "삼성전자": "005930",
}


def _extract_rsi_range_from_text(text):
    match = re.search(r"rsi\s*(\d+(?:\.\d+)?)\s*(?:~|-|부터|에서|to)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if not match:
        return None
    start = float(match.group(1))
    end = float(match.group(2))
    if not (0 <= start <= 100 and 0 <= end <= 100 and start <= end):
        return None
    return f"{start:g}-{end:g}"


def _extract_krw_amount_from_text(text):
    word_amounts = {
        "백만원": 1_000_000,
        "천만원": 10_000_000,
        "일억원": 100_000_000,
        "일억": 100_000_000,
    }
    for word, amount in word_amounts.items():
        if word in text:
            return amount

    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(억|만|천)(?:\s*원)?|(\d+(?:\.\d+)?)\s*원", text):
        if match.group(1):
            value = float(match.group(1))
            suffix = match.group(2)
            multiplier = {"억": 100_000_000, "만": 10_000, "천": 1_000}[suffix]
            return int(value * multiplier)
        return int(float(match.group(3)))
    return None


def _extract_split_count_from_text(text):
    match = re.search(r"(\d+)\s*(?:개|분할|번)", text)
    return int(match.group(1)) if match else None


def _extract_exchange_from_text(text):
    lowered = text.lower()
    if "빗썸" in lowered or "bithumb" in lowered:
        return "bithumb"
    if "업비트" in lowered or "upbit" in lowered:
        return "upbit"
    if "한투" in lowered or "한국투자" in lowered or "kis" in lowered:
        return "kis"
    return None


def _compact_text(text):
    return re.sub(r"\s+", "", str(text).lower())


def _extract_ticker_from_text(text):
    stock_match = re.search(r"\b(\d{6})\b", text)
    if stock_match:
        return stock_match.group(1)
    compact = _compact_text(text)
    for label, ticker in TICKER_ALIASES.items():
        if label in compact:
            return ticker
    for match in re.finditer(r"[A-Za-z]{2,10}", text):
        token = match.group(0).upper()
        if token not in {"RSI", "KRW", "UPBIT", "BITHUMB", "KIS"}:
            return token.replace("KRW-", "")
    return None


def _looks_like_rsi_split_request(text):
    lowered = text.lower()
    return "rsi" in lowered and any(hint in text for hint in RSI_SPLIT_HINTS)


def _looks_like_strategy_status_request(text):
    compact = _compact_text(text)
    if any(hint in compact for hint in OPEN_ORDER_HINTS):
        return False
    return any(hint in compact for hint in ORDER_STATUS_HINTS)


def _contains_any(compact_text, hints):
    return any(hint in compact_text for hint in hints)


def _has_order_change_hint(text):
    return _contains_any(_compact_text(text), ORDER_CHANGE_HINTS)


def _intent_with_optional_exchange(action, text):
    intent = {"action": action}
    exchange = _extract_exchange_from_text(text)
    if exchange:
        intent["exchange"] = exchange
    return intent


def preprocess_natural_language_intent(text, user):
    compact = _compact_text(text)
    if not compact or _has_order_change_hint(text):
        return None

    if _contains_any(compact, HELP_HINTS):
        return {"action": "help"}
    if _contains_any(compact, CONFIG_VIEW_HINTS):
        return {"action": "config_view"}
    if _looks_like_strategy_status_request(text) or "자동매매상태" in compact or "전략상태" in compact:
        return _intent_with_optional_exchange("status", text)
    if _contains_any(compact, OPEN_ORDER_HINTS) or "실제걸린주문" in compact or "거래소에걸" in compact:
        return _intent_with_optional_exchange("orders", text)
    if _contains_any(compact, ASSET_HINTS):
        return _intent_with_optional_exchange("asset", text)
    if _contains_any(compact, HISTORY_HINTS):
        intent = _intent_with_optional_exchange("history", text)
        ticker = _extract_ticker_from_text(text)
        if ticker:
            intent["ticker"] = ticker
        return intent
    if _contains_any(compact, PRICE_HINTS):
        ticker = _extract_ticker_from_text(text)
        if ticker:
            intent = _intent_with_optional_exchange("price", text)
            intent["ticker"] = ticker
            return intent
    ticker = _extract_ticker_from_text(text)
    if ticker and _contains_any(compact, AMBIGUOUS_VIEW_HINTS):
        return {
            "action": "clarify",
            "ticker": ticker,
            "question": "시세, 보유 자산, 전략 상태 중 무엇을 볼까요? 예: `BTC 시세`, `자산 보여줘`, `전략 상태`",
        }
    return None


def normalize_natural_language_intent(text, intent, user):
    intent = dict(intent or {})
    rsi_range = intent.get("buy_rsi_range") or _extract_rsi_range_from_text(text)
    amount = intent.get("amount_krw") or _extract_krw_amount_from_text(text)
    count = intent.get("count") or _extract_split_count_from_text(text)
    ticker = intent.get("ticker") or _extract_ticker_from_text(text)
    exchange = intent.get("exchange") or _extract_exchange_from_text(text) or user.get("preferences", {}).get("default_exchange", "upbit")

    if _looks_like_strategy_status_request(text):
        return {**intent, "action": "status", "question": None}

    if _looks_like_rsi_split_request(text) and rsi_range and amount and count and ticker:
        return {
            **intent,
            "action": "rsitrade",
            "exchange": exchange,
            "ticker": ticker,
            "price": None,
            "volume": None,
            "amount_krw": amount,
            "start_price": None,
            "end_price": None,
            "count": count,
            "buy_rsi_range": rsi_range,
            "sell_rsi_range": intent.get("sell_rsi_range"),
            "config_key": None,
            "config_value": None,
            "question": None,
        }
    return intent


def sanitize_natural_language_log_text(text):
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    cleaned = re.sub(r"[A-Za-z0-9_-]{20,}", "<TOKEN>", cleaned)
    cleaned = re.sub(r"(?<!\d)\d{6}(?!\d)", "<STOCK>", cleaned)
    cleaned = re.sub(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", "<NUMBER>", cleaned)
    return cleaned[:160]


def _trim_jsonl_file(path, max_lines):
    if max_lines <= 0 or not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[-max_lines:])
    except Exception as e:
        print(f"NL log trim error: {e}")


def append_natural_language_log(text, llm_intent, final_intent, path=NL_UNMATCHED_LOG_PATH):
    row = {
        "ts": datetime.now(KST).isoformat(timespec="seconds"),
        "text_norm": sanitize_natural_language_log_text(text),
        "llm_action": (llm_intent or {}).get("action"),
        "final_action": (final_intent or {}).get("action"),
    }
    try:
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.chmod(path, 0o600)
        _trim_jsonl_file(path, NL_UNMATCHED_LOG_MAX_LINES)
    except Exception as e:
        print(f"NL log append error: {e}")


def append_preprocess_hit(intent, path=NL_PREPROCESS_HIT_PATH):
    action = (intent or {}).get("action")
    if not action:
        return
    stats = read_preprocess_hit_stats(path)
    stats[action] = int(stats.get(action, 0)) + 1
    try:
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        os.chmod(path, 0o600)
    except Exception as e:
        print(f"NL hit append error: {e}")


def read_preprocess_hit_stats(path=NL_PREPROCESS_HIT_PATH):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {str(key): int(value) for key, value in raw.items()}
    except Exception:
        return {}


def _counter_dict(counter):
    return dict(sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))


def read_natural_language_log_stats(path=NL_UNMATCHED_LOG_PATH, limit=10):
    grouped = {}
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            text_norm = row.get("text_norm")
            if not text_norm:
                continue
            bucket = grouped.setdefault(
                text_norm,
                {"count": 0, "llm_actions": Counter(), "final_actions": Counter()},
            )
            bucket["count"] += 1
            bucket["llm_actions"][str(row.get("llm_action"))] += 1
            bucket["final_actions"][str(row.get("final_action"))] += 1

    rows = []
    for text_norm, bucket in grouped.items():
        rows.append(
            {
                "text_norm": text_norm,
                "count": bucket["count"],
                "llm_actions": _counter_dict(bucket["llm_actions"]),
                "final_actions": _counter_dict(bucket["final_actions"]),
            }
        )
    return sorted(rows, key=lambda row: (-row["count"], row["text_norm"]))[:limit]


def read_recent_natural_language_logs(path=NL_UNMATCHED_LOG_PATH, limit=20):
    limit = max(1, min(int(limit), 50))
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("text_norm"):
                rows.append(row)
    return rows[-limit:]


def clear_natural_language_logs(log_path=NL_UNMATCHED_LOG_PATH, hit_path=NL_PREPROCESS_HIT_PATH):
    for path, empty in ((log_path, ""), (hit_path, "{}\n")):
        try:
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(empty)
            os.chmod(path, 0o600)
        except Exception as e:
            print(f"NL log clear error: {e}")
