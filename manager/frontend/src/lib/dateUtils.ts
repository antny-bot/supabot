/**
 * dateUtils.ts
 * 전역 타임존 기반 날짜/시간 포맷팅 유틸리티.
 * 기본값: 'Asia/Seoul' (한국 표준시 KST)
 */

export const DEFAULT_TIMEZONE = 'Asia/Seoul'
export const TIMEZONE_STORAGE_KEY = 'user_timezone'

export interface TimezoneOption {
  value: string
  label: string
  city: string
  offset: string
}

export const TIMEZONE_OPTIONS: TimezoneOption[] = [
  { value: 'Asia/Seoul', label: '한국 / 서울 (KST, UTC+9)', city: '서울', offset: 'UTC+9' },
  { value: 'Asia/Tokyo', label: '일본 / 도쿄 (JST, UTC+9)', city: '도쿄', offset: 'UTC+9' },
  { value: 'America/New_York', label: '미국 동부 / 뉴욕 (EST/EDT)', city: '뉴욕', offset: 'UTC-5/-4' },
  { value: 'America/Los_Angeles', label: '미국 서부 / LA (PST/PDT)', city: '로스앤젤레스', offset: 'UTC-8/-7' },
  { value: 'Europe/London', label: '영국 / 런던 (GMT/BST)', city: '런던', offset: 'UTC+0/+1' },
  { value: 'UTC', label: '협정 세계시 (UTC, UTC+0)', city: 'UTC', offset: 'UTC+0' },
]

export function getUserTimezone(): string {
  if (typeof window === 'undefined') return DEFAULT_TIMEZONE
  return localStorage.getItem(TIMEZONE_STORAGE_KEY) || DEFAULT_TIMEZONE
}

export function setUserTimezone(tz: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(TIMEZONE_STORAGE_KEY, tz || DEFAULT_TIMEZONE)
  window.dispatchEvent(new Event('timezone-changed'))
}

/**
 * ISO 날짜 문자열이나 타임스탬프를 지정된 타임존 기준 'YYYY-MM-DD HH:mm:ss' 또는 'YYYY-MM-DD HH:mm'으로 포맷.
 */
export function formatDateTime(
  dateInput: string | number | Date | null | undefined,
  includeSeconds: boolean = false,
  customTz?: string
): string {
  if (!dateInput) return '—'
  try {
    let d: Date
    if (typeof dateInput === 'number') {
      // 10자리 unix timestamp면 ms로 변환
      d = new Date(dateInput < 10000000000 ? dateInput * 1000 : dateInput)
    } else if (dateInput instanceof Date) {
      d = dateInput
    } else {
      // ISO string 또는 timestamp string
      const str = String(dateInput).trim()
      if (!str) return '—'
      // 만약 타임존 오프셋이 없고 'Z'도 없는 ISO면 UTC로 가정
      const normalized = str.includes('Z') || str.includes('+') || (str.includes('-') && str.indexOf('-', 8) > 0)
        ? str
        : `${str}Z`
      d = new Date(normalized)
    }

    if (isNaN(d.getTime())) return String(dateInput)

    const tz = customTz || getUserTimezone()
    const formatter = new Intl.DateTimeFormat('ko-KR', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: includeSeconds ? '2-digit' : undefined,
      hour12: false,
    })

    const parts = formatter.formatToParts(d)
    const partMap: Record<string, string> = {}
    for (const p of parts) {
      partMap[p.type] = p.value
    }

    const y = partMap.year || ''
    const m = partMap.month || ''
    const day = partMap.day || ''
    const h = partMap.hour || ''
    const min = partMap.minute || ''
    const sec = partMap.second || ''

    if (includeSeconds && sec) {
      return `${y}-${m}-${day} ${h}:${min}:${sec}`
    }
    return `${y}-${m}-${day} ${h}:${min}`
  } catch {
    return String(dateInput)
  }
}

/**
 * 지정된 타임존 기준 'YYYY-MM-DD' 포맷
 */
export function formatDate(
  dateInput: string | number | Date | null | undefined,
  customTz?: string
): string {
  if (!dateInput) return '—'
  try {
    const full = formatDateTime(dateInput, false, customTz)
    return full.slice(0, 10)
  } catch {
    return String(dateInput).slice(0, 10)
  }
}
