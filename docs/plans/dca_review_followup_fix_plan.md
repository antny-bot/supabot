# DCA 리뷰 후속 수정 계획 (commits `2ee9683`, `bc11e3f`)

> 대상: `src/core/dca_manager.py`, `src/core/order_sync.py`, `src/internal_api.py`, `manager/backend/services/budget_manager.py`, `manager/backend/routers/templates.py`, `manager/frontend/src/...`
> 작성일: 2026-11-08 / 상태: 미착수
> ⚠️ 실거래 코드다. 반드시 [100_project_standards.md](../100_project_standards.md) 준수 (실주문 호출 금지, 테스트는 mock 사용).

## 0. 수정 항목 요약

| # | 우선순위 | 구분 | 항목 | 파일 |
|---|---|---|---|---|
| 1 | 높음 | 버그 | DCA 예산 차감이 원장(`BUY_ORDER_SPEND`)을 거치지 않음 + 시장가 체결 후 차감액 정산 없음 | dca_manager.py, budget_manager.py, order_sync.py |
| 2 | 높음 | 버그 | params 전체 read-modify-write로 갱신 유실 가능, 예외를 debug로 삼킴 | dca_manager.py |
| 3 | 높음 | 버그 | DCA volume 템플릿이 예산관리 대상으로 바뀜, 기본 3,000,000 하드코딩, 프론트/백엔드 unlimited 해석 불일치 | budget_manager.py, templates.py, strategyTypes.ts, Operations.tsx |
| 4 | 중간 | 버그 | `carryover_count`가 휴장 이월/일반 실패 경로에서 초기화되지 않음 | dca_manager.py |
| 5 | 중간 | 버그 | `delay_20m` 알림 제목/본문 불일치, 재알림 없음 | dca_manager.py |
| 6 | 중간 | 버그 | volume DCA 예산 사전검사(`price`)와 실제 소요(`current_price`) 기준 혼용 | dca_manager.py |
| 7 | 중간 | 버그 | `order_sync` 보정 조건이 지정가 DCA까지 포함, `volume` None 안전성 | order_sync.py |
| 8 | 중간 | 버그 | `_load_schedules` DB/파일 병합 한계, 폴백 저장 시 필드 유실 가시성 | dca_manager.py |
| 9 | 낮음 | 점검 | 요일 범위 정규식 확장에 따른 에러 메시지 회귀 | dca_manager.py |
| 10 | 낮음 | 점검 | `internal_api` order_type/carryover_mode 400 검증으로 인한 호환성 | internal_api.py |
| R1 | 리팩토링 | | 예산 차감 공통화 | |
| R2 | 리팩토링 | | carryover 상태 헬퍼화 (`orig_sched`/`sched` 이중 갱신 제거) | |
| R3 | 리팩토링 | | 스케줄 병합 로직 중복 추출 | |
| R4 | 리팩토링 | | `execute_due_dca_schedules` 분리 | |
| R5 | 리팩토링 | | 기본 예산 상수화 | |
| R6 | 리팩토링 | | 프론트 `hasDcaBudget`/unlimited 판정 공통화 | |

---

## 1. 상세

### 1. 예산 차감 원장 통합 (높음)
- 현재: `execute_due_dca_schedules`가 주문 성공 직후 `strategy_templates.params`의 `carryover_budget`/`monthly_spent`를 직접 UPDATE.
- 문제: `budget_manager`의 차감 함수(`BUY_ORDER_SPEND` 원장 기록, 약 L200-246)를 쓰지 않아 원장 잔액과 어긋남. 취소 환원(`refund_cancelled_orders`)만 원장을 쓰므로 비대칭. 시장가 체결 시 `order_sync`가 volume을 실제 체결 수량으로 바꾸지만 차감액은 추정치 그대로.
- 수정:
  1. 직접 UPDATE를 `budget_manager`의 차감 함수 호출로 교체 (`group_no`, `cycle_no`, `ticker`, `qty`, `cost_krw`, `order_uuid` 전달). 시그니처는 실제 코드를 읽고 맞출 것. `src`에서 `manager/backend`를 import하는 구조가 불가하면 공용 모듈 위치를 먼저 확인하고 판단.
  2. 시장가 DCA 체결 완료 시(`order_sync`) 실제 체결금액과 차감액 차이를 보정하는 원장 항목(예: `BUY_ORDER_ADJUST`)을 추가하거나, 최소한 차이를 로그와 원장에 남긴다.
- 완료 기준: DCA 매수 1회 후 params의 잔액과 원장 `balance_after_krw`가 일치. 취소 환원 후에도 일치.

