import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.parsers import parse_config_value
from core.signal_engine import SignalEngine


def test_parse_signal_combine_mode():
    """F4: signal_combine_mode 파싱 검증"""
    assert parse_config_value("signal_combine_mode", "and") == "and"
    assert parse_config_value("signal_combine_mode", "or") == "or"
    assert parse_config_value("signal_combine_mode", "AND") == "and"
    with pytest.raises(ValueError):
        parse_config_value("signal_combine_mode", "xor")


@pytest.mark.asyncio
async def test_signal_combine_mode_or_and(tmp_path):
    """F4: or 모드 및 and 모드 알림 발생 여부 검증"""
    snooze_file = str(tmp_path / "snooze.json")
    mock_um = MagicMock()
    mock_ea = MagicMock()
    se = SignalEngine(mock_um, mock_ea, snooze_file_path=snooze_file)

    # indicators: RSI는 25(과매도), BB는 current 1000 >= lower 900 (터치 안함)
    bb_mock = MagicMock()
    bb_mock.lower = 900.0
    indicators = {
        "rsi": 25.0,
        "bbands": bb_mock,
        "current_price": 1000.0,
    }
    se.get_indicators = AsyncMock(return_value=indicators)

    # 1. OR 모드: RSI 과매도(25 <= 30)로 알림 발생
    user_or = {
        "is_active": True,
        "preferences": {
            "signal_alerts": True,
            "signal_rsi_threshold": 30.0,
            "signal_bb_alert": True,
            "signal_combine_mode": "or",
            "rsi_interval": "day",
        },
        "exchanges": {
            "upbit": {"watchlist": ["KRW-BTC"]}
        }
    }
    mock_um.users = {"user_or": user_or}
    mock_app = MagicMock()
    mock_app.bot.send_message = AsyncMock()

    await se.analyze_watchlist(mock_app)
    assert mock_app.bot.send_message.call_count == 1

    # 2. AND 모드: RSI 과매도이나 BB 미터치이므로 알림 미발생
    se._alert_snooze.clear()
    user_and = {
        "is_active": True,
        "preferences": {
            "signal_alerts": True,
            "signal_rsi_threshold": 30.0,
            "signal_bb_alert": True,
            "signal_combine_mode": "and",
            "rsi_interval": "day",
        },
        "exchanges": {
            "upbit": {"watchlist": ["KRW-BTC"]}
        }
    }
    mock_um.users = {"user_and": user_and}
    mock_app.bot.send_message.reset_mock()

    await se.analyze_watchlist(mock_app)
    assert mock_app.bot.send_message.call_count == 0

    # 3. AND 모드: RSI 과매도(25 <= 30) AND BB 터치(850 < 900) 모두 만족 -> 알림 발생
    indicators_both = {
        "rsi": 25.0,
        "bbands": bb_mock,
        "current_price": 850.0,
    }
    se.get_indicators = AsyncMock(return_value=indicators_both)
    await se.analyze_watchlist(mock_app)
    assert mock_app.bot.send_message.call_count == 1
