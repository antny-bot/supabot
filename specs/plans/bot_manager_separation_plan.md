# Bot ↔ Manager 역할 분리 및 Bot 경량화 계획

작성일: 2026-11-14 · 상태: 확정 (Phase 0부터 순차 진행)

## 0. 확정 아키텍처 전제 (2026-11-14)

> **이 절이 아래 §3~§8과 충돌하면 이 절이 우선한다.**

### 0.1 확정된 전제
1. **단일 멀티유저 봇 유지**: 봇 1개(`TELEGRAM_BOT_TOKEN` 1개)가 여러 사용자를 `user_id` 기준으로 격리해 동시 운영한다. (현재 코드가 이미 이 구조로 동작 중이므로 N개 봇 중복 실행 문제 없음.)
2. **거래소 호출은 봇에서만 수행**: IP 화이트리스트·인증 제약으로 실주문/시세/잔고 조회는 봇이 담당한다.
3. **DB 접근은 Manager API 경유 원칙 (예외 명시)**: 봇을 최대한 가볍게 유지하기 위해, 봇의 `get_db()` 직접 호출(16개 파일)을 단계적으로 제거하고 **Manager REST API**를 경유한다.
   - **단, 실시간 주문 추적(`orders`)과 `trading_gate`(kill-switch)는 봇 로컬 상태(메모리+로컬 SQLite/파일)로 유지**한다. `order_sync`가 매 주기마다 Manager API를 왕복하면 네트워크 지연/장애 시 손절·취소가 늦어지기 때문이다. 변경 이벤트만 Manager로 전송(outbox)한다.
4. **Manager 장애 시 동작 정책**:
   - DCA·시그널 알림 같은 **스케줄링(언제/얼마를 살지 판단)**을 Manager로 옮기면, Manager가 죽어 있는 동안 봇은 새 DCA를 시작하지 못한다(시세 조회 문제 때문이 아니라 **스케줄 두뇌가 Manager에 있기 때문**).
   - 대신 봇의 핵심 안전 기능(이미 걸린 주문의 체결 감시, 손절/트레일링, 장외 재주문, 수동 취소, `/halt`)은 Manager와 무관하게 계속 동작한다. Manager 복구 후 놓친 스케줄은 이월/알림으로 처리한다.

### 0.2 코드 검증 완료 사항 (§8 해소)
- **`/internal/order-events`**: `src/`와 `manager/backend/` 어디에도 구현이 없다(문서에만 존재). 실제 봇 내부 라우트는 `notify, execute_grid/sgrid/rsitrade/dca, cancel_order, sync_order, wake_orders, force_update_order, get_prices, get_balances, backup/*` 뿐이다. → 문서를 정정하고 Phase 6에서 신규 설계한다.
- **`DcaManager` 결합도**: `DcaManager`(430~735행)는 스케줄 상태 CRUD만 담당하고 주문 발행(`execute_due_dca_schedules`, 949행~)과 분리되어 있다. 파서·`compute_next_run_at`도 순수 함수라 Phase 1·5 분리가 수월하다.
- **LLM(Phase 4)**: 단일 신뢰 봇이므로, 봇에서 `google`/Gemini 의존성을 완전히 걷어내고 `POST /api/bot/nl`로 Manager에 이전하는 원래 계획대로 진행한다(Manager에도 이미 `crypto.py`가 존재하므로 키 복호화 가능 여부를 Phase 4 시작 시 확인).

---

## 1. 목표

> **Bot = 얇은 "실행기(Executor) + 텔레그램 UI 어댑터"**, **Manager Backend = "두뇌(판단·계획·집계·저장 로직)"**

- 봇은 상태가 적고, 재시작해도 안전하며, 코드 변경이 드물어야 한다 (실거래 경로이므로 변경 최소화가 곧 안전).
- 복잡한 로직(스케줄링, 예산, 분석, LLM, 백업, 리포트, 포맷팅)은 manager에서 테스트 가능한 순수 함수/서비스로 구현한다.
- 봇↔매니저 경계는 **명시적 API 계약**으로만 통신한다. DB 직접 접근 경로를 줄인다.

## 2. 현황 진단 (코드 근거)

