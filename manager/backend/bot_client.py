import os
import hmac
import hashlib
import time
import json
import requests

def _send_signed_request(endpoint: str, payload: dict) -> requests.Response:
    bot_url = os.environ.get("BOT_NOTIFY_URL", "").rstrip("/")
    api_key = os.environ.get("MANAGER_API_KEY", "")
    if not bot_url or not api_key:
        raise ValueError("BOT_NOTIFY_URL 또는 MANAGER_API_KEY 환경변수가 설정되지 않았습니다.")
        
    url = f"{bot_url}{endpoint}"
    body_bytes = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))
    
    # HMAC-SHA256 서명 생성
    msg = timestamp.encode("utf-8") + body_bytes
    sig = hmac.new(api_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    
    headers = {
        "X-API-Key": api_key,  # 하위 호환성 유지
        "X-Timestamp": timestamp,
        "X-Signature": sig,
        "Content-Type": "application/json"
    }
    
    return requests.post(url, data=body_bytes, headers=headers, timeout=10)

def notify(chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    """Send Telegram message via the bot's /internal/notify endpoint with signature."""
    try:
        resp = _send_signed_request(
            "/internal/notify",
            {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        )
        return resp.ok
    except Exception:
        return False

def execute_grid(user_id: str, exchange: str, ticker: str, start_price: float, end_price: float, count: int, budget: float) -> tuple[bool, str]:
    """Send Grid trade execution request via the bot's /internal/execute_grid endpoint with signature."""
    try:
        resp = _send_signed_request(
            "/internal/execute_grid",
            {
                "user_id": user_id,
                "exchange": exchange,
                "ticker": ticker,
                "start_price": start_price,
                "end_price": end_price,
                "count": count,
                "budget": budget,
            }
        )
        if resp.ok:
            return True, "ok"
        return False, resp.text or f"HTTP 에러 {resp.status_code}"
    except Exception as e:
        return False, str(e)

def execute_sgrid(user_id: str, exchange: str, ticker: str, start_price: float, end_price: float, count: int, total_volume: float) -> tuple[bool, str]:
    """Send sGrid (split sell) execution request via the bot's /internal/execute_sgrid endpoint."""
    try:
        resp = _send_signed_request(
            "/internal/execute_sgrid",
            {
                "user_id": user_id,
                "exchange": exchange,
                "ticker": ticker,
                "start_price": start_price,
                "end_price": end_price,
                "count": count,
                "total_volume": total_volume,
            }
        )
        if resp.ok:
            return True, "ok"
        return False, resp.text or f"HTTP 에러 {resp.status_code}"
    except Exception as e:
        return False, str(e)

def cancel_order(user_id: str, exchange: str, uuid: str, ticker: str) -> tuple[bool, str]:
    """Cancel a single order via the bot's /internal/cancel_order endpoint."""
    try:
        resp = _send_signed_request(
            "/internal/cancel_order",
            {"user_id": user_id, "exchange": exchange, "uuid": uuid, "ticker": ticker},
        )
        if resp.ok:
            data = resp.json()
            return data.get("ok", False), ""
        return False, resp.text or f"HTTP 에러 {resp.status_code}"
    except Exception as e:
        return False, str(e)

def sync_order(user_id: str, exchange: str, uuid: str, ticker: str) -> tuple[bool, str, dict | None]:
    """Sync a single order's status from the exchange via the bot's /internal/sync_order endpoint."""
    try:
        resp = _send_signed_request(
            "/internal/sync_order",
            {"user_id": user_id, "exchange": exchange, "uuid": uuid, "ticker": ticker},
        )
        if resp.ok:
            data = resp.json()
            return data.get("ok", False), data.get("error", ""), data
        return False, resp.text or f"HTTP 에러 {resp.status_code}", None
    except Exception as e:
        return False, str(e), None

def force_update_order(uuid: str, state: str, filled_volume: float) -> tuple[bool, str]:
    """Force update a single order's status and filled volume via the bot's /internal/force_update_order endpoint."""
    try:
        resp = _send_signed_request(
            "/internal/force_update_order",
            {"uuid": uuid, "state": state, "filled_volume": filled_volume},
        )
        if resp.ok:
            data = resp.json()
            return data.get("ok", False), ""
        return False, resp.text or f"HTTP 에러 {resp.status_code}"
    except Exception as e:
        return False, str(e)

def get_prices(requests_: list[dict]) -> list[dict]:
    """봇 프로세스에 있는 거래소 자격증명을 통해 실시간 현재가를 조회한다.

    requests_: [{"user_id": str, "exchange": str, "ticker": str}, ...]
    반환: [{"user_id", "exchange", "ticker", "price"}, ...] (실패 시 빈 리스트)
    """
    if not requests_:
        return []
    try:
        resp = _send_signed_request("/internal/get_prices", {"requests": requests_})
        if resp.ok:
            return resp.json().get("prices", [])
        return []
    except Exception:
        return []

def execute_rsitrade(user_id: str, exchange: str, ticker: str, buy_rsi_range: str, sell_rsi_range: str, count: int, budget: float, weighted: bool = False) -> tuple[bool, str]:
    """Send RSITrade execution request via the bot's /internal/execute_rsitrade endpoint with signature."""
    try:
        resp = _send_signed_request(
            "/internal/execute_rsitrade",
            {
                "user_id": user_id,
                "exchange": exchange,
                "ticker": ticker,
                "buy_rsi_range": buy_rsi_range,
                "sell_rsi_range": sell_rsi_range,
                "count": count,
                "budget": budget,
                "weighted": weighted,
            }
        )
        if resp.ok:
            return True, "ok"
        return False, resp.text or f"HTTP 에러 {resp.status_code}"
    except Exception as e:
        return False, str(e)
