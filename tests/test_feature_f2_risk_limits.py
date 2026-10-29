import pytest
from core.parsers import parse_config_value
from core.trading_gate import assert_risk_limits, check_can_place_order


def test_parse_risk_limit_config_values():
    """F2: 리스크 한도 설정값 파싱 검증"""
    assert parse_config_value("max_ticker_exposure_krw", "1000000") == 1000000.0
    assert parse_config_value("max_ticker_exposure_krw", "none") is None
    assert parse_config_value("daily_max_order_count", "50") == 50
    assert parse_config_value("daily_max_order_count", "무제한") is None
    with pytest.raises(ValueError):
        parse_config_value("daily_max_order_count", "0")
    assert parse_config_value("daily_max_loss_krw", "500000") == 500000.0


def test_risk_limits_default_unlimited():
    """F2: 기본 설정(None) 시 모든 주문 정상 허용"""
    user = {"preferences": {}}
    ok, msg = assert_risk_limits(
        user=user,
        open_orders=[],
        new_order_krw=10_000_000,
        ticker="KRW-BTC",
        side="bid",
        today_order_count=100,
        today_realized_loss_krw=5_000_000,
    )
    assert ok is True
    assert msg is None


def test_risk_limits_max_ticker_exposure():
    """F2: 종목별 최대 노출 한도 검증"""
    user = {
        "preferences": {
            "max_ticker_exposure_krw": 1_000_000.0,
        }
    }
    open_orders = [
        {"ticker": "KRW-BTC", "side": "bid", "volume": 0.01, "filled_volume": 0.0, "price": 50_000_000.0},  # 500,000원
    ]

    # 1. 400,000원 추가 매수 -> 총 900,000원 <= 1,000,000원 -> 허용
    ok, msg = assert_risk_limits(user, open_orders, 400_000, ticker="KRW-BTC", side="bid")
    assert ok is True

    # 2. 600,000원 추가 매수 -> 총 1,100,000원 > 1,000,000원 -> 차단
    ok, msg = assert_risk_limits(user, open_orders, 600_000, ticker="KRW-BTC", side="bid")
    assert ok is False
    assert "종목별 최대 노출 한도" in msg

    # 3. 다른 종목(KRW-ETH) 매수는 KRW-BTC 노출과 무관하게 한도 이내면 허용
    ok_eth, _ = assert_risk_limits(user, open_orders, 600_000, ticker="KRW-ETH", side="bid")
    assert ok_eth is True


def test_risk_limits_daily_max_orders():
    """F2: 일일 최대 주문 건수 검증"""
    user = {
        "preferences": {
            "daily_max_order_count": 10,
        }
    }
    # 9건 실행 상태에서 신규 주문 -> 허용
    ok, _ = assert_risk_limits(user, [], 10000, today_order_count=9)
    assert ok is True

    # 10건 도달 상태에서 신규 주문 -> 차단
    ok, msg = assert_risk_limits(user, [], 10000, today_order_count=10)
    assert ok is False
    assert "일일 최대 주문 건수" in msg


def test_risk_limits_daily_max_loss():
    """F2: 일일 최대 허용 손실액 검증"""
    user = {
        "preferences": {
            "daily_max_loss_krw": 200_000.0,
        }
    }
    # 손실 150,000원 -> 허용
    ok, _ = assert_risk_limits(user, [], 10000, today_realized_loss_krw=150_000.0)
    assert ok is True

    # 손실 200,000원 도달 -> 차단
    ok, msg = assert_risk_limits(user, [], 10000, today_realized_loss_krw=200_000.0)
    assert ok is False
    assert "일일 최대 허용 손실액" in msg


def test_risk_limits_stoploss_always_allowed():
    """F2: 보호성 매도(stoploss)는 모든 한도 초과 시에도 항상 허용"""
    user = {
        "preferences": {
            "max_ticker_exposure_krw": 100.0,
            "daily_max_order_count": 1,
            "daily_max_loss_krw": 100.0,
        }
    }
    # 한도가 모두 극단적으로 초과된 상태
    ok, msg = check_can_place_order(
        user=user,
        open_orders=[],
        new_order_krw=10_000_000,
        ticker="KRW-BTC",
        side="ask",
        strategy="stoploss",
        today_order_count=999,
        today_realized_loss_krw=999_999_999,
    )
    assert ok is True
    assert msg is None