| 영역 | Bot (`src/`) 현재 | Manager (`manager/backend/`) 현재 | 문제 |
|---|---|---|---|
| 규모 | `src/` 약 18k줄: dca_manager 1,336 / formatters 1,147 / nl_tools 823 / order_sync 881 / nl_intent_handlers 700 / internal_api 675 / main 663 | reports 1,836 / budget_manager 1,036 / progression_manager 817 | 봇이 전혀 가볍지 않음 |
| DB 직접 접근 | `get_db()` 사용 16개 파일 (order_manager 12, dca_manager 8, user_manager 7, trade_log 5 …) | 자체 `db.py` | 동일 테이블을 양쪽이 직접 읽고 씀 → 쓰기 주체 불명확 |
| 코드 공유 | — | `src/`를 **import 하지 않음** (import 0건) | 중복 구현 발생 (아래) |
| 중복 | `core/exchanges/common.py` 틱사이즈, `core/db.py`, `core/secret_crypto.py`, `core/backtest.py`, `core/budget_ledger.py` | `services/order_planner.py` 틱사이즈, `db.py`, `crypto.py`, `services/backtest_engine.py`, `services/budget_manager.py` | 로직 불일치 위험 (예: 호가 단위, 예산 정산) |
| 스케줄링 | `main.order_sync_loop`에서 `execute_due_dca_schedules`, `check_daily_cash_alerts`, `signal_analysis_loop`, `backup_loop` 모두 구동 | TOP N 스케줄러 + progression (단일 워커 락) | 스케줄러가 양쪽에 분산 |
| 양방향 호출 | `manager_api_client.request_manager_api` (nl_tools 12곳 + nl_intent 1곳) | `bot_client.py` (`execute_grid/sgrid/rsitrade/dca`, cancel, sync, wake, backup …) | 방향이 혼재, 일부는 이미 이상적 구조 |
| 백업 | `backup_manager.py`(561) + `gdrive_client.py`(340) | `routers/backup.py`(338) + `gdrive.py` | 양쪽 구현, 봇 경유 download 프록시 |
| 자연어(LLM) | `natural_language`, `nl_agent`, `nl_tools`, `nl_intent_handlers` ≈ 2.1k줄, 유저 Gemini 키 복호화 | `nl_logs` 조회만 | 가장 크고 복잡한 비실행 로직이 봇에 있음 |

> 이미 올바른 방향인 부분: ① manager가 `/internal/execute_dca`, `/internal/orders/wake`로 봇을 호출 ② `nl_tools`가 manager REST를 호출 ③ TOP N/예산/progression은 manager 소유. 이 패턴을 확장하는 것이 핵심이다.

## 3. 목표 책임 분배 (Target Architecture)

### 3.1 Bot에 남길 것 (Executor + UI adapter)

1. **텔레그램 I/O**: 명령 파싱(최소), 인증/권한 확인, 콜백 토큰, 응답 전송. 비즈니스 판단 없음.
2. **거래소 어댑터**: `core/exchanges/*`, `exchange_adapter`, websocket 시세 — API 키가 필요한 모든 실주문/조회 호출 (IP 화이트리스트 등 배포 제약이 있을 수 있으므로 봇에 유지, §8 가정 참고).
3. **주문 실행 프리미티브**: create / cancel / status / balances / ticker.
4. **주문 상태 머신(`order_sync`)**: 체결·취소·만료 감지, 장외 재주문, 손절/트레일링, kill-switch(`trading_gate`). *사후 정산(예산 원장, 연동 익절 가격 산정 등)은 manager로 위임* (Phase 6).
5. **내부 API(`internal_api`)**: manager가 호출하는 실행 엔드포인트 + 헬스/heartbeat.

### 3.2 Manager Backend로 이동할 것 (Brain)

