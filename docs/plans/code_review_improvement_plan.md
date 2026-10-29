# 코드 리뷰 기반 개선 개발 계획서

> 대상 구현자: Gemini (AI 에이전트) · 작성일: 2026-10-29
> 근거: 2026-10-29 코드 리뷰 (보안 / 안정성 / 성능 / 기능 확장)

---

## 0. 작업 전 필수 규칙 (반드시 준수)

작업 전 [AGENTS.md](file:///E:/apps/supabot/AGENTS.md)와 [100_project_standards.md](file:///E:/apps/supabot/docs/100_project_standards.md)를 정독한다.

1. **모든 주문 경로는 실거래다.** `create_order`, `cancel_order`, `_create_kis_order` 등을 테스트에서 실제 호출하면 실주문이 나간다. 테스트에서는 `_run_upbit_cli`, `_request_bithumb`, `_request_kis` 등을 **반드시 mock** 한다.
2. **시크릿 평문 노출 금지.** 로그·에러 응답·커밋에 API 키, `SESSION_SECRET`, `MANAGER_API_KEY`, `SUPABASE_SERVICE_KEY`를 남기지 않는다. `config/.env`, `manager/.env`는 건드리지 않는다.
3. **UTF-8** 인코딩으로 파일을 읽고 쓴다(한글 주석 유지). 변경과 무관한 기존 주석·docstring은 보존한다.
4. **최소 변경 원칙.** 각 작업 항목(Task)은 별도 커밋 단위로 진행하고, 요청 범위 밖의 리팩터링은 하지 않는다.
5. **검증 (호스트에 Python 없음 → Docker 사용)**
   ```bash
   docker compose run --rm supabot python -m pytest tests/
   docker compose run --rm supabot python -m py_compile src/main.py
   # manager 변경 시
   cd manager && python -m py_compile backend/**/*.py
   ```
   - 플래그 없이 `pytest tests/`만 실행한다(`pytest.ini`의 `addopts` 적용, `-v` 금지).
   - 주문·거래소·KIS 로직을 변경하면 **전체 테스트 통과가 필수**다.
6. 기능 추가 시 관련 문서(`docs/2xx`, `docs/102a_roadmap_future.md` 체크박스)를 함께 갱신한다.
7. 각 Task는 **"완료 조건(Acceptance Criteria)"을 모두 충족**하고, 해당 **테스트를 추가**해야 완료다.

### 진행 순서 및 우선순위

| 단계 | Task | 영역 | 위험도 |
|------|------|------|--------|
| 1 | S1~S5 | 보안 설정 | 낮음 (변경 작고 효과 큼) |
| 2 | R1, R2 | 주문 저장 순서 · RSI 무한루프 | 중간 (주문 경로) |
| 3 | P1~P3 | 성능 | 중간 |
| 4 | Q1~Q3 | 코드 품질 · 리팩터링 | 중간~높음 (회귀 위험) |
| 5 | F1~F6 | 기능 확장 | 가변 |

> ⚠️ 단계 2~4는 주문 경로를 건드린다. 변경 전후 `tests/test_sync_orders.py`, `tests/test_order_execution.py`를 반드시 통과시킨다.

---

## 1단계. 보안 (Security)

### S1. 세션 시크릿 기본값 제거

- **파일**: [manager/backend/main.py](file:///E:/apps/supabot/manager/backend/main.py) (약 19~23행)
- **문제**: `SESSION_SECRET` 미설정 시 `"change-me-in-production"`으로 동작한다. 세션 쿠키 위조가 가능하다.
- **변경**
  - 기본값을 제거하고, 환경변수가 없거나 빈 값이거나 `"change-me-in-production"`이면 **기동 시 `RuntimeError`** 를 발생시킨다.
  - 테스트에서 import가 깨지지 않도록 `os.environ.setdefault("SESSION_SECRET", "test-secret-...")`를 `tests/conftest.py`(없으면 신설) 또는 각 manager 테스트 상단에서 설정한다. 기존 manager 테스트를 모두 확인한다.
- **완료 조건**
  - 시크릿 미설정 시 앱 import/기동이 명확한 메시지로 실패한다.
  - 기존 `tests/test_manager_*.py` 통과.
  - `config/.env.template`, `manager/.env` 템플릿(있다면), `docs/101_user_onboarding.md`에 필수 항목임을 명시한다.

### S2. 세션 쿠키 보안 옵션 + CSRF 방어

- **파일**: [manager/backend/main.py](file:///E:/apps/supabot/manager/backend/main.py), `manager/backend/routers/*.py`
- **문제**: `SessionMiddleware`에 `https_only`, `same_site`가 없다(로드맵 Phase 8 "세션 보안" 미완료).
- **변경**
  - `SessionMiddleware(..., same_site="lax", https_only=<환경변수 SESSION_HTTPS_ONLY, 운영 기본 True>, max_age=86400)`.
    - 로컬 개발(HTTP)용으로 `SESSION_HTTPS_ONLY=false`를 허용하되 **운영 기본값은 True**.
  - 상태 변경 요청(POST/PUT/PATCH/DELETE, `/api/*`)에 대해 **Origin/Referer 검증 미들웨어**를 추가한다. 허용 Origin은 환경변수 `MANAGER_ALLOWED_ORIGINS`(쉼표 구분)로 지정한다. 단, 봇이 호출하는 `/api/realtime/trigger`(API Key 인증)는 예외로 한다.
- **완료 조건**
  - 허용되지 않은 Origin의 POST 요청은 403이다.
  - 로그인과 기존 API 흐름이 정상이다(프론트 `fetch`가 동일 Origin이므로 영향이 없어야 한다).
  - 신규 테스트: 허용/비허용 Origin, API Key 경로 예외.

### S3. 내부 API Key 상수시간 비교 + 서명 통일

- **파일**: [manager/backend/main.py](file:///E:/apps/supabot/manager/backend/main.py) `realtime_trigger` (약 78~89행), [src/internal_api.py](file:///E:/apps/supabot/src/internal_api.py) `trigger_realtime_sync`
- **문제**: `request.headers.get("X-API-Key") != api_key`는 타이밍 공격에 취약하다.
- **변경**
  - **1차(필수)**: `hmac.compare_digest(provided.encode(), api_key.encode())`로 교체한다. `provided`가 None이면 빈 문자열로 처리한다.
  - **2차(선택)**: 봇 `_verify_webhook_request`와 동일한 `X-Timestamp`/`X-Signature` HMAC 방식으로 통일한다. 이 경우 `trigger_realtime_sync`와 `manager/backend/bot_client.py`의 서명 로직을 공통 헬퍼로 정리한다. 하위호환이 필요하면 헤더 방식을 한 릴리스 동안 병행 지원한다.
- **완료 조건**: 잘못된/누락된 키는 401이다. 올바른 키는 200이다. `compare_digest`를 사용한다.

### S4. 예외 메시지 외부 노출 차단

- **파일**: [src/internal_api.py](file:///E:/apps/supabot/src/internal_api.py) (`_internal_notify_handler`, `_internal_execute_grid_handler`, `_internal_execute_rsitrade_handler` 등 `text=str(e)`를 쓰는 모든 곳), `manager/backend/routers/*.py`
- **문제**: `Response(status=500, text=str(e))`로 예외 문자열이 그대로 반환된다. 내부 정보나 시크릿이 섞일 수 있다.
- **변경**
  - 클라이언트에는 `"Internal error"` 같은 **고정 메시지**만 반환한다. 예외 상세는 `_log.warning/error(..., exc_info=e)`로 서버 로그에만 남긴다.
  - 입력 검증 실패(400)의 사용자용 한글 메시지(예: 최소 주문 금액 안내)는 **유지**한다. 대상은 *예기치 못한 예외* 경로뿐이다.
  - `grep -rn "str(e)" src/internal_api.py manager/backend`로 대상을 전수 확인한다.
- **완료 조건**: 500 응답 본문에 예외 문자열이 없다. 로그에는 남는다. `tests/test_internal_api_webhook_auth.py` 통과 + 신규 테스트(예외 유도 시 본문 검증).

### S5. 웹훅 IP 화이트리스트 강화

- **파일**: [src/internal_api.py](file:///E:/apps/supabot/src/internal_api.py) `_verify_webhook_request` (약 46~92행)
- **문제**
  - `ALLOWED_WEBHOOK_IPS`가 비어 있으면 IP 검증을 건너뛴다.
  - `127.0.0.1`은 항상 허용된다. 리버스 프록시 뒤에서는 외부 요청도 로컬로 보이므로 우회 경로가 된다.
- **변경**
  - HMAC 검증은 **항상 필수**로 유지한다(이미 그렇다).
  - `ALLOWED_WEBHOOK_IPS` 미설정 시 기동 로그에 **WARNING 1회**(HMAC만으로 보호 중임을 알림)를 남긴다.
  - 로컬호스트 항상 허용은 `WEBHOOK_ALLOW_LOOPBACK`(기본 `true`, 하위호환)으로 제어 가능하게 한다. 문서(`docs/205b_security_logging.md`)에 프록시 환경 주의사항을 기록한다.
  - CIDR 지원(`ipaddress.ip_network`)을 추가한다.
- **완료 조건**: CIDR 허용/차단 테스트, loopback 비허용 설정 테스트를 추가한다. 기존 테스트는 통과한다.

---

## 2단계. 안정성 (Reliability)

### R1. 주문 DB 쓰기 순서 보장 (`replace_order_uuid`)

- **파일**: [src/core/order_manager.py](file:///E:/apps/supabot/src/core/order_manager.py) `_db_upsert`, `_db_delete`, `replace_order_uuid`
- **문제**: `replace_order_uuid`는 `_db_delete(old)`와 `_db_upsert(new)`를 **서로 독립된 fire-and-forget 태스크**로 보낸다. 실행 순서가 보장되지 않는다. 또한 실패 시 `enqueue_task`로 보내는 폴백 경로가 순서를 무시한다. 이 때문에 새 주문이 DB에서 사라지거나 중복 추적될 수 있다.
- **변경**
  - 순서가 중요한 연산을 위해 **직렬화된 쓰기 큐**를 도입한다: 내부 `asyncio.Queue`와 단일 워커, 또는 `uuid` 단위 `asyncio.Lock`으로 같은 주문에 대한 쓰기를 순차 처리한다.
  - `replace_order_uuid`는 **"신규 upsert 성공 → 구 uuid delete"** 순서를 하나의 코루틴(`_run_replace`)에서 수행한다. 실패 시 `enqueue_task`에 **두 작업을 순서대로** 적재한다.
  - `flush_pending_writes()` 의미(모든 쓰기 완료 대기)는 유지한다. 기존 `_track_task` 강한 참조 패턴도 유지한다.
  - 이벤트 루프가 없는 동기 폴백 경로(`RuntimeError` 분기)의 동작은 유지한다.
- **완료 조건**
  - 신규 테스트(DB는 mock): `replace_order_uuid` 호출 시 upsert가 delete보다 먼저 await 되는지 검증한다. upsert 실패 시 delete가 **호출되지 않는지** 검증한다(구 주문 보존).
  - `tests/test_order_manager_reload.py`, `tests/test_sync_orders.py` 통과.

### R2. RSI 역산 탐색의 무한루프 방지 및 저가 종목 정확도

- **파일**: [src/core/signal_engine.py](file:///E:/apps/supabot/src/core/signal_engine.py) `_search_price_for_target_rsi` (약 128~198행)
- **문제**
  - ask 분기 `while high_rsi < target_rsi: high *= 1.02`는 상한이 없다. 목표 RSI가 100에 가깝거나 데이터가 특이하면 끝나지 않는다.
  - bid 분기 `while low > 1 and low_rsi > target_rsi`는 가격이 1 미만인 종목에서 조건이 처음부터 거짓이 되어 부정확하다.
  - 1단계 역산의 `except Exception: pass`는 실패를 조용히 삼킨다.
- **변경**
  - 두 `while`에 **최대 반복 횟수(예: 200회)** 와 **가격 경계**(bid는 `low > current_price * 1e-4`, ask는 `high < current_price * 10`)를 둔다. 한도에 도달하면 경계값을 반환한다. 또는 `None`을 반환하고 `get_price_by_rsi`가 `None`(레그 건너뜀)을 반환하도록 한다. **후자를 권장**한다. 이상한 가격으로 실주문이 나가는 것을 막기 때문이다.
  - bid의 `low > 1` 조건은 상대 경계로 대체한다.
  - `except Exception: pass`에서 `_log.debug(...)`로 원인을 남긴다.
- **완료 조건**
  - 극단 RSI 목표(예: 99.9, 0.1)와 평탄한 가격 시계열에서도 **유한 시간 내 종료**한다.
  - 정상 케이스 결과는 기존과 동일하다. `tests/test_signal_engine.py` 통과 + 경계 테스트를 추가한다.

---

## 3단계. 성능 (Performance)

### P1. 레그별 RSI 중복 계산 제거

- **파일**: [src/core/signal_engine.py](file:///E:/apps/supabot/src/core/signal_engine.py) `get_price_by_rsi`, [src/core/order_execution.py](file:///E:/apps/supabot/src/core/order_execution.py) `execute_rsitrade_orders`, `execute_sgridrsi_orders`
- **문제**: 레그(`count`건)마다 `get_price_by_rsi`가 `get_rsi`를 호출해 캔들 조회와 RSI 계산을 반복한다.
- **변경**
  - `get_price_by_rsi`에 선택 인자 `_precomputed=(current_rsi, df)`를 추가하거나, `get_prices_by_rsi(exchange, ticker, targets, side, ...)` **배치 메서드**를 신설한다(캔들 1회 조회 → 목표 RSI 리스트 전체 계산). 기존 시그니처는 하위호환으로 유지한다.
  - `leg_fn`에서 배치 결과를 사용한다. 매 호출 전에 `await` 가능한 구조를 유지한다.
- **완료 조건**: `count=10`일 때 `get_candles` 호출이 1회다(mock 호출 횟수로 검증). 가격 결과는 기존과 동일하다.

### P2. `sync_orders` 거래소 조회 병렬화

- **파일**: [src/main.py](file:///E:/apps/supabot/src/main.py) `sync_orders` (556행~)
- **문제**: 주문마다 순차 `await`라 주문이 많을수록 사이클이 길어진다.
- **변경**
  - **Q1(리팩터링)을 먼저 완료한 후** 진행한다.
  - 거래소(및 유저)별 `asyncio.Semaphore`로 동시성을 제한(예: 거래소당 3~5)해 **상태 조회만** 병렬화한다.
  - **주문 상태 변경·주문 생성·체결 후 연동 매도 같은 쓰기 로직은 순차를 유지**한다. 중복 발행 방지가 우선이다.
  - 거래소 레이트 리밋(`docs/201_exchange_adapter.md` 참고)을 넘지 않도록 한다.
- **완료 조건**: 기존 `tests/test_sync_orders.py` 전부 통과, 동시성 한도 테스트를 추가한다.

### P3. `save_orders` 전체 upsert 축소

- **파일**: [src/core/order_manager.py](file:///E:/apps/supabot/src/core/order_manager.py) `save_orders`
- **변경**: `grep`으로 호출 지점을 확인한다. 개별 `_db_upsert`로 대체 가능하면 대체하고, 필요한 곳에만 남긴다. 남길 경우 변경된 주문(dirty set)만 upsert한다.
- **완료 조건**: 동작 동일, 호출 빈도 감소(테스트 또는 로그로 확인).

---

## 4단계. 코드 품질 (Quality)

### Q1. `sync_orders` 분해 (약 350줄 → 단계별 함수)

- **파일**: [src/main.py](file:///E:/apps/supabot/src/main.py) 556~907행 → 신규 `src/core/order_sync.py` (또는 main.py 내 private 함수)
- **원칙**: **동작 변화 없는 순수 리팩터링.** 단계 분리 → 각 단계 단위 테스트 → 기존 테스트 통과 순서로 진행한다.
- **제안 분해**
  1. `_cleanup_stale_caches(active_uuids)` — `_limit_warned_orders`, `_reorder_failures`, `_status_check_failures` 정리
  2. `_handle_market_closed(ord, ex_obj)` — 장외 상태 및 `next_check_at` 갱신
  3. `_submit_reserved_or_reorder(ord, ...)` — 예약/재주문 제출, 상하한가 검증, 중복 방지
  4. `_detect_fills(ord, ...)` — 체결 감지
  5. `_apply_stop_loss(ord, ...)` — 손절
  6. `_create_linked_sell(ord, ...)` — 연동 매도 (기존 `_create_linked_sell_order` 재사용)
- **주의**: 모듈 전역 상태(`_limit_warned_orders` 등)와 `application`, `trading_gate` 의존성을 명시적 인자로 주입한다. `tests/test_sync_orders.py`(986줄)가 patch하는 경로(`main.xxx`)를 깨지 않도록 한다. 경로가 바뀌면 테스트 patch 경로를 함께 수정하되, **테스트 의도는 변경하지 않는다.**
- **완료 조건**: 전체 테스트 통과, `sync_orders` 본문이 단계 호출 중심으로 단순화된다(목표 100줄 이내).

### Q2. 광범위 `except Exception` 정리

- **대상**: `grep -rnE "except Exception:\s*$|except:\s*$" src` 결과 약 23곳
- **변경**: 각 지점을 검토해 (a) 구체적 예외로 좁히거나, (b) 최소한 `_log.debug/warning`으로 원인을 남긴다. **의도적 무시**는 이유를 주석으로 적는다. 동작은 바꾸지 않는다.
- **완료 조건**: 무로그 `pass` 0건(의도적 무시 제외), 전체 테스트 통과.

### Q3. 저장소 위생 및 기타 코드 정리

- [src/core/order_execution.py](file:///E:/apps/supabot/src/core/order_execution.py) 1행의 `import inspect`가 모듈 docstring보다 앞에 있어 docstring이 모듈 문서가 되지 않는다. import를 docstring 뒤로 이동한다.
- [src/core/order_manager.py](file:///E:/apps/supabot/src/core/order_manager.py) `_db_upsert`/`_db_delete` 내부의 중복 `import asyncio`를 제거한다(상단에 이미 있다).
- `manager/frontend/dist`와 `docs/toss.json`(약 250KB)이 git에 추적되는지 확인한다. 추적 중이면 `.gitignore`/CI 빌드 전환을 **제안만** 하고, 삭제는 사용자 확인 후에 한다.
- **완료 조건**: 동작 변화 없음, 전체 테스트 통과.

### Q4. SSE 브로드캐스터 견고화

- **파일**: [manager/backend/main.py](file:///E:/apps/supabot/manager/backend/main.py) `RealtimeBroadcastManager` (약 52~70행)
- **변경**
  - `asyncio.Queue(maxsize=100)`로 제한한다. `trigger`에서는 `put_nowait`의 `QueueFull`을 잡아 해당 이벤트를 드롭하거나 오래된 항목을 비우고 넣는다.
  - `subscribe`는 `try/finally`로 `discard`한다(현재 `CancelledError`만 처리하고 `remove`를 쓴다).
  - `trigger` 순회 중 set이 변경되지 않도록 `list(self.active_connections)`로 복사한다.
- **완료 조건**: 가득 찬 큐에서 `trigger`가 예외 없이 동작하고, 구독 종료 후 `active_connections`에서 제거됨을 테스트한다.

### Q5. 로그인 시도 Rate Limit

- **파일**: [manager/backend/main.py](file:///E:/apps/supabot/manager/backend/main.py) 로그인 엔드포인트
- **변경**: IP+이메일 기준 인메모리 슬라이딩 윈도우(예: 5분 내 10회 초과 시 429). 성공 시 카운터를 초기화한다. 의존성을 새로 추가하지 않는다.
- **완료 조건**: 한도 초과 시 429이고, 정상 로그인은 영향받지 않는다. 테스트를 추가한다.

---

## 5단계. 기능 확장 (Features)

> 각 기능은 **별도 설계 문서(`docs/plans/<feature>.md`)를 먼저 작성**한 뒤 구현한다. 아래는 범위와 수용 기준이다.

### F1. 시그널 스누즈 영속화

- **파일**: [src/core/signal_engine.py](file:///E:/apps/supabot/src/core/signal_engine.py) `_alert_snooze`
- **변경**: 스누즈 만료 시각을 DB(Supabase) 또는 `data/snooze.json` 폴백에 저장한다. 시작 시 로드하고, 만료 항목은 정리한다. 기존 DB 폴백 패턴(`core/db.py`, `core/db_sync.py`)을 따른다. 테이블이 필요하면 스키마 SQL을 `docs/200_system_architecture.md`에 기록한다.
- **완료 조건**: 재시작 후에도 스누즈가 유지된다(테스트: 저장 → 새 인스턴스 로드).

### F2. 글로벌 리스크 한도 (최우선 기능)

- **연계**: [src/core/trading_gate.py](file:///E:/apps/supabot/src/core/trading_gate.py) (현재 킬스위치 성격)
- **요구사항**
  - 유저별 설정: 일일 최대 손실액, 종목별 최대 노출액(미체결+보유), 일일 최대 주문 건수.
  - 신규 주문 발행 직전(`order_execution._execute_order_batch`, 수동 주문, `sync_orders`의 재주문)에 한도를 검사한다. **초과 시 주문하지 않고 사용자에게 사유를 알린다.**
  - **보호성 매도(손절)는 한도와 무관하게 허용**한다.
  - 기본값은 "제한 없음"(하위호환). 설정은 `/config` 및 매니저 UI에서 변경한다.
- **완료 조건**: 한도 초과/미초과/손절 예외 케이스 단위 테스트(거래소 API mock). `docs/` 문서를 갱신한다.

### F3. 모니터링 알림 (로드맵 Phase 8 장기)

- **연계**: [src/core/metrics.py](file:///E:/apps/supabot/src/core/metrics.py), `src/core/operational_events.py`, `src/main.py` `_check_ops_health`, `_ops_alert_key`
- **요구사항**: 임계치(동기화 연속 실패, DB 쓰기 큐 적체, 체결 지연, 거래소 API 오류율) 초과 시 관리자에게 텔레그램 알림을 보낸다. 기존 **알림 쿨다운**(`tests/test_ops_alert_cooldown.py` 참고)으로 스팸을 방지한다.
- **완료 조건**: 임계치 초과/복구/쿨다운 테스트.

### F4. 멀티지표 조합 신호 (로드맵 Phase 7 중기)

- **파일**: [src/core/signal_engine.py](file:///E:/apps/supabot/src/core/signal_engine.py) `analyze_watchlist`
- **현재**: RSI 또는 BB 하단(OR)으로 알림.
- **변경**: 유저 설정 `signal_combine_mode`(`"or"` 기본 | `"and"`)를 추가한다. `and`이면 RSI 과매도와 BB 하단 터치를 모두 충족할 때만 알림을 보낸다. `/config` 핸들러에 선택 UI를 추가한다.
- **완료 조건**: or/and 각각 알림 발생/미발생 테스트(`tests/test_signal_engine.py` 확장).

### F5. 백테스트 엔진 (로드맵 Phase 7 장기)

- **신규**: `src/core/backtest.py`
- **요구사항**: 과거 캔들(`exchange_adapter.get_candles`)로 RSI 분할 매수/매도 전략을 시뮬레이션한다. 산출물은 승률, MDD, 누적 손익, 거래 수다. **어떤 경우에도 실주문 API를 호출하지 않는다**(주문 대신 가상 체결 함수 사용). 수수료/슬리피지 파라미터를 지원한다. `/backtest` 명령(또는 매니저 리포트)으로 노출한다.
- **완료 조건**: 고정 합성 캔들 데이터로 결과가 결정론적으로 재현되는 단위 테스트. `create_order` 호출이 0회임을 mock으로 검증한다.

### F6. 기타 로드맵 항목 (후순위)

- 트레일링 스탑: `order_manager.add_order`의 `trailing_stop_pct` 필드는 있으나 로직이 없다. 구현하거나 필드를 정리한다. 별도 설계 문서가 필요하다.
- KIS 시장가 옵션, 조용한 시간대 세분화, Slack/Discord 알림 채널은 [102a_roadmap_future.md](file:///E:/apps/supabot/docs/102a_roadmap_future.md)의 해당 항목을 따른다.

---

## 부록 A. Task별 변경 파일 매트릭스

| Task | 주요 파일 | 신규 테스트 |
|------|-----------|-------------|
| S1 | `manager/backend/main.py`, `tests/conftest.py` | 시크릿 미설정 기동 실패 |
| S2 | `manager/backend/main.py` | Origin 허용/차단 |
| S3 | `manager/backend/main.py`, `src/internal_api.py` | 키 검증 |
| S4 | `src/internal_api.py`, `manager/backend/routers/*` | 500 본문 비노출 |
| S5 | `src/internal_api.py` | CIDR, loopback |
| R1 | `src/core/order_manager.py` | upsert→delete 순서 |
| R2 | `src/core/signal_engine.py` | 극단 RSI 종료 |
| P1 | `signal_engine.py`, `order_execution.py` | 캔들 1회 조회 |
| P2 | `src/main.py` | 동시성 한도 |
| P3 | `order_manager.py` | 호출 감소 |
| Q1 | `src/main.py` → `src/core/order_sync.py` | 단계별 단위 테스트 |
| Q2~Q3 | `src/**` | 기존 테스트 |
| Q4~Q5 | `manager/backend/main.py` | 큐 가득 참, 429 |
| F1~F6 | 각 설계 문서 참고 | 각 기능 |

## 부록 B. 작업 완료 체크리스트

각 Task마다 다음을 확인한다.

- [ ] 변경이 요청 범위 안에 있고, 무관한 주석·코드를 건드리지 않았다.
- [ ] 테스트에서 라이브 거래소 API를 호출하지 않는다(전부 mock).
- [ ] 시크릿이 로그·응답·커밋에 노출되지 않는다.
- [ ] 신규/변경 동작에 대한 테스트를 추가했다.
- [ ] `docker compose run --rm supabot python -m pytest tests/` 전체 통과.
- [ ] 관련 문서와 로드맵 체크박스를 갱신했다.
