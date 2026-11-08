# DCA/전략 로직 점검 이슈 수정 개발 계획서

- 작성일: 2026-11-08
- 대상 커밋: `6c8aa65`(DCA 시장가·요일·이월), `45938cf`(통합 예산 플랜), `ec9e5eb`(RSI 연결 매도 template_id)
- 주 대상 파일: `src/core/dca_manager.py`, `src/internal_api.py`, `src/core/exchanges/{upbit,bithumb,kis,toss}.py`, `tests/test_dca_market_and_schedule.py`
- 필독: [100_project_standards.md](../100_project_standards.md) (실거래 경고, 테스트에서 라이브 API 호출 금지)

## 작업 원칙
- 모든 주문 경로는 실거래. 테스트에서는 `exchange_adapter.create_order` 등을 반드시 mock.
- 이슈 단위로 작은 커밋. 변경 범위 최소화(무관한 리팩터링 금지).
- 검증: `docker compose run --rm supabot python -m pytest tests/`, `python -m py_compile src/main.py`

---

## Phase 1 — 🔴 높음 (먼저 수행)

### P1-1. 일요일 요일 파싱 버그 (`rstrip("요일")`)
- **원인**: `str.rstrip("요일")`은 문자 집합 제거. `"일"`, `"일요일"` → `""`. `"화~일"` 범위는 `_WEEKDAY_TOKEN_MAP[""]`에서 `KeyError`.
- **위치**: `parse_dca_schedule` 내 `m_range`, 복수 요일 `parts` 루프, `cleaned_no_yoil`.
- **수정**: 헬퍼 `_strip_yoil(tok)` 추가. `tok.removesuffix("요일")` 후 결과가 맵에 없으면 원본 토큰으로 조회. 범위 파싱은 잘못된 토큰에 `ValueError`(한글 메시지) 발생시켜 `KeyError` 방지.
- **테스트**: `"일"`, `"일요일"`, `"화~일"`, `"수-일"`, `"월~일"`(daily), `"토,일요일"`, `"월수금"`, 잘못된 토큰(ValueError).

### P1-2. 수량형 시장가 매수 `effective_budget` NameError
- **원인**: `amount_type == "volume"` + 업비트/빗썸 + 시장가 매수에서 `ord_price = effective_budget` 사용. 변수는 `budget` 분기에서만 정의.
- **수정**: 시장가 블록 진입 전 `effective_budget`을 항상 정의. volume형이면 `volume * current_price`(필요 시 0.999 곱 반영 여부 주석). 또는 이 조합을 등록 단계(`internal_api`)에서 거부하고 실행부에서도 방어 처리. 기존 동작과 일관된 쪽 선택 후 주석으로 명시.
- **테스트**: upbit/bithumb, volume형, market bid → NameError 없이 `create_order(price=금액, volume=0, ord_type="market")` 호출 확인(mock).

### P1-3. 사이드카 오탐 키워드와 무한 재시도
- **원인**: `is_sidecar_err` 키워드에 `호가`, `일시`, `정지` 포함 → 일반 거부 에러도 20분 무한 재시도, `_dca_fail_counts` 우회.
- **수정**:
  1. 키워드를 `사이드카`, `서킷브레이커`, `거래정지`, `halt`(대소문자 무시)로 제한.
  2. 스케줄에 `carryover_count` 누적(상한 예: 연속 12회 = 4시간). 상한 초과 시 일반 실패 처리(`_dca_fail_counts`)로 전환하고 사용자 알림.
  3. `_db_upsert`에서 `carryover_count`는 이미 제외 중이므로 파일 폴백에만 보관되는지 확인.
- **테스트**: 일반 에러("호가 단위 오류")는 이월되지 않고 실패 카운트 증가, 사이드카 에러는 이월, 상한 초과 시 전환.

---

## Phase 2 — 🟠 중간

### P2-4. 킬스위치와 사이드카 처리 분리
- `trading_gate.is_trading_halted()`가 true일 때 알림 없이 `_DCA_RETRY_DELAY_SECONDS`(5분) 무음 지연(기존 동작 복원).
- 사이드카 알림은 주문 에러 기반 분기에서만 발송. 알림은 스케줄당 이월 시작 시 1회만(`is_carryover` 활용).
- 확인 순서(킬스위치 / `is_active`)가 비활성 유저에게 알림을 보내지 않는지 점검.
- 테스트: 킬스위치 on 시 `_safe_notify` 미호출, 지연 시각 = now+300.

### P2-5. 템플릿 예산 한도 조회 실패 처리와 원자성
- 조회 예외 시 `warning` 로그를 남기고 해당 회차를 보류(`defer_schedule`). 전액 주문으로 통과시키지 않음.
- 같은 템플릿의 스케줄 간 동시 실행에서 `carryover_budget` 초과가 없도록 주문 접수 직후 차감하는 위치를 `budget_manager`와 맞춰 점검. 이중 차감이 생기지 않는지 코드로 확인하고, 불확실하면 분석 결과를 PR 설명에 기록(임의 대규모 변경 금지).
- 테스트: 조회 예외 → 주문 미호출, 잔액 부족 → 한도 축소.

