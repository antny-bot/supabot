export function krwFmt(n: number) {
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`
  if (n >= 10_000) return `${(n / 10_000).toFixed(0)}만`
  return n.toLocaleString()
}

// 한국식 손익 색상 컨벤션: 수익(상승)=빨강, 손실(하락)=파랑
export function pnlTextClass(v: number) {
  if (v > 0) return 'text-up-600 dark:text-up-400'
  if (v < 0) return 'text-down-600 dark:text-down-400'
  return 'text-slate-500 dark:text-slate-400'
}

export function pnlBgClass(v: number) {
  return v >= 0 ? 'bg-up-500' : 'bg-down-500'
}

export const PNL_UP_HEX = '#e52222'
export const PNL_DOWN_HEX = '#1666e0'