### 2. 예산 갱신 원자성/오류 처리 (높음)
- 현재: SELECT로 읽은 params 전체를 수정해 UPDATE (약 L1010-1022). 예외는 `_log.debug`.
- 수정:
  1. 가능하면 최신 params를 UPDATE 직전에 다시 읽어 필요한 키만 병합 (또는 RPC/낙관적 락). 최소 요건: 차감 대상 키(`carryover_budget`, `monthly_spent`) 외 키를 덮어쓰지 않을 것.
  2. 실패 시 `_log.error`로 올리고 사용자 알림 1회 + 동일 template의 다음 실행에서 재검증되도록 처리.
- 완료 기준: 동시 갱신 시나리오 테스트(두 번의 연속 갱신 후 둘 다 반영) 통과.

### 3. DCA volume 예산 관리 대상 변경 영향 (높음)
- 문제:
  - `is_budget_managed_strategy`가 DCA volume도 관리 대상으로 판단 (`unlimited`만 제외).
  - 프론트 `templateToForm`은 `budget_mode`/`carryover_budget` 없는 DCA를 `unlimited`로 해석. 백엔드 `ensure_budget_plan_initialized`는 `budget_mode` 없으면 monthly_budget을 3,000,000으로 초기화 → 기존 무제한 volume DCA에 임의 한도 생김.
- 수정:
  1. `budget_mode`가 없는 기존 DCA 템플릿을 어떻게 취급할지 단일 규칙으로 정하고 프론트/백엔드 양쪽에 동일 적용 (권장: `budget_mode` 없음 + `carryover_budget` 없음 → unlimited로 간주, 백엔드 `ensure_budget_plan_initialized`가 이런 템플릿에 한도를 만들지 않도록).
  2. 필요하면 기존 DCA 템플릿에 `budget_mode: "unlimited"`를 채우는 1회성 마이그레이션 스크립트(`scripts/` 또는 `sql/`) 작성. 실DB 실행은 하지 말고 스크립트만 제공.
  3. 3,000,000 기본값은 상수화 (R5).
- 완료 기준: 신규 로직에서 budget_mode 없는 volume DCA가 재동기화 후에도 한도 없이 동작. 테스트 추가.

### 4. `carryover_count` 초기화 누락 (중간)
- 수정: 사이드카 경로 이외의 이월/실패 경로(휴장 이월 `delay_20m`/`next_day`, 일반 실패 skip, 성공)에서 `carryover_count`를 sched/orig_sched 양쪽에서 제거. R2 헬퍼로 일원화.
- 완료 기준: "사이드카 오류 → 휴장 이월 → 다음날 사이드카 오류" 시 카운트가 1부터 다시 시작하는 테스트.

### 5. `delay_20m` 알림 (중간)
- 현재 제목 "+20분 이월"에 본문 "다음 개장 시점" 혼재, `is_carryover` 이미 true면 재알림 없음.
- 수정: 실제 재시도 시각이 20분 뒤이면 현재 문구, 다음 개장이면 제목도 "다음 개장 이월"로 분기. 재알림 정책(최초 1회)은 유지하되 문구 분기만 정리.

### 6. volume DCA 사전검사 가격 기준 (중간)
- 수정: `price`와 `current_price`의 정의를 확인하고, 예산 사전검사(`est_cost_1share`, `avail_cob / price`)를 실제 소요 계산(`effective_budget = volume * current_price`)과 같은 기준으로 통일. 시장가면 `current_price`, 지정가면 주문 가격.
- 완료 기준: 가용 예산 경계값(1주 가격 ±1원) 테스트.

### 7. order_sync 보정 조건 (중간)
- 수정 (`src/core/order_sync.py` L553 부근):
  - 조건을 시장가 주문으로 한정 (주문 레코드에 `order_type`이 없다면 DCA 스케줄/주문 기록 쪽에서 구분 가능한 필드를 먼저 확인).
  - `ord.get("volume") or 0` 형태로 None 안전화.
  - 보정 후 예산 정산은 항목 1과 연동.

### 8. 스케줄 DB/파일 병합 (중간)
- 수정: 병합 정책을 문서화하고(DB 우선, 컬럼 미존재 시에만 파일 보강) 마이그레이션 미적용 상태 감지를 경고에서 명확한 1회성 error 로그로 상향. 병합 코드는 R3로 추출. 사용자가 DB에서 의도적으로 지운 값이 되살아나지 않도록, DB 스키마에 해당 컬럼이 없을 때만 병합하도록 제한 검토.

### 9. 요일 범위 파싱 회귀 (낮음)
- 점검: `"1~5"`, `"월~"`, `"월~foo"`, `"일~월"`, `"화~일요일"`, `"토~월"`(순환) 입력 테스트 추가, 에러 메시지가 사용자 친화적인지 확인.

