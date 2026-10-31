# supabot-manager Frontend Design

## Purpose

Shared page structure, typography, icon usage, responsive layout, and core UI components for `manager/frontend`.
Every new page and every page-level redesign must follow these rules unless there is a deliberate product decision to change the whole design system.

> Directory/module map (pages, components, hooks, api, ...) lives in `manager/README.md` → "프론트엔드 구조". This document covers *how things must look and behave*, not *where files live*.

---

## 🚨 Core Frontend Directives (필수 UI/UX 준수 원칙)

사용자 피드백 및 디자인 일관성을 위해 확립된 최우선 프론트엔드 구성 지시사항입니다.

### 1. 페이지 헤더 규칙 (Page Header Rule)
- 모든 앱 페이지(로그인 제외)는 공통 컴포넌트인 `PageHeader`를 사용한다. 직접 `h1`을 개별 작성하지 않는다.
- **서브타이틀(subtitle) 제거 원칙**: 페이지 타이틀 아래의 설명성 서브타이틀 문구는 불필요하므로 노출하지 않는다.
- 좌측 아이콘 박스(`p-3 rounded-2xl bg-primary-50`), 페이지 제목(`h1.text-app-title font-bold`), 우측 액션 버튼들을 수직 중앙 정렬(`items-center`)로 일관되게 배치하여 헤더 높이를 깔끔하게 정돈한다.

### 2. 서브메뉴 구성 표준화 (Responsive Sheet Tabs)
- **'관리자'의 '시트' 메뉴 구성 방식으로 일원화**: 모든 다중 탭/서브메뉴(관리자, 리포트, 설정 등)는 `ResponsiveTabs` 컴포넌트를 사용한다.
- **이중 카테고리 그룹핑 금지**: '전체 리포트', '포트폴리오'와 같은 상위 세그먼트 컨트롤로 탭을 이중 분류하지 않고, 단일 반응형 시트 탭 스트립으로 명확하고 단순하게 구성한다.
- **Desktop (`md:`)**: 밑줄 인디케이터 시트 탭 (`border-b-2 -mb-px`, `overflow-x-auto scrollbar-none`, `shrink-0 whitespace-nowrap break-keep`).
- **Mobile (기본)**: 가로 스크롤 다이얼 pill 버튼 (`overflow-x-auto scrollbar-none snap-x`, `shrink-0 whitespace-nowrap break-keep`).
- 기간 필터(`DateRangePicker`) 등 탭 종속 컨트롤은 탭 바 우측 또는 탭 바로 아래 컨텐츠 영역에 배치한다.

### 3. 한국어 타이포그래피 및 줄바꿈 방지 규칙
- **전역 단어 단위 줄바꿈 (`word-break: keep-all`)**: 한국어 텍스트는 브라우저 기본값에서 글자 단위로 어색하게 쪼개지므로, `body` 및 전역에 `word-break: keep-all; overflow-wrap: break-word;`를 필수로 적용한다.
- **탭/버튼/라벨 한 줄 유지 (`whitespace-nowrap break-keep`)**: 특히 태블릿, 창 크기 축소 환경에서 '주문 및 신호 주기', '전략 템플릿' 등의 긴 한글 라벨이 두 줄로 꺾이는 현상이 발생하지 않도록, 모든 탭(`ResponsiveTabs`, `SegmentedControl`, `FilterBar`) 버튼에 `whitespace-nowrap break-keep` 및 컨테이너 가로 스크롤을 보장한다.

### 4. 컬럼 레이아웃 및 카드 상단 높이 정렬 규칙 (`space-y-*` 주의)
- **인접 컬럼 상단 높이 정렬**: 좌/우 다중 컬럼(예: 대시보드 좌측 7/12, 우측 5/12)의 첫 번째 카드는 상단 높이가 정확히 수평 일치해야 한다.
- **반응형 숨김 요소 포함 시 `space-y-*` 금지**: 자식 요소 중에 모바일 전용 UI(`<div className="md:hidden">`) 등 반응형 숨김 요소가 포함된 경우 부모 컨테이너에 `space-y-*`를 사용하지 않는다.
  - Tailwind의 `space-y-*`는 CSS `> * + *` 선택자로 동작하여 데스크톱에서 `display: none`인 요소 뒤에 오는 첫 번째 카드에 불필요한 `margin-top`을 붙여 높이가 어긋난다.
  - **해결책**: 반드시 `flex flex-col gap-*` 또는 CSS Grid `gap-*`을 사용하여 숨김 요소가 간격 계산에서 완전히 배제되도록 한다.

