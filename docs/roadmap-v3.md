# supabot V3 Development Roadmap

멀티유저·멀티거래소(Upbit, Bithumb, KIS) 텔레그램 자동매매 봇의 **차기 비전 로드맵**입니다.

V2(Phase 1~6)는 모두 완료되었습니다 — 상세 내역은 [`docs/roadmap.md`](./roadmap.md) 참조.
V3는 완성된 기반 위에서 **① 전략·지표 다양화, ② 운영 안정성, ③ 거래소·자산 확장, ④ 사용자 경험**
네 트랙을 단기 실행과제부터 중장기 비전까지 확장하는 것을 목표로 합니다.

> ⚠️ 모든 주문 경로는 실거래입니다. 신규 기능 구현 전 반드시 `AGENTS.md`의 안전 규칙을 확인하세요.

---

## ✅ 완료된 기반 (V2 요약)

이미 운영 중인 기능. V3 과제의 출발점입니다.

- [x] **텔레그램 핸들러** (`src/main.py`)
    - 시스템: `/start`, `/help`, `/info`, `/whoami`·`/me`
    - 조회: `/asset`, `/price`·`/p`, `/history`, `/orders`
    - 매매: `/buy`, `/sell`, `/cancel`, `/grid`, `/sgrid`, `/rsitrade`·`/rsigrid`
    - 감시·설정: `/watch`, `/unwatch`, `/config`·`/cfg`, `/status`
- [x] **자연어 라우팅** — 정규식 전처리(`natural_language.py`) + Gemini LLM 하이브리드, 인라인 버튼 컨펌
- [x] **백그라운드 루프** — 주문 동기화(`order_sync_loop`), 신호 분석(`signal_analysis_loop`)
- [x] **거래소 통합** (`exchange_adapter.py`) — 3거래소 주문/취소/상태/잔고/시세/캔들
- [x] **주문 상태기계** (`order_manager.py`) — `wait → partial → done/cancel`, KIS `pending_reorder` 재주문
- [x] **신호 엔진** (`signal_engine.py`) — RSI 계산, 목표 RSI 가격 역산(이분 탐색), 워치리스트 분석
- [x] **유저·보안** (`user_manager.py`) — 권한(`is_admin`/`is_active`), Fernet 암호화 비밀 저장
- [x] **전략** — Grid(분할 매수), SGrid(분할 매도), RSITrade(RSI 순환 매매 + 자동 익절 연동)
- [x] **인프라** — Dockerfile, docker-compose, GitHub Actions(GHCR 빌드 + Oracle VM 자동배포)

### 알려진 한계 (V3에서 해소)
- 테스트 커버리지 ~20% — `sync_orders`·rsitrade·grid·LLM 흐름 미테스트, `pytest.ini` 부재
- `.env.template`에 `USER_SECRET_KEY` 누락, 시작 시 환경변수 검증 없음
- 헬스체크·롤백·백업 정책 부재, 구조화 로깅·메트릭 없음, 캔들 캐싱 없음
- 지표가 RSI 단일에 국한, 백테스트·손절·트레일링 없음
- KIS 분봉/시장가 미지원, Grid/SGrid는 KIS 미지원

---

## ✅ Phase A/B/C 완료 (아키텍처 분리)

V3 본 로드맵과 병행하여, 봇을 경량화하고 데이터 계층을 분리하며 웹 대시보드를 도입하는
3단계 아키텍처 작업이 완료되었습니다. 결과적으로 단일 봇 리포지토리가 **모노레포**로 재구성되었습니다.

- [x] **Phase A — 봇 경량화**
    - 운영 잡음 명령 정리: `/diag`·`/nlstats`(admin) 제거, 관리자 폴링 주기(`poll_active_interval` 등) preference 제거
    - 외부 알림 수신용 `/internal/notify` HTTP 엔드포인트 추가 (포트 `8765`) — 매니저·외부 시스템이 봇으로 알림 push
- [x] **Phase B — Supabase 데이터 계층**
    - JSON 파일(`users.json`/`orders.json`) → **Supabase Postgres**(6개 테이블)로 이전
    - 연결 실패 시 기존 JSON 파일로 **자동 폴백**(file fallback) — 가용성 보존
    - 비밀 키는 `USER_SECRET_KEY` Fernet 암호화 유지, `SUPABASE_*` 환경변수 추가
- [x] **Phase C — supabot-manager 웹 대시보드**
    - Synology에서 구동되는 **FastAPI + Jinja2 + HTMX** 웹 대시보드 신규 도입
    - 봇과 **동일한 Supabase DB 공유** — 자산·주문·전략·유저 현황을 웹에서 조회·관리
