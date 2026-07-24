# 205b_security_logging.md

보안 관리, 운영 로그 및 거래 안전장치 명세.

## 사용자 Secret 암호화

- **보관**: `USER_SECRET_KEY` 설정 시 거래소/Gemini 키 `enc:v1:<ciphertext>` 포맷으로 `data/users.json` 저장.
- **대상**: Upbit/Bithumb (`access_key`, `secret_key`), KIS (`app_key`, `app_secret`, `account_no`), Gemini (`gemini_api_key`).
- **작동**:
  - `get_user()` 호출 시 메모리상 복호화 사본 반환. DB/파일 내부는 암호문 유지.
  - 봇 기동 시 기존 평문 secret 자동 마이그레이션.
  - `USER_SECRET_KEY` 미설정/부적합 시 평문 읽기만 지원, 새 secret 저장 불가.
  - 키 불일치 시 `get_user()` secret 필드 빈 값 반환 + `_secret_error` 표시하여 오작동 예방.
- **검증 캐시**: 저장 직후 API 키 유효성 검증 결과를 캐시하여 `/config -v` 에서 마지막 성공/실패 시각 표시 (매번 라이브 호출 차단).
- **모듈**: `core.secret_crypto` 분리 (`encrypt_secret`/`decrypt_secret`).

## 이벤트 로그 및 일회용 토큰

- **운영 로그**: `core.operational_events` 가 `operational_events` 테이블 및 로컬 파일 이중 기록 (dual write).
  - 기록: 백그라운드 루프 예외, Telegram 메뉴/기동 알림 실패, secret key 오류, API 검증 실패, 주문 실패, 확인 요청 만료 등.
  - 마스킹: API 키, secret, 토큰, 계좌 번호 필터링.
- **수동 주문 토큰**: `/buy`, `/sell` 콜백에 주문 정보 배제. 서버 메모리 `_pending_manual_orders` 임시 토큰 매칭 (10분 만료, 실행 직전 한도 재검증).
- **전략 토큰**: `/grid`, `/sgrid`, `/rsitrade`, `/sgridrsi` 실행 시 `core.strategy_tokens` 일회용 토큰 발행 (10분 만료). 콜백 데이터 `gridrun|<token>` 형태로 전송해 Telegram 64바이트 제한 회피 및 중복 클릭 방지.
- **취소 토큰**: `/cancel`, `/cancelno` 취소 목록 제시 시 `_pending_cancel_orders` 토큰 연동 (10분 만료). `cancelrun|<token>` (실행) / `cancelabort|<token>` (취소) 처리.
- **조회 토큰**: `/orders`, `/status`, `/history`, `/report`, `/asset` 목록 펼치기/페이지네이션용 `core.list_view_tokens` 사용 (10분 sliding TTL, 비파괴 조회 peek 지원). 
  - `/orders`, `/status` 는 클릭 시 로컬 `order_manager` 데이터 실시간 재조회.
  - `/history`, `/report`, `/asset` 은 최초 조회 시점의 데이터 스냅샷 재출력.
- **초기화 토큰**: `/resetuser <user_id>` (관리자용) 실행 시 `_pending_reset_users` 토큰 발행 (10분 만료). 확정 시 `order_manager.clear_user_orders()` 및 `trade_log.clear_user_trades()` 실행 (DB/파일 삭제, 감사로그 기록).

## 거래 안전장치 (Kill-Switch · 노출 한도)

- **글로벌 거래 중지 (Kill-Switch)**:
  - 관리자 `/halt`(중지) / `/resume`(재개).
  - 상태: `system_config.trading_halt` (`'1'`/`'0'`) 저장. DB 실패 시 `data/trading_halt.flag` 파일 폴백.
  - 적용: 수동/전략 주문 confirm 및 KIS 재주문 (`sync_orders`) 직전 `core.trading_gate.assert_can_trade()` 가 감지하여 주문 차단. **보호성 매도(손절/익절)는 비차단**.
- **총 노출 한도**:
  - 유저 preference `max_open_exposure_krw` 설정.
  - 미체결 원화 주문 잔여 노출 (`core.parsers.compute_open_exposure_krw`) + 신규 주문 합이 한도 초과 시 매수 거부 (`validate_total_exposure`). USD (Toss 해외주식) 주문은 대상 외.
