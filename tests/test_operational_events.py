import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.operational_events import append_operational_event, read_recent_operational_events, sanitize_event_text


def test_operational_event_sanitizes_sensitive_text():
    text = sanitize_event_text("secret=abc123 token=abcdef1234567890abcdef123456 account 12345678")

    assert "abc123" not in text
    assert "<TOKEN>" in text or "<NUMBER>" in text


def test_operational_event_writes_and_reads_recent_rows(tmp_path):
    path = tmp_path / "bot_events.jsonl"

    append_operational_event("info", "test", "ok", path=str(path))
    append_operational_event("warning", "test", "warn", "secret=abc123", path=str(path))
    append_operational_event("error", "test", "err", path=str(path))

    rows = read_recent_operational_events(levels={"warning", "error"}, limit=2, path=str(path))

    assert [row["level"] for row in rows] == ["warning", "error"]
    assert rows[0]["details"] == "secret=<REDACTED>"
