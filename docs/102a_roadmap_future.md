# 102a_roadmap_future.md

supabot V3 미래 페이즈 및 기술 로드맵 명세.

## 📈 Phase 7 — 전략 · 지표 고도화

### 단기 계획
- [x] **손절(Stop-Loss)**: RSITrade 매도 주문 `stop_price` 적용 (`stop_loss_pct` 기반 손절 기준가 산출). *트레일링 스탑은 미구현.*
- [x] **지표 구조화**: `src/core/indicators.py` 신설 (`ta` 라이브러리 기반 RSI/MACD/볼린저밴드/스토캐스틱 통합).

### 중기 계획
- [x] **추가 기술 지표**: MACD, 볼린저밴드, 스토캐스틱을 `/indicators`·`/ind` 명령어로 조회 가능하게 지원.
- [ ] **멀티지표 조합 전략**: "RSI 과매도 + 볼린저 하단 터치" 등 복합 신호 매매 엔진 및 `/config` 설정 UI 구축.

### 장기 계획
- [x] **백테스트 엔진**: 과거 캔들 기반 시뮬레이터, 승률/MDD/손익 보고서 생성 기능 (`backtest_engine.py`).
- [x] **전략 성과 리포트**: Reports 대시보드 내 전략별 누적 수익률 비교, 배치별 분석 및 리포팅.
- [x] **통합 예산 플랜 & 감사 원장(Budget Audit Ledger)**: 전략별 일일 충전/주문 차감/취소 환원/매도 재투입 5대 불변식 감사 원장 시스템 (`budget_manager.py`).
- [x] **KOSPI/KOSDAQ TOP N 순환매매 전략**: 시총 상위 50위 일별 스냅샷 기반 목표 비중 리밸런싱 및 일단위 진행 관리 (`progression_manager.py`).
- [x] **정기 적립식 매매(DCA/SDCA) 고도화**: 매일/요일/월간 스케줄, 시장가/지정가 주문, 휴장일·서킷브레이커 자동 이월 (`dca_manager.py`).
- [x] **매수/매도 권장 실행 시각 프리셋 및 TOP N 가격 모드**: 일중 유동성 기반 추천 시각(`trading_presets.py`) 및 TOP N 실시간 발주 모드(`order_price_mode`: 현재가/공격적 2틱/시장가, 단가 변동 차액 원장 정산).
- [ ] **로컬 모의투자(Sandbox)**: 거래소 API 연동 없는 인메모리/DB 모의 거래 테스트 환경 구축.

## 🧪 Phase 8 — 안정성 · 테스트 · 관측성

### 단기 계획
- [x] **테스트 설정**: `pytest.ini` 구성, CI 워크플로(`ci-test.yml`)에 자동 테스트 실행 연동.
- [x] **핵심 흐름 테스트**: 라이브 API mock을 사용한 주문/전략 통합 테스트 구현.

### 중기 계획
- [ ] **세션 보안**: 웹 UI 로그인 세션 강제 검증, HTTPS 강제 미들웨어, 쿠키 보안 설정 (`secure`/`httponly`/`samesite`).
- [x] **구조화 로깅**: `src/core/bot_logger.py` 활용한 JSON 형식 stdout 로그 수집.
- [x] **헬스체크 & 기동 검증**: docker-compose healthcheck 연동 (`data/health.json`), 기동 시 `.env` 주요 환경 변수 강제 검증.
- [x] **백업 및 복구**: `scripts/backup.sh` 자동 백업 스크립트 + `src/core/backup_manager.py` 기반 Supabase 14개 테이블 정기 SQLite/ZIP 덤프, Google Drive OAuth 클라우드 업로드(`gdrive_client.py`), 로컬 SQLite 읽기 폴백(`data/fallback_latest.sqlite3`) 및 대시보드 백업 Health Card 연동.
- [x] **DB 장애 복구 동기화**: DB 다운 시 로컬 JSON 임시 누적 후 DB 복구 시점 재시도 동기화 트랜잭션 구축. `trade_logs` DB insert 실패 시 사일런트 드롭 방지(비동기 큐 연동) 및 조회 시 중복제거 병합 보장.
- [x] **Webhook 검증 & 봇 즉시 동기화**: `/internal/notify` 및 `/internal/orders/wake` 호출 시 HMAC 서명 검증 및 IP 필터, 배치 주문 즉시 기상 연동.

