import { api } from './client'
import type {
  PnlReport,
  StrategyReport,
  RoiRankingReport,
  MonthlyReport,
  PairsReport,
  WinStatsReport,
} from '../types'

export const fetchReportPnl        = (period = '30d') => api.get<PnlReport>(`/api/reports/pnl?period=${period}`)
export const fetchReportStrategy   = (period = '30d') => api.get<StrategyReport>(`/api/reports/strategy?period=${period}`)
export const fetchReportRoiRanking = (period = '30d') => api.get<RoiRankingReport>(`/api/reports/roi-ranking?period=${period}`)
export const fetchReportMonthly    = ()               => api.get<MonthlyReport>('/api/reports/monthly')
export const fetchReportPairs      = (period = '30d') => api.get<PairsReport>(`/api/reports/pairs?period=${period}`)
export const fetchReportWinStats   = (period = '30d') => api.get<WinStatsReport>(`/api/reports/win-stats?period=${period}`)
