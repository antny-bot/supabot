import { api } from './client'
import type {
  PnlReport,
  StrategyReport,
  RoiRankingReport,
  MonthlyReport,
  HoldingsReport,
  PairsReport,
  WinStatsReport,
  NlLogsData,
} from '../types'
import type { DateRangeValue } from '../components/ui/DateRangePicker'

function buildPeriodParams(range: DateRangeValue): string {
  const params = new URLSearchParams()
  if (range.mode === 'custom') {
    if (range.from) params.set('date_from', range.from)
    if (range.to) params.set('date_to', range.to)
  } else {
    params.set('period', range.mode)
  }
  return params.toString()
}

export const fetchReportPnl        = (range: DateRangeValue) => api.get<PnlReport>(`/api/reports/pnl?${buildPeriodParams(range)}`)
export const fetchReportStrategy   = (range: DateRangeValue) => api.get<StrategyReport>(`/api/reports/strategy?${buildPeriodParams(range)}`)
export const fetchReportRoiRanking = (range: DateRangeValue) => api.get<RoiRankingReport>(`/api/reports/roi-ranking?${buildPeriodParams(range)}`)
export const fetchReportMonthly    = ()                      => api.get<MonthlyReport>('/api/reports/monthly')
export const fetchReportHoldings   = ()                      => api.get<HoldingsReport>('/api/reports/holdings')
export const fetchReportPairs      = (range: DateRangeValue) => api.get<PairsReport>(`/api/reports/pairs?${buildPeriodParams(range)}`)
export const fetchReportWinStats   = (range: DateRangeValue) => api.get<WinStatsReport>(`/api/reports/win-stats?${buildPeriodParams(range)}`)
export const fetchNlLogs           = (period: string, limit: number) => api.get<NlLogsData>(`/api/nl-logs?period=${period}&limit=${limit}`)
