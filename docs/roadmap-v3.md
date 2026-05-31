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
    - 시스템: `/start`, `/help`, `/info`, `/whomai`·`/me`
    - 조회: `/asset`, `/price`·`/p`, `/history`, `/orders`
    - 매매: `/buy`, `/sell`, `/cancel`, `/grid`, `/sgrid`, `/rsitrade`·`/rsigrid`
    - 감시·설정: `/watch`, `/unwatch`, `/config`, `/status`, `/diag`(admin), `/nlstats`(admin)
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

## 📈 Phase 7 — 전략·지표 고도화

RSI 단일 의존에서 벗어나 리스크 관리와 다지표 전략으로 확장.

### 단기
- [ ] **손절(Stop-Loss) / 트레일링 스탑** — RSITrade 매수 체결분에 대해 하락 임계 도달 시 자동 손절.
      `sync_orders`(`main.py`)의 체결 감지 지점에 손절 조건 평가 추가, 주문 스키마에 `stop_price` 확장
- [ ] **지표 모듈 구조화** — `signal_engine.py`를 지표 플러그인 구조로 리팩터링(공통 인터페이스: 캔들 입력 → 신호 출력),
      RSI를 첫 구현체로 이전

### 중기
- [ ] **MACD · 볼린저밴드 · 스토캐스틱 추가** — `ta` 라이브러리 기반, 각 지표를 모듈로 추가
- [ ] **멀티지표 조합 전략** — "RSI 과매도 + 볼린저 하단 터치" 같은 AND/OR 조건 신호. `/config`에 조건 설정 UI

### 장기
- [ ] **백테스트 엔진** — 과거 캔들로 전략 시뮬레이션, 수수료 버퍼 반영, 승률·MDD·손익 리포트
- [ ] **전략 성과 리포트** — 실거래 결과 누적 집계 및 전략별 비교

---

## 🧪 Phase 8 — 안정성 · 테스트 · 관측성

상용 운영 신뢰성 확보. 모든 테스트는 라이브 API를 mock (AGENTS.md 규칙 준수).

### 단기
- [ ] **테스트 설정 정비** — `pytest.ini` 추가, `requirements`에 `pytest` 명시, CI에 테스트 게이트 추가
- [ ] **핵심 흐름 통합테스트** — `sync_orders`(부분 체결·매도 연동·KIS 정규장 정책), `rsitrade`/`grid` 핸들러,
      자연어 intent 흐름. `_run_upbit_cli`/`_request_bithumb`/`_request_kis` mock 필수

### 중기
- [ ] **구조화 로깅** — print → 구조화 로거 전환, 주문/오류 이벤트 일관 포맷
- [ ] **헬스체크 & 환경변수 검증** — docker-compose healthcheck, 시작 시 `BOT_TOKEN`·`ADMIN_CHAT_ID`·`USER_SECRET_KEY` 누락 감지·중단
- [ ] **백업 · 롤백 절차** — `data/orders.json`·`data/users.json` 주기 백업, 배포 롤백 가이드 문서화
- [ ] **`.env.template` 보강** — `USER_SECRET_KEY` 추가 및 발급 안내

### 장기
- [ ] **메트릭 수집** — 주문 성공률, API 응답 지연, 폴링 주기 건전성
- [ ] **운영 모니터링 알림** — 임계 초과 시 관리자 알림(`/diag` 확장)

---

## 🌐 Phase 9 — 거래소 · 자산 확장

거래소별 기능 격차 해소 및 신규 자산군 편입.

### 단기
- [ ] **KIS 분봉 한계 명확화** — `rsi_interval`이 분봉일 때 KIS 거부 메시지/일봉 폴백을 일관 처리
      (`exchange_adapter.py` 캔들 조회 + `signal_engine` 경로)
- [ ] **캔들 캐싱** — 동일 주기·종목 반복 조회 시 단기 캐시로 API 호출 절감

### 중기
- [ ] **KIS 시장가 주문** — `_create_kis_order`에 시장가(`ORD_DVSN`) 지원
- [ ] **KIS Grid/SGrid 지원** — 현재 암호화폐 전용 전략을 정수 수량·정규장 정책에 맞게 확장
- [ ] **신규 거래소 어댑터** — 어댑터 인터페이스 기반으로 추가 거래소(예: 바이낸스) 연동

### 장기
- [ ] **통합 포트폴리오** — 코인↔주식 합산 자산 뷰
- [ ] **리밸런싱 전략** — 목표 비중 기반 자동 조정

---

## 💬 Phase 10 — UX · 운영 편의

사용자 접근성과 일상 운영 편의 향상.

### 단기
- [ ] **`/config` UX 개선** — 대화형 단계 축소, 현재 설정 한눈에 보기
- [ ] **자연어 커버리지 확대** — `/nlstats` 패턴 데이터를 근거로 전처리 규칙 보강, LLM 호출 비용 절감

### 중기
- [ ] **수익률 리포트** (`/report`) — 기간별 실현 손익·체결 요약
- [ ] **알림 세분화** — 채널·임계값별 알림 on/off, 조용 시간(Quiet Hours)

### 장기
- [ ] **웹 대시보드** — 자산·주문·전략 현황 시각화
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
