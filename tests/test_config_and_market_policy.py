import datetime as dt
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.order_manager import OrderManager
from core.user_manager import UserManager
import main


def test_default_rsi_interval_is_day():
    assert UserManager.DEFAULT_PREFERENCES["rsi_interval"] == "day"


def test_parse_rsi_interval_aliases():
    assert main.parse_config_value("rsi_interval", "daily") == "day"
    assert main.parse_config_value("rsi_interval", "1d") == "day"
    assert main.parse_config_value("rsi_interval", "60") == "60"


def test_parse_rsi_interval_rejects_unknown_value():
    try:
        main.parse_config_value("rsi_interval", "2h")
    except ValueError as exc:
        assert "RSI 캔들 기준" in str(exc)
    else:
        raise AssertionError("invalid RSI interval should fail")


def test_llm_enabled_requires_gemini_key():
    user = {"preferences": {}, "llm": {"gemini_api_key": ""}}
    try:
        main.validate_config_update(user, "llm_enabled", True)
    except ValueError as exc:
        assert "Gemini" in str(exc)
    else:
        raise AssertionError("llm_enabled should require a Gemini key")


def test_default_llm_model_uses_flash_lite():
    assert UserManager.DEFAULT_PREFERENCES["llm_model"] == "gemini-2.5-flash-lite"


def test_bot_display_name_is_ttbot():
    assert main.BOT_DISPLAY_NAME == "TTBot"


def test_llm_prompt_uses_compact_english_command_catalog():
    user = {"preferences": {"default_exchange": "bithumb"}}

    prompt = main._build_llm_prompt("BTC 9500만원에 0.01개 사줘", user)

    assert "Commands:" in prompt
    assert "buy req=exchange,ticker,price,volume run=confirm" in prompt
    assert "price req=ticker opt=exchange run=now" in prompt
    assert "Use help only for usage/capability questions." in prompt
    assert "Missing required fields => clarify." in prompt
    assert "RSI + split/grid/거미줄 + budget => rsitrade." in prompt
    assert "grid is price-range only, not RSI." in prompt
    assert "Missing sell_rsi_range => null; server uses default." in prompt
    assert "Default exchange: bithumb." in prompt


def test_help_intent_runs_immediately():
    assert main._is_immediate_intent("help") is True


def test_natural_language_rsi_grid_phrase_normalizes_to_rsitrade():
    user = {"preferences": {"default_exchange": "upbit"}}
    text = "빗썸에 BTC를 거미줄 매매방식으로 RSI 20~30 기준으로 100만원을 5개로 나눠 주문해"

    intent = main.normalize_natural_language_intent(text, {"action": "clarify"}, user)

    assert intent["action"] == "rsitrade"
    assert intent["exchange"] == "bithumb"
    assert intent["ticker"] == "BTC"
    assert intent["buy_rsi_range"] == "20-30"
    assert intent["sell_rsi_range"] is None
    assert intent["count"] == 5
    assert intent["amount_krw"] == 1000000


def test_natural_language_rsi_phrase_without_budget_stays_clarify():
    user = {"preferences": {"default_exchange": "upbit"}}
    text = "BTC를 RSI 20~30 기준으로 5개로 나눠 주문해"

    intent = main.normalize_natural_language_intent(text, {"action": "clarify"}, user)

    assert intent["action"] == "clarify"


def test_natural_language_price_grid_intent_is_not_rewritten_to_rsitrade():
    user = {"preferences": {"default_exchange": "upbit"}}
    text = "BTC 9000만~9500만 5개 100만원 거미줄"
    intent = {"action": "grid", "ticker": "BTC", "start_price": 90000000, "end_price": 95000000}

    normalized = main.normalize_natural_language_intent(text, intent, user)

    assert normalized["action"] == "grid"


def test_natural_language_pending_order_phrase_routes_to_status():
    user = {"preferences": {"default_exchange": "bithumb"}}

    normalized = main.normalize_natural_language_intent(
        "주문대기중인것은?",
        {"action": "orders"},
        user,
    )

    assert normalized["action"] == "status"


def test_natural_language_tracked_strategy_order_phrase_routes_to_status():
    user = {"preferences": {"default_exchange": "bithumb"}}

    normalized = main.normalize_natural_language_intent(
        "예약된 주문이나 추적 중인 전략 주문 있어?",
        {"action": "orders"},
        user,
    )

    assert normalized["action"] == "status"


def test_natural_language_open_order_phrase_stays_orders():
    user = {"preferences": {"default_exchange": "bithumb"}}

    normalized = main.normalize_natural_language_intent(
        "미체결 주문 뭐가 있지?",
        {"action": "orders"},
        user,
    )

    assert normalized["action"] == "orders"


def test_preprocess_natural_language_routes_safe_status_without_llm():
    user = {"preferences": {"default_exchange": "bithumb"}}

    intent = main.preprocess_natural_language_intent("주문대기중인것은?", user)

    assert intent == {"action": "status"}


def test_preprocess_natural_language_routes_safe_asset_with_exchange():
    user = {"preferences": {"default_exchange": "upbit"}}

    intent = main.preprocess_natural_language_intent("빗썸 잔고 보여줘", user)

    assert intent == {"action": "asset", "exchange": "bithumb"}


