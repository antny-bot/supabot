# exchange_adapter.md

**파일**: `src/core/exchange_adapter.py` (201줄) + `src/core/exchanges/{base,common,upbit,bithumb,kis,toss}.py`

## 역할
Upbit(CLI), Bithumb(REST+JWT), KIS(OAuth2), Toss(OAuth2) 4개 거래소 단일 async 인터페이스 추상화. Strategy 패턴:

- **`ExchangeAdapter`** (`exchange_adapter.py`) — 레지스트리/파사드. `self._exchanges = {"upbit": UpbitExchange(self), ...}` 보유, 공개 메서드(`get_balances`/`create_order`/`cancel_order`/`get_order_status`/`get_candles`/`get_ticker`/`get_order_history`)는 `self._exchanges[exchange].<메서드>(...)` 로 dispatch. HTTP 세션(`_bithumb_session` 등), 토큰 캐시(`_kis_tokens` 등), 캔들 캐시(`_candle_cache`) 단일 소유.
- **`BaseExchange`** (`exchanges/base.py`) — 공통 기본값 + capability 선언. `get_exchange(exchange)` 인스턴스에 `.supports_minute_candles()`, `.is_market_open()`, `.requires_numeric_ticker()`, `.round_volume(raw)`, `.requires_integer_volume()`, `.format_volume(vol)`, `.adjust_price_to_tick(price, ticker=None)`, `.env_label(client)`, `.required_credential_fields()` 호출로 차이 캡슐화 — 호출부(`main.py`/`handlers/*.py`/`signal_engine.py`)는 `if exchange == "kis"` 분기 안 함.
- **`XxxExchange(BaseExchange)`** (`exchanges/{upbit,bithumb,kis,toss}.py`) — 공개 메서드는 `self.adapter` (`ExchangeAdapter`) 저수준 메서드(`_request_kis`, `_get_kis_balances`, `_run_upbit_cli` 등, `XxxMixin` 정의) 위임 래퍼. capability 거래소별 오버라이드 (예: `KisExchange.is_market_open()` -> `is_kis_regular_session()`, `supports_minute_candles()` -> `False`).
- **`XxxMixin`** (같은 파일) — 저수준 HTTP/인증 코드(`_request_*`, `_get_*_session`, `_get_*_token` 등). `ExchangeAdapter`가 4개 Mixin 상속 — 테스트 `adapter._request_kis = fake_request_kis` monkeypatch 유지.

`get_candles()`는 `(exchange, ticker, interval, count)` 키로 `_candle_cache` 적용. interval별 TTL `_CANDLE_TTL` 정의, 캐시 유효 시 바로 반환.

> 거래소 추가·변경: `exchanges/` 에 `XxxMixin`+`XxxExchange(BaseExchange)` 추가 후 `ExchangeAdapter.__init__` `_exchanges` 등록. 호출부(`main.py`/`handlers/*.py`) 변경 불필요 — capability 차이 시 `BaseExchange` 오버라이드.

## 공개 인터페이스

```python
adapter = ExchangeAdapter(user_manager)
await adapter.close()   # HTTP 세션 정상 종료

# 시장 데이터
candles = await adapter.get_candles(exchange, ticker, interval, count, user_id)
info    = await adapter.get_ticker(exchange, ticker, user_id)
prices  = await adapter.get_krw_ticker_prices(exchange)   # 전체 KRW 마켓 시세

# 인증 필요
balances = await adapter.get_balances(user_id, exchange)
order    = await adapter.create_order(user_id, exchange, ticker, side, price, volume)
ok       = await adapter.cancel_order(user_id, exchange, order_id, ticker)
status   = await adapter.get_order_status(user_id, exchange, order_id, ticker)
history  = await adapter.get_order_history(user_id, exchange, ticker)
valid    = await adapter.validate_api_keys(user_id, exchange)
```

`side` 허용값: `"bid"/"buy"/"매수"` → 내부 `"bid"` 정규화, `"ask"/"sell"/"매도"` → `"ask"`.

## 거래소별 인증

