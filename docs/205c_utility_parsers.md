# 205c_utility_parsers.md

주요 파싱, 검증 및 포맷팅 유틸리티 함수 명세.

## core.parsers (파싱 및 검증)

- `parse_exchange_and_ticker(args, default_exchange)`: 인수 파싱 → `(exchange, ticker)` 반환.
- `normalize_exchange(value)`: 거래소 명칭 표준화 (예: `"빗썸"` → `"bithumb"`, `"한투"` → `"kis"`).
- `parse_number(value)`: 한글 단위 포함 숫자 변환 (예: `"100만"` → `1000000.0`).
- `parse_rsi_range("25-30")`: 문자열 파싱 → `(25.0, 30.0)` 범위 반환.
- `interpolate_range(start, end, i, count)`: 시작가와 종료가 사이의 `i`번째 균등 분할가 계산.
- `validate_max_order(user, order_krw)`: 유저별 `max_order_krw` 주문 금액 제한 초과 여부 확인.
- `parse_config_value(key, raw_value)`: `/config set` 입력값 타입 검증 및 적절한 형변환.
- `validate_config_update(user, key, value)`: 설정 업데이트 시 유효성 제약 위반 검사 (`ValueError` 유발).
- `is_kis_regular_session(now=None)`: KST 기준 평일 09:00-15:35 정규장 여부 판정.
- `next_kis_regular_session(now=None)`: 다음 KIS 정규장 시작 시각 반환.
- `kis_next_check_timestamp(now=None)`: 다음 정규장 체크 지점의 Unix timestamp 반환.

## core.formatters (메시지 템플릿)

- `build_account_summary(user_id, user)`: `/whoami` 명령 호출 시 권한 및 계정 상태 응답 텍스트 생성.

## core.natural_language (자연어 보조)

- `preprocess_natural_language_intent(text, user)`: 안전한 조회형 액션 전처리 판단.
- `append_natural_language_log(text, llm_intent, final_intent)`: 보안 필터링을 거친 자연어 요청 로그 기록.
