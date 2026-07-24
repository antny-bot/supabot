# AGENTS.md — supabot 에이전트 진입점

AI 에이전트(Claude Code, Codex, Antigravity) 공통 진입점. 작업 전 확인 필수.

## 🚨 프로젝트 표준 및 안전 규칙 (필독)
작업 전 정독. 사고·데이터 유실 방지.
- **[100_project_standards.md](file:///E:/apps/supabot/docs/100_project_standards.md)**: 실거래 경고, 테스트 제약, 키 관리, 검증, 백업/롤백

## 🗂️ 개발 문서 인덱스 (넘버링 가이드)

### 1. 프로젝트 개요 & 로드맵
- **[[101] 유저 온보딩 가이드](file:///E:/apps/supabot/docs/101_user_onboarding.md)**: 신규 유저 세팅
- **[[102] 로드맵 V3](file:///E:/apps/supabot/docs/102_roadmap_v3.md)**: 기능 개선, 향후 계획 요약
  - **[로드맵 상세계획](file:///E:/apps/supabot/docs/102a_roadmap_future.md)**: 미래 페이즈 계획, 의존성 메모

### 2. 아키텍처 & 핵심 모듈 구현
- **[[200] 시스템 아키텍처 및 데이터 스키마](file:///E:/apps/supabot/docs/200_system_architecture.md)**: 봇/UI 맵, DB 스키마, 거래소 인증·제약
- **[[201] 거래소 어댑터](file:///E:/apps/supabot/docs/201_exchange_adapter.md)**: Upbit, Bithumb, KIS, Toss 인터페이스
- **[[202] 주문 관리자](file:///E:/apps/supabot/docs/202_order_manager.md)**: 주문 상태 추적, 파일/DB 동기화
- **[[203] 사용자 관리자](file:///E:/apps/supabot/docs/203_user_manager.md)**: 유저 설정, 권한, 키 관리
- **[[204] 시그널 엔진](file:///E:/apps/supabot/docs/204_signal_engine.md)**: RSI 계산·분석
- **[[205] 메인 핸들러](file:///E:/apps/supabot/docs/205_main_handlers.md)**: 텔레그램 명령 처리, 루프 통제
  - **[자연어 처리 흐름](file:///E:/apps/supabot/docs/205a_natural_language.md)**: Gemini 자연어 처리 및 로그 명세
  - **[보안 및 안전장치](file:///E:/apps/supabot/docs/205b_security_logging.md)**: API 암호화, 일회용 토큰, 킬스위치
  - **[유틸리티 파서](file:///E:/apps/supabot/docs/205c_utility_parsers.md)**: 주요 파서 및 포맷터 함수 목록
- **[[206] 토스 API 레퍼런스](file:///E:/apps/supabot/docs/206_toss_api_reference.md)**: 엔드포인트·필드

### 3. 알고리즘 & 정책 상세
- **[[301] RSI 거래 알고리즘](file:///E:/apps/supabot/docs/301_rsi_algorithm.md)**: RSI/거미줄 매매 로직
- **[[302] 한국투자증권(KIS) 시장 정책](file:///E:/apps/supabot/docs/302_kis_market_policy.md)**: KIS 정규장/장외 매매 정책, 재주문
- **[[303] 토스증권 해외주식 정책](file:///E:/apps/supabot/docs/303_toss_overseas_stock.md)**: 미국주식 통화 분기, 예외 처리
- **[[304] Gemini 자연어 분석 인텐트](file:///E:/apps/supabot/docs/304_gemini_intent.md)**: LLM 자연어 처리, 인텐트 로깅

### 4. 인프라 & 배포
- **[[401] Oracle Cloud VM 설정](file:///E:/apps/supabot/docs/401_oracle_cloud_vm_setup.md)**: 서버 VM 초기 셋업
- **[[402] Oracle Cloud 배포 순서](file:///E:/apps/supabot/docs/402_oracle_cloud_deploy_sequence.md)**: Docker 빌드, 운영 배포 시퀀스
- **[[403] GitHub Actions 워크플로우](file:///E:/apps/supabot/docs/403_github_actions_workflows.md)**: CI/CD 자동화 사양
