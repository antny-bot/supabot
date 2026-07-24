# Manager Display Font Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add manager-wide display controls for Korean font family and font size using local browser preferences and shared typography tokens.

**Architecture:** Keep the change frontend-only. Persist display preferences in `localStorage`, apply them at the document root through CSS variables and data attributes, and migrate shared UI/page text sizes from direct Tailwind classes to app typography tokens so the entire manager responds consistently.

**Tech Stack:** React, TypeScript, Vite, Tailwind CSS, localStorage, CSS custom properties

---

### Task 1: Add display preference infrastructure

**Files:**
- Create: `manager/frontend/src/lib/displayPreferences.ts`
- Modify: `manager/frontend/src/components/layout/AppLayout.tsx`
- Modify: `manager/frontend/src/index.css`

- [ ] Define the local display preference model, default values, storage key, clamp logic, and root-application helpers.
- [ ] Apply saved preferences on manager app startup from `AppLayout.tsx`.
- [ ] Add app typography token utilities and font-family selectors in `index.css`.

### Task 2: Add the display settings UI

**Files:**
- Modify: `manager/frontend/src/pages/Config.tsx`

- [ ] Add a new display settings card for font family and font size.
- [ ] Make changes apply immediately and persist to `localStorage`.
- [ ] Add a readable preview block and reset action.

### Task 3: Migrate shared typography classes

**Files:**
- Modify: `manager/frontend/src/components/layout/TopBar.tsx`
- Modify: `manager/frontend/src/components/layout/BottomNav.tsx`
- Modify: `manager/frontend/src/components/ui/PageHeader.tsx`
- Modify: `manager/frontend/src/components/ui/FilterBar.tsx`
- Modify: `manager/frontend/src/components/ui/Button.tsx`
- Modify: `manager/frontend/src/components/ui/Badge.tsx`
- Modify: `manager/frontend/src/components/ui/StatCard.tsx`
- Modify: `manager/frontend/src/components/ui/ProgressBar.tsx`
- Modify: `manager/frontend/src/components/ui/ErrorBanner.tsx`
- Modify: `manager/frontend/src/components/settings/MfaSettingsCard.tsx`

- [ ] Replace direct small/medium text sizes in shared layout/UI with app token classes.
- [ ] Preserve `font-mono` where numeric/code styling is intentional.
- [ ] Ensure top bar and bottom nav remain stable at larger sizes.

### Task 4: Migrate high-traffic manager pages

**Files:**
- Modify: `manager/frontend/src/pages/Config.tsx`
- Modify: `manager/frontend/src/pages/Dashboard.tsx`
- Modify: `manager/frontend/src/pages/Orders.tsx`
- Modify: `manager/frontend/src/pages/Trades.tsx`
- Modify: `manager/frontend/src/pages/Users.tsx`
- Modify: `manager/frontend/src/pages/Reports.tsx`
- Modify: `manager/frontend/src/pages/Templates.tsx`
- Modify: `manager/frontend/src/pages/Events.tsx`
- Modify: `manager/frontend/src/pages/Login.tsx`

- [ ] Replace repeated `text-xs`, `text-sm`, and micro pixel sizes with app typography tokens.
- [ ] Normalize labels, captions, table text, and card headings.
- [ ] Keep dense layouts readable on both desktop tables and mobile cards.

### Task 5: Verify

**Files:**
- Verify only

- [ ] Run `cd manager/frontend && npm.cmd run build`.
- [ ] Run `cd manager && python -m py_compile backend/**/*.py`.
- [ ] Spot-check the updated files for obvious overflow or inconsistent typography usage.