def test_preprocess_natural_language_routes_safe_price_with_ticker():
    user = {"preferences": {"default_exchange": "upbit"}}

    intent = main.preprocess_natural_language_intent("BTC 시세 알려줘", user)

    assert intent == {"action": "price", "ticker": "BTC"}


def test_preprocess_natural_language_routes_safe_config_view():
    user = {"preferences": {"default_exchange": "upbit"}}

    intent = main.preprocess_natural_language_intent("현재 설정 보여줘", user)

    assert intent == {"action": "config_view"}


def test_preprocess_natural_language_ignores_order_change_requests():
    user = {"preferences": {"default_exchange": "upbit"}}

    assert main.preprocess_natural_language_intent("BTC 주문 취소해", user) is None
    assert main.preprocess_natural_language_intent("비트 100만원어치 사줘", user) is None


def test_natural_language_log_anonymizes_and_summarizes(tmp_path):
    log_path = tmp_path / "nl_unmatched.jsonl"

    main.append_natural_language_log(
        "BTC 123456원 TOKENabcdef1234567890abcdef 주문?",
        {"action": "clarify"},
        {"action": "clarify"},
        path=str(log_path),
    )
    main.append_natural_language_log(
        "BTC 999999원 TOKENabcdef1234567890abcdef 주문?",
        {"action": "clarify"},
        {"action": "clarify"},
        path=str(log_path),
    )

    rows = main.read_natural_language_log_stats(path=str(log_path), limit=5)

    assert rows == [
        {
            "text_norm": "BTC <STOCK>원 <TOKEN> 주문?",
            "count": 2,
            "llm_actions": {"clarify": 2},
            "final_actions": {"clarify": 2},
        }
    ]


def test_rsitrade_intent_summary_is_user_friendly():
    intent = {
        "action": "rsitrade",
        "exchange": "bithumb",
        "ticker": "BTC",
        "buy_rsi_range": "20-30",
        "sell_rsi_range": None,
        "count": 5,
        "amount_krw": 1000000,
    }

    summary = main._intent_summary(intent)

    assert "BITHUMB KRW-BTC" in summary
    assert "매수 RSI 20-30" in summary
    assert "매도 RSI 기본값" in summary
    assert "5분할" in summary
    assert "총 1,000,000원" in summary


def test_grid_preview_lists_each_order_price_volume_and_budget():
    lines = main.build_grid_preview_lines("KRW-BTC", 90000000, 95000000, 3, 600000)

    assert len(lines) == 3
    assert "1. 90,000,000원" in lines[0]
    assert "약 0.0022 BTC" in lines[0]
    assert "200,000원" in lines[0]
    assert "3. 95,000,000원" in lines[2]


def test_rsi_preview_lists_each_order_rsi_price_volume_and_budget():
    lines = main.build_rsi_preview_lines("KRW-BTC", [(20, 90000000), (25, 92500000)], 400000)

    assert len(lines) == 2
    assert "1. RSI 20" in lines[0]
    assert "90,000,000원" in lines[0]
    assert "약 0.0022 BTC" in lines[0]
    assert "200,000원" in lines[0]
    assert "2. RSI 25" in lines[1]


def test_rsigrid_is_registered_as_rsitrade_alias():
    assert "rsigrid" in main.RSI_GRID_COMMAND_ALIASES
    assert "rsitrade" in main.RSI_GRID_COMMAND_ALIASES


def test_docker_build_metadata_uses_kst_and_build_args():
    dockerfile = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    compose = open(os.path.join(ROOT, "docker-compose.yml"), encoding="utf-8").read()
    deploy = open(os.path.join(ROOT, "scripts", "deploy.sh"), encoding="utf-8").read()

    assert 'date +"%Y-%m-%d %H:%M KST"' in dockerfile
    assert "GIT_SHA: ${GIT_SHA:-unknown}" in compose
    assert "VERSION: ${VERSION:-dev}" in compose
    assert "git rev-parse --short=12 HEAD" in deploy
    assert 'GIT_SHA="$GIT_SHA" docker compose up -d --build' in deploy


def test_kis_market_time_gate():
    market_time = dt.datetime(2026, 5, 29, 10, 0)
    after_close = dt.datetime(2026, 5, 29, 16, 0)
    saturday = dt.datetime(2026, 5, 30, 10, 0)

    assert main.is_kis_regular_session(market_time) is True
    assert main.is_kis_regular_session(after_close) is False
    assert main.is_kis_regular_session(saturday) is False
    assert main.next_kis_regular_session(after_close) == dt.datetime(2026, 6, 1, 9, 0)


def test_order_manager_updates_reorder_metadata(tmp_path):
    path = tmp_path / "orders.json"
    manager = OrderManager(str(path))
    manager.add_order("1", "kis", "005930", "old", 70000, 3, strategy="rsitrade")

    assert manager.mark_reorder_pending("old", next_check_at=123.0)
    order = manager.orders[0]
    assert order["status"] == "pending_reorder"
    assert order["next_check_at"] == 123.0

    assert manager.replace_order_uuid("old", "new")
    assert manager.orders[0]["uuid"] == "new"
    assert manager.orders[0]["status"] == "wait"