| 이동 대상 | 현재 위치(Bot) | 이동 후 | 봇에 남는 것 |
|---|---|---|---|
| 자연어/LLM 에이전트 | `natural_language`, `nl_agent`, `nl_tools`, `nl_schema`, `ticker_disambiguation` 로직 | `POST /api/bot/nl` (텍스트 → 응답 텍스트 + 제안 액션) | 텍스트 전달, 제안 액션의 **확인 버튼 → 실행 API 호출** |
| DCA 스케줄링·현금 분석 | `dca_manager.py`(파서, `compute_next_run_at`, `execute_due_dca_schedules`, `analyze_user_cash_sufficiency`, `check_daily_cash_alerts`) | manager 스케줄러가 due 판정·주문 계획·예산 차감 → 봇 `/internal/execute_dca` 호출 | 단일 주문 실행 + 결과 반환 |
| 시그널 분석/알림 | `signal_analysis_loop`, `signal_engine`, `indicators`, `watch_handlers` | manager가 분석·알림 대상 판정 → `/internal/notify` 로 전송 | `/watch` 명령 → manager API |
| 백업 / Drive | `backup_manager`, `gdrive_client`, `/internal/backup/*` | manager `routers/backup.py` 단일화 | 봇 로컬 파일 폴백(`data/*.json`) 스냅샷 제공 엔드포인트 하나만 (필요 시) |
| 백테스트 | `core/backtest.py` | `services/backtest_engine.py`로 단일화 | 없음 |
| 예산 원장 | `core/budget_ledger.py` | `services/budget_manager.py`로 단일화, 봇은 이벤트만 전송 | 이벤트 발행 |
| 조회·리포트 렌더링 | `formatters.py`(1,147), `list_view_handlers`, `query_handlers`, `status_handlers` | `GET /api/bot/view/{orders,history,report,status,asset}` 가 **텔레그램용 텍스트/페이지**를 반환 | 받은 텍스트 전송, 페이징 콜백 |
| 유저/설정 CRUD | `user_manager` 대부분, `config_handlers` | manager `users` 라우터가 쓰기 주체. 봇은 캐시된 읽기 전용 | 읽기 캐시(TTL) |
| 종목명 해석 | `stock_resolver` | manager `stock_cache` 라우터 | API 호출 |

### 3.3 데이터 소유권 (Single Writer 원칙)

| 테이블 | 쓰기 주체 | 읽기 |
|---|---|---|
| `orders` (거래소 상태 필드: status, filled_volume, uuid, next_check_at) | **Bot** | Manager (읽기) |
| `orders` (의도 필드: `cancel_requested`, 전략 메타) | **Manager** | Bot |
| `trade_logs` | Bot이 이벤트 발행 → **Manager가 기록** (Phase 6) | 양쪽 |
| `budget_ledger`, `strategy_templates`, `dca_schedules`, `system_config`, `users` | **Manager** | Bot(읽기 전용 캐시) |
| `operational_events` | 양쪽 append-only | Manager |

## 4. 단계별 실행 계획

각 Phase는 **독립 배포·롤백 가능**해야 하며, 주문 경로 변경 Phase는 반드시 `docs/100_project_standards.md`의 테스트 규칙(라이브 API mock)을 지킨다.

### Phase 0 — 선행: 안정화 (이전 리뷰 P0)
`order_sync` 예외 격리, 손절 실패 시 추적 유지, `reload_from_db_async` 레이스 수정, 부분체결 trade 로그 누락 수정, 잔고 심볼 매칭 버그 수정. 이후 이동 작업의 회귀 안전망이 된다.

### Phase 1 — 공유 패키지 및 중복 제거 (저위험)
- `shared/` 에 순수 파이썬 패키지 `supabot_common` 신설: KRX/코인 틱사이즈, `secret_crypto`, 파서(`parsers`), 상수.
- 봇·매니저 양쪽 Dockerfile이 이 패키지를 설치/복사하도록 수정.
- `order_planner.get_tick_size`와 `exchanges/common.py` 구현을 하나로 통합하고 **동일 입력 동일 출력 테스트** 추가.
- 완료 기준: 중복 모듈 삭제, 양쪽 테스트 통과.

### Phase 2 — 계약 정의 (코드 변경 최소)
- `specs/` 또는 `docs/`에 **Bot↔Manager API 계약 문서** 작성: 엔드포인트, 인증(HMAC), 요청/응답 스키마, 멱등성 키, 타임아웃/재시도 정책.
- manager→bot, bot→manager 호출 목록을 표로 정리하고 `bot_client.py` / `manager_api_client.py`를 각각 **유일한 통로**로 고정.
- 양방향 실패 시 동작(매니저 다운 시 봇 degraded 모드: 조회 명령은 "일시 사용 불가", **주문 취소·kill-switch는 항상 동작**)을 명시.