### 5. 좌측 사이드바(Sidebar) 너비 표준
- 본문 작업 공간(대시보드 차트, 주문 테이블, 리포트 등)을 충분히 넓게 활용하기 위해 사이드바 폭을 콤팩트하게 유지한다.
- **펼침 상태**: `w-[150px]` (기존 224px 대비 약 2/3 폭)
- **접힘 상태**: `w-14` (56px)
- 내부 네비게이션 아이템은 패딩과 아이콘(`17px`)을 콤팩트하게 다듬고 `whitespace-nowrap break-keep`을 적용하여 5글자 이상의 한글 메뉴도 말줄임표 없이 여유 있게 표시한다.

### 6. 도넛/파이 차트 경계선 제거 및 모듈화 (`DonutChart`)
- **다크모드 흰색 테두리 노출 금지**: Recharts의 `<Pie>` 컴포넌트는 기본 `stroke="#fff"`가 설정되어 있어 다크모드에서 각 조각 둘레에 부자연스러운 흰색 경계선이 노출된다.
- **`stroke="none"` 및 `strokeWidth={0}` 필수 적용**: 테두리를 없애고 조각 간 간격은 `paddingAngle`로만 깔끔하게 시각적 분리를 제공한다.
- **공통 컴포넌트([DonutChart.tsx](file:///E:/apps/supabot/manager/frontend/src/components/ui/DonutChart.tsx)) 사용**: 도넛 차트 구현 시 개별 작성 대신 공통 컴포넌트를 사용하여 다크모드 툴팁, 레전드 스타일, 반응형 높이를 일관되게 유지한다.

---

## Icon Rule

- The header icon must reuse the same Lucide icon used for the page in navigation, sourced from `src/config/pageMeta.ts`.
- `BottomNav`, `TopBar`, `Sidebar`, and page headers must all reference the icon defined there.
- New page checklist: define metadata + icon in `pageMeta.ts` first, then reuse that icon in `PageHeader`.

## Page Composition

Default order for app pages: `PageHeader` → status feedback (`ErrorBanner`/success banners) → filters/summary controls → summary cards → primary data card/table/chart/form → small footer metadata (totals, etc).

Use vertical flex/grid with `gap-4`/`gap-5`/`gap-6` and keep one clear vertical rhythm.

## Core Components

Prefer these shared building blocks before inventing new page-specific UI:
`PageHeader`, `ResponsiveTabs`, `DonutChart`, `StatCard`, `FilterBar`, `ErrorBanner`, `Spinner`, `Skeleton`, `Badge`, `Button`, `ProgressBar`, `SegmentedControl`, `BottomSheet`, `MfaSettingsCard`, `DisplaySettingsCard`.

If a pattern repeats on 2+ pages, extract it into `src/components/ui` (or another shared folder) instead of duplicating markup.

## Card and Surface Style

- Default card shell: `bg-white dark:bg-slate-900` / `border border-slate-200 dark:border-slate-800` / `rounded-xl` / `shadow-sm`.
- Tables live inside a card shell with a bordered header row.
- Filters sit above the main content — not mixed into unrelated cards.

## Typography

- Manager-wide font system is user-adjustable from `Config > 표시` (font family + size `12px`–`22px`, default `16px`; storage in `src/lib/displayPreferences.ts`). Root uses `font-app-ui` so preferences apply everywhere.
- Fonts: `Pretendard JP Variable`, `Pretendard`, `Noto Sans KR`, `Noto Serif KR`.
- Korean word break: `word-break: keep-all; overflow-wrap: break-word;` 기본 적용.

Prefer these app tokens over page-local `text-*` sizing:

| Use | Token |
|---|---|
| Page title | `text-app-title font-bold` |
| Card section title | `text-app-body font-semibold` |
| Body / compact body | `text-app-body` / `text-app-body-sm` |
| Labels, table headers | `text-app-label` |
| Metadata, badges | `text-app-caption` |
| Large metric values | `text-app-metric` |

`src/index.css` remaps legacy `text-xs`…`text-3xl` inside `.font-app-ui` as a *compatibility layer*. Numeric/code-like cells keep `font-mono`; only the surrounding size scale should change.

## Display Settings

- The `표시` card (font family + size) lives on `Config`, applies immediately while editing, and persists via `localStorage` only — **never** route it through `/api/sysconfig` or other shared backend config.

## Actions

- Page-level primary actions tied directly to the page belong in the `PageHeader` actions slot (e.g. template creation on `Templates`, sync indicators).
- Secondary filters can sit below the header when multiple controls would make the header too dense.

## Responsive Layout (Mobile ↔ Desktop)

> Frontend 구조(파일 위치)는 `manager/README.md` "프론트엔드 구조" 참고.

### Breakpoint convention
- **단일 브레이크포인트 `md:` (768px)** 로 모바일/데스크톱을 가른다 — mobile-first 기본 스타일에 `md:`로 데스크톱을 오버라이드한다.
- **레이아웃 스위치**: `AppLayout`이 분기한다.
  ```
  md+:  [ Sidebar (sticky, full-height) ] [ main content (flex-1) ]
  <md:  [ TopBar ] / [ main content ] / [ BottomNav (fixed bottom) ]
  ```
  `TopBar`는 `md:hidden`, `Sidebar`는 `hidden md:flex`로 상호 배타 — 둘 다 보이면 회귀.

### Desktop sidebar layout
`AppLayout`이 `md:`+ 에서 `Sidebar.tsx`(sticky 좌측, full-height)를 렌더링하고 본문이 우측에 위치한다.

| State | Width | 표시 |
|---|---|---|
| Expanded | `w-[150px]` (150px) | 모든 항목의 아이콘 + 라벨, 슬림 콤팩트 레이아웃 |
| Collapsed | `w-14` (56px) | 아이콘만, 호버 시 `title` 툴팁 |

- 토글 = 사이드바 헤더 우측의 햄버거(`Menu`) 아이콘. collapsed 상태는 `localStorage` 키 `sbm_sidebar_collapsed`에 저장.
- 헤더: 좌측 = supabot 로고(Zap + "supabot", collapsed 시 숨김, `/dashboard` NavLink) / 우측 = `Menu` 토글.
- Nav 항목은 `APP_NAV_ITEMS`를 `adminOnly` vs `user.is_admin`으로 필터. 활성 = `bg-primary-50 text-primary-600`(light) / `bg-primary-900/30 text-primary-400`(dark).
- 하단 유저 행: 아바타 + 이메일/이름, 클릭 시 위로 슬라이드되는 설정 팝업(myhome 표준 포맷: 설정, 테마 토글, 로그아웃). 사이드바가 collapsed(접힘) 상태일 때도 팝업이 잘리지 않도록 `collapsed ? 'left-2 w-52' : 'left-2 right-2 w-auto'`로 오른쪽 영역으로 넓게 전개.

### Mobile navigation — Bottom Nav + 전체 Drawer
- 하단 네비는 **최대 6개**: 고정 항목 최대 5개 + 고정 **"전체"** 버튼(햄버거, 맨 우측).
- **전체 Drawer (`AllMenuDrawer`)**: "전체" 버튼으로 바텀시트 슬라이드업.
- 모든 페이지는 `src/config/pageMeta.ts`의 `APP_NAV_ITEMS`에 선언.

## Page Architecture

- **Dashboard** (`/dashboard`): 3초 룰 기반 글랜스 UI 적용. 좌측(7/12) 손익 추이 및 자산 배분 / 우측(5/12) 보유 자산 요약 및 최근 체결 내역. 컬럼 컨테이너는 `flex flex-col gap-5`를 사용하여 카드 상단 높이를 완벽 정렬.
- **Orders** (`/orders`): `활성 주문(Open)`과 `주문 이력(History)` 듀얼 뷰 탭 분리.
- **Trades** (`/trades`): 체결 거래 목록과 함께 실시간 매수/매도 비율 게이지 바 및 날짜 필터 제공.
- **Templates** (`/templates`): 전략 템플릿 카드 라이브러리 및 폼 모달 제공 (그리드, 스마트그리드, RSI).
- **Reports** (`/reports`): 이중 카테고리 그룹핑을 제거하고, 관리자 방식의 1차원 `ResponsiveTabs` 시트 메뉴(15개 탭)로 일원화. 기간 민감 탭 선택 시 하단 우측에 `DateRangePicker` 연동.
- **Admin** (`/admin`, admin-only): `ResponsiveTabs` 시트 탭 기반 유저관리, 이벤트, 모니터링, 종목 캐시, NL 로그 등 관리.
- **Config** (`/config`): `ResponsiveTabs` 시트 탭 기반 화면 표시, 보안(MFA) 설정.

## Accordion / Collapsible Animation

모든 collapsible 패널(`collapsible`+`isOpen`+`onToggle` props)은 열림/닫힘 애니메이션이 필수다.
CSS `grid-template` 전환(`0fr → 1fr`)으로 구현.

## Maintenance Rule

- 새 페이지 추가 시 `src/config/pageMeta.ts` 업데이트 후 `PageHeader` 적용 (서브타이틀 없이 제목만 구성).
- 다중 탭 화면 구성 시 반드시 `ResponsiveTabs` 사용 (카테고리 다중 그룹핑 금지).
- 모든 탭, 버튼, 라벨 요소에 `whitespace-nowrap break-keep` 적용 필수.
- 컬럼 레이아웃에서 반응형 숨김 요소가 포함될 경우 `space-y-*` 대신 `flex flex-col gap-*` 사용.
- 사이드바 너비는 `w-[150px]` (접힘 `w-14`) 표준 준수.
