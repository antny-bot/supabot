# supabot-manager UI/UX 개선 및 신규 기능 개발 계획

## 1. 개요
본 계획은 `supabot-manager` 웹 대시보드의 사용성과 시각화 완성도를 높이고, 포트폴리오 자산 배분 및 리스크(MDD) 분석, 봇 관제 등 운영 편의 기능을 추가하여 전반적인 사용자 경험(UX)을 대폭 개선하기 위한 개발 계획서입니다.

---

## 2. 핵심 목표 및 설계 원칙
1. **디자인 시스템 및 표준 준수 (`manager/frontend/DESIGN.md`)**:
   - 단일 반응형 브레이크포인트 `md:` (768px) 엄수 (mobile-first 기본 + `md:` 데스크톱 오버라이드).
   - 모든 페이지 `PageHeader` 표준 적용 및 `pageMeta.ts` 기반 단일 아이콘 소스 유지.
   - Recharts 기반 직관적인 시각화(자산 성장 곡선, 도넛 차트, 언더워터 차트).
2. **백엔드-프론트엔드 연계 및 안정성**:
   - FastAPI 백엔드 라우터 확장 및 Pydantic 스키마 정의.
   - 기존 Supabase DB 테이블(`orders`, `trades`, `bot_logs`, `sys_config`) 최대한 활용.
3. **사용자 피드백 및 조작성 강화**:
   - 실시간 인터랙션 피드백을 위한 토스트(Toast) 알림 시스템 구축.
   - 데이터 분석을 위한 CSV 내보내기(Export) 기능.

---

## 3. 세부 구현 단계 (Phases)

### Phase 1: 대시보드(Dashboard) 리뉴얼 및 시각화 강화
- **6대 핵심 지표 카드 확장**:
  - 총 평가금액 (Total Value)
  - 총 투자원금 (Total Invested)
  - 총 평가손익 & 수익률 (Total Unrealized PnL & ROI)
  - 24시간 실현손익 (24h Realized PnL)
  - 활성(오픈) 주문 수 (Open Orders)
  - 봇 상태 (Bot Loop Status)
- **자산 성장 곡선 (Equity Area Chart)**:
  - 일별 총 평가자산 및 누적 손익 추이를 보여주는 Recharts 면적/라인 차트.
- **거래소별/자산군별 비중 도넛 차트 (Asset Allocation Donut)**:
  - Upbit / Bithumb / KIS / Toss 증권 간 비중 및 코인/주식/현금 비중 시각화.
- **원클릭 긴급 제어 (Emergency Order Cancel)**:
  - 위험 상황 발생 시 전체 미체결 주문 일괄 취소 요청 모달.

### Phase 2: 신규 리포트 확장 (리스크/MDD & 자산배분)
- **백엔드 라우터 (`manager/backend/routers/reports.py`) 확장**:
  - `GET /api/reports/drawdown`: 누적 수익률 기반 MDD(Maximum Drawdown), 고점 대비 낙폭(DD), 손익비(Profit Factor), 최대 이익/손실 거래 통계 제공.
  - `GET /api/reports/allocation`: 거래소별, 자산군별(가상자산/국내주식/해외주식/현금) 비중 집계 데이터 제공.
- **프론트엔드 신규 리포트 탭 추가 (`manager/frontend/src/pages/reports/`)**:
  - `DrawdownSection.tsx`: 언더워터 차트(Underwater Chart), 최고점/최저점 통계, 리스크 지표 카드.
  - `AllocationSection.tsx`: 자산군별 파이 차트 및 목표 비중 대비 괴리율 테이블.
  - `Reports.tsx`에 `drawdown`(리스크/MDD) 및 `allocation`(자산 배분) 탭 등록.

### Phase 3: 인터랙션 강화 & 편의 도구
- **글로벌 토스트(Toast) 피드백 시스템**:
  - `src/components/ui/Toast.tsx` 및 `ToastContext` 구현.
  - 주문 취소, 템플릿 실행, 긴급 조치 시 성공/실패 토스트 노출.
- **데이터 CSV 내보내기 (Export Utility)**:
  - 주문 목록, 체결 내역, 리포트 테이블 데이터를 CSV 파일로 다운로드하는 공통 유틸 함수 구현.
- **모바일 뷰 최적화**:
  - 모바일 화면에서 주문 테이블 간결화 및 카드형 요약 제공.

### Phase 4: 봇 시스템 헬스 관제 탭
- **백엔드 헬스 체크 확장 (`manager/backend/routers/dashboard.py` or `analytics.py`)**:
  - 봇 프로세스 동작 및 최종 활동 시간 조회 엔드포인트 연동.
- **Admin 페이지 내 관제 탭 (`manager/frontend/src/pages/Admin.tsx`)**:
  - 봇 헬스 상태, API 레이트 리밋 상태, 최근 시스템 이벤트/오류 요약 카드 배치.

---

## 4. 검증 계획
1. **백엔드 테스트**:
   - `pytest` 실행하여 기존 테스트 통과 여부 및 신규 리포트 API 응답 검증.
2. **프론트엔드 빌드 및 타입 검사**:
   - `npm run build`를 통해 TypeScript 컴파일 에러 및 Vite 빌드 성공 검증.
3. **반응형 UI 검증**:
   - 데스크톱(`md:`) 및 모바일 브레이크포인트에서의 레이아웃 및 차트 리사이징 검증.

---

## 5. 작업 일정 및 PR 계획
- 신규 브랜치 `feat/manager-ui-ux-enhancement` 생성
- 순차적 커밋 및 테스트 완료 후 원격 저장소 푸시
- Pull Request(PR) 작성 및 최종 보고
