import { api } from './client'
import type { TradesData } from '../types'
import type { DateRangeValue } from '../components/ui/DateRangePicker'

function buildParams(range: DateRangeValue, page: number, pageSize: number): string {
  const params = new URLSearchParams()
  if (range.mode === 'custom') {
    if (range.from) params.set('date_from', range.from)
    if (range.to) params.set('date_to', range.to)
  } else {
    params.set('period', range.mode)
  }
  params.set('page', String(page))
  params.set('page_size', String(pageSize))
  return params.toString()
}

export const fetchTrades = (range: DateRangeValue, page = 1, pageSize = 50) =>
  api.get<TradesData>(`/api/trades?${buildParams(range, page, pageSize)}`)
