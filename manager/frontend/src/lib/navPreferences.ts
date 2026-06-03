const NAV_ORDER_KEY = 'sbm_nav_order'
const NAV_DEFAULT_KEY = 'sbm_nav_default'

export const ALL_NAV_KEYS = [
  'dashboard', 'orders', 'trades', 'templates', 'reports', 'admin', 'config',
] as const
export type NavKey = (typeof ALL_NAV_KEYS)[number]

const DEFAULT_ORDER: NavKey[] = [
  'dashboard', 'orders', 'trades', 'reports', 'config', 'templates', 'admin',
]

export const MAX_PINNED = 5

export function readNavOrder(): NavKey[] {
  try {
    const raw = localStorage.getItem(NAV_ORDER_KEY)
    if (raw) {
      const stored = JSON.parse(raw) as NavKey[]
      const valid = stored.filter((k): k is NavKey => (ALL_NAV_KEYS as readonly string[]).includes(k))
      const missing = (ALL_NAV_KEYS as readonly NavKey[]).filter((k) => !valid.includes(k))
      return [...valid, ...missing]
    }
  } catch {}
  return [...DEFAULT_ORDER]
}

export function writeNavOrder(order: NavKey[]) {
  localStorage.setItem(NAV_ORDER_KEY, JSON.stringify(order))
  window.dispatchEvent(new Event('sbm-navprefs-change'))
}

export function readDefaultPage(): string | null {
  return localStorage.getItem(NAV_DEFAULT_KEY)
}

export function writeDefaultPage(route: string | null) {
  if (route === null) localStorage.removeItem(NAV_DEFAULT_KEY)
  else localStorage.setItem(NAV_DEFAULT_KEY, route)
  window.dispatchEvent(new Event('sbm-navprefs-change'))
}
