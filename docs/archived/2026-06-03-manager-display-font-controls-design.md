# Manager Display Font Controls Design

## Goal

Add a display settings section to the Supabot manager so an admin can:

- choose a Korean UI font between `Noto Sans KR` and `Noto Serif KR`
- adjust the manager font size with a slider from `12px` to `22px`
- apply the choice across the entire manager UI, including top bar, bottom navigation, cards, tables, forms, buttons, badges, and empty states

This is a per-browser display preference, not a shared system setting.

## Scope

In scope:

- `manager/frontend/src/pages/Config.tsx` display settings UI
- manager frontend local persistence via `localStorage`
- manager-wide typography tokens for font family and size
- React manager pages and shared UI/layout components
- desktop and mobile manager layouts

Out of scope:

- Supabot bot runtime settings
- backend `sysconfig` storage or API changes
- legacy Jinja templates under `manager/frontend/templates/`

## Constraints

- Keep the existing dark mode behavior unchanged.
- Do not store display preferences in Supabase or shared backend config.
- Preserve monospace rendering for numeric/code-like cells where `font-mono` is already intentional.
- Replace scattered Tailwind text sizing usage with app typography classes rather than relying on a single global body font-size override.

## Recommended Approach

Use a Tailwind class replacement strategy with app-specific typography tokens.

Why:

- It matches the requested implementation direction.
- It keeps visual hierarchy stable while still allowing the base size to grow or shrink.
- It avoids browser-zoom style layout distortion.
- It gives explicit control over tiny text usages that are currently too small for older users.

## Architecture

### 1. Local display preference model

Create a frontend-only display settings model with:

- `fontFamily`: `noto-sans-kr` | `noto-serif-kr`
- `fontSizePx`: number from 12 to 22

Persist it in `localStorage`, similar to the current theme toggle.

Suggested key:

- `manager.display.preferences`

### 2. Display settings hook

Add a shared hook or utility that:

- reads the saved preference on startup
- applies the active font family and font scale to the document root
- exposes current values and setters for the settings page

The root should receive attributes or classes that can drive typography tokens, for example:

- `data-font-family="noto-sans-kr"`
- `style="--app-font-size: 16px"`

### 3. Typography token layer

Define app-specific typography utility classes in `manager/frontend/src/index.css` using Tailwind layers and CSS variables.

Representative tokens:

- `text-app-caption`
- `text-app-label`
- `text-app-body`
- `text-app-body-sm`
- `text-app-title`
- `text-app-title-lg`
- `font-app-ui`

These tokens should derive from `--app-font-size` with fixed relative steps so the whole UI grows proportionally without losing hierarchy.

Example intent:

- captions and badge text remain smaller than body text
- table text and form text follow the same body scale
- page titles stay visually prominent

### 4. Class migration strategy

Replace direct Tailwind size classes in shared UI and major pages with app typography tokens.

Priority order:

1. Shared layout/components:
   - `AppLayout.tsx`
   - `TopBar.tsx`
   - `BottomNav.tsx`
   - `PageHeader.tsx`
   - `FilterBar.tsx`
   - `Button.tsx`
2. Settings page:
   - `Config.tsx`
3. High-density data pages:
   - `Orders.tsx`
   - `Trades.tsx`
   - `Users.tsx`
   - `Reports.tsx`
   - `Templates.tsx`
   - `Dashboard.tsx`

Direct pixel micro-sizes such as `text-[8px]`, `text-[9px]`, `text-[10px]`, and repeated `text-xs` usages should be normalized into the app token scale unless there is a strict visual reason not to.

### 5. Config page UI

Add a new "display" card in `Config.tsx` with:

- font family segmented buttons or radio-style choices:
  - `Noto Sans KR`
  - `Noto Serif KR`
- font size slider:
  - min `12`
  - max `22`
  - step `1`
- current value label such as `16px`
- one-line preview text
- reset action back to the default profile if helpful

The setting should apply immediately while editing and remain after refresh.

## Data Flow

1. App boots.
2. Display preferences are read from `localStorage`.
3. Root font variables and font-family markers are applied.
4. Shared typography token classes resolve against those variables.
5. Settings page updates the same store and writes back to `localStorage`.
6. UI rerenders with the new typography immediately.

No backend request is required for display settings.

## Defaults

Recommended defaults:

- font family: `Noto Sans KR`
- font size: `16px`

Rationale:

- `16px` is a safer baseline for a broader age range than the current effective UI density.
- sans-serif should remain the default because it is more neutral for dense admin tables.

## Error Handling

- If `localStorage` is unavailable or parsing fails, fall back to defaults silently.
- If an unknown font value is found, coerce to `Noto Sans KR`.
- If the saved size is outside `12..22`, clamp it into range.

## Testing

### Functional verification

- Open manager config page.
- Change font family and confirm the whole manager updates.
- Change font size across the slider range and confirm:
  - top bar updates
  - bottom navigation updates
  - tables update
  - form labels and inputs update
  - badges and helper text remain readable
- Refresh and confirm preferences persist.

### Layout verification

- Desktop:
  - dashboard
  - orders
  - trades
  - reports
  - config
- Mobile width:
  - bottom nav wrapping/overflow
  - table cards and dense summaries
  - config controls spacing

### Build and syntax verification

- `cd manager/frontend && npm.cmd run build`
- manager backend syntax check per repo guidance:
  - `cd manager && python -m py_compile backend/**/*.py`

## Risks and Mitigations

- Risk: incomplete class migration leaves some pages visually inconsistent.
  - Mitigation: migrate shared components first, then the highest-traffic pages, then sweep remaining direct text classes with targeted search.

- Risk: larger sizes may cause dense table overflow.
  - Mitigation: keep table cells on tokenized sizes and verify both table and mobile card layouts at 20px and 22px.

- Risk: serif font may reduce dense data readability.
  - Mitigation: keep serif as an option, not the default, and preserve `font-mono` for numbers.

## Implementation Notes

- This design intentionally avoids backend schema or API changes.
- The change should stay isolated to the manager frontend.
- If a future requirement needs per-account synced display settings, the local preference model can later be mirrored to a user profile endpoint, but that is not part of this implementation.
