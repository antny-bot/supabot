# 102_roadmap_v3.md

멀티유저·멀티거래소(Upbit, Bithumb, KIS) 자동매매 봇 차기 로드맵.
V3 지향점: **① 전략/지표 다양화, ② 운영 안정성, ③ 자산 확장, ④ UX 개선**.

> ⚠️ 모든 주문 실거래 연동. 작업 전 `AGENTS.md` 안전 규칙 숙지 필수.

---

## ✅ 완료된 V2 기반

- [x] **텔레그램 핸들러** (`src/main.py`): 핵심 제어 명령어, 전략 설정 및 조회 커맨드 지원.
- [x] **자연어 라우팅**: 정규식 기반 빠른 전처리 + Gemini 하이브리드 인텐트 처리.
- [x] **백그라운드 루프**: 주문 상태 동기화 및 신호/지표 분석 병렬 기동.
- [x] **거래소 통합** (`exchange_adapter.py`): 3대 거래소 API 추상화.
- [x] **주문 상태기계** (`order_manager.py`): 비동기 주문 추적, KIS 장외 주문 재시도 핸들링.
- [x] **신호 엔진**: RSI 분석 및 지표 가격 역산(RSI 목표가 계산).
- [x] **유저 및 보안**: Fernet 대칭키 기반 키 암호화 및 유저 권한 통제.
- [x] **인프라**: Docker, docker-compose 구축 및 GitHub Actions를 활용한 Oracle Cloud VM CD 파이프라인.

---

## ✅ Phase A/B/C 완료 (아키텍처 분리)

- [x] **Phase A — 봇 경량화**: 불필요한 테스트용 커맨드 정리 및 외부 알림 push API `/internal/notify` 도입.
- [x] **Phase B — 데이터 계층 분리**: 로컬 JSON 파일 의존성을 Supabase PostgreSQL로 마이그레이션. 장애 시 파일 자동 폴백.
- [x] **Phase C — 웹 대시보드 도입**: FastAPI + Jinja2 + HTMX 기반 대시보드 (`supabot-manager`) 신설, DB 공유.
- [x] **모노레포 전환**: 봇(`src/`), 매니저(`manager/`), 스키마 파일 통합 관리 및 이미지 개별 빌드 워크플로 구축.

---

## ✅ Phase D 완료 (전략·예산·스케줄 고도화)

- [x] **통합 예산 플랜 및 감사 원장(`budget_ledger`)**: 5대 불변식(항등식, 멱등성, 잔액보존 등)을 보장하는 1원 단위 감사 원장 시스템 도입.
- [x] **DCA/SDCA 정기 매매 엔진 고도화**: 시장가(`market`) 및 지정가(`limit`) 선택 지원, 휴장일/임시공휴일/사이드카 시 3종 이월 정책(`next_day`, `delay_20m`, `skip`) 자동 처리.
- [x] **KOSPI/KOSDAQ 시총 TOP N 순환매매**: 마스터 스냅샷 일별 프리징, 일단위 진행 상태(Progression) 및 배치 대사(Reconciliation) 구현.
- [x] **봇 코어 엔진 모듈화**: `order_sync.py`(주문 동기화/수명주기), `dca_manager.py`(DCA 스케줄러), `order_execution.py`(주문 실행) 완전 분리.
- [x] **관리 UI 고도화 & MFA 탑재**: 전략 운용 및 템플릿 통합 메뉴 일원화, 필터링 영속화, Google Authenticator MFA 2차 인증 탑재.

---

## 🔗 연관 로드맵 문서
- **Phase 7 ~ 10 미래 계획 및 우선순위**: [102a_roadmap_future.md](file:///E:/apps/supabot/docs/102a_roadmap_future.md)