### P2-6. 시장가 주문 기록 정확도
- 시장가 매수(upbit/bithumb)의 `add_order` 기록: 추정 수량임을 표시하고, `order_sync` 체결 동기화 시 실제 체결 수량·평균가로 덮어쓰는지 확인. 덮어쓰지 않으면 보정 로직 추가.
- 테스트: 시장가 주문 기록 후 체결 동기화가 수량을 갱신(mock).

### P2-7. `_db_upsert` 폴백 키 불일치
- `order_type`, `carryover_mode`가 폴백(`basic_keys`) 경로에서 유실되지 않도록 처리. 마이그레이션 미적용 DB에서는 경고 로그에 "마이그레이션 `2026-11-07-dca-order-type-carryover.sql` 적용 필요"를 명시.
- 재시작 후 로드 시 `order_type`/`carryover_mode` 기본값이 시장가를 지정가로 바꾸지 않는지 확인(파일 폴백 JSON에 보존).
- 테스트: 첫 upsert 실패 → 폴백 → 파일 폴백에 두 필드 유지.

---

## Phase 3 — 🟡 낮음

- **P3-8**: `parse_dca_schedule`의 중복 `"매일"` 분기 제거(데드 코드). 동작 변경 없음 확인.
- **P3-9**: `delay_20m`에도 `is_carryover` 표시와 첫 1회 안내 알림 적용. 휴장 주말 내내 폴링하는 문제는 `next_check_timestamp`가 더 늦으면 그 시각을 우선하도록 개선.
- **P3-10**: `internal_api._internal_execute_dca_handler`에서 `carryover_mode`·`order_type` 허용값 검증. 잘못된 값은 400 응답. 응답 메시지는 정규화된 값(`sched`)으로 표시.
- **P3-11**: 위 모든 항목의 테스트를 `tests/test_dca_market_and_schedule.py`에 추가하고 기존 테스트 전부 통과 확인.

## 추가 확인 (코드 수정 전 조사)
- KIS 시장가 매도에서 `price=0` 전달 시 `_create_kis_order`의 `ORD_DVSN`(시장가 코드) 분기가 올바른지 확인. 토스 `MARKET`에서 가격 필드 처리 확인. 문제 시 별도 이슈로 보고.

## 완료 기준
- [x] P1-1~P1-3 수정 및 테스트 통과
- [ ] P2-4~P2-7 수정 및 테스트 통과
- [ ] P3-8~P3-11 반영
- [ ] 전체 `pytest tests/` 통과, `py_compile` 통과
- [ ] 관련 문서(`docs/205_main_handlers.md`, `docs/200_system_architecture.md`의 DCA 항목) 갱신

---

## 🤖 Gemini 개발 프롬프트 (아래 코드블록 전체 복사)

### Phase 1 프롬프트

```text
supabot 프로젝트(E:\apps\supabot)에서 DCA 전략 로직 버그를 수정해줘. 모든 답변과 주석은 한글로.

먼저 읽을 문서: AGENTS.md, docs/100_project_standards.md, docs/plans/dca_strategy_review_fix_plan.md (Phase 1 섹션).
주 대상: src/core/dca_manager.py, src/internal_api.py, tests/test_dca_market_and_schedule.py

안전 규칙: 모든 주문 경로는 실거래다. 테스트에서 실제 거래소 API를 호출하지 말고 exchange_adapter.create_order 등을 반드시 mock해라. 관련 없는 리팩터링은 하지 마라.

수정할 항목:
1) P1-1 요일 파싱 버그: parse_dca_schedule의 rstrip("요일")은 문자 집합 제거라 "일", "일요일"이 빈 문자열이 된다. 헬퍼(_strip_yoil)를 만들어 removesuffix("요일")를 사용하고, 결과가 맵에 없으면 원본 토큰으로 조회해라. 범위(예: "화~일")에서 잘못된 토큰은 KeyError가 아니라 ValueError(한글 메시지)로 처리해라.
2) P1-2 execute_due_dca_schedules의 시장가 블록에서 amount_type == "volume" + 업비트/빗썸 + 매수일 때 effective_budget이 정의되지 않아 NameError가 난다. effective_budget을 항상 정의하도록 고쳐라(volume형은 volume * current_price). 동작 선택 이유를 주석으로 남겨라.
3) P1-3 is_sidecar_err 키워드에서 "호가", "일시", "정지"를 제거하고 "사이드카", "서킷브레이커", "거래정지", "halt"(대소문자 무시)로 제한해라. 스케줄에 carryover_count를 누적하고 상한(연속 12회) 초과 시 일반 실패 처리(_dca_fail_counts)로 전환하며 사용자에게 알려라.

테스트: tests/test_dca_market_and_schedule.py에 다음을 추가해라.
- "일", "일요일", "화~일", "수-일", "월~일", "토,일요일", "월수금", 잘못된 토큰(ValueError)
- upbit/bithumb volume형 시장가 매수가 NameError 없이 create_order(ord_type="market")를 호출하는지
- 일반 에러는 이월되지 않고 실패 카운트가 증가하는지, 사이드카 에러는 이월되는지, 상한 초과 시 전환되는지

검증: docker compose run --rm supabot python -m pytest tests/ 와 python -m py_compile src/main.py 가 모두 통과해야 한다. 끝나면 변경 파일과 테스트 결과를 요약해라.
```