### 10. internal_api 400 검증 호환성 (낮음)
- 점검: 웹 백엔드/프론트/텔레그램 봇에서 `order_type`·`carryover_mode`로 보내는 모든 값을 grep으로 확인 (`market_order` 등 변형 포함). 필요한 별칭만 허용 목록에 추가.

---

## 2. 리팩토링

- **R1** 예산 차감 공통화: 항목 1·2와 함께 처리.
- **R2** `_set_carryover(sched_id, reason, count=None)`, `_clear_carryover(sched_id)` 헬퍼 추가. sched와 `get_schedule()` 원본을 함께 갱신하고 `_db_upsert` 1회 호출. 기존 중복 코드 제거.
- **R3** `_merge_file_fields(rows, file_map)` 추출. `_load_schedules`와 reload 양쪽에서 사용.
- **R4** `execute_due_dca_schedules`를 `_check_budget_limit()`, `_handle_sidecar_error()`, `_record_post_order()` 등으로 분리. 동작 변경 없이 순수 이동, 기존 테스트 전부 통과해야 함.
- **R5** `DEFAULT_DCA_PLAN_BUDGET = 3000000.0` 상수화 (백엔드). 프론트도 상수 하나로.
- **R6** `hasDcaBudget` 판정과 `templateToForm`의 unlimited 기본값 판정을 `strategyTypes.ts`의 유틸 함수 하나로 모아 `Operations.tsx`에서 사용.

## 3. 작업 순서
1 → 2 → 3 → 4 → 7 → 6 → 5 → 8 → 9 → 10 → 리팩토링(R2 → R3 → R5 → R6 → R4)

## 4. 검증
```powershell
python -m pytest tests/test_dca_market_and_schedule.py -q
python -m pytest tests -q
cd manager/frontend; npm run build
```
- 실거래 API 호출 금지. 거래소·DB는 mock.
- 변경한 동작은 `docs/200_system_architecture.md`, `docs/205_main_handlers.md` 등 관련 문서에 반영.

---

## 5. Gemini 수정 프롬프트 (복사해서 사용)

````text
프로젝트: e:\apps\supabot (실거래 자동매매 봇). 모든 답변은 한글.
먼저 AGENTS.md와 docs/100_project_standards.md를 읽고 규칙을 지켜라. 실주문 API를 호출하는 테스트/스크립트는 절대 실행하지 말고 mock만 사용한다. 실DB에 마이그레이션을 실행하지 않는다.

작업: docs/plans/dca_review_followup_fix_plan.md 를 끝까지 읽고, 문서의 "3. 작업 순서"대로 항목 1~10과 리팩토링 R1~R6을 수정하라.

대상 커밋은 2ee9683, bc11e3f 이며 `git show` 로 변경 내용을 먼저 확인하라. 주요 파일:
- src/core/dca_manager.py
- src/core/order_sync.py
- src/internal_api.py
- manager/backend/services/budget_manager.py
- manager/backend/routers/templates.py
- manager/frontend/src/components/strategy/strategyTypes.ts, StrategyFormModal.tsx, pages/Operations.tsx
- tests/test_dca_market_and_schedule.py

규칙:
1. 각 항목을 수정하기 전에 해당 코드를 직접 읽어 문서의 설명이 실제와 맞는지 검증하라. 다르면 실제 코드를 기준으로 판단하고 최종 보고에 차이를 적어라. 추측으로 수정하지 마라.
2. 항목마다 재현/회귀 테스트를 tests/ 에 추가한다. 기존 테스트는 모두 통과해야 한다.
3. 최소 변경 원칙. 요청 범위 밖 코드는 건드리지 말고, 기존 주석과 docstring은 유지한다.
4. 리팩토링(R2~R6)은 동작 변경 없이 수행하고, 리팩토링 전후로 테스트를 돌려 동일 결과를 확인한다.
5. 항목 1·3은 설계 판단이 필요하다. 구현 전에 선택한 방안과 이유를 짧게 정리한 뒤 진행하라. src가 manager/backend 모듈을 import할 수 없는 구조라면 임의로 구조를 바꾸지 말고 대안을 제시하라.
6. 완료 후 아래를 실행해 결과를 보고하라.
   - python -m pytest tests/test_dca_market_and_schedule.py -q
   - python -m pytest tests -q
   - cd manager/frontend; npm run build
7. 관련 문서(docs/200_system_architecture.md, docs/205_main_handlers.md, docs/plans/dca_strategy_review_fix_plan.md)에 변경 사항을 반영하라.
8. git commit 은 하지 마라. 변경 파일 목록과 항목별 처리 결과(완료/보류/사유)를 표로 보고하라.
````
