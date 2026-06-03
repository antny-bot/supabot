import time

from core.db import get_db, is_db_available


def log_command(user_id: str, command: str, source: str = "direct",
                exchange: str | None = None, ticker: str | None = None) -> None:
    if not is_db_available():
        return
    row: dict = {
        "user_id": str(user_id),
        "command": command,
        "source": source,
        "created_at": time.time(),
    }
    if exchange:
        row["exchange"] = exchange
    if ticker:
        row["ticker"] = ticker
    try:
        get_db().table("command_logs").insert(row).execute()
    except Exception:
        pass