### 장기 계획
- [x] **메트릭 수집**: `src/core/metrics.py` 인메모리 수집기 구축.
- [ ] **모니터링 알림**: 시스템 임계치 초과 시 관리자용 텔레그램/대시보드 push 알림 연동.
- [x] **2차 인증**: 웹 매니저 로그인 시 MFA/TOTP (Google OTP) 탑재 (`manager/backend/routers/mfa.py`).
- [ ] **DB 권한 세분화**: 봇과 웹 대시보드 접근 권한 분리 및 RLS(Row Level Security) 정책 고도화.

## 🌐 Phase 9 — 거래소 · 자산 확장

### 단기 계획
- [x] **KIS 분봉 제한 대응**: RSI 분봉 계산 요구 시 일봉 강제 폴백 및 에러 핸들링.
- [x] **캔들 캐싱**: 동일 주기 및 종목 중복 조회 시 API 호출 제한 회피용 메모리 캐싱.
- [x] **Upbit API 포팅**: Node.js subprocess 호출 방식을 `aiohttp`/`pyupbit` 기반 순수 비동기 파이썬 코드로 이관.

### 중기 계획
- [x] **KIS 시장가**: KIS 주문에 시장가(`ORD_DVSN="01"`) 전송 옵션 구현 (`src/core/exchanges/kis.py`).
- [x] **KIS 분할 매매 & 주식 주문 지원**: 주식(KIS/Toss) 정수/소수점 수량, 정규장 시장가/지정가, 장외 예약 주문(`reserved`) 및 익일 재주문 지원.
- [ ] **신규 거래소 연동**: 바이낸스 등 글로벌 거래소 어댑터 추가.
- [x] **실시간 시세 엔진**: Upbit/Bithumb/KIS WebSocket 연동 실시간 시세 수집 및 캔들 업데이트 구조 구축.

### 장기 계획
- [ ] **통합 포트폴리오**: 주식과 암호화폐 자산 일괄 조회 및 관리.
- [ ] **리밸런싱 전략**: 목표 자산 비중에 맞춘 자동 자산 조정 기능.

## 💬 Phase 10 — UX · 운영 편의

### 단기 계획
- [ ] **설정 UX 개선**: `/config` 단계 최소화 및 현 상태 시각화.
- [ ] **자연어 범위 확장**: 미적중 로그 기반 전처리 정규식 지속 보강으로 API 호출 비용 최소화.
- [ ] **멀티 알림 채널**: Slack, Discord 등 알림 수신 채널 연동 다각화.

### 중기 계획
- [x] **수익률 리포트**: `/report` 명령어 포맷 강화.
- [x] **알림 세분화**: 조용 시간(Quiet Hours) 및 일일 DCA 예수금 부족 경고 알림.
- [x] **차트 시각화**: 웹 대시보드 내 실시간 자산 성장 곡선 및 PnL 차트 구축, 일단위 스냅샷 시계열 인터랙티브 라인차트(7D~ALL, 총자산/현금/손익/수익률 토글) 전면 개편.
- [x] **실행 시각 프리셋 UI**: `TimePickerInput` 기반 매수/매도 권장 시각 퀵 선택 칩 연동.

### 장기 계획
- [x] **웹 대시보드 고도화**: supabot-manager 웹 서비스 내 UI 고도화.
- [ ] **다국어**: 메시지 i18n 처리.

---

## 🧭 우선순위 및 의존성 메모

### 단기 착수 우선순위
1. **테스트 게이트 구축 (Phase 8)**: 안전망 확보.
2. **손절 & 지표 모듈화 (Phase 7)**: 실거래 리스크 관리 극대화.
3. **KIS 분봉 대응 및 캐싱 (Phase 9)**: API 레이트 리밋 완화.
4. **환경 변수 검증 및 백업 스크립트 (Phase 8)**: 인프라 안정화.

### 기능 의존성 구조
- 지표 모듈화(P7) → MACD·볼린저(P7 중기) → 멀티지표 전략(P7 중기) → 백테스트(P7 장기)
- 어댑터 인터페이스(기존) → 신규 거래소(P9 중기) → 통합 포트폴리오(P9 장기)
- 구조화 로깅(P8) → 메트릭·모니터링(P8 장기)
