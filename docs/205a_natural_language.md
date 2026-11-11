# 205a_natural_language.md — Gemini 자연어 처리 흐름 및 Function Calling 에이전트 명세

텔레그램 봇의 Gemini 자연어 처리 흐름, 도구 사용(Function Calling), HMAC 대리 인증 및 감사 로그 명세.

## 자연어 처리 흐름

1. **입력**: 일반 텍스트 수신 → `natural_language_command` (조건: `llm_enabled` 활성 및 Gemini API 키 등록)
2. **컨텍스트 확인**: `context.user_data["_nl_recent_context"]`에서 최근 대화 이력(최대 4턴 슬라이딩 윈도우) 로드
3. **1차 패스트트랙 (룰 기반 전처리)**:
   - `preprocess_natural_language_intent(text, user)`로 단순 조회성 액션 우선 판별
   - 허용 액션: `asset`, `price`, `orders`, `status`, `history`, `config_view`, `help`, `rsi`, `indicators`
   - 효과: 단순 조회는 Gemini 호출 없이 0초대 즉시 응답, 비용 0, 최근 컨텍스트에 기록
4. **2차 에이전트 루프 (Gemini Function Calling)**:
   - 전처리 미적중 및 복합/변경 요청 시 `run_nl_agent_loop` 진입 (최대 5 스텝)
   - 읽기 도구 18종(실시간 시세/잔고/지표 8종 + Manager REST API 리포트 10종: 손익/승률/일별/월별/ROI랭킹/전략/거래소/MDD/자산배분/DCA배치)을 필요 시 연속 자동 호출하여 실시간 데이터 수집
   - 변경 제안 도구 7종(`propose_manual_order`, `propose_cancel_orders`, `propose_template_action` 등) 호출 시 실제 즉시 실행하지 않고 `ProposedAction` 큐에 적재
5. **실행 분기**:
   - **조회/분석만 수행된 경우**: 최종 브리핑 자연어 메시지로 상태 메시지 즉시 수정 (`reply_text`)
   - **변경 작업이 제안된 경우**:
     - `result.reply_text` + 실행 계획 요약 목록 결합
     - `_pending_nl_intents[token]`에 일괄 적재
     - `[✅ 실행] / [❌ 취소]` 인라인 키보드 버튼 부착
6. **사용자 승인 및 실행**:
   - `[✅ 실행]` 클릭 시 `natural_language_confirm_callback` → `execute_confirmed_actions` 순차 일괄 실행
   - `[❌ 취소]` 클릭 시 안전하게 취소 처리 및 로그 `rejected` 상태 갱신

## Manager REST API HMAC 대리 인증

봇이 사용자를 대리하여 Manager Backend REST API(`/api/templates`, `/api/orders`, `/api/reports`)를 안전하게 호출:
- `X-Bot-User-Id`, `X-Timestamp`, `X-Signature`, `X-Is-Admin` 헤더 기반 인증
- 서명: `HMAC-SHA256(MANAGER_API_KEY, f"{timestamp}:{bot_user_id}:{path}")`
- 세션 쿠키 없이도 Manager Backend 라우터 재사용 지원

## 로그 및 감사 추적

- **전처리 적중**: `data/nl_preprocess_hits.json`에 액션별 카운트 기록
- **에이전트 호출 기록**: `append_natural_language_log()` 호출 → `data/nl_unmatched.jsonl` 및 Supabase `nl_logs` 테이블 기록 (`tool_trace` 및 `proposed_actions` 상세 내역 보존)
- **도구 추적 및 관리자 분석**: 에이전트가 호출한 도구 이력이 `llm_action` 필드에 요약 기록 (예: `get_open_orders, propose_cancel_orders`)되며, Manager `/api/reports/nl-logs`에서 도구 체인(`tool_chain`, `tool_count`, `is_multi_turn`), 도구별 사용 빈도, 승인율 통계를 산출 (`nl_logs` 장애 시 `data/nl_unmatched.jsonl` 폴백)
- **보안 마스킹**: 개인정보 및 보안 토큰은 `<TOKEN>`, `<STOCK>`, `<NUMBER>`로 마스킹
