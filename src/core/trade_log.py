import json
import os
import time
from datetime import datetime, timedelta, timezone

from core.db import get_db, is_db_available

TRADE_LOG_PATH = os.getenv("TRADE_LOG_PATH", "data/trades.jsonl")
TRADE_LOG_MAX_LINES = 10_000

KST = timezone(timedelta(hours=9))


def append_trade(user_id, exchange, ticker, side, price, volume, strategy, uuid, path=TRADE_LOG_PATH):
    ts = time.time()
    record = {
        "ts": ts,
        "user_id": str(user_id),
        "exchange": exchange,
        "ticker": ticker,
        "side": side,
        "price": float(price),
        "volume": float(volume),
        "strategy": strategy,
        "uuid": uuid,
    }
    if is_db_available():
        try:
            get_db().table("trade_logs").insert({
                "user_id": str(user_id),
                "exchange": exchange,
                "ticker": ticker,
                "side": side,
                "price": float(price),
                "volume": float(volume),
                "strategy": strategy,
                "uuid": uuid,
                "executed_at": ts,
            }).execute()
        except Exception:
            pass
    try:
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        os.chmod(path, 0o600)
        _trim_trade_log(path)
    except Exception:
        pass


def _trim_trade_log(path):
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > TRADE_LOG_MAX_LINES:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[-TRADE_LOG_MAX_LINES:])
    except Exception:
        pass


def _period_cutoff_ts(period):
    now = datetime.now(KST)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    if period == "week":
        return (now - timedelta(days=7)).timestamp()
    if period == "month":
        return (now - timedelta(days=30)).timestamp()
    return 0.0


def read_trades(user_id, period="all", path=TRADE_LOG_PATH):
    cutoff = _period_cutoff_ts(period)
    if not os.path.exists(path):
        return []
    result = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("user_id") != str(user_id):
                continue
            if rec.get("ts", 0) < cutoff:
                continue
            result.append(rec)
    return result