| 거래소 | 방식 | 세부 |
|--------|------|------|
| **Upbit** | CLI subprocess | `asyncio.create_subprocess_exec("upbit", ..., "--access-key", "--secret-key")`. Node.js 바이너리, 세션 없음. |
| **Bithumb** | REST + JWT (HS256) | `_bithumb_session` (aiohttp) 재사용. `_get_bithumb_jwt()` 요청마다 JWT 생성, write endpoint SHA512 query hash 포함. |
| **KIS** | OAuth2 client_credentials | `_kis_session` (aiohttp) 재사용. 토큰 `_kis_tokens["{user_id}:{env}:{app_key}"]` 캐시 (만료 60초 전 갱신). `env="paper"` → `openapivts.koreainvestment.com:29443`, `env="real"` → `openapi.koreainvestment.com:9443`. TR_ID는 paper/real별 상이. |
| **Toss** | OAuth2 Bearer | `_toss_session` (aiohttp) 재사용. 토큰 `_toss_tokens["{user_id}:{client_id}"]` 캐시. 인증: `POST /api/v1/oauth2/token` (client_credentials). 주문·잔고 요청 `X-Tossinvest-Account: {account_seq}` 헤더 첨부. `account_seq` 최초 validate 시 `_get_toss_account_seq()` 자동 조회·저장. 엔드포인트: `openapi.tossinvest.com`. **국내(005930)·해외(AAPL) 동일 엔드포인트, symbol로 시장 자동판별** — 해외주식 세부 `docs/303_toss_overseas_stock.md`. |

## 정규화 캔들 형식

모든 거래소 동일 dict 리스트 반환:
```python
{
    "candle_date_time_kst": str,   # "20260529" 또는 ISO 형식
    "trade_price":   float,        # 종가
    "opening_price": float,
    "high_price":    float,
    "low_price":     float,
}
```
KIS는 `_get_kis_daily_candles()` 정규화, Upbit/Bithumb는 원본 그대로.

## 정규화 주문 상태

`_normalize_order_state(state, executed_volume)` 출력:

| 값 | 의미 |
|----|------|
| `"done"` | 전체 체결 |
| `"cancel"` | 취소됨 |
| `"partial"` | 일부 체결, 미체결 잔량 있음 |
| `"wait"` | 미체결 |

## KIS 주문 ID 형식
`"{KRX_FWDG_ORD_ORGNO}:{ODNO}"` 복합 문자열.

## 틱사이즈 유틸리티

두 종류 공존 — 혼동 주의:

- **`CommonMixin`의 static 유틸** (`exchanges/common.py`, `ExchangeAdapter.<메서드>(price)` 직접 호출): `get_tick_size(price)`/`adjust_price_to_tick(price)`(코인), `get_krx_tick_size(price)`/`adjust_krx_price_to_tick(price)`(KIS/Toss 국내), `adjust_us_price_to_tick(price)`(Toss 해외, 센트 단위). 거래소 직접 판단하는 구 호출부(`formatters.py`) 사용.
- **`BaseExchange.adjust_price_to_tick(self, price, ticker=None)`** (인스턴스 capability, `exchange_adapter.get_exchange(exchange).adjust_price_to_tick(price, ticker)` 호출): 거래소 몰라도 되는 신규 호출부(`main.py`/`signal_engine.py`/`order_execution.py`) 사용. `KisExchange`/`TossExchange` 내부 static 유틸(`adjust_krx_price_to_tick`/`adjust_us_price_to_tick`) 호출 오버라이드 — `TossExchange`는 `ticker`로 `is_us_stock_ticker()` 판단해 국내/해외 자동 분기(`docs/303_toss_overseas_stock.md`).

## 참조
- KIS 장외/재주문: `docs/302_kis_market_policy.md`
- RSI 역산 수식: `docs/301_rsi_algorithm.md`
- 토스 해외주식: `docs/303_toss_overseas_stock.md`
- 토스 API 엔드포인트 요약: `docs/206_toss_api_reference.md` (원본 OpenAPI 스펙 `docs/toss.json`)
