import { api } from './client'
import type {
  PnlReport,
  StrategyReport,
  ExchangeReport,
  DailyReport,
  RoiRankingReport,
  MonthlyReport,
  HoldingsReport,
  PairsReport,
  WinStatsReport,
  NlLogsReport,
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
export const fetchReportExchange   = (range: DateRangeValue) => api.get<ExchangeReport>(`/api/reports/exchange?${buildPeriodParams(range)}`)
export const fetchReportDaily      = (range: DateRangeValue) => api.get<DailyReport>(`/api/reports/daily?${buildPeriodParams(range)}`)
export const fetchReportRoiRanking = (range: DateRangeValue) => api.get<RoiRankingReport>(`/api/reports/roi-ranking?${buildPeriodParams(range)}`)
export const fetchReportMonthly    = ()                      => api.get<MonthlyReport>('/api/reports/monthly')
export const fetchReportHoldings   = ()                      => api.get<HoldingsReport>('/api/reports/holdings')
export const fetchReportPairs      = (range: DateRangeValue) => api.get<PairsReport>(`/api/reports/pairs?${buildPeriodParams(range)}`)
export const fetchReportWinStats   = (range: DateRangeValue) => api.get<WinStatsReport>(`/api/reports/win-stats?${buildPeriodParams(range)}`)
export const fetchReportNlLogs     = (limit = 100, offset = 0) => api.get<NlLogsReport>(`/api/reports/nl-logs?limit=${limit}&offset=${offset}`)
