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
