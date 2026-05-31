"""
One-time migration: JSON/JSONL files → Supabase tables.

Run from repo root:
    PYTHONPATH=src python scripts/migrate_to_supabase.py
"""
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv("config/.env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in config/.env")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def _upsert(table: str, rows: list) -> None:
    if not rows:
        return
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        resp = SESSION.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            json=chunk,
            timeout=60,
        )
        if not resp.ok:
            raise RuntimeError(f"{table} upsert failed [{resp.status_code}]: {resp.text[:200]}")


def migrate_users(path="data/users.json"):
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return
    with open(path, "r", encoding="utf-8") as f:
        users = json.load(f)
    rows = []
    for user_id, user in users.items():
        status = "active" if user.get("is_active") else "pending"
        rows.append({
            "user_id": user_id,
            "username": user.get("username", ""),
            "is_admin": bool(user.get("is_admin", False)),
            "status": status,
            "preferences": user.get("preferences") or {},
            "exchanges": user.get("exchanges") or {},
            "llm": user.get("llm") or {},
            "api_validation": user.get("api_validation") or {},
        })
    _upsert("users", rows)
    print(f"[ok] users: {len(rows)} rows migrated")


def migrate_orders(path="data/orders.json"):
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return
    with open(path, "r", encoding="utf-8") as f:
        orders = json.load(f)
    _upsert("orders", orders)
    print(f"[ok] orders: {len(orders)} rows migrated")


def migrate_trade_logs(path="data/trades.jsonl"):
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append({
                "user_id": str(rec.get("user_id", "")),
                "exchange": rec.get("exchange", ""),
                "ticker": rec.get("ticker", ""),
                "side": rec.get("side", ""),
                "price": float(rec.get("price", 0)),
                "volume": float(rec.get("volume", 0)),
                "strategy": rec.get("strategy", "manual"),
                "uuid": rec.get("uuid"),
                "executed_at": float(rec.get("ts", time.time())),
            })
    _upsert("trade_logs", rows)
    print(f"[ok] trade_logs: {len(rows)} rows migrated")


def migrate_operational_events(path="data/bot_events.jsonl"):
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append({
                "level": rec.get("level", "info"),
                "source": rec.get("source", ""),
                "message": rec.get("message", ""),
                "details": rec.get("details", ""),
                "created_at": rec.get("ts", ""),
            })
    _upsert("operational_events", rows)
    print(f"[ok] operational_events: {len(rows)} rows migrated")


def migrate_nl_logs(path="data/nl_unmatched.jsonl"):
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append({
                "raw_text": rec.get("text_norm", ""),
                "llm_action": rec.get("llm_action"),
                "final_action": rec.get("final_action"),
                "logged_at": time.time(),
            })
    _upsert("nl_logs", rows)
    print(f"[ok] nl_logs: {len(rows)} rows migrated")


if __name__ == "__main__":
    print("Starting migration to Supabase...")
    migrate_users()
    migrate_orders()
    migrate_trade_logs()
    migrate_operational_events()
    migrate_nl_logs()
    print("Migration complete.")
