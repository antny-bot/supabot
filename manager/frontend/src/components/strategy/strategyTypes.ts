import type { Template, TemplateParams } from '../../api/templates'
import { formatWithCommas, stripCommas } from '../../utils/formatters'

/**
 * 사용자 입력 시간 문자열을 HH:MM (00:00 ~ 23:59) 형식으로 정규화한다.
 * - '1430' -> '14:30'
 * - '905' -> '09:05'
 * - '14:30' -> '14:30'
 * - '14시 30분' -> '14:30'
 * - '14' -> '14:00'
 */
export function normalizeTimeInput(input: string): string {
  const clean = String(input || '').trim()
  if (!clean) return ''

  // 1) 14:30, 9:05 등 콜론 형태
  const colonMatch = clean.match(/^(\d{1,2}):(\d{1,2})$/)
  if (colonMatch) {
    const h = parseInt(colonMatch[1], 10)
    const m = parseInt(colonMatch[2], 10)
    if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
      return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
    }
  }

  // 2) 1430, 905 등 3~4자리 연속 숫자
  const numMatch = clean.match(/^(\d{3,4})$/)
  if (numMatch) {
    const digits = numMatch[1]
    const h = parseInt(digits.slice(0, digits.length - 2), 10)
    const m = parseInt(digits.slice(-2), 10)
    if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
      return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
    }
  }

  // 3) 14시 30분, 14시 등 한글 형태
  const koMatch = clean.match(/^(\d{1,2})시(?:\s*(\d{1,2})분?)?$/)
  if (koMatch) {
    const h = parseInt(koMatch[1], 10)
    const m = parseInt(koMatch[2] || '0', 10)
    if (h >= 0 && h <= 23 && m >= 0 && m <= 59) {
      return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
    }
  }

  // 4) 1~2자리 숫자 (시 단위: 14 -> 14:00, 9 -> 09:00)
  const hourMatch = clean.match(/^(\d{1,2})$/)
  if (hourMatch) {
    const h = parseInt(hourMatch[1], 10)
    if (h >= 0 && h <= 23) {
      return `${String(h).padStart(2, '0')}:00`
    }
  }

  return clean
}

export function isValidTimeInput(timeStr: string): boolean {
  if (!timeStr) return false
  const match = timeStr.trim().match(/^([01]\d|2[0-3]):([0-5]\d)$/)
  return Boolean(match)
}

/**
 * 매수/매도 추천 시각 프리셋 인터페이스
 */
export interface TradingTimePreset {
  label: string
  time: string
  timeRange: string
  rank: 1 | 2 | 3
  type: 'buy' | 'sell'
  reason: string
  description: string
}

/**
 * 매수 추천 시각 프리셋:
 * - 1순위: 15:10 (15:00~15:20) - 종가 추세 형성
 * - 2순위: 09:40 (09:30~10:00) - 시초가 변동성 진정
 * - 3순위: 10:30 (10:30 전후) - 아시아 장 개장
 */
export const BUY_RECOMMENDED_TIME_PRESETS: TradingTimePreset[] = [
  {
    rank: 1,
    time: '15:10',
    timeRange: '15:00~15:20',
    type: 'buy',
    label: '15:10 (1순위: 종가추세)',
    reason: '종가 추세 형성',
    description: '당일 장세의 종가 방향성이 잡히고 오버나잇 리스크를 줄이며 안정적으로 진입하는 최적 시각',
  },
  {
    rank: 2,
    time: '09:40',
    timeRange: '09:30~10:00',
    type: 'buy',
    label: '09:40 (2순위: 변동성진정)',
    reason: '시초가 변동성 진정',
    description: '개장 직후 30분의 과도한 갭과 휩소 변동성이 진정되고 당일 지지선이 확인되는 시각',
  },
  {
    rank: 3,
    time: '10:30',
    timeRange: '10:30 전후',
    type: 'buy',
    label: '10:30 (3순위: 아시아장)',
    reason: '아시아 장 개장',
    description: '중국·홍콩 등 아시아 주요 증시가 개장하며 장중 수급 방향성이 2차로 확인되는 시각',
  },
]

/**
 * 매도 추천 시각 프리셋:
 * - 1순위: 09:20 (09:10~09:30) - 당일 거래량 급증 및 고점 형성
 * - 2순위: 11:15 (11:00~11:30) - 전장 반등 노림
 * - 3순위: 15:10 (15:00~15:20) - 당일 차익 실현 마무리
 */
