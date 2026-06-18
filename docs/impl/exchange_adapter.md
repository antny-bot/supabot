# exchange_adapter.md

**파일**: `src/core/exchange_adapter.py` (1128줄)

## 역할
Upbit(CLI), Bithumb(REST+JWT), KIS(OAuth2), Toss(OAuth2) 네 거래소를 단일 async 인터페이스로 추상화.

`get_candles()`는 `(exchange, ticker, interval, count)` 키로 인메모리 TTL 캐시(`_candle_cache`)를 적용한다. interval별 TTL은 `_CANDLE_TTL`로 정의하며, 캐시가 유효하면 거래소 호출 없이 캐시된 캔들을 반환한다.

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

`side` 허용값: `"bid"/"buy"/"매수"` → 내부에서 `"bid"` 정규화; `"ask"/"sell"/"매도"` → `"ask"`.

## 거래소별 인증

| 거래소 | 방식 | 세부 |
|--------|------|------|
| **Upbit** | CLI subprocess | `asyncio.create_subprocess_exec("upbit", ..., "--access-key", "--secret-key")`. Node.js 바이너리, 세션 없음. |
| **Bithumb** | REST + JWT (HS256) | `_bithumb_session` (aiohttp) 재사용. `_get_bithumb_jwt()` 가 요청마다 JWT 생성; write endpoint는 SHA512 query hash 포함. |
| **KIS** | OAuth2 client_credentials | `_kis_session` (aiohttp) 재사용. 토큰 `_kis_tokens["{user_id}:{env}:{app_key}"]` 캐시, 만료 60초 전 갱신. `env="paper"` → `openapivts.koreainvestment.com:29443`, `env="real"` → `openapi.koreainvestment.com:9443`. TR_ID는 paper/real별 상이. |
| **Toss** | OAuth2 Bearer | `_toss_session` (aiohttp) 재사용. 토큰 `_toss_tokens["{user_id}:{client_id}"]` 캐시. 인증: `POST /api/v1/oauth2/token` (client_credentials). 주문·잔고 요청에 `X-Tossinvest-Account: {account_seq}` 헤더 첨부. `account_seq`는 최초 validate 시 `_get_toss_account_seq()`로 자동 조회·저장. 엔드포인트: `openapi.tossinvest.com`. |

## 정규화 캔들 형식

모든 거래소에서 동일한 dict 리스트 반환:
```python
{
    "candle_date_time_kst": str,   # "20260529" 또는 ISO 형식
    "trade_price":   float,        # 종가
    "opening_price": float,
    "high_price":    float,
    "low_price":     float,
}
```
KIS는 `_get_kis_daily_candles()` 에서 정규화, Upbit/Bithumb는 원본 그대로.

## 정규화 주문 상태

`_normalize_order_state(state, executed_volume)` 출력:

| 값 | 의미 |
|----|------|
| `"done"` | 전체 체결 |
| `"cancel"` | 취소됨 |
| `"partial"` | 일부 체결, 아직 미체결 잔량 있음 |
| `"wait"` | 미체결 |

## KIS 주문 ID 형식
`"{KRX_FWDG_ORD_ORGNO}:{ODNO}"` 복합 문자열.

## 틱사이즈 유틸리티
- `get_tick_size(price)` → KRX/Upbit/Bithumb 틱 단위 반환
- `adjust_price_to_tick(price)` → 유효 틱으로 내림. `signal_engine` 에서 호출.

## 참조
- KIS 장외/재주문: `docs/detail/kis_market_policy.md`
- RSI 역산 수식: `docs/detail/rsi_algorithm.md`
