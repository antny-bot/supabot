# supabot-manager Frontend Design

## Purpose

This document defines the shared page structure, typography, icon usage, and core UI components for `manager/frontend`.
Every new page and every page-level redesign must follow these rules unless there is a deliberate product decision to change the whole design system.

## Page Header Rule

- Every app page except `Login` must render a shared `PageHeader` at the top.
- `PageHeader` must contain:
  - a left icon
  - a page title
  - a page subtitle
  - optional right-side actions
- Do not render a bare `h1` directly in page files for app pages.
- Titles should be short, explicit nouns.
- Subtitles should explain the page's operational purpose in one sentence.

## Icon Rule

- The header icon must reuse the same Lucide icon used for the page in navigation.
- The source of truth is `src/config/pageMeta.ts`.
- `BottomNav`, `TopBar`, and page headers must reference the same icon definitions.
- When a new page is added:
  - define its metadata in `pageMeta.ts`
  - choose the navigation icon there first
  - reuse that icon in `PageHeader`

## Page Composition

Use this order for app pages by default:

1. `PageHeader`
2. status feedback like `ErrorBanner` or success banners
3. filters or summary controls
4. summary cards when needed
5. primary data card, table, chart, or form
6. small footer metadata like totals

Pages should normally use `space-y-4`, `space-y-5`, or `space-y-6` and keep one clear vertical rhythm.

## Core Components

Prefer these shared building blocks before inventing new page-specific UI:

- `PageHeader`
- `StatCard`
- `FilterBar`
- `ErrorBanner`
- `Spinner`
- `Badge`
- `Button`
- `ProgressBar`
- `MfaSettingsCard`
- `DisplaySettingsCard`

If a new repeated pattern appears on 2 or more pages, extract it into `src/components/ui` or another shared component folder instead of duplicating markup.

## Card and Surface Style

- Primary content surfaces use rounded cards with border and subtle shadow.
- Default card shell:
  - `bg-white dark:bg-slate-900`
  - `border border-slate-200 dark:border-slate-800`
  - `rounded-xl`
  - `shadow-sm`
- Tables should live inside a card shell with a bordered header row.
- Filters should sit above the main content, not be mixed into unrelated cards.

## Typography

- The manager font system is user-adjustable from `Config > 표시`.
- Display preferences are local browser preferences, not shared backend settings.
- Storage and root application live in `src/lib/displayPreferences.ts`.
- The app root must use `font-app-ui` so display preferences affect the whole manager surface.
- Font choices:
  - `Noto Sans KR`
  - `Noto Serif KR`
- Font size range:
  - `12px` to `22px`
  - default `16px`

Prefer these app typography tokens over page-local `text-*` sizing when touching manager UI:

- Page title: `text-app-title font-bold`
- Subtitle: `text-app-body-sm text-slate-500 dark:text-slate-400`
- Section title inside cards: `text-app-body font-semibold`
- Body copy: `text-app-body`
- Compact body: `text-app-body-sm`
- Labels and table headers: `text-app-label`
- Supporting metadata and badges: `text-app-caption`
- Large metric values: `text-app-metric`

Implementation note:

- `src/index.css` also remaps legacy `text-xs`, `text-sm`, `text-lg`, `text-xl`, `text-2xl`, and `text-3xl` inside `.font-app-ui` so older screens still respond to display settings.
- This remap is a compatibility layer, not the preferred long-term authoring style.

Keep titles and subtitles visually consistent across all pages.

## Display Settings

- The `표시` card belongs on `Config`.
- It controls:
  - manager-wide font family
  - manager-wide font size slider
- Changes should apply immediately while editing.
- Changes must persist through refresh using `localStorage`.
- Do not route display settings through `/api/sysconfig` or other shared backend config.
- Numeric/code-like cells should keep `font-mono`; only the surrounding size scale should change.

## Actions

- Page-level primary actions belong in the `PageHeader` actions slot when they are directly tied to the page.
- Examples:
  - template creation on `Templates`
  - period filter on `Reports` or `Trades`
- Secondary filters can remain below the header when multiple controls would make the header too dense.

## Responsiveness

- Desktop and mobile must preserve the same information hierarchy.
- Header icon, title, and subtitle must stay visible on mobile.
- Page header actions may wrap below the title block on smaller screens.
- Mobile bottom navigation labels may be shorter than desktop labels, but they must still reference the same page metadata and icon.
- When increasing font size toward the top of the allowed range, navigation labels, filter chips, and dense tables must remain readable without breaking the information hierarchy.

## Maintenance Rule

- Any new page must add or update:
  - `src/config/pageMeta.ts`
  - its page file to use `PageHeader`
  - navigation config if the page is user-visible in nav
- Any change to page-level titles, subtitles, or representative icons must update `pageMeta.ts` first.
- Any shared typography change must be reflected in `src/index.css` and this document together.
- Any new display-preference control must stay frontend-local unless there is an explicit product decision to sync it server-side.
- Reviewers should treat missing subtitles or page-local icon drift as design regressions.
