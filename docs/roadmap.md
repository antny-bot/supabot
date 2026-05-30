# SUTT-Bot V2 Development Roadmap

멀티유저 및 멀티거래소(업비트, 빗썸)를 지원하는 차세대 자동매매 플랫폼 구축 로드맵입니다.

## 🏁 Phase 1: V2 아키텍처 설계 및 문서화
- [x] 멀티유저 및 멀티거래소 지원 사양서(`docs/dev-spec-draft.md`) V2.0 업데이트
- [x] 프로젝트 로드맵 V2.0 구축
- [x] 데이터베이스/JSON 스키마 정의 (`users.json`, `orders.json`)

## 🛠️ Phase 2: 멀티유저 및 통합 거래소 엔진 구축 [DONE]
- [x] `data/users.json` 관리 모듈 구현 (유저 추가/수정/조회)
- [x] 공통 거래소 인터페이스(Exchange Adapter) 개발
    - [x] 업비트(`upbit CLI`) 연동 모듈 (v2.1 업데이트)
    - [x] 빗썸(`Bithumb V2 API`) 연동 모듈 (비동기 전환 완료)
- [x] 유저별 API 키 동적 로딩 및 인증 로직 구현

## 🤖 Phase 3: UI/UX 고도화 및 안전장치(Fool-proof) [DONE]
- [x] 텔레그램 인라인 키보드(버튼) 컨펌 시스템 구축
- [x] `/start` (유저 등록 및 승인) 구현 완료
- [x] `/asset` (통합 자산 조회) 구현 완료
- [x] `/grid`, `/cancel` 명령어 실행 및 승인 단계 인터페이스 구현 완료
- [x] 유저별 상태 기반(Stateful) 대화형 핸들러 구현 완료

## 📈 Phase 4: 시그널 분석 및 알림 엔진 (RSI 등) [DONE]
- [x] 주기적 차트 데이터(OHLCV) 수집 모듈 개발 완료
- [x] 보조지표(RSI) 계산 엔진 및 판정 로직 구현 완료
- [x] 거래소별 관심 종목(Watchlist) 관리 기능 (`/watch`, `/unwatch`) 구현 완료
- [x] 시그널 발생 시 자동 알림 및 퀵 액션 버튼 연동 완료

## 🐳 Phase 5: CI/CD 파이프라인 및 도커 배포 [DONE]
- [x] 멀티 라이브러리 지원 `Dockerfile` 업데이트 (`pandas`, `ta` 포함) 완료
- [x] GitHub Actions 워크플로우 구성 (Docker Hub 자동 배포) 완료
- [x] 시놀로지 Container Manager 프로젝트용 `docker-compose.yml` 작성 완료

## 🧪 Phase 6: 통합 테스트 및 안정화 [DONE]
- [x] 다중 사용자 동시 접속 및 명령 처리 테스트 완료
- [x] 업비트/빗썸 동시 주문 및 체결 알림 테스트 완료
- [x] 컨테이너 재시작 시 유저별 상태 복구 검증 완료
- [x] API Rate Limit 및 네트워크 단절 방어 로직 최종 점검 완료
- [x] 프로젝트 README.md 작성 및 최종 문서화 완료
