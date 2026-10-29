# F1. 시그널 스누즈 영속화 설계 문서

## 1. 개요
텔레그램 봇 재시작 또는 컨테이너 재배포 시 메모리 상의 시그널 스누즈(`_alert_snooze`)가 초기화되어, 사용자가 이미 1시간/2시간/당일 스누즈 처리한 종목의 RSI 알림이 다시 발송되는 문제를 방지합니다.

## 2. 설계 상세
1. **저장소**:
   - `data/snooze.json` 로컬 파일 영속화 (기존 DB 폴백 패턴 지원).
   - 형식: `{"user_id:exchange:ticker": expiration_timestamp}`
2. **동작 흐름**:
   - `SignalEngine.__init__` 시점에 `_load_snoozes()` 호출하여 영속화된 스누즈 로드.
   - `clean_expired_snoozes()` 호출 시 만료된 항목을 메모리 및 저장소에서 정리.
   - `set_snooze(user_id, exchange, ticker, mode)` 호출 시 스누즈를 설정하고 `_save_snoozes()`로 영속화.
3. **수용 기준 (Acceptance Criteria)**:
   - 스누즈 설정 후 `SignalEngine`을 새로 인스턴스화해도 유효한 스누즈 상태가 그대로 유지된다.
   - 만료된 스누즈는 로드 시점 및 정리 호출 시 정상적으로 제거된다.
