from unittest.mock import AsyncMock, MagicMock
import pytest

from handlers.dca_handlers import (
    _format_dca_amount_text,
    build_dca_confirm_summary,
    build_dca_list_message,
    dca_command,
    sdca_command,
)
from handlers import strategy_handlers


def test_dca_format_amount():
    assert _format_dca_amount_text("upbit", "KRW-BTC", "budget", 50000) == "50,000원"
    assert _format_dca_amount_text("kis", "005930", "volume", 10) == "10주"
    assert _format_dca_amount_text("toss", "AAPL", "budget", 100) == "$100.00"


def test_dca_confirm_summary():
    payload = {
        "exchange": "upbit",
        "ticker": "KRW-BTC",
        "side": "bid",
        "amount": 50000.0,
        "amount_type": "budget",
        "frequency": "daily",
        "exec_time": "09:05",
        "max_runs": 20,
    }
    summary = build_dca_confirm_summary(payload)
    assert "정기 매수 전략 확인" in summary
    assert "KRW-BTC" in summary
    assert "매일" in summary
    assert "50,000원" in summary
    assert "총 20회 실행 후 자동 종료" in summary


def test_strategy_handlers_reexport_dca():
    # Verify backward compatibility re-exports
    assert hasattr(strategy_handlers, "dca_command")
    assert hasattr(strategy_handlers, "sdca_command")
    assert hasattr(strategy_handlers, "dca_confirm_callback")
    assert hasattr(strategy_handlers, "dca_delete_callback")
    assert hasattr(strategy_handlers, "build_dca_list_message")
    assert hasattr(strategy_handlers, "build_dca_confirm_summary")
    assert strategy_handlers.dca_command is dca_command
    assert strategy_handlers.sdca_command is sdca_command


def test_main_reexport_order_sync():
    import main
    # Verify backward compatibility re-exports in main.py
    assert hasattr(main, "sync_orders")
    assert hasattr(main, "startup_recovery")
    assert hasattr(main, "cancel_and_remove_order")
    assert hasattr(main, "_create_linked_sell_order")
    assert hasattr(main, "_find_linked_sell_orders")
    assert hasattr(main, "_find_linked_sell_order")
    assert hasattr(main, "_submit_reserved_or_reorder")
    assert hasattr(main, "_process_order_fill")
    assert hasattr(main, "_apply_stop_loss")
