# supabot-manager Frontend Design

## Purpose

Shared page structure, typography, icon usage, responsive layout, and core UI components for `manager/frontend`.
Every new page and every page-level redesign must follow these rules unless there is a deliberate product decision to change the whole design system.

> Directory/module map (pages, components, hooks, api, ...) lives in `manager/README.md` → "프론트엔드 구조". This document covers *how things must look and behave*, not *where files live*.

## Page Header Rule

- Every app page except `Login` must render a shared `PageHeader` (left icon + title + subtitle + optional right-side actions). Never render a bare `h1` for app pages.
- Titles: short, explicit nouns. Subtitles: one sentence on the page's operational purpose.

## Icon Rule

- The header icon must reuse the same Lucide icon used for the page in navigation, sourced from `src/config/pageMeta.ts`.
- `BottomNav`, `TopBar`, `Sidebar`, and page headers must all reference the icon defined there.
- New page checklist: define metadata + icon in `pageMeta.ts` first, then reuse that icon in `PageHeader`.

## Page Composition

Default order for app pages: `PageHeader` → status feedback (`ErrorBanner`/success banners) → filters/summary controls → summary cards → primary data card/table/chart/form → small footer metadata (totals, etc).

Use `space-y-4`/`space-y-5`/`space-y-6` and keep one clear vertical rhythm.

## Core Components

Prefer these shared building blocks before inventing new page-specific UI:
`PageHeader`, `StatCard`, `FilterBar`, `ErrorBanner`, `Spinner`, `Badge`, `Button`, `ProgressBar`, `MfaSettingsCard`, `DisplaySettingsCard`.

If a pattern repeats on 2+ pages, extract it into `src/components/ui` (or another shared folder) instead of duplicating markup.

## Card and Surface Style

- Default card shell: `bg-white dark:bg-slate-900` / `border border-slate-200 dark:border-slate-800` / `rounded-xl` / `shadow-sm`.
- Tables live inside a card shell with a bordered header row.
- Filters sit above the main content — not mixed into unrelated cards.

## Typography

- Manager-wide font system is user-adjustable from `Config > 표시` (font family + size `12px`–`22px`, default `16px`; storage in `src/lib/displayPreferences.ts`). Root uses `font-app-ui` so preferences apply everywhere.
- Fonts: `Noto Sans KR`, `Noto Serif KR`.

Prefer these app tokens over page-local `text-*` sizing:

| Use | Token |
|---|---|
| Page title | `text-app-title font-bold` |
| Subtitle | `text-app-body-sm text-slate-500 dark:text-slate-400` |
| Card section title | `text-app-body font-semibold` |
| Body / compact body | `text-app-body` / `text-app-body-sm` |
| Labels, table headers | `text-app-label` |
| Metadata, badges | `text-app-caption` |
| Large metric values | `text-app-metric` |

`src/index.css` remaps legacy `text-xs`…`text-3xl` inside `.font-app-ui` as a *compatibility layer* (not the preferred authoring style — use the tokens above for new code). Numeric/code-like cells keep `font-mono`; only the surrounding size scale should change. Keep titles/subtitles visually consistent across all pages.

## Display Settings

- The `표시` card (font family + size) lives on `Config`, applies immediately while editing, and persists via `localStorage` only — **never** route it through `/api/sysconfig` or other shared backend config.

## Actions

- Page-level primary actions tied directly to the page belong in the `PageHeader` actions slot (e.g. template creation on `Templates`, period filter on `Reports`/`Trades`).
- Secondary filters can sit below the header when multiple controls would make the header too dense.

## Responsive Layout (Mobile ↔ Desktop)

> Frontend 구조(파일 위치)는 `manager/README.md` "프론트엔드 구조" 참고. 여기서는 모바일↔데스크톱 전환 규칙만 다룬다.

### Breakpoint convention
- **단일 브레이크포인트 `md:` (768px)** 로 모바일/데스크톱을 가른다 — mobile-first 기본 스타일에 `md:`로 데스크톱을 오버라이드한다.
  (코드 기준 `md:` 사용 44회 vs `sm:`/`lg:`/`xl:` 합계 9회 — 압도적 표준. 새 분기점을 임의로 추가하지 않는다.)
- **레이아웃 스위치**: `AppLayout`이 분기한다.
  ```
  md+:  [ Sidebar (sticky, full-height) ] [ main content (flex-1) ]
  <md:  [ TopBar ] / [ main content ] / [ BottomNav (fixed bottom) ]
  ```
  `TopBar`는 `md:hidden`, `Sidebar`는 `hidden md:flex`로 상호 배타 — 둘 다 보이면 회귀.

