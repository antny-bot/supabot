# Bot ↔ Manager API 계약 명세서 (API Contract)

작성일: 2026-11-14 · 상태: 확정 (Phase 2)

## 1. 아키텍처 원칙 및 역할 분담 (§0 확정 원칙 준수)

1. **Bot (Executor & Telegram Adapter)**:
   - 거래소 직접 통신(주문 생성/취소/상태조회/잔고/시세) 전담 (IP 화이트리스트 및 보안 키 관리).
   - 실시간 주문 상태 머신(`order_sync`) 및 긴급 안전장치(`trading_gate` / kill-switch, 손절, 장외 재주문)는 **봇 로컬에서 독자적으로 동작**.
   - Manager 장애/다운 시에도 봇의 주문 취소, kill-switch, 손절, 장외 재주문은 영향 없이 유지됨.
2. **Manager Backend (Brain)**:
   - 판단, 계획, 스케줄링(DCA, TOP N), 분석, LLM 자연어 처리, 예산 원장 정산.
   - 단일 진실 공급원(Single Source of Truth) DB 접근 주체.
3. **통신 채널**:
   - Bot → Manager: `src/core/manager_api_client.py` 단일 통로 사용.
   - Manager → Bot: `manager/backend/bot_client.py` 단일 통로 사용.

---

## 2. 인증 및 보안 계약 (HMAC-SHA256)

양방향 통신 모두 환경변수 `MANAGER_API_KEY`를 비밀키로 사용하는 HMAC-SHA256 서명 방식을 적용한다.

### 2.1 Bot → Manager 요청 헤더
- `X-Bot-User-Id`: 봇을 호출한 텔레그램 사용자 ID
- `X-Timestamp`: Unix Timestamp (초 단위 문자열)
- `X-Signature`: `HMAC_SHA256(MANAGER_API_KEY, "{timestamp}:{user_id}:{normalized_path}")`
- `X-Is-Admin`: 관리자 권한 여부 (`true` | `false`)
- **허용 윈도우**: 요청 시각 오차 ±300초 이내 유효.

### 2.2 Manager → Bot 요청 헤더
- `X-API-Key`: `MANAGER_API_KEY`
- `X-Timestamp`: Unix Timestamp (초 단위 문자열)
- `X-Signature`: `HMAC_SHA256(MANAGER_API_KEY, "{timestamp}" + body_bytes)`
- **허용 윈도우**: 요청 시각 오차 ±300초 이내 유효.

---

## 3. Manager → Bot 엔드포인트 목록 (`bot_client.py`)

기본 주소: `BOT_NOTIFY_URL` (예: `http://localhost:8765`)

| 엔드포인트 | 메서드 | 주요 파라미터 / 페이로드 | 목적 및 설명 | 멱등성 보장 |
|---|---|---|---|---|
| `/internal/notify` | POST | `chat_id, text, parse_mode` | 텔레그램 메시지 전송 | No (단순 메시지) |
| `/internal/execute_grid` | POST | `user_id, exchange, ticker, start_price, end_price, count, budget, template_id` | 거미줄 주문 배치 실행 | Yes (기존 주문 확인) |
| `/internal/execute_sgrid` | POST | `user_id, exchange, ticker, anchor_price, grid_count, step_pct, budget, template_id` | 스마트 거미줄 실행 | Yes |
| `/internal/execute_rsitrade` | POST | `user_id, exchange, ticker, buy_rsi, sell_rsi, budget, template_id` | RSI 매수 주문 실행 | Yes |
| `/internal/execute_dca` | POST | `user_id, exchange, ticker, budget, order_type, template_id, group_no, schedule_id, run_at` | DCA 1회 발주 실행 | **Yes (`schedule_id`+`run_at` 멱등키)** |
| `/internal/cancel_order` | POST | `user_id, exchange, uuid, ticker` | 거래소 미체결 주문 취소 | Yes (중복 취소 안전) |
| `/internal/sync_order` | POST | `user_id, exchange, uuid, ticker` | 주문 상태 즉시 동기화 | Yes |
| `/internal/wake_orders` | POST | `{}` | `order_sync` 즉시 기상 알림 | Yes |
| `/internal/force_update_order` | POST | `uuid, updates` | 봇 인메모리 주문 강제 갱신 | Yes |
| `/internal/get_prices` | POST | `requests: [{exchange, ticker}]` | 실시간 시세 일괄 조회 | Yes (Read Only) |
| `/internal/get_balances` | POST | `user_id, exchange` | 거래소 잔고 조회 | Yes (Read Only) |
| `/internal/backup/status` | GET | - | 봇 로컬 백업 상태 | Yes (Read Only) |
| `/internal/backup/trigger` | POST | - | 봇 로컬 백업 강제 실행 | Yes |
| `/internal/backup/download` | GET | `filename` | 봇 로컬 백업 파일 다운로드 | Yes (Read Only) |