### Phase 3 — 백업/백테스트/예산 중복 제거 (저~중위험)
- 백업·Drive를 manager로 단일화, 봇의 `backup_manager`·`gdrive_client` 제거 (봇 로컬 폴백 파일 스냅샷만 유지할지 먼저 결정).
- `core/backtest.py` → manager `backtest_engine`으로 통합.
- `core/budget_ledger.py` 의 봇 측 호출(`order_sync`의 `record_budget_adjust`, `_refund_unfilled_budget`)은 Phase 6에서 이벤트화하기 전까지 유지하되, 로직 원본은 한 곳으로 모은다.

### Phase 4 — 자연어/LLM 이전 (효과 최대, 중위험)
- manager에 `/api/bot/nl` 추가: `natural_language`, `nl_agent`, `nl_tools`를 이동. `nl_tools`의 `request_manager_api` HTTP 왕복이 **함수 직접 호출**로 바뀌어 단순해진다.
- 응답 스키마: `{reply_text, proposed_actions:[{action_id, kind, params, confirm_text}]}`.
- 봇의 `nl_intent_handlers`는 텍스트 전달 + 확인 버튼 → 기존 실행 API 호출만 남긴다. Gemini 키 복호화는 manager에서만 수행 (봇에서 키 접근 제거 = 보안 이점).
- 완료 기준: 봇 `src/`에서 `google`/Gemini 의존성 제거, `nl_*` 파일 삭제.

### Phase 5 — DCA 스케줄러 이전 (중~고위험, 실거래 경로)
- manager 스케줄러(기존 단일 워커 락 `_acquire_scheduler_lock` 재사용)가 `dca_schedules` due 판정·`compute_next_run_at`·이월(carryover) 판단·예산 사전 차감·현금 분석/일일 알림을 수행.
- 실제 발주는 `bot_client.execute_dca` → 봇 `/internal/execute_dca` (이미 존재). **멱등성 키(schedule_id + run_at)** 를 추가해 재시도 시 중복 주문 방지.
- 봇은 `execute_due_dca_schedules` 루프 제거. 전환은 **feature flag**(`DCA_SCHEDULER=manager|bot`)로 점진 전환하고, 두 스케줄러가 동시에 돌지 않도록 DB 락/플래그로 상호배제.
- **Manager 장애 시 정책**: Manager가 내려가 있는 동안 새 DCA는 실행되지 않으며(봇에 폴백 스케줄러를 두지 않음), Manager 복구 후 누락 회차를 이월(`carryover`) 또는 사용자 알림으로 처리한다.
- 파서(`parse_dca_schedule` 등)는 Phase 1의 shared 패키지로 이동 (봇 `/dca` 명령과 manager가 같은 파서를 사용).

### Phase 6 — order_sync 슬림화와 이벤트화 (고위험, 마지막)
- 봇은 체결/취소/만료 **이벤트만 발행** (`POST /api/internal/order-events`, 멱등 키 = uuid + filled_volume).
- manager가 `trade_logs` 기록, 예산 정산(`BUY_ORDER_ADJUST`, `ORDER_CANCEL_REFUND`), 연동 익절 **가격 산정**을 수행하고, 필요 시 봇에 `create_order` 지시.
- 이벤트 전달 실패 대비: 봇 로컬 outbox(파일/SQLite) + 재전송. 이 보장이 없으면 이 Phase를 진행하지 않는다.
- 손절·트레일링·장외 재주문·kill-switch는 **지연 민감**하므로 봇에 유지한다 (매니저 장애 시에도 보호 동작).

### Phase 7 — 핸들러 씬화 및 문서 정리
- `formatters.py`·`list_view_handlers`·`query_handlers`의 렌더링을 manager `GET /api/bot/view/*`로 이전, 봇은 텍스트 중계 + 페이징 콜백.
- 봇 `get_db()` 직접 호출(`users`, `dca_schedules`, `strategy_templates`, `budget_ledger`, `trade_logs` 등)을 단계적으로 제거하고 **Manager REST API 경유**로 전환한다. (예외: 실시간 주문 추적 `orders`·`trading_gate`는 봇 로컬 상태 유지, heartbeat만 최소 유지.)
- `docs/200_system_architecture.md`, `AGENTS.md` 모듈 맵 갱신.