### General principles
- Desktop과 mobile은 동일한 정보 위계를 유지한다. 헤더 아이콘·제목·부제는 모바일에서도 항상 보여야 한다.
- 페이지 헤더 액션은 작은 화면에서 제목 블록 아래로 줄바꿈될 수 있다.
- 모바일 하단 네비 라벨은 데스크톱보다 짧을 수 있으나 동일한 page metadata/icon을 참조해야 한다.
- 폰트 크기를 허용 범위 상단까지 키워도 네비 라벨·필터 칩·밀집 테이블의 가독성과 정보 위계가 깨지면 안 된다.

### Tab strip — responsive 2-mode
다중 탭 페이지는 반드시 이 패턴을 쓴다:
- **Desktop (`md:`)**: underline 탭 — `border-b-2 -mb-px`, 하단 보더 컨테이너로 감쌈. 활성 = `border-indigo-600 text-indigo-600`
- **Mobile (기본)**: 가로 스크롤 다이얼 — `overflow-x-auto`, `snap-x snap-mandatory`, pill 버튼(`rounded-full`). 활성 = `bg-indigo-600 text-white`

규칙: 탭에 `flex-wrap` 금지(여러 줄 줄바꿈 = 회귀) · 모바일 스크롤 컨테이너는 `index.css`의 `scrollbar-none` 유틸로 스크롤바 숨김(Tailwind 스크롤바 플러그인 추가 금지).

### Mobile navigation — Bottom Nav + 전체 Drawer
- 하단 네비는 **최대 6개**: 고정 항목 최대 5개(`localStorage` nav 순서의 앞 `MAX_PINNED`개) + 고정 **"전체"** 버튼(햄버거, 맨 우측). 순서·기본 페이지는 `src/lib/navPreferences.ts`에 저장.
- **전체 Drawer (`AllMenuDrawer`)**: "전체" 버튼으로 바텀시트 슬라이드업, admin 전용 항목은 비admin에 숨김.
  - **드래그 재정렬**: `@dnd-kit/core`+`@dnd-kit/sortable` → `writeNavOrder`로 즉시 저장, 상위 5개가 고정 항목이 됨. 이 패턴을 다른 화면에 재구현할 때는 `docs/drag-reorder-menu.md` 참고.
  - **별표(★) = 기본 페이지**: 탭하면 로그인 후 랜딩 페이지로 지정(`writeDefaultPage`), 동시에 하나만 가능.
  - `BottomNav`는 `sbm-navprefs-change` 커스텀 이벤트로 변경을 구독·재렌더링.
- 모든 페이지는 `src/config/pageMeta.ts`의 `APP_NAV_ITEMS`에 선언. 현재 키: `dashboard`, `orders`, `trades`, `templates`, `reports`, `admin`(admin 전용), `config`. `adminOnly: true` 항목은 drawer에서 숨겨지고 비admin에 고정되지 않음.
- **규칙**: `APP_NAV_ITEMS` 밖에서 nav 리스트 하드코딩 금지 · 슬롯 6개(고정 5 + 전체) 초과 금지 · 기본 고정 순서 `dashboard, orders, trades, reports, config` · 새 페이지는 `APP_NAV_ITEMS` + `navPreferences.ALL_NAV_KEYS`에 등록하면 drawer에 자동 표시.

### Desktop sidebar layout
`AppLayout`이 `md:`+ 에서 `Sidebar.tsx`(sticky 좌측, full-height)를 렌더링하고 본문이 우측에 위치한다.

| State | Width | 표시 |
|---|---|---|
| Expanded | `w-56` (224px) | 모든 항목의 아이콘 + 라벨 |
| Collapsed | `w-16` (64px) | 아이콘만, 호버 시 `title` 툴팁 |

- 토글 = 사이드바 헤더 우측의 햄버거(`Menu`) 아이콘 (영역 밖 떠 있는 chevron 버튼 금지). collapsed 상태는 `localStorage` 키 `sbm_sidebar_collapsed`에 저장.
- 헤더: 좌측 = supabot 로고(Zap + "supabot", collapsed 시 숨김, `/dashboard` NavLink) / 우측 = `Menu` 토글.
- Nav 항목은 `APP_NAV_ITEMS`를 `adminOnly` vs `user.is_admin`으로 필터. 활성 = `bg-indigo-50 text-indigo-600`(light) / `bg-indigo-900/30 text-indigo-400`(dark). **설정(`/config`)·관리자(`/admin`)는 일반 nav 항목** — 별도 하단 버튼으로 중복 배치 금지.
- **하단 유저 행**: 아바타(이메일 첫 글자) + 이메일(collapsed 시 숨김), 클릭 시 위로 슬라이드되는 설정 팝업(`absolute bottom-full`):
  1. 테마 행 (Sun/Moon, 활성 모드 `bg-indigo-50` 강조) → 2. **설정** `/config` → 3. **관리자 메뉴** `/admin` (admin만) → 4. **로그아웃** (상단 보더 구분, rose)
  - 팝업은 외부 클릭(`mousedown`) 또는 네비 링크 클릭 시 닫힘. Settings/Theme/Logout 전용 별도 버튼 추가 금지.
