import os

import requests


def notify(chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    """Send Telegram message via the bot's /internal/notify endpoint."""
    bot_url = os.environ.get("BOT_NOTIFY_URL", "").rstrip("/")
    api_key = os.environ.get("MANAGER_API_KEY", "")
    if not bot_url or not api_key:
        return False
    try:
        resp = requests.post(
            f"{bot_url}/internal/notify",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=10,
        )
        return resp.ok
    except Exception:
        return False


def execute_grid(user_id: str, exchange: str, ticker: str, start_price: float, end_price: float, count: int, budget: float) -> tuple[bool, str]:
    """Send Grid trade execution request via the bot's /internal/execute_grid endpoint."""
    bot_url = os.environ.get("BOT_NOTIFY_URL", "").rstrip("/")
    api_key = os.environ.get("MANAGER_API_KEY", "")
    if not bot_url or not api_key:
        return False, "BOT_NOTIFY_URL 또는 MANAGER_API_KEY 환경변수가 설정되지 않았습니다."
    try:
        resp = requests.post(
            f"{bot_url}/internal/execute_grid",
            json={
                "user_id": user_id,
                "exchange": exchange,
                "ticker": ticker,
                "start_price": start_price,
                "end_price": end_price,
                "count": count,
                "budget": budget,
            },
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.ok:
            return True, "ok"
        return False, resp.text or f"HTTP 에러 {resp.status_code}"
    except Exception as e:
        return False, str(e)


def execute_rsitrade(user_id: str, exchange: str, ticker: str, buy_rsi_range: str, sell_rsi_range: str, count: int, budget: float) -> tuple[bool, str]:
    """Send RSITrade execution request via the bot's /internal/execute_rsitrade endpoint."""
    bot_url = os.environ.get("BOT_NOTIFY_URL", "").rstrip("/")
    api_key = os.environ.get("MANAGER_API_KEY", "")
    if not bot_url or not api_key:
        return False, "BOT_NOTIFY_URL 또는 MANAGER_API_KEY 환경변수가 설정되지 않았습니다."
    try:
        resp = requests.post(
            f"{bot_url}/internal/execute_rsitrade",
            json={
                "user_id": user_id,
                "exchange": exchange,
                "ticker": ticker,
                "buy_rsi_range": buy_rsi_range,
                "sell_rsi_range": sell_rsi_range,
                "count": count,
                "budget": budget,
            },
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=10,
        )
        if resp.ok:
            return True, "ok"
        return False, resp.text or f"HTTP 에러 {resp.status_code}"
    except Exception as e:
        return False, str(e)


