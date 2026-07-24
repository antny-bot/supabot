# toss_api_reference.md — 토스증권 OpenAPI 요약

**원본**: `docs/toss.json` (OpenAPI 3.0 스펙, 6400+줄). 봇 사용 엔드포인트 요약. **세부 스키마/에러코드/example 필요시 `docs/toss.json`에서 `operationId` 또는 path 검색**. KR/US 차이점 개요용.

토스증권 어댑터 코드는 `src/core/exchange_adapter.py` (`docs/201_exchange_adapter.md`), 해외주식 통화 분기는 `docs/303_toss_overseas_stock.md` 참조.

## 인증

`POST /oauth2/token` — OAuth2 client_credentials. 코드: `_get_toss_token()`.

## 시장 데이터 (인증 불필요, `need_account=False`)

| 메서드/경로 | 설명 | 비고 |
|---|---|---|
| `GET /api/v1/prices?symbols=` | 현재가 조회 | 봇 `get_ticker` 사용. KR/US 응답 동일, `currency` 필드 구분 |
| `GET /api/v1/candles?symbol=&interval=&count=&before=&adjusted=` | OHLCV 캔들, 최대 200봉 | 봇 `_get_toss_candles` 사용 |
| `GET /api/v1/orderbook?symbol=` | 호가 조회 | 봇 미사용 |
| `GET /api/v1/trades?symbol=&count=` | 최근 체결 내역(공개 시세) | 봇 미사용 — `/history`는 `/api/v1/orders`(본인 주문) 사용 |
| `GET /api/v1/price-limits?symbol=` | 상/하한가 조회 | 봇 미사용 |
| `GET /api/v1/stocks?symbols=` | 종목 기본 정보 | 봇 미사용 (종목코드 resolve는 `stock_resolver.py` KIS 검색API 처리) |
| `GET /api/v1/stocks/{symbol}/warnings` | 매수 주의사항 조회 | 봇 미사용 |
| `GET /api/v1/exchange-rate?dateTime=&baseCurrency=&quoteCurrency=` | KRW↔USD 환율(참고용, 1분 갱신) | 봇 미사용 — 손익 계산 환율 미적용(USD 별도 합계 표시, `docs/303_toss_overseas_stock.md` 참조) |
| `GET /api/v1/market-calendar/KR?date=` / `.../US?date=` | 국내/해외(미국) 장 운영시간 조회 | 봇 미사용. KIS는 자체 `is_kis_regular_session()` 사용 — Toss 장외 체크 없음(향후 버그 가능) |

## 계좌/잔고 (인증 필요, `X-Tossinvest-Account` 헤더)

| 메서드/경로 | 설명 | 비고 |
|---|---|---|
| `GET /api/v1/accounts` | 계좌 목록 조회 | `accountSeq` 획득용. 봇 `_get_toss_account_seq()` 최초 1회 호출 후 저장 |
| `GET /api/v1/holdings?symbol=` | 보유 주식 조회 (KR+US) | 봇 `get_balances` 사용. 종목별 `currency` 필드 포함 |
| `GET /api/v1/buying-power?currency=` | 매수 가능 금액 (현금) | 봇 `currency=KRW`만 조회 — **USD 매수가능금액 별도 조회 안 함** |
| `GET /api/v1/sellable-quantity?symbol=` | 매도 가능 수량 조회 | 봇 미사용 — 매도 시 보유량 검증 없이 바로 주문 |
| `GET /api/v1/commissions` | 시장별(국내/해외) 수수료율 조회 | 봇 미사용 — `/report` 손익 수수료 미반영 |

## 주문

| 메서드/경로 | 설명 | KR vs US 차이 |
|---|---|---|
| `GET /api/v1/orders?status=&symbol=&from=&to=&cursor=&limit=` | 주문 목록 조회 | `status`는 `OPEN`/`CLOSED`만 허용 |
| `POST /api/v1/orders` | 주문 생성 | 아래 표 참조 |
| `GET /api/v1/orders/{orderId}` | 주문 단건 조회 | — |
| `POST /api/v1/orders/{orderId}/modify` | 주문 정정 | KR: `quantity` 필수(정수). **US: `quantity` 변경 불가**(가격만) — 전달 시 `400 us-modify-quantity-not-supported` |
| `POST /api/v1/orders/{orderId}/cancel` | 주문 취소 | 체결 주문 취소 불가 |

### `POST /api/v1/orders` 요청 필드 (`OrderCreateRequest`)

`symbol`/`side`(`BUY`/`SELL`)/`orderType`(`LIMIT`/`MARKET`) 공통. 수량 지정 방식은 둘 중 하나:

| 필드 | 설명 | KR | US |
|---|---|---|---|
| `quantity` | 주문 수량(주, 정수 문자열) | 사용 | 사용 |
| `orderAmount` | 주문 금액(달러) — 수량 대신 금액 지정 | 미지원 | **US MARKET 전용**, 정규장 가능(장외 호출 시 `422 amount-order-outside-regular-hours`). 봇 `orderAmount` 미사용 (항상 `quantity` 정수 주문 — `docs/303_toss_overseas_stock.md` 참조) |
| `price` | 지정가 가격 | 원 단위 정수. 호가 단위 불일치 시 `400` | 달러 소수(센트 단위) |
| `timeInForce` | `DAY`(기본)/`CLS`(종가지정, LIMIT 결합 시 LOC) | 둘 다 가능 | 둘 다 가능. 봇은 `DAY` 사용 |
| `confirmHighValueOrder` | 1억 이상 주문 시 `true` 필수, 누락 시 `400 confirm-high-value-required` | 적용 | 적용 — 미전송으로 **1억원 이상 주문 실패 가능** (`exchange_adapter.py` `create_order` toss 분기) |
| `symbol` | 종목코드 | KRX 6자리 (`005930`) | 미국 티커 (`AAPL`) — `is_us_stock_ticker()` 판별 |

## 알려진 봇 쪽 미연동 항목 (참고용, 우선순위 낮음)

- 고액주문 확인 플래그(`confirmHighValueOrder`) 미전송 → 1억원 이상 토스 주문 시 `400` 가능성.
- `buying-power` KRW만 조회 → 해외주식 매수가능금액(USD) 사전 검증 없음, 실패 시점 확인.
- `sellable-quantity` 미조회 → 매도 시 보유 부족 여부 API 에러로만 확인.
- `market-calendar/US` 미연동 → 휴장일 주문 시도(토스 자체 거부). KIS `is_kis_regular_session()` 사전 가드 없음.

사전 차단/안내 약함 — 문제 발생 시 검토.
