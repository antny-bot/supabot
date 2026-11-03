export function krwFmt(n: number) {
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`
  if (n >= 10_000) return `${(n / 10_000).toFixed(0)}만`
  return n.toLocaleString()
}

/**
 * 숫자나 숫자 문자열에 천단위 콤마를 추가합니다.
 * 정수부와 소수부를 분리하여 소수점 및 마이너스 기호를 보존합니다.
 */
export function formatWithCommas(val: string | number | undefined | null): string {
  if (val === '' || val === null || val === undefined) return ''
  const str = String(val).replace(/,/g, '')
  if (str === '' || str === '-') return str

  const parts = str.split('.')
  // parts[0]에서 천단위 콤마 처리
  const integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  if (parts.length > 1) {
    return `${integerPart}.${parts[1]}`
  }
  return integerPart
}

/**
 * 콤마가 포함된 문자열에서 콤마를 제거합니다.
 */
export function stripCommas(val: string): string {
  return val.replace(/,/g, '')
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
