import os
import time
import pytest
from unittest.mock import MagicMock

from core.signal_engine import SignalEngine


def test_snooze_persistence_across_instances(tmp_path):
    """F1: 스누즈 설정 후 새 SignalEngine 인스턴스에서도 스누즈가 유지되는지 검증"""
    snooze_file = str(tmp_path / "snooze.json")
    mock_um = MagicMock()
    mock_ea = MagicMock()

    # 인스턴스 1에서 1시간 스누즈 설정
    engine1 = SignalEngine(mock_um, mock_ea, snooze_file_path=snooze_file)
    exp = engine1.set_snooze("user1", "upbit", "KRW-BTC", "1h")
    assert exp > time.time()
    assert ("user1", "upbit", "KRW-BTC") in engine1._alert_snooze

    # 새 인스턴스 2 생성
    engine2 = SignalEngine(mock_um, mock_ea, snooze_file_path=snooze_file)
    assert ("user1", "upbit", "KRW-BTC") in engine2._alert_snooze
    assert abs(engine2._alert_snooze[("user1", "upbit", "KRW-BTC")] - exp) < 0.001


def test_snooze_expired_cleaned_up(tmp_path):
    """F1: 만료된 스누즈 항목이 로드 시 또는 clean_expired_snoozes 호출 시 제거되는지 검증"""
    snooze_file = str(tmp_path / "snooze.json")
    mock_um = MagicMock()
    mock_ea = MagicMock()

    engine = SignalEngine(mock_um, mock_ea, snooze_file_path=snooze_file)
    # 과거 시각(만료된 항목) 직접 주입
    engine._alert_snooze[("user1", "upbit", "KRW-ETH")] = time.time() - 100
    engine._save_snoozes()

    # 새 인스턴스는 만료된 항목을 로드하지 않음
    engine_new = SignalEngine(mock_um, mock_ea, snooze_file_path=snooze_file)
    assert ("user1", "upbit", "KRW-ETH") not in engine_new._alert_snooze
