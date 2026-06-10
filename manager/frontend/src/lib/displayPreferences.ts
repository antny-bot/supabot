export type ManagerFontFamily = 'noto-sans-kr' | 'noto-serif-kr'
export type ManagerAccentColor = 'blue' | 'violet' | 'green'

export interface DisplayPreferences {
  fontFamily: ManagerFontFamily
  fontSizePx: number
  accentColor: ManagerAccentColor
}

export const DISPLAY_PREFERENCES_STORAGE_KEY = 'manager.display.preferences'
export const DISPLAY_PREFERENCES_EVENT = 'manager-display-preferences-change'

export const DISPLAY_FONT_OPTIONS: Array<{ value: ManagerFontFamily; label: string }> = [
  { value: 'noto-sans-kr', label: 'Noto Sans KR' },
  { value: 'noto-serif-kr', label: 'Noto Serif KR' },
]

export const DISPLAY_ACCENT_OPTIONS: Array<{ value: ManagerAccentColor; label: string; swatch: string }> = [
  { value: 'blue', label: 'Blue', swatch: '#0066ff' },
  { value: 'violet', label: 'Violet', swatch: '#5b37ed' },
  { value: 'green', label: 'Green', swatch: '#00bf40' },
]

export const DEFAULT_DISPLAY_PREFERENCES: DisplayPreferences = {
  fontFamily: 'noto-sans-kr',
  fontSizePx: 16,
  accentColor: 'blue',
}

function clampFontSize(value: number) {
  if (!Number.isFinite(value)) return DEFAULT_DISPLAY_PREFERENCES.fontSizePx
  return Math.min(22, Math.max(12, Math.round(value)))
}

function normalizeFontFamily(value: unknown): ManagerFontFamily {
  return value === 'noto-serif-kr' ? 'noto-serif-kr' : 'noto-sans-kr'
}

function normalizeAccentColor(value: unknown): ManagerAccentColor {
  return value === 'violet' || value === 'green' ? value : 'blue'
}

export function normalizeDisplayPreferences(
  value: Partial<DisplayPreferences> | null | undefined,
): DisplayPreferences {
  return {
    fontFamily: normalizeFontFamily(value?.fontFamily),
    fontSizePx: clampFontSize(Number(value?.fontSizePx)),
    accentColor: normalizeAccentColor(value?.accentColor),
  }
}

export function readDisplayPreferences(): DisplayPreferences {
  if (typeof window === 'undefined') return DEFAULT_DISPLAY_PREFERENCES

  try {
    const raw = window.localStorage.getItem(DISPLAY_PREFERENCES_STORAGE_KEY)
    if (!raw) return DEFAULT_DISPLAY_PREFERENCES
    const parsed = JSON.parse(raw) as Partial<DisplayPreferences>
    return normalizeDisplayPreferences(parsed)
  } catch {
    return DEFAULT_DISPLAY_PREFERENCES
  }
}

export function applyDisplayPreferences(preferences: DisplayPreferences) {
  if (typeof document === 'undefined') return preferences

  const next = normalizeDisplayPreferences(preferences)
  const root = document.documentElement
  root.dataset.fontFamily = next.fontFamily
  root.dataset.accent = next.accentColor
  root.style.setProperty('--app-font-size', `${next.fontSizePx}px`)
  return next
}

export function saveDisplayPreferences(preferences: Partial<DisplayPreferences>) {
  const current = readDisplayPreferences()
  const next = normalizeDisplayPreferences({
    ...current,
    ...preferences,
  })

  if (typeof window !== 'undefined') {
    window.localStorage.setItem(DISPLAY_PREFERENCES_STORAGE_KEY, JSON.stringify(next))
    window.dispatchEvent(new CustomEvent(DISPLAY_PREFERENCES_EVENT, { detail: next }))
  }

  return applyDisplayPreferences(next)
}

export function resetDisplayPreferences() {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(DISPLAY_PREFERENCES_STORAGE_KEY)
    window.dispatchEvent(
      new CustomEvent(DISPLAY_PREFERENCES_EVENT, {
        detail: DEFAULT_DISPLAY_PREFERENCES,
      }),
    )
  }

  return applyDisplayPreferences(DEFAULT_DISPLAY_PREFERENCES)
}

export function applySavedDisplayPreferences() {
  return applyDisplayPreferences(readDisplayPreferences())
}