export const SELL_RECOMMENDED_TIME_PRESETS: TradingTimePreset[] = [
  {
    rank: 1,
    time: '09:20',
    timeRange: '09:10~09:30',
    type: 'sell',
    label: '09:20 (1순위: 고점형성)',
    reason: '거래량 폭발 & 당일 고점 형성',
    description: '개장 직후 거래량이 가장 활발히 터지며 당일 장중 고점이 빈출되는 익절 최적 시각',
  },
  {
    rank: 2,
    time: '11:15',
    timeRange: '11:00~11:30',
    type: 'sell',
    label: '11:15 (2순위: 전장반등)',
    reason: '전장 반등 타이밍',
    description: '오전 눌림목 이후 전장 마감(오전장 후반) 전 기술적 반등 파동을 노려 차익 실현하는 시각',
  },
  {
    rank: 3,
    time: '15:10',
    timeRange: '15:00~15:20',
    type: 'sell',
    label: '15:10 (3순위: 당일마감)',
    reason: '당일 차익 실현 마무리',
    description: '장 마감 직전 오버나잇 변동성을 피하고 당일 수익을 확실하게 확정·정리하는 시각',
  },
]

export const ALL_RECOMMENDED_TIME_PRESETS: TradingTimePreset[] = [
  ...BUY_RECOMMENDED_TIME_PRESETS,
  ...SELL_RECOMMENDED_TIME_PRESETS,
]


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
  dcaOrderType: 'limit' | 'market'
  dcaCarryoverMode: 'next_day' | 'delay_20m' | 'skip'
  topMarket: string
  rankStart: string
  rankEnd: string
  excludePreferred: boolean
  upperExitMode: 'sell_on_any_exit' | 'hold_on_promotion'
  exitRankBuffer: string
  exitConfirmDays: string
  sellSplitDays: string
  budgetMode: 'total' | 'monthly' | 'daily' | 'unlimited'
  dailyFixedBudget: string
  tradingDaysPerMonth: string
  cycleAllocMode: 'one_share' | 'target_amount'
  cycleTargetKrw: string
  sellProceedsMode: 'keep_cash' | 'recycle_to_budget'
  orderPriceMode: 'limit_current' | 'limit_aggressive' | 'market'
  scheduleEnabled: boolean
  isDryRun: boolean
  dcaPlanBudget: string
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
  dcaOrderType: 'limit',
  dcaCarryoverMode: 'next_day',
  topMarket: 'KOSPI',
  rankStart: '1',
  rankEnd: '10',
  excludePreferred: true,
  upperExitMode: 'sell_on_any_exit',
  exitRankBuffer: '2',
  exitConfirmDays: '2',
  sellSplitDays: '5',
  budgetMode: 'total',
  dailyFixedBudget: '150000',
  tradingDaysPerMonth: '20',
  cycleAllocMode: 'one_share',
  cycleTargetKrw: '300000',
  sellProceedsMode: 'keep_cash',
  orderPriceMode: 'limit_current',
  scheduleEnabled: true,
  isDryRun: false,
  dcaPlanBudget: '1000000',
}

export const DEFAULT_DCA_PLAN_BUDGET = 3000000

export function hasDcaBudget(templateOrParams: any): boolean {
  if (!templateOrParams) return false
  const p = (templateOrParams.params || templateOrParams) as any
  const stype = normalizeStrategyType(templateOrParams.strategy_type || p.strategy_type)
  if (stype !== 'dca' && stype !== 'sdca') return false
  const bMode = String(p.budget_mode || '').toLowerCase()
  if (bMode === 'unlimited') return false
  // budget_mode가 명시되지 않았고 carryover_budget도 없는 기존 DCA는 무제한으로 취급
  if (!bMode && p.carryover_budget === undefined && p.carryover_budget === null) return false
  return Boolean(
    p.carryover_budget !== undefined ||
    Number(p.monthly_budget || 0) > 0 ||
    Number(p.dca_plan_budget || 0) > 0 ||
    bMode
  )
}

