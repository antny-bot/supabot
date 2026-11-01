# UI 단순화 및 벤토 그리드(Bento Grid) 레이아웃 고도화 개발계획

## 1. 개요 및 배경
- **배경**: 신규 기능(전략 템플릿의 복수 종목 TOP N, 분할매도 정책, 예산 플랜, 거래소 확장 등) 추가로 인해 설정 항목 및 모달 폼의 복잡도가 급격히 상승함.
- **문제점**:
  1. 전략 템플릿 모달 내 30여 개에 달하는 폼 필드가 한 번에 노출되어 초보자 및 일반 사용자의 진입 장벽이 큼.
  2. 대시보드 및 리포트, 관리자 화면 등 정보 밀집도가 높은 페이지에서 좌/우 불균형 컬럼 레이아웃으로 인한 여백 낭비 및 시각적 피로도 발생.
- **목표**:
  - 점진적 공개(Progressive Disclosure) 원칙을 적용하여 기본값 위주로 핵심 설정을 유지하고, 세부/고급 설정은 기본 접힘(`AdvancedSection`)으로 단순화.
  - 12컬럼 기반 **벤토 그리드(Bento Grid)** 레이아웃 표준을 Dashboard에 이어 Reports(자산 배분/투자 현황) 및 Admin 시스템 현황까지 확장 적용.

---

## 2. 세부 개발 범위

### A. 전략 템플릿(Templates) 폼 고급 설정 접기 & 기본값 체계화
1. **공통 컴포넌트 (`AdvancedSection.tsx`) 도입**:
   - `grid-template-rows: 0fr -> 1fr` CSS 애니메이션 기반 부드러운 아코디언.
   - 접혀 있는 상태에서도 설정된 주요 옵션 요약(summary pill) 제공.
2. **복수 종목 (TOP N DCA) 모달 간소화**:
   - Step 2: '순위 이탈 안전장치(휩쏘 방지 버퍼, 확인 일수, 분할매도 일수)'를 `AdvancedSection`으로 접기.
   - Step 3: '종목 배분 방식 및 매도 대금 처리 방식'을 `AdvancedSection`으로 접기.
3. **단일 종목 (Grid, DCA, RSI) 모달 간소화**:
   - 전략별 세부 파라미터(RSI 가중 매수, DCA 스케줄 상세 등)를 점진적 공개 형태로 정돈.

### B. 정보 밀집 화면 벤토 그리드(Bento Grid) 확장 적용
1. **대시보드 (`Dashboard.tsx`)** (적용 완료):
   - 1행: KPI 4타일 (`col-span-3` × 4)
   - 2행: 일별 실현손익 차트(`col-span-8`) + 거래소별 자산 배분 도넛(`col-span-4`)
   - 3행: 보유 자산 요약(`col-span-6`) + 최근 체결 내역(`col-span-6`)
2. **리포트 - 자산 배분 (`AllocationSection.tsx`)**:
   - 단일 12컬럼 그리드 적용: 상단 헤더 요약 + 2개 도넛 차트(`col-span-6` × 2)의 대칭 및 반응형 높이 일치.
3. **관리자 시스템 현황 (`Admin.tsx - DashboardTab`)**:
   - 1행: 봇 상태 퀵 배너 및 엔진 상태
   - 2행: 핵심 6대 지표 KPI (`col-span-4` sm / `col-span-2` xl)
   - 3행: Supabase DB 헬스(`col-span-5` lg) + 최근 미확인 이벤트 테이블(`col-span-7` lg)

---

## 3. UI/UX 디자인 표준 준수 사항 (`DESIGN.md`)
- **컨테이너**: 반응형 숨김 요소 포함 시 `space-y-*` 금지, `flex flex-col gap-*` 또는 CSS Grid `gap-*` 통일.
- **모바일 대응**: Desktop에서는 12컬럼 그리드, 모바일(`md:`) 미만에서는 1열 스택 및 세그먼트 전환 유지.
- **타이포그래피 및 라벨**: `whitespace-nowrap break-keep` 유지로 한글 깨짐 방지.

---

## 4. 일정 및 롤아웃 계획
1. `AdvancedSection` 컴포넌트 추가 및 `Templates.tsx` 폼 아코디언 적용
2. `AllocationSection.tsx` 및 `Admin.tsx` 벤토 그리드 리팩토링
3. 타입체크(`tsc`) 및 단위 테스트(`vitest`) 통과 검증
4. `main` 브랜치 커밋 및 푸시
