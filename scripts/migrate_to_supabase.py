"""
One-time migration: JSON/JSONL files → Supabase tables.

Run from repo root:
    python scripts/migrate_to_supabase.py

Prerequisites:
    - SUPABASE_URL and SUPABASE_SERVICE_KEY set in config/.env
    - shared/schema.sql already applied in Supabase SQL Editor
"""
import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv("config/.env")
sys.path.insert(0, "src")

from core.db import get_db  # noqa: E402


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
    if rows:
        get_db().table("users").upsert(rows).execute()
    print(f"[ok] users: {len(rows)} rows migrated")


def migrate_orders(path="data/orders.json"):
    if not os.path.exists(path):
        print(f"[skip] {path} not found")
        return
    with open(path, "r", encoding="utf-8") as f:
        orders = json.load(f)
    if orders:
        get_db().table("orders").upsert(orders).execute()
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
    if rows:
        # Insert in chunks of 500
        for i in range(0, len(rows), 500):
            get_db().table("trade_logs").insert(rows[i:i + 500]).execute()
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
    if rows:
        for i in range(0, len(rows), 500):
            get_db().table("operational_events").insert(rows[i:i + 500]).execute()
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
    if rows:
        for i in range(0, len(rows), 500):
            get_db().table("nl_logs").insert(rows[i:i + 500]).execute()
    print(f"[ok] nl_logs: {len(rows)} rows migrated")


if __name__ == "__main__":
    print("Starting migration to Supabase...")
    migrate_users()
    migrate_orders()
    migrate_trade_logs()
    migrate_operational_events()
    migrate_nl_logs()
    print("Migration complete.")
