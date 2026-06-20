# toss_overseas_stock.md — 토스증권 해외(미국)주식 지원

**해당 작업**: 토스증권 해외주식(AAPL, TSLA 등 USD 티커) 관련 수정. KIS/Upbit/Bithumb 작업이면 이 문서 불필요.

## 왜 별도 처리가 필요한가

토스증권 OpenAPI(`docs/toss.json`)는 국내·해외 주문을 **동일 엔드포인트**(`/api/v1/orders` 등)로 처리하고
`symbol` 값으로 시장을 자동 판별한다 (`005930` = 국내, `AAPL` = 해외). 그래서 주문 생성/체결조회/잔고조회
자체는 거래소 어댑터 코드 변경 없이 이미 동작한다.

문제는 **가격 단위**다. 기존 코드는 KIS/Toss 주문가를 전부 KRX 호가단위(원 단위 정수)로 내림 보정했는데,
이걸 USD 가격(예: $185.50)에 그대로 적용하면 소수점이 날아간다(`185.5` → `185`). 화면 표시도 전부
"원"으로 하드코딩돼 있어 USD 주문에 그대로 쓰면 통화가 뒤바뀐 것처럼 보인다.

## 판별 기준

```python
# src/core/parsers.py
def is_us_stock_ticker(exchange, ticker):
    """토스증권 해외(미국) 주식 종목코드 여부 (알파벳 티커, 예: AAPL). KIS는 해외주문 미지원."""
    text = str(ticker or "").replace("KRW-", "")
    return exchange == "toss" and text.isalpha()
```

- `exchange == "toss"`이고 티커가 **숫자 없이 알파벳으로만** 구성되면 해외주식으로 간주.
- KIS는 국내전용 TR_ID(`_create_kis_order`)만 구현돼 있어 이 판별에서 항상 제외된다 — KIS 해외주문은 미지원.
- Upbit/Bithumb 코인 티커(`BTC`, `ETH`)는 `exchange == "toss"` 조건에서 걸러지므로 오판 없음.

## 영향받는 코드 경로

| 위치 | 무엇을 분기하는가 |
|------|------|
| `src/core/exchange_adapter.py` | `adjust_us_price_to_tick(price)` 추가 — 센트(0.01) 단위 내림. 기존 `adjust_krx_price_to_tick`(원 단위)와 분리 |
| `src/core/order_execution.py` `execute_grid_orders` | `ex.adjust_price_to_tick(price, ticker)` capability 메서드로 위임 (`TossExchange`가 내부에서 `self.is_us_stock(ticker)`로 자동 판별, 호출부는 해외/국내 분기를 직접 알 필요 없음) |
| `src/main.py` (트레일링스톱/손절 3곳) | `rsitrade_sell` 손절가 계산 시 동일하게 `exchange_adapter.get_exchange(exchange).adjust_price_to_tick(...)` 호출로 위임 |
| `src/core/signal_engine.py` `get_price_by_rsi` | RSI 역산 목표가 보정 시 동일하게 `self.exchange_adapter.get_exchange(exchange).adjust_price_to_tick(target_price, ticker)` 호출로 위임 |
| `src/core/parsers.py` `validate_max_order(user, amount, is_usd=...)` | `max_order_krw`는 원화 캡이라 USD 금액과 비교 불가 → `is_usd=True`면 검증 스킵 (안전 쪽으로 치우침: 잘못된 비교로 차단/허용하지 않음) |
| `src/core/formatters.py` | `build_manual_order_confirm_message`, `build_grid_preview_lines`, `build_rsi_preview_lines`, `build_cancel_confirm_message`, `build_report_view` — USD면 `$`+소수 2자리, 아니면 기존 `원` 포맷 |
| `src/handlers/query_handlers.py` `/price`, `/history`, `/orders` | `ticker_data.get('currency')` 또는 `is_us_stock_ticker`로 분기 표시 |
| `src/handlers/strategy_handlers.py` | `/grid`,`/sgrid`,`/rsitrade`,`/gridrsi`,`/sgridrsi` 확인 메시지·최소주문 검증 전부 `is_usd` 분기 |
| `src/handlers/status_handlers.py` | `/status` 거래소 루프에 `toss`가 누락돼 있던 **기존 버그**도 같이 수정(토스 전략 주문이 대시보드에서 안 보임) |

## 수량(주) 처리

미국주식도 토스 API는 정수 주 단위 주문(`quantity`)만 사용한다(분수 주문 `orderAmount`는 미지원 — 정규장 외 422 에러 등 까다로워 범위 밖). 그래서 기존 KIS/Toss 공용 `int(volume)` 처리가 그대로 재사용된다 — 별도 분기 불필요.

## 알려진 미지원/한계 (의도적 범위 제외)

1. **`trade_logs` 테이블/파일에 currency 컬럼 없음.** `/report` 는 ticker 패턴(`is_us_stock_ticker`)으로 통화를 그때그때 추론해 KRW/USD 합계를 분리한다. DB 스키마에 `currency` 컬럼을 추가하는 정식 마이그레이션은 하지 않았다 — 과거 기록 중 토스 해외주식이 한국 종목코드로 잘못 기록된 적이 있다면(없음, 항상 AAPL 같은 알파벳 티커로 기록됨) 추론이 깨질 일은 없지만, 다른 거래소가 알파벳 티커를 쓰게 되면 재검토 필요.
2. **`/rsitrade`, `/gridrsi`, `/sgridrsi` 예산 입력은 그대로 plain number**(`parse_number`가 "만/억/천" 접미사 없으면 그냥 float 변환) — USD는 접미사 없이 `100`, `1000.5` 형태로 입력하면 된다. 별도 파서 분기 불필요했음.
3. **`/asset`, `get_balances`** 는 이미 해외 종목별 `currency` 필드를 토스 API 응답에서 그대로 내려주고 있어(`stock.get("currency")`) 이번 작업 이전부터 정상 동작했음 — 변경 없음.

## 참조
- 토스 API 엔드포인트 요약(마크다운): `docs/impl/toss_api_reference.md` — 원본 스펙은 `docs/toss.json`(6400+줄, 세부 필드/에러코드 필요할 때만)
- 거래소 어댑터 전체: `docs/impl/exchange_adapter.md`