---

## 4. Bot → Manager 엔드포인트 목록 (`manager_api_client.py`)

기본 주소: `MANAGER_BACKEND_URL` (예: `http://localhost:8000`)

| 엔드포인트 | 메서드 | 목적 및 데이터 | 멱등성 및 장애 시 대응 |
|---|---|---|---|
| `/api/orders` | GET | 유저 주문 목록 조회 | Read Only. 매니저 다운 시 봇 로컬 `order_manager.orders` 캐시 사용 |
| `/api/orders/{uuid}/cancel` | POST | 주문 취소 요청 | 취소 의도 전달. 봇 로컬 취소 우선 실행 가능 |
| `/api/templates` | GET / POST | 전략 템플릿 목록/생성 | 매니저 다운 시 텔레그램 "일시 사용 불가" 응답 |
| `/api/templates/{id}/start` | POST | 템플릿 시작 | 매니저 스케줄러 등록 |
| `/api/templates/{id}/stop` | POST | 템플릿 정지 | 매니저 스케줄러 중지 |
| `/api/dca` | GET / POST | DCA 스케줄 조회/생성 | 매니저 다운 시 "일시 사용 불가" |
| `/api/bot/nl` (Phase 4 신설) | POST | 텍스트 자연어 질의 분석 | LLM 분석 및 제안 액션 수신 |
| `/api/bot/view/{kind}` (Phase 7 신설)| GET | 텔레그램 렌더링용 뷰 데이터 | 렌더링 텍스트 수신 |
| `/api/internal/order-events` (Phase 6 신설) | POST | 체결/취소 이벤트 outbox 전송 | 멱등키: `uuid` + `filled_volume` |

---

## 5. 장애 격리 및 Degraded 모드 정책

1. **Manager가 완전히 다운된 경우**:
   - **봇의 안전 기능 유지 (100% 정상)**:
     - 텔레그램 `/halt`, `/resume` (kill-switch) 정상 동작.
     - 기존 체결 감시 및 손절(Stop-Loss), 트레일링 스톱 정상 동작.
     - 정규장 외 시간 만료 주문의 장외 재주문 정상 동작.
     - 텔레그램 수동 취소 명령 정상 동작.
   - **봇의 조회 기능 저하 (Degraded)**:
     - Manager REST 경유 조회 명령(`/orders`, `/templates` 등)은 *"⚠️ 서버 연결 지연으로 상세 조회를 가져올 수 없습니다. 봇 로컬 상태로 표시합니다"* 메시지와 함께 로컬 캐시를 보여주거나 일시 불가 안내.
2. **Bot이 완전히 다운된 경우**:
   - Manager 대시보드는 봇 상태를 'Offline'으로 표시.
   - 실주문이 수반되는 대시보드 액션(주문 취소, 즉시 실행 등)은 "봇 응답 없음 (오프라인)" 에러 반환.
