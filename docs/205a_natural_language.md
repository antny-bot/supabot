# 205a_natural_language.md

Gemini 자연어 처리 흐름 및 로그 명세.

## 자연어 처리 흐름

1. **입력**: 일반 텍스트 → `natural_language_command` (조건: `llm_enabled` 활성)
2. **컨텍스트 확인**: `context.user_data["_nl_recent_context"]`에서 최근 대화 이력(최대 2턴, 4개 이벤트) 로드
3. **전처리**: `preprocess_natural_language_intent(text, user)` 조회성 안전 액션 우선 처리
   - 허용 액션: `asset`, `price`, `orders`, `status`, `history`, `config_view`, `help`, `rsi`, `indicators`
   - 미처리: 매수/매도/취소/설정 변경 (LLM 우회 차단)
   - 효과: 전처리 성공 시 Gemini 미호출, 원문 미기록, 최근 컨텍스트에 기록
4. **LLM 호출**: 전처리 실패 시 `parse_natural_language_intent(text, user, recent_context)` 호출
   - Pydantic BaseModel(`TradeIntentModel`, `core.nl_schema`)을 `response_schema`로 지정하여 엄격한 JSON Intent 추출
   - 이전 턴의 티커나 액션을 자연스럽게 이어받아 처리 (예: "삼성전자 시세" → "10주 사줘")
5. **후처리**: `normalize_natural_language_intent(text, intent, user)` 서버 보정
   - `주문대기`, `예약 주문`, `추적 전략 주문` → `status`
   - `미체결`, `오픈오더`, `거래소 주문` → `orders`
   - RSI 분할 매매/매도 및 DCA 모드 정규화
   - 정규화된 의도를 최근 컨텍스트(`_nl_recent_context`)에 갱신
6. **실행 분기**:
   - **읽기 액션** (조회): `execute_query_intent` 즉시 실행
   - **쓰기 액션** (매매/설정): 확인 버튼 제시 → 클릭 시 `execute_confirmed_intent` 실행

## 로그 및 통계

- **전처리 적중**: `data/nl_preprocess_hits.json`에 액션별 카운트 기록 (개인정보보호 위해 원문 미저장)
- **미적중(LLM 전달)**: `append_natural_language_log()` 호출 → `data/nl_unmatched.jsonl` 익명 기록
- **영속화**: `core.natural_language` 관리, `nl_logs` 테이블 + 파일 폴백 이중 기록
- **보안**: `chat_id`, `user_id` 저장 배제. 숫자, 6자리 주식코드, 보안 토큰 마스킹 처리. (※ `/nlstats` 명령 폐기됨)
