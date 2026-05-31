"""Phase 8 중기: 구조화 로거 테스트"""
import json
import logging
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.bot_logger import _JSONFormatter, get_logger


def _capture_log(logger_name: str, level: str, msg: str, extra=None) -> dict:
    """로그 레코드를 JSON으로 직렬화해 dict 반환."""
    formatter = _JSONFormatter()
    record = logging.LogRecord(
        name=logger_name,
        level=getattr(logging, level),
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    if extra:
        for k, v in extra.items():
            setattr(record, k, v)
    return json.loads(formatter.format(record))


def test_json_formatter_contains_required_fields():
    """JSON 출력에 ts·level·module·msg 필드가 반드시 포함되어야 함."""
    result = _capture_log("test", "INFO", "hello")
    assert "ts" in result
    assert "level" in result
    assert "module" in result
    assert "msg" in result


def test_json_formatter_level_matches():
    """level 필드가 실제 로그 레벨 이름과 일치해야 함."""
    for level in ("INFO", "WARNING", "ERROR"):
        result = _capture_log("test", level, "msg")
        assert result["level"] == level


def test_json_formatter_extra_fields_included():
    """extra로 전달한 event·exchange·ticker·user_id·uuid·path가 출력에 포함."""
    extra = {"event": "test_event", "exchange": "upbit", "ticker": "KRW-BTC"}
    result = _capture_log("test", "INFO", "test", extra=extra)
    assert result["event"] == "test_event"
    assert result["exchange"] == "upbit"
    assert result["ticker"] == "KRW-BTC"


def test_json_formatter_extra_none_fields_omitted():
    """extra에 없는 선택 필드는 출력에 포함되지 않아야 함."""
    result = _capture_log("test", "INFO", "msg")
    for field in ("event", "exchange", "ticker", "user_id", "uuid", "path"):
        assert field not in result


def test_json_formatter_output_is_valid_json():
    """JSON 형식임을 검증 — json.loads 성공 여부로 판단."""
    formatter = _JSONFormatter()
    record = logging.LogRecord("n", logging.INFO, "f", 1, "hello world", (), None)
    raw = formatter.format(record)
    parsed = json.loads(raw)
    assert parsed["msg"] == "hello world"


def test_get_logger_returns_logger():
    """get_logger()가 logging.Logger 인스턴스를 반환해야 함."""
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)


def test_get_logger_does_not_propagate():
    """중복 출력 방지를 위해 propagate=False여야 함."""
    logger = get_logger("test_no_propagate")
    assert logger.propagate is False


def test_get_logger_same_name_returns_same_instance():
    """동일 이름으로 두 번 호출해도 핸들러가 중복 추가되지 않아야 함."""
    logger1 = get_logger("duplicate_test")
    handler_count = len(logger1.handlers)
    logger2 = get_logger("duplicate_test")
    assert logger1 is logger2
    assert len(logger2.handlers) == handler_count
