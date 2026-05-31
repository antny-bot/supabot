import json
import os
import re
from datetime import datetime, timedelta, timezone

from core.db import get_db, is_db_available

KST = timezone(timedelta(hours=9))
OPERATIONAL_EVENTS_PATH = os.getenv("OPERATIONAL_EVENTS_PATH", "data/bot_events.jsonl")
OPERATIONAL_EVENTS_MAX_LINES = 300


def sanitize_event_text(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"[A-Za-z0-9_-]{20,}", "<TOKEN>", text)
    text = re.sub(r"(?<!\d)\d{6,}(?!\d)", "<NUMBER>", text)
    text = re.sub(r"(key|secret|token|password)\s*[:=]\s*[^,\s]+", r"\1=<REDACTED>", text, flags=re.IGNORECASE)
    return text[:240]


def _trim_jsonl_file(path, max_lines):
    if max_lines <= 0 or not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines[-max_lines:])
            os.chmod(path, 0o600)
    except Exception as e:
        print(f"Operational event trim error: {e}")


def append_operational_event(level, source, message, details=None, path=OPERATIONAL_EVENTS_PATH):
    ts = datetime.now(KST).isoformat(timespec="seconds")
    row = {
        "ts": ts,
        "level": sanitize_event_text(level).lower() or "info",
        "source": sanitize_event_text(source),
        "message": sanitize_event_text(message),
        "details": sanitize_event_text(details or ""),
    }
    if is_db_available():
        try:
            get_db().table("operational_events").insert({
                "level": row["level"],
                "source": row["source"],
                "message": row["message"],
                "details": row["details"],
                "created_at": ts,
            }).execute()
        except Exception:
            pass
    try:
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.chmod(path, 0o600)
        _trim_jsonl_file(path, OPERATIONAL_EVENTS_MAX_LINES)
    except Exception as e:
        print(f"Operational event append error: {e}")


def read_recent_operational_events(levels=None, limit=5, path=OPERATIONAL_EVENTS_PATH):
    if not os.path.exists(path):
        return []
    wanted = {str(level).lower() for level in levels} if levels else None
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if wanted and str(row.get("level", "")).lower() not in wanted:
                    continue
                rows.append(row)
    except Exception as e:
        print(f"Operational event read error: {e}")
        return []
    return rows[-max(0, int(limit)):]