- **규칙**: 데스크톱에서 `TopBar` 금지(`md:hidden`) · 모바일에서 `Sidebar` 금지(`hidden md:flex`) · `Sidebar.tsx`가 데스크톱 네비/유저 표시/세션 액션의 단일 소스 · `<aside>`에 `overflow-visible` 필수(없으면 팝업이 잘림).

## Page Architecture

- **Admin** (`/admin`, admin-only): 3개 탭 — 유저관리(`<UsersContent />` from `pages/Users.tsx`), 이벤트(`<EventsContent />` from `pages/Events.tsx`), 주문 및 신호 주기(모니터링 간격 설정 폼). `/users`·`/events`는 `/admin`으로 redirect. 새 admin 전용 기능은 새 라우트 대신 `Admin.tsx`에 탭 추가.
- **Config** (`/config`): 2개 탭 — 화면 표시(`DisplaySettingsCard`, localStorage only), 보안(`MfaSettingsCard`, TOTP/MFA). 모니터링 간격은 `/admin` "주문 및 신호 주기" 탭으로 이동됨.

## Accordion / Collapsible Animation

모든 collapsible 패널(`collapsible`+`isOpen`+`onToggle` props)은 열림/닫힘 애니메이션이 필수다. 즉시 전환은 디자인 회귀로 처리한다.

**기법**: JS 높이 측정이나 외부 라이브러리 없이 CSS `grid-template` 전환(`0fr → 1fr`)으로 구현. 방향에 따라 `grid-rows`/`grid-cols` 선택.

#### 1. 세로 아코디언 — 일반 패널/설정창
```tsx
<div className={`grid transition-all duration-200 ease-in-out ${
  isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'
}`}>
  <div className="overflow-hidden min-h-0">
    <div className="pt-2">{/* content */}</div>
  </div>
</div>
```
아이콘: `ChevronDown`, 열릴 때 180° 회전.

#### 2. 가로 아코디언 — 다중 필터 바 (`FilterBar`, `DateRangePicker`)
닫혀있을 때 필터 버튼들을 밀착시키고, 펼쳐질 때 우측 공간을 확보한다.
```tsx
<div className={`flex items-center ${className}`}>
  <button onClick={onToggle} className="shrink-0">{/* trigger chip */}</button>
  <div className={`grid transition-all duration-200 ease-in-out ${
    isOpen ? 'grid-cols-[1fr] opacity-100 ml-1.5' : 'grid-cols-[0fr] opacity-0 ml-0'
  }`}>
    <div className="overflow-hidden min-w-0">
      <div className="flex flex-nowrap items-center gap-1.5 whitespace-nowrap">
        {/* filter options */}
      </div>
    </div>
  </div>
</div>
```
아이콘: `ChevronRight`, 열릴 때 180°(좌측 방향) 회전. **주의**: 펼쳐지는 동안 줄바꿈이 생기면 애니메이션이 끊기므로 `flex-nowrap`+`whitespace-nowrap` 필수.

**공통 규칙**: 표준 duration **200ms ease-in-out**(제품적 이유 없이 변경 금지) · 트리거 칩은 항상 마운트 유지(unmount/remount 금지) · `overflow-hidden`+`min-h-0`(또는 `min-w-0`) 필수(없으면 `0fr`로 완전히 수축되지 않음) · `grid-rows-[0fr]`/`grid-cols-[1fr]`은 Tailwind JIT arbitrary value로 지원됨.

지원 브라우저: Chrome 107+, Firefox 109+, Safari 16.4+ (관리자 대시보드 지원 범위).

## Maintenance Rule

- New page → update `src/config/pageMeta.ts`, use `PageHeader`, add nav config if user-visible.
- Title/subtitle/icon changes → update `pageMeta.ts` first.
- Shared typography changes → update `src/index.css` and this document together.
- New display-preference controls stay frontend-local unless there's an explicit product decision to sync server-side.
- Missing subtitles or page-local icon drift = design regressions; reviewers should flag them.