- [x] **모노레포 & 빌드 분리**
    - 봇은 `src/`, 매니저는 `manager/`, 공통 스키마는 `shared/schema.sql`
    - 배포는 **GHCR** 사용: `ghcr.io/antny-bot/supabot`, `ghcr.io/antny-bot/supabot-manager`
    - 이미지 빌드 워크플로 분리: `build-bot.yml` / `build-manager.yml` (Docker Hub 미사용)

---

## 📈 Phase 7 — 전략·지표 고도화

RSI 단일 의존에서 벗어나 리스크 관리와 다지표 전략으로 확장.

### 단기
- [x] **손절(Stop-Loss)** — RSITrade 매도 주문에 `stop_price` 적용(주문 스키마에 `stop_price` 컬럼 추가,
      `rsitrade_sell` 경로에서 `stop_loss_pct` 기반 손절 기준가 산출). *트레일링 스탑은 미구현(추후 과제).*
- [x] **지표 모듈 구조화** — `src/core/indicators.py` 신설(`ta` 라이브러리 기반 RSI/MACD/볼린저밴드/스토캐스틱).
      *기존 `signal_engine.py`의 RSI 경로를 이 모듈로 완전 통합하는 리팩터링은 일부 잔존.*

### 중기
- [x] **MACD · 볼린저밴드 · 스토캐스틱 추가** — `src/core/indicators.py`에 `ta` 라이브러리 기반으로 구현,
      `/indicators`·`/ind` 명령으로 조회
- [ ] **멀티지표 조합 전략** — "RSI 과매도 + 볼린저 하단 터치" 같은 AND/OR 조건 신호. `/config`에 조건 설정 UI 및 복합 기술적 지표 결합 전략 엔진 개발

### 장기
- [ ] **백테스트 엔진** — 과거 캔들로 전략 시뮬레이션, 수수료 버퍼 반영, 승률·MDD·손익 리포트
- [ ] **전략 성과 리포트** — 실거래 결과 누적 집계 및 전략별 비교
- [ ] **로컬 모의투자(Sandbox) 엔진** — Upbit, Bithumb 등의 가상 자산 거래를 지원하는 인메모리/DB 기반 모의 거래 엔진 구축 및 시뮬레이션 환경 제공

---

## 🧪 Phase 8 — 안정성 · 테스트 · 관측성

상용 운영 신뢰성 확보. 모든 테스트는 라이브 API를 mock (AGENTS.md 규칙 준수).

### 단기
- [x] **테스트 설정 정비** — `pytest.ini` 추가, CI 워크플로(`ci-test.yml`)에서 pytest 테스트 게이트 실행
- [x] **핵심 흐름 통합테스트** — 통합 테스트 추가(라이브 API mock). *추가 흐름 커버리지 확대는 지속 과제.*
- [ ] **웹 UI 로그인 세션 보안 강화** — `SESSION_SECRET` 강제 검증, HTTPS 강제 미들웨어 구축, 쿠키 세션 보안 속성 (`secure`, `httponly`, `samesite`) 명시 설정

### 중기
- [x] **구조화 로깅** — `src/core/bot_logger.py`로 JSON 구조화 로그를 stdout 출력
- [x] **헬스체크 & 환경변수 검증** — docker-compose healthcheck(`data/health.json`), 시작 시 환경변수 검증
      (`.env.template`에 `USER_SECRET_KEY`·`SUPABASE_*` 반영)
- [x] **백업 · 롤백 절차** — `scripts/backup.sh` 추가, 롤백 절차를 `AGENTS.md`에 문서화
- [x] **`.env.template` 보강** — `USER_SECRET_KEY` 및 `SUPABASE_*` 변수 추가
- [x] **DB 장애 폴백 데이터 동기화(Sync) 고도화** — Supabase 복구 시 로컬 JSON의 누적 쓰기 트랜잭션을 원격 DB로 재시도하는 동기화 메커니즘 구축
- [x] **외부 Webhook 서명 검증 및 IP 화이트리스팅** — 매니저-봇 간 `/internal/notify` 호출 시 HMAC 서명 검증 및 IP 필터 적용

### 장기
- [x] **메트릭 수집** — `src/core/metrics.py`(인메모리 운영 메트릭). *외부 수집기 연동은 추후.*
- [ ] **운영 모니터링 알림** — 임계 초과 시 관리자 알림 (supabot-manager 대시보드/Telegram 연동 확장)
- [ ] **매니저 2차 인증(MFA/TOTP) 도입** — Google OTP/Authenticator 등 연동 기능 탑재
- [ ] **Supabase DB 접근 권한 격리 및 RLS 강화** — `service_role` 직접 공유 탈피, 봇/매니저 권한 역할(Role) 분리 및 테이블별 RLS 정책 재정립 (장기 과제로 조정)

---

## 🌐 Phase 9 — 거래소 · 자산 확장