## 5. 우선순위와 효과

| Phase | 위험 | 봇 코드 감소(대략) | 비고 |
|---|---|---|---|
| 0 | 중 | 0 | 선행 필수 |
| 1 | 낮음 | 소폭 | 이후 모든 Phase의 기반 |
| 2 | 낮음 | 0 | 문서·계약 |
| 3 | 낮음~중 | ~0.9k줄 | 중복 제거 |
| 4 | 중 | ~2.1k줄 | 효과 최대 |
| 5 | 중~높음 | ~1.3k줄 | 멱등성 필수 |
| 6 | 높음 | ~0.3k줄 + 구조 단순화 | outbox 선결 |
| 7 | 중 | ~1.5k줄 | UI 중계화 |

## 6. 리스크와 완화

| 리스크 | 완화 |
|---|---|
| manager 장애 시 봇 기능 마비 | 취소/kill-switch/손절은 봇 단독 동작. 조회는 degraded 메시지 |
| 이벤트·요청 중복/유실로 이중 주문·예산 오차 | 모든 변경 API에 멱등성 키, outbox 재전송, 예산 원장 항등식 점검 테스트 |
| 두 스케줄러 동시 실행 | feature flag + DB 락, 전환 시 한쪽 비활성 확인 |
| 지연 증가 | 판단 로직이 이동해도 실행 경로의 동기 HTTP 왕복은 1회 이내로 제한, 타임아웃/재시도 정책 명시 |
| 실계좌 사고 | 각 Phase 별 `pytest` 전체 통과, 라이브 API mock, 소액/paper(KIS) 검증 후 배포, 직전 이미지 태그로 롤백 가능하게 유지 |
| 인증 경계 확대 | HMAC(timestamp 포함) 유지, 재전송 방지 윈도우, 키 로테이션 절차 문서화 |

## 7. 완료 기준 (Definition of Done)

- 봇 `src/`에 LLM·백업·백테스트·예산 원장·스케줄러(DCA/시그널) 코드가 없다.
- 봇의 DB 접근은 `orders` 상태와 heartbeat로 한정된다 (또는 Repo 인터페이스 뒤에 있다).
- 틱사이즈·암호화·파서는 `shared/` 단일 구현이다.
- Bot↔Manager API 계약 문서가 존재하고 양쪽 클라이언트가 이를 따른다.
- 매니저를 내려도 봇의 취소·kill-switch·손절·재주문이 동작한다 (테스트로 증명).
- 문서(`docs/200`, `AGENTS.md`)가 최신 구조를 반영한다.

## 8. 분석 한계 및 개발 전 확인 사항

이 계획은 `order_sync.py`·`order_manager.py` 전체, `main.py`/`internal_api.py`/`dca_manager.py`(400~735행)/`progression_manager.py`의 구조와 import 관계를 근거로 작성했다.

1. ~~거래소 호출이 봇에만 있어야 하는 이유~~ → **확정** (§0.1: 봇 전용, 단일 멀티유저 봇 유지).
2. ~~`/internal/order-events`의 현재 방향과 페이로드~~ → **확인 완료** (§0.2: 코드에 미구현, Phase 6에서 신규 설계).
3. ~~`dca_manager.py`의 `DcaManager`와 `execute_due_dca_schedules` 결합도~~ → **확인 완료** (§0.2: 상태 CRUD와 실행이 분리되어 있음).
4. **미확인 — Phase 4 시작 전 검증 필요**: manager가 `manager/backend/crypto.py`로 유저의 Gemini API 키를 복호화해 LLM을 직접 호출할 수 있는지, 환경변수(`USER_SECRET_KEY`) 공유 여부 확인.
5. **범위 외**: 프론트엔드·`reports.py`(1,836줄)는 분리 대상이 아니라 별도 리팩토링 대상으로 둔다.

---

## 9. Gemini 개발 진행용 프롬프트

아래 블록을 그대로 Gemini(Antigravity)에 붙여 넣어 **Phase 단위로** 진행한다. 한 번에 한 Phase만 요청할 것.

