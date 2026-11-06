import type { Template, TemplateParams } from '../../api/templates'
import { formatWithCommas, stripCommas } from '../../utils/formatters'

export interface TemplateFormState {
  name: string
  exchange: string
  ticker: string
  strategyType: string
  startPrice: string
  endPrice: string
  count: string
  budget: string
  buyRsiRange: string
  sellRsiRange: string
  weighted: boolean
  dcaSchedule: string
  dcaExecTime: string
  dcaAmountType: 'budget' | 'volume'
  topMarket: string
  rankStart: string
  rankEnd: string
  excludePreferred: boolean
  upperExitMode: 'sell_on_any_exit' | 'hold_on_promotion'
  exitRankBuffer: string
  exitConfirmDays: string
  sellSplitDays: string
  budgetMode: 'monthly' | 'daily'
  dailyFixedBudget: string
  tradingDaysPerMonth: string
  cycleAllocMode: 'one_share' | 'target_amount'
  cycleTargetKrw: string
  sellProceedsMode: 'keep_cash' | 'recycle_to_budget'
  orderPriceMode: 'limit_current' | 'limit_aggressive' | 'market'
  scheduleEnabled: boolean
  isDryRun: boolean
}

export const DEFAULT_SINGLE_FORM: TemplateFormState = {
  name: '',
  exchange: 'upbit',
  ticker: 'BTC',
  strategyType: 'grid',
  startPrice: '',
  endPrice: '',
  count: '10',
  budget: '100000',
  buyRsiRange: '25-30',
  sellRsiRange: '65-75',
  weighted: false,
  dcaSchedule: '매일',
  dcaExecTime: '09:05',
  dcaAmountType: 'budget',
  topMarket: 'KOSPI',
  rankStart: '1',
  rankEnd: '10',
  excludePreferred: true,
  upperExitMode: 'sell_on_any_exit',
  exitRankBuffer: '2',
  exitConfirmDays: '2',
  sellSplitDays: '5',
  budgetMode: 'monthly',
  dailyFixedBudget: '150000',
  tradingDaysPerMonth: '20',
  cycleAllocMode: 'one_share',
  cycleTargetKrw: '300000',
  sellProceedsMode: 'keep_cash',
  orderPriceMode: 'limit_current',
  scheduleEnabled: true,
  isDryRun: false,
}

export const DEFAULT_MULTI_FORM: TemplateFormState = {
  ...DEFAULT_SINGLE_FORM,
  name: '',
  exchange: 'toss',
  ticker: 'KOSPI_TOP10',
  strategyType: 'kospi_top_dca',
  budget: '3000000',
  dcaExecTime: '09:10',
  topMarket: 'KOSPI',
  rankStart: '1',
  rankEnd: '10',
  count: '10',
}

export const STRATEGY_TYPE_LABELS: Record<string, string> = {
  kospi_top_dca: 'KOSPI/KOSDAQ 시총 상위 TOP N 모으기 & 분할매도',
  grid: '거미줄 분할 매수 (/grid)',
  sgrid: '거미줄 분할 매도 (/sgrid)',
  rsitrade: 'RSI 순환 매매 (/rsitrade)',
  rsi: 'RSI 순환 매매 (/rsitrade)',
  dca: '정기 적립식 매수 (/dca)',
  sdca: '정기 분할 매도 (/sdca)',
}

export const STRATEGY_BADGE_LABELS: Record<string, string> = {
  kospi_top_dca: 'TOP N DCA',
  grid: '거미줄 매수 (GRID)',
  sgrid: '거미줄 매도 (SGRID)',
  rsitrade: 'RSI 순환매매',
  rsi: 'RSI 순환매매',
  dca: '정기 매수 (DCA)',
  sdca: '정기 매도 (SDCA)',
}

export function normalizeStrategyType(raw?: string): string {
  if (!raw) return 'grid'
  if (raw === 'rsi') return 'rsitrade'
  return raw
}