export const DEFAULT_MULTI_FORM: TemplateFormState = {
  ...DEFAULT_SINGLE_FORM,
  name: '',
  exchange: 'toss',
  ticker: 'KOSPI_TOP10',
  strategyType: 'kospi_top_dca',
  budget: '3000000',
  budgetMode: 'monthly',
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
    if (stype === 'grid') {
      payload.params = {
        budget_mode: form.budgetMode || 'total',
        monthly_budget: payload.budget,
        sell_proceeds_mode: form.sellProceedsMode || 'keep_cash',
      }
    }
  } else if (stype === 'rsitrade') {
    payload.params = {
      buy_rsi_range: form.buyRsiRange.trim(),
      sell_rsi_range: form.sellRsiRange.trim(),
      weighted: form.weighted,
      budget_mode: form.budgetMode || 'total',
      monthly_budget: payload.budget,
      sell_proceeds_mode: form.sellProceedsMode || 'recycle_to_budget',
    }
  } else if (stype === 'dca' || stype === 'sdca') {
    const maxRuns = payload.count > 0 ? payload.count : null
    const isBidDca = stype === 'dca'
    const parsedPlanBudget = parseFloat(stripCommas(form.dcaPlanBudget))
    const defaultTotal = form.dcaAmountType === 'volume'
      ? (parsedPlanBudget > 0 ? parsedPlanBudget : (payload.budget > 0 ? payload.budget * 20 : DEFAULT_DCA_PLAN_BUDGET))
      : (parsedPlanBudget > 0 ? parsedPlanBudget : (maxRuns ? payload.budget * maxRuns : payload.budget * 20))
    const isUnlimited = form.budgetMode === 'unlimited'
    payload.params = {
      schedule: form.dcaSchedule.trim() || '매일',
      exec_time: normalizeTimeInput(form.dcaExecTime) || '09:05',
      amount_type: form.dcaAmountType,
      max_runs: maxRuns,
      side: stype === 'sdca' ? 'ask' : 'bid',
      order_type: form.dcaOrderType || 'limit',
      order_price_mode: form.dcaOrderType || 'limit',
      carryover_mode: form.dcaCarryoverMode || 'next_day',
      ...(isBidDca && !isUnlimited
        ? {
            per_order_budget: form.dcaAmountType === 'budget' ? payload.budget : 0,
            budget_mode: form.budgetMode || 'total',
            monthly_budget: defaultTotal,
            dca_plan_budget: defaultTotal,
            daily_fixed_budget: form.budgetMode === 'daily' ? (form.dcaAmountType === 'budget' ? payload.budget : 0) : 0,
            sell_proceeds_mode: form.sellProceedsMode || 'keep_cash',
          }
        : isBidDca
        ? {
            budget_mode: 'unlimited',
          }
        : {}),
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
      schedule_time: normalizeTimeInput(form.dcaExecTime) || '09:10',
    } as any
  }

  return payload
}

export function templateToForm(template: Template): TemplateFormState {
  const strategyType = normalizeStrategyType(template.strategy_type)
  const p = (template.params || {}) as any
  const rawBudget =
    strategyType === 'kospi_top_dca'
      ? (p.monthly_budget ?? template.budget)
      : strategyType === 'dca' && p.per_order_budget
      ? p.per_order_budget
      : template.budget
  const defaultBudgetMode =
    strategyType === 'kospi_top_dca' ? 'monthly' : 'total'
  const defaultSellMode =
    strategyType === 'rsitrade' ? 'recycle_to_budget' : 'keep_cash'
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
    budgetMode:
      p.budget_mode === 'daily' || p.budget_mode === 'monthly' || p.budget_mode === 'total' || p.budget_mode === 'unlimited'
        ? p.budget_mode
        : (strategyType === 'dca' && !hasDcaBudget(template) ? 'unlimited' : defaultBudgetMode),
    dailyFixedBudget: formatWithCommas(p.daily_fixed_budget ?? '150000'),
    tradingDaysPerMonth: String(p.trading_days_per_month ?? '20'),
    cycleAllocMode: p.cycle_alloc_mode === 'target_amount' ? 'target_amount' : 'one_share',
    cycleTargetKrw: formatWithCommas(p.cycle_target_krw ?? '300000'),
    sellProceedsMode:
      p.sell_proceeds_mode === 'recycle_to_budget' || p.sell_proceeds_mode === 'keep_cash'
        ? p.sell_proceeds_mode
        : defaultSellMode,
    orderPriceMode:
      p.order_price_mode === 'limit_aggressive' || p.order_price_mode === 'market'
        ? p.order_price_mode
        : 'limit_current',
    scheduleEnabled: p.schedule_enabled !== undefined ? Boolean(p.schedule_enabled) : true,
    isDryRun: Boolean(p.is_dry_run),
    dcaPlanBudget: formatWithCommas(p.monthly_budget ?? (Number(rawBudget || 0) * 10 || 1000000)),
    dcaOrderType: (p.order_type === 'market' || p.order_price_mode === 'market') ? 'market' : 'limit',
    dcaCarryoverMode: p.carryover_mode === 'delay_20m' || p.carryover_mode === 'skip' ? p.carryover_mode : 'next_day',
  }
}
