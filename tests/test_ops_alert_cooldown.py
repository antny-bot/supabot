import os
import sys
from unittest.mock import AsyncMock, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import main


def _make_app():
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    return app


def _setup(monkeypatch, issues):
    monkeypatch.setattr(main, "ADMIN_CHAT_ID", "admin-1")
    monkeypatch.setattr(main, "_ops_alert_last_sent", {})
    mock_metrics = MagicMock()
    mock_metrics.ops_alerts = MagicMock(return_value=issues)
    monkeypatch.setattr(main, "metrics", mock_metrics)


async def test_ops_alert_sends_on_first_occurrence(monkeypatch):
    app = _make_app()
    _setup(monkeypatch, ["주문 실패율 높음 [toss]: 2/5건 (40% 실패)"])

    await main._check_ops_health(app)

    app.bot.send_message.assert_awaited_once()
    text = app.bot.send_message.call_args.kwargs["text"]
    assert "40% 실패" in text


async def test_ops_alert_does_not_repeat_within_cooldown(monkeypatch):
    app = _make_app()
    _setup(monkeypatch, ["주문 실패율 높음 [toss]: 2/5건 (40% 실패)"])

    # 동일한 누적 지표(metrics가 리셋되지 않음)로 6회 연속 점검 — 첫 번째만 전송되어야 함
    for _ in range(6):
        await main._check_ops_health(app)

    app.bot.send_message.assert_awaited_once()


async def test_ops_alert_resends_after_cooldown_expires(monkeypatch):
    app = _make_app()
    _setup(monkeypatch, ["주문 실패율 높음 [toss]: 2/5건 (40% 실패)"])

    await main._check_ops_health(app)
    assert app.bot.send_message.await_count == 1

    # 쿨다운이 이미 지난 것처럼 마지막 전송 시각을 과거로 조작
    for issue in list(main._ops_alert_last_sent):
        main._ops_alert_last_sent[issue] -= main._OPS_ALERT_COOLDOWN_SECONDS + 1

    await main._check_ops_health(app)
    assert app.bot.send_message.await_count == 2


async def test_ops_alert_no_admin_chat_id_skips_send(monkeypatch):
    app = _make_app()
    _setup(monkeypatch, ["주문 실패율 높음 [toss]: 2/5건 (40% 실패)"])
    monkeypatch.setattr(main, "ADMIN_CHAT_ID", None)

    await main._check_ops_health(app)

    app.bot.send_message.assert_not_awaited()