````text
너는 supabot 프로젝트(E:\apps\supabot)의 개발자다. 모든 답변과 문서는 한글로 작성한다.

[필독]
1. AGENTS.md 와 docs/100_project_standards.md 를 먼저 읽고 안전 규칙을 지켜라. (모든 주문 경로는 실거래, 테스트에서 라이브 API 호출 금지, 키/시크릿 로그 노출 금지, UTF-8, 검증은 docker compose run --rm supabot python -m pytest tests/)
2. specs/plans/bot_manager_separation_plan.md 를 끝까지 읽어라. 특히 "§0 확정 아키텍처 전제"가 §3~§8과 충돌하면 §0이 우선한다(단일 멀티유저 봇 유지 + DB 접근은 Manager API 경유 원칙, 단 실시간 주문 상태·kill-switch는 봇 로컬 유지). 목표는 "Bot = 얇은 실행기 + 텔레그램 어댑터, Manager Backend = 판단/계획/집계 두뇌" 로의 분리다.

[이번 작업]
계획서의 "Phase {N}: {제목}" 만 수행한다. (다른 Phase는 건드리지 않는다.)

[진행 방식]
1. 먼저 계획서 §8의 "확인 사항" 중 이번 Phase와 관련된 항목을 실제 코드에서 검증하고, 결과와 계획 수정 필요 여부를 요약해 보고하라. 가정이 틀렸다면 구현 전에 나에게 질문하라.
2. 구현 계획(변경 파일, 새 API 스키마, 멱등성 키, feature flag, 롤백 방법)을 짧게 제시하고 내 승인을 기다려라. 주문 경로(order_sync, order_execution, dca_manager, exchanges/*)를 수정하는 Phase(0, 5, 6)는 반드시 승인 후 진행한다.
3. 승인 후 작은 단위로 구현한다. 원칙:
   - 동작 보존 리팩토링과 기능 변경을 같은 커밋에 섞지 않는다.
   - 이동하는 로직은 먼저 manager/shared 쪽에 테스트와 함께 구현 → 봇에서 호출 전환(feature flag) → 안정화 후 봇 쪽 코드 삭제 순서로 한다.
   - 모든 변경성 API에는 멱등성 키를 둔다. 이벤트/요청 유실·중복 시나리오 테스트를 작성한다.
   - Manager가 내려가도 봇의 주문 취소, kill-switch, 손절, 장외 재주문은 동작해야 한다.
   - 요청된 범위 밖의 코드는 수정하지 않는다. 불필요한 추상화를 만들지 않는다.
4. 검증: 관련 테스트 추가 + 전체 pytest 통과 + manager 는 python -m py_compile backend/**/*.py, 프론트엔드 변경 시 타입체크/테스트. 라이브 거래소 호출은 모두 mock 한다.
5. 완료 후: docs/200_system_architecture.md 모듈 맵, AGENTS.md 인덱스, 관련 docs/20x 문서를 갱신하고, 변경 요약 / 삭제된 파일 / 남은 리스크 / 롤백 방법을 보고하라.

[Phase 0을 요청하는 경우 상세]
src/core/order_sync.py, order_manager.py 에서 다음을 수정하고 각각 회귀 테스트를 추가하라:
 (a) sync_orders 메인 루프 주문 단위 예외 격리 + _fetch_status 의 asyncio.gather(return_exceptions=True)
 (b) _apply_stop_loss: 손절 주문 발행 실패 시 remove_order 하지 말고 추적 유지·재시도, create_order 예외 처리, 수량 round_volume 적용
 (c) OrderManager.reload_from_db_async: DB 읽기 중 add_order 된 주문이 교체 시 유실되지 않도록 병합
 (d) _process_order_fill: 만료→재주문 대기 전환 전에 exec_vol>0 부분 체결분 append_trade 기록 (replace_order_uuid 이후 체결량 의미를 먼저 확인할 것)
 (e) _create_linked_sell_order 잔고 심볼 매칭을 정규화한 정확 일치로 변경 (빈 문자열 endswith 버그)
 (f) 연동 매도 no_price/failed 재시도 횟수 제한 + 알림

[시작]
Phase {N}부터 시작해라. 먼저 1번(확인 사항 검증 보고)부터 수행하라.
````
