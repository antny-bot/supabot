# toss_api_reference.md — 토스증권 OpenAPI 요약

**원본**: `docs/toss.json` (OpenAPI 3.0 스펙, 6400+줄). 이 문서는 그 중 봇이 실제로 쓰는/쓸 만한 엔드포인트만
요약한 것. **세부 스키마(필드 하나하나, 에러코드 전체, 모든 example)가 필요하면 `docs/toss.json`에서
해당 `operationId`나 path로 검색** — 이 문서는 "어떤 엔드포인트가 있고 KR/US가 뭐가 다른지" 빠르게 훑는 용도.

토스증권 어댑터 코드 자체는 `src/core/exchange_adapter.py` (`docs/impl/exchange_adapter.md`),
해외주식 통화 분기는 `docs/detail/toss_overseas_stock.md` 참조.

## 인증

`POST /oauth2/token` — OAuth2 client_credentials. 코드: `_get_toss_token()`.

## 시장 데이터 (인증 불필요, `need_account=False`)

| 메서드/경로 | 설명 | 비고 |
|---|---|---|
| `GET /api/v1/prices?symbols=` | 현재가 조회 | 봇 `get_ticker` 사용. KR/US 동일 응답 구조, `currency` 필드로 구분 |
| `GET /api/v1/candles?symbol=&interval=&count=&before=&adjusted=` | OHLCV 캔들, 최대 200봉 | 봇 `_get_toss_candles` 사용 |
| `GET /api/v1/orderbook?symbol=` | 호가 조회 | 봇 미사용 |
| `GET /api/v1/trades?symbol=&count=` | 최근 체결 내역(공개 시세) | 봇 미사용 — `/history`는 `/api/v1/orders`(본인 주문) 사용 |
| `GET /api/v1/price-limits?symbol=` | 상/하한가 조회 | 봇 미사용 |
| `GET /api/v1/stocks?symbols=` | 종목 기본 정보 | 봇 미사용 (종목코드 resolve는 `stock_resolver.py`가 KIS 검색API로 처리) |
| `GET /api/v1/stocks/{symbol}/warnings` | 매수 주의사항 조회 | 봇 미사용 |
| `GET /api/v1/exchange-rate?dateTime=&baseCurrency=&quoteCurrency=` | KRW↔USD 환율(참고용, 1분 갱신) | 봇 미사용 — 손익 계산에 환율 미적용(USD 별도 합계로만 표시, `docs/detail/toss_overseas_stock.md` 참조) |
| `GET /api/v1/market-calendar/KR?date=` / `.../US?date=` | 국내/해외(미국) 장 운영 시간 조회 | 봇 미사용. KIS는 자체 `is_kis_regular_session()` 휴리스틱 사용 — Toss는 장외 체크 없음(주의: 향후 버그 가능 지점) |

## 계좌/잔고 (인증 필요, `X-Tossinvest-Account` 헤더)

| 메서드/경로 | 설명 | 비고 |
|---|---|---|
| `GET /api/v1/accounts` | 계좌 목록 조회 | `accountSeq` 획득용. 봇 `_get_toss_account_seq()`가 최초 1회 호출 후 저장 |
| `GET /api/v1/holdings?symbol=` | 보유 주식 조회 (KR+US 혼합) | 봇 `get_balances` 사용. 종목별 `currency` 필드 포함 (이미 currency-aware) |
| `GET /api/v1/buying-power?currency=` | 매수 가능 금액 (현금 기준) | 봇은 `currency=KRW`만 조회 — **USD 매수가능금액은 별도 조회 안 함** (개선 여지) |
| `GET /api/v1/sellable-quantity?symbol=` | 매도 가능 수량 조회 | 봇 미사용 — 매도 시 보유량 검증 없이 바로 주문 시도 |
| `GET /api/v1/commissions` | 시장별(국내/해외) 매매 수수료율 조회 | 봇 미사용 — `/report` 손익은 수수료 미반영(추정치, 안내문 있음) |

## 주문

| 메서드/경로 | 설명 | KR vs US 차이 |
|---|---|---|
| `GET /api/v1/orders?status=&symbol=&from=&to=&cursor=&limit=` | 주문 목록 조회 | `status`는 `OPEN`/`CLOSED`만 허용 |
| `POST /api/v1/orders` | 주문 생성 | 아래 표 참조 |
| `GET /api/v1/orders/{orderId}` | 주문 단건 조회 | — |
| `POST /api/v1/orders/{orderId}/modify` | 주문 정정 | KR: `quantity` 필수(정수). **US: `quantity` 변경 불가**(가격만) — 제공 시 `400 us-modify-quantity-not-supported` |
| `POST /api/v1/orders/{orderId}/cancel` | 주문 취소 | 체결된 주문은 취소 불가 |

### `POST /api/v1/orders` 요청 필드 (`OrderCreateRequest`)

`symbol`/`side`(`BUY`/`SELL`)/`orderType`(`LIMIT`/`MARKET`) 공통. 수량 지정 방식은 둘 중 정확히 하나:

| 필드 | 설명 | KR | US |
|---|---|---|---|
| `quantity` | 주문 수량(주 단위, 정수 문자열) | 사용 | 사용 |
| `orderAmount` | 주문 금액(달러) — 수량 대신 금액 지정, 체결수량은 시장가로 결정 | 미지원 | **US MARKET 전용**, 정규장 시간에만 가능(장외 호출 시 `422 amount-order-outside-regular-hours`). 봇은 `orderAmount` 미사용 (항상 `quantity` 정수 주문 — `docs/detail/toss_overseas_stock.md` "수량(주) 처리" 참조) |
| `price` | 지정가 가격 | 원 단위 정수. KRX 호가단위 안 맞으면 `400` | 달러 소수(센트 단위) |
| `timeInForce` | `DAY`(기본)/`CLS`(종가지정, LIMIT와 결합 시 LOC) | 둘 다 가능 | 둘 다 가능. 봇은 항상 `DAY` 기본값 사용 |
| `confirmHighValueOrder` | 1억 이상 주문 시 `true` 필수, 아니면 `400 confirm-high-value-required` | 적용 | 적용 — 봇이 이 플래그를 안 보내므로 **1억원 이상 고액 주문은 실패할 수 있음** (개선 여지, `exchange_adapter.py` `create_order` toss 분기) |
| `symbol` | 종목코드 | KRX 6자리 (`005930`) | 미국 티커 (`AAPL`) — `is_us_stock_ticker()` 판별 기준 |

## 알려진 봇 쪽 미연동 항목 (참고용, 우선순위 낮음)

- 고액주문 확인 플래그(`confirmHighValueOrder`) 미전송 → 1억원 이상 토스 주문 시 `400` 가능성.
- `buying-power`를 KRW로만 조회 → 해외주식 매수가능금액(USD) 사전 검증 없음, 주문 실패 시점에야 알게 됨.
- `sellable-quantity` 미조회 → 매도 시 보유 부족 여부를 토스 API 에러로만 확인.
- `market-calendar/US` 미연동 → 미국 장 휴장일에도 주문 시도(토스가 알아서 거부할 것으로 추정, 봇이 사전 차단은 안 함). KIS의 `is_kis_regular_session()` 같은 사전 가드 없음.

위 항목들은 기능은 동작하되 에러 사전 차단/사용자 안내가 약한 지점들 — 실제 사용 중 문제 생기면 우선 검토.
