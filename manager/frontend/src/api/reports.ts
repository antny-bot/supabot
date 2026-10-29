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
  DrawdownReport,
  AllocationReport,
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
export const fetchReportDrawdown   = (range: DateRangeValue) => api.get<DrawdownReport>(`/api/reports/drawdown?${buildPeriodParams(range)}`)
export const fetchReportAllocation = ()                      => api.get<AllocationReport>('/api/reports/allocation')


export interface BatchSummaryItem {
  group_no: number
  exchange: string
  ticker: string
  raw_ticker: string
  strategy: string
  bid_count: number
  ask_count: number
  bid_krw: number
  ask_krw: number
  realized_pnl: number
  holding_vol: number
  avg_buy_price: number
  first_at_fmt: string
  last_at_fmt: string
}

export interface BatchTimelineEvent {
  seq: number
  executed_at: number
  date_fmt: string
  exchange: string
  ticker: string
  raw_ticker: string
  side: string
  price: number
  volume: number
  amount: number
  strategy: string
  group_no: number | null
  holding_vol: number
  avg_buy_price: number
  trade_pnl: number | null
  cum_realized_pnl: number
}

export interface ActiveDcaScheduleItem {
  id: string
  group_no: number | null
  exchange: string
  ticker: string
  raw_ticker: string
  side: string
  frequency: string
  exec_time: string
  amount_type: string
  amount: number
  run_count: number
  max_runs: number | null
  next_run_fmt: string
}

export interface CashAlertItem {
  level: string
  message: string
  details: string
  created_at: string
}

export interface BatchesReport {
  batches: BatchSummaryItem[]
  timeline: BatchTimelineEvent[]
  tickers: string[]
  dca_schedules: ActiveDcaScheduleItem[]
  cash_alerts: CashAlertItem[]
}

export const fetchReportBatches = (
  range: DateRangeValue,
  groupNo?: number | null,
  ticker?: string
) => {
  const params = new URLSearchParams(buildPeriodParams(range))
  if (groupNo !== undefined && groupNo !== null) {
    params.set('group_no', String(groupNo))
  }
  if (ticker && ticker.trim()) {
    params.set('ticker', ticker.trim())
  }
  return api.get<BatchesReport>(`/api/reports/batches?${params.toString()}`)
}