거래소별 기능 격차 해소 및 신규 자산군 편입.

### 단기
- [x] **KIS 분봉 한계 명확화** — `rsi_interval`이 분봉일 때 KIS 거부 메시지/일봉 폴백을 일관 처리
      (`exchange_adapter.py` 캔들 조회 + `signal_engine` 경로)
- [x] **캔들 캐싱** — 동일 주기·종목 반복 조회 시 단기 캐시로 API 호출 절감
- [x] **Upbit API 연동 Python 포팅** — 외부 Node.js CLI subprocess 실행 방식을 `aiohttp`/`pyupbit` 기반의 비동기 호출로 포팅하여 단일 언어 스택 통합

### 중기
- [ ] **KIS 시장가 주문** — `_create_kis_order`에 시장가(`ORD_DVSN`) 지원
- [ ] **KIS Grid/SGrid 지원** — 현재 암호화폐 전용 전략을 정수 수량·정규장 정책에 맞게 확장
- [ ] **신규 거래소 어댑터** — 어댑터 인터페이스 기반으로 추가 거래소(예: 바이낸스) 연동
- [x] **웹소켓(WebSocket) 기반 실시간 시세 수집 엔진 도입** — Upbit/Bithumb/KIS WebSocket 연결을 통해 실시간 시세 수집 및 캔들 업데이트 구조화

### 장기
- [ ] **통합 포트폴리오** — 코인↔주식 합산 자산 뷰
- [ ] **리밸런싱 전략** — 목표 비중 기반 자동 조정

---

## 💬 Phase 10 — UX · 운영 편의

사용자 접근성과 일상 운영 편의 향상.

### 단기
- [ ] **`/config` UX 개선** — 대화형 단계 축소, 현재 설정 한눈에 보기
- [ ] **자연어 커버리지 확대** — `data/nl_unmatched.jsonl`·`nl_logs` 테이블의 미처리 패턴을 근거로 전처리 규칙 보강, LLM 호출 비용 절감
      (`/nlstats` 명령은 Phase A에서 제거됨)
- [ ] **멀티 채널 알림 연동** — Slack, Discord Webhook 연동 옵션 추가로 텔레그램 단일 알림 채널 분산

### 중기
- [x] **수익률 리포트** (`/report`) — 기간별 실현 손익·체결 요약
- [ ] **알림 세분화** — 채널·임계값별 알림 on/off, 조용 시간(Quiet Hours)
- [x] **웹 대시보드 실시간 자산 시각화** — React UI에서 Recharts 등을 이용한 투자 대비 수익률(PnL), 자산 성장 곡선 차트 구현

### 장기
- [x] **웹 대시보드** — supabot-manager(FastAPI/HTMX)로 자산·주문·전략 현황 시각화 (Phase C, 별도 모노레포 패키지)
- [ ] **다국어 지원** — 메시지 i18n

---

## 🧭 우선순위 · 의존성 메모

권장 단기 착수 순서:

1. **테스트 게이트 (Phase 8)** — 이후 모든 변경의 안전망. 가장 먼저.
2. **손절/트레일링 + 지표 모듈화 (Phase 7 단기)** — 리스크 관리는 실거래 보호 효과 큼. 모듈화는 이후 지표 추가의 전제.
3. **KIS 분봉 한계 명확화 + 캔들 캐싱 (Phase 9 단기)** — 사용자 혼란·API 부하 즉시 완화.
4. **`.env.template` 보강 + 헬스체크 (Phase 8 중기 일부)** — 배포 안정성 빠른 개선.

의존성:
- 지표 모듈화(P7) → MACD·볼린저(P7 중기) → 멀티지표 전략(P7 중기) → 백테스트(P7 장기)
- 어댑터 인터페이스 정비(기존) → 신규 거래소(P9 중기) → 통합 포트폴리오(P9 장기)
- 구조화 로깅(P8) → 메트릭·모니터링(P8 장기)

---

## 📂 관련 코드 · 문서

| 트랙 | 주요 코드 | 관련 문서 |
|------|-----------|-----------|
| 전략·지표 | `src/core/signal_engine.py`, `src/main.py`(rsitrade/grid) | `docs/impl/signal_engine.md`, `docs/detail/rsi_algorithm.md` |
| 안정성·테스트 | `tests/`, `src/main.py`(`sync_orders`) | `docs/impl/main_handlers.md`, `AGENTS.md` |
| 거래소·자산 | `src/core/exchange_adapter.py`, `src/core/order_manager.py` | `docs/impl/exchange_adapter.md`, `docs/detail/kis_market_policy.md` |
| UX·운영 | `src/main.py`, `src/core/user_manager.py`, `src/core/natural_language.py` | `docs/impl/user_manager.md`, `docs/detail/gemini_intent.md` |