export function buildPayload(form: TemplateFormState) {
  const stype = normalizeStrategyType(form.strategyType)
  const parsedCount = parseInt(stripCommas(form.count), 10)
  const payload = {
    name: form.name.trim(),
    exchange: form.exchange,
    ticker: form.ticker.trim().toUpperCase(),
    start_price: 0,
    end_price: 0,
    count: Number.isNaN(parsedCount) ? 0 : parsedCount,
    budget: parseFloat(stripCommas(form.budget)) || 0,
    strategy_type: stype,
    params: {} as TemplateParams,
  }

  if (stype === 'grid' || stype === 'sgrid') {
    payload.start_price = parseFloat(stripCommas(form.startPrice)) || 0
    payload.end_price = parseFloat(stripCommas(form.endPrice)) || 0
  } else if (stype === 'rsitrade') {
    payload.params = {
      buy_rsi_range: form.buyRsiRange.trim(),
      sell_rsi_range: form.sellRsiRange.trim(),
      weighted: form.weighted,
    }
  } else if (stype === 'dca' || stype === 'sdca') {
    const maxRuns = payload.count > 0 ? payload.count : null
    payload.params = {
      schedule: form.dcaSchedule.trim() || '매일',
      exec_time: form.dcaExecTime.trim() || '09:05',
      amount_type: form.dcaAmountType,
      max_runs: maxRuns,
      side: stype === 'sdca' ? 'ask' : 'bid',
    }
  } else if (stype === 'kospi_top_dca') {
    const rStart = Math.max(1, parseInt(form.rankStart, 10) || 1)
    const rEnd = Math.max(rStart, parseInt(form.rankEnd, 10) || 10)
    const mkt = form.topMarket || 'KOSPI'
    payload.ticker = rStart === 1 ? `${mkt}_TOP${rEnd}` : `${mkt}_TOP${rStart}_${rEnd}`
    payload.count = rEnd - rStart + 1
    payload.budget =
      form.budgetMode === 'daily'
        ? parseFloat(stripCommas(form.dailyFixedBudget)) || 150000
        : parseFloat(stripCommas(form.budget)) || 3000000
    payload.params = {
      market: mkt,
      rank_start: rStart,
      rank_end: rEnd,
      top_n: rEnd,
      exclude_preferred: form.excludePreferred,
      upper_exit_mode: form.upperExitMode,
      exit_rank_buffer: Math.max(0, parseInt(form.exitRankBuffer, 10) || 0),
      exit_confirm_days: Math.max(1, parseInt(form.exitConfirmDays, 10) || 1),
      sell_split_days: Math.max(1, parseInt(form.sellSplitDays, 10) || 5),
      budget_mode: form.budgetMode,
      monthly_budget: parseFloat(stripCommas(form.budget)) || 0,
      daily_fixed_budget: parseFloat(stripCommas(form.dailyFixedBudget)) || 150000,
      trading_days_per_month: Math.max(1, parseInt(form.tradingDaysPerMonth, 10) || 20),
      cycle_alloc_mode: form.cycleAllocMode,
      cycle_target_krw: parseFloat(stripCommas(form.cycleTargetKrw)) || 300000,
      sell_proceeds_mode: form.sellProceedsMode,
      order_price_mode: form.orderPriceMode,
      schedule_enabled: form.scheduleEnabled,
      is_dry_run: form.isDryRun,
      strategy_status: form.scheduleEnabled ? 'active' : 'paused',
      schedule_time: form.dcaExecTime.trim() || '09:10',
    } as any
  }

  return payload
}

export function templateToForm(template: Template): TemplateFormState {
  const strategyType = normalizeStrategyType(template.strategy_type)
  const p = (template.params || {}) as any
  const rawBudget = strategyType === 'kospi_top_dca' ? (p.monthly_budget ?? template.budget) : template.budget
  return {
    name: template.name,
    exchange: template.exchange,
    ticker: template.ticker,
    strategyType,
    startPrice: template.start_price ? formatWithCommas(template.start_price) : '',
    endPrice: template.end_price ? formatWithCommas(template.end_price) : '',
    count: String(template.count ?? 0),
    budget: formatWithCommas(rawBudget),
    buyRsiRange: p.buy_rsi_range || '25-30',
    sellRsiRange: p.sell_rsi_range || '65-75',
    weighted: Boolean(p.weighted),
    dcaSchedule: p.schedule || '매일',
    dcaExecTime: p.schedule_time || p.exec_time || (strategyType === 'kospi_top_dca' ? '09:10' : '09:05'),
    dcaAmountType: p.amount_type || (strategyType === 'sdca' ? 'volume' : 'budget'),
    topMarket: p.market || 'KOSPI',
    rankStart: String(p.rank_start ?? '1'),
    rankEnd: String(p.rank_end ?? p.top_n ?? template.count ?? '10'),
    excludePreferred: p.exclude_preferred !== undefined ? Boolean(p.exclude_preferred) : true,
    upperExitMode: p.upper_exit_mode === 'hold_on_promotion' ? 'hold_on_promotion' : 'sell_on_any_exit',
    exitRankBuffer: String(p.exit_rank_buffer ?? '2'),
    exitConfirmDays: String(p.exit_confirm_days ?? '2'),
    sellSplitDays: String(p.sell_split_days ?? '5'),
    budgetMode: p.budget_mode === 'daily' ? 'daily' : 'monthly',
    dailyFixedBudget: formatWithCommas(p.daily_fixed_budget ?? '150000'),
    tradingDaysPerMonth: String(p.trading_days_per_month ?? '20'),
    cycleAllocMode: p.cycle_alloc_mode === 'target_amount' ? 'target_amount' : 'one_share',
    cycleTargetKrw: formatWithCommas(p.cycle_target_krw ?? '300000'),
    sellProceedsMode: p.sell_proceeds_mode === 'recycle_to_budget' ? 'recycle_to_budget' : 'keep_cash',
    orderPriceMode:
      p.order_price_mode === 'limit_aggressive' || p.order_price_mode === 'market'
        ? p.order_price_mode
        : 'limit_current',
    scheduleEnabled: p.schedule_enabled !== undefined ? Boolean(p.schedule_enabled) : true,
    isDryRun: Boolean(p.is_dry_run),
  }
}