### Phase 2 프롬프트

```text
supabot 프로젝트(E:\apps\supabot)에서 docs/plans/dca_strategy_review_fix_plan.md 의 Phase 2(P2-4 ~ P2-7)를 구현해줘. 한글로 답하고 주석도 한글로. Phase 1은 이미 완료된 상태다.

먼저 읽을 문서: AGENTS.md, docs/100_project_standards.md, 위 계획서.
안전 규칙: 실거래 경로이므로 테스트에서 라이브 API 호출 금지(반드시 mock). 무관한 리팩터링 금지.

- P2-4: trading_gate.is_trading_halted()일 때는 알림 없이 _DCA_RETRY_DELAY_SECONDS(5분) 무음 지연(기존 동작 복원). 사이드카 알림은 주문 에러 기반 분기에서 스케줄당 이월 시작 시 1회만 보내라. 비활성 유저에게 알림이 가지 않는지도 확인해라.
- P2-5: strategy_templates의 carryover_budget 조회가 예외로 실패하면 warning 로그를 남기고 해당 회차를 보류(defer)해라. 같은 템플릿의 여러 스케줄이 동시에 실행될 때 한도를 초과하지 않는지 budget_manager의 차감 위치를 점검해라. 불확실하면 임의로 크게 바꾸지 말고 분석 결과를 보고해라.
- P2-6: 시장가 매수(upbit/bithumb)로 add_order에 기록하는 volume은 추정치다. order_sync 체결 동기화가 실제 체결 수량과 평균가로 갱신하는지 확인하고, 아니면 보정 로직을 추가해라.
- P2-7: _db_upsert 폴백(basic_keys)에서 order_type, carryover_mode가 유실되어 재시작 후 시장가가 지정가로 바뀌지 않도록 고쳐라. 마이그레이션(2026-11-07-dca-order-type-carryover.sql) 미적용 시 경고 로그에 안내 문구를 넣어라.

각 항목마다 tests/test_dca_market_and_schedule.py 에 테스트를 추가하고, 마지막에 docker compose run --rm supabot python -m pytest tests/ 와 py_compile 통과를 확인해라. 변경 파일과 결과를 요약해라.
```

### Phase 3 및 마무리 프롬프트

```text
supabot 프로젝트(E:\apps\supabot)에서 docs/plans/dca_strategy_review_fix_plan.md 의 Phase 3(P3-8 ~ P3-11)과 '추가 확인' 항목을 처리해줘. 한글로 답하고 주석도 한글로. Phase 1~2는 완료된 상태다.

- P3-8: parse_dca_schedule의 중복된 "매일" 분기(데드 코드)를 제거해라. 동작은 변하면 안 된다.
- P3-9: delay_20m 모드에도 is_carryover 표시와 첫 1회 안내 알림을 적용해라. next_check_timestamp가 더 늦으면 그 시각을 우선해 휴장 주말 내내 20분 폴링하지 않게 해라.
- P3-10: src/internal_api.py 의 _internal_execute_dca_handler 에서 carryover_mode(delay_20m|next_day|skip), order_type(market|limit)의 허용값을 검증하고, 잘못된 값은 400으로 응답해라. 응답 메시지는 정규화된 값을 써라.
- 추가 확인: KIS 시장가 매도(price=0)에서 _create_kis_order의 ORD_DVSN 분기와 토스 MARKET 주문의 가격 필드 처리가 올바른지 코드를 읽고 확인해라. 문제가 있으면 수정하지 말고 근거와 함께 보고해라(실거래 영향).
- P3-11: 전체 테스트 보강 후 docker compose run --rm supabot python -m pytest tests/ 와 py_compile을 통과시켜라.
- 마지막으로 docs/205_main_handlers.md, docs/200_system_architecture.md 의 DCA 관련 항목(요일 파싱, 시장가, 이월 정책, 상한)을 갱신하고, 계획서의 완료 기준 체크박스를 업데이트해라.
```
