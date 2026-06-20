export function krwFmt(n: number) {
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`
  if (n >= 10_000) return `${(n / 10_000).toFixed(0)}만`
  return n.toLocaleString()
}

export function pctFmt(v: number) {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

export function pctColor(v: number) {
  if (v > 0) return 'text-up-600 dark:text-up-400'
  if (v < 0) return 'text-down-600 dark:text-down-400'
  return 'text-slate-500 dark:text-slate-400'
}

export const PNL_UP_HEX = '#e52222'
export const PNL_DOWN_HEX = '#1666e0'

export const CARD = 'bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm'
export const TH = 'px-4 py-2.5 font-medium'
export const TD = 'px-4 py-2.5'
export const MEDALS = ['🥇', '🥈', '🥉']
