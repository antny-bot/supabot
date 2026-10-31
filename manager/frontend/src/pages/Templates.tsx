import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
  ChevronDown,
  Copy,
  Loader2,
  Pencil,
  Play,
  Plus,
  Trash2,
  X,
  Layers,
  AlertCircle,
} from 'lucide-react'
import { ApiError } from '../api/client'
import { fetchStockCache, type StockCacheRow } from '../api/stockCache'
import {
  createTemplate,
  deleteTemplate,
  duplicateTemplate,
  executeTemplate,
  fetchTemplates,
  type Template,
  type TemplateParams,
  updateTemplate,
} from '../api/templates'
import Badge from '../components/ui/Badge'
import PageHeader from '../components/ui/PageHeader'
import { CardSkeleton } from '../components/ui/Skeleton'
import { PAGE_META } from '../config/pageMeta'
import { useToast } from '../contexts/ToastContext'
import { krwFmt } from '../utils/formatters'

interface TemplateFormState {
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

const DEFAULT_FORM: TemplateFormState = {
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

const STRATEGY_TYPE_LABELS: Record<string, string> = {
  kospi_top_dca: 'KOSPI/KOSDAQ 시총 상위 TOP N 모으기 & 분할매도',
  grid: '거미줄 분할 매수 (/grid)',
  sgrid: '거미줄 분할 매도 (/sgrid)',
  rsitrade: 'RSI 순환 매매 (/rsitrade)',
  rsi: 'RSI 순환 매매 (/rsitrade)',
  dca: '정기 적립식 매수 (/dca)',
  sdca: '정기 분할 매도 (/sdca)',
}

const STRATEGY_BADGE_LABELS: Record<string, string> = {
  kospi_top_dca: 'TOP N DCA',
  grid: '거미줄 매수 (GRID)',
  sgrid: '거미줄 매도 (SGRID)',
  rsitrade: 'RSI 순환매매',
  rsi: 'RSI 순환매매',
  dca: '정기 매수 (DCA)',
  sdca: '정기 매도 (SDCA)',
}

function normalizeStrategyType(raw?: string): string {
  if (!raw) return 'grid'
  if (raw === 'rsi') return 'rsitrade'
  return raw
}

function buildPayload(form: TemplateFormState) {
  const stype = normalizeStrategyType(form.strategyType)
  const parsedCount = parseInt(form.count, 10)
  const payload = {
    name: form.name.trim(),
    exchange: form.exchange,
    ticker: form.ticker.trim().toUpperCase(),
    start_price: 0,
    end_price: 0,
    count: Number.isNaN(parsedCount) ? 0 : parsedCount,
    budget: parseFloat(form.budget),
    strategy_type: stype,
    params: {} as TemplateParams,
  }

  if (stype === 'grid' || stype === 'sgrid') {
    payload.start_price = parseFloat(form.startPrice)
    payload.end_price = parseFloat(form.endPrice)
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
        ? parseFloat(form.dailyFixedBudget) || 150000
        : parseFloat(form.budget) || 3000000
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
      monthly_budget: parseFloat(form.budget) || 0,
      daily_fixed_budget: parseFloat(form.dailyFixedBudget) || 150000,
      trading_days_per_month: Math.max(1, parseInt(form.tradingDaysPerMonth, 10) || 20),
      cycle_alloc_mode: form.cycleAllocMode,
      cycle_target_krw: parseFloat(form.cycleTargetKrw) || 300000,
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

function templateToForm(template: Template): TemplateFormState {
  const strategyType = normalizeStrategyType(template.strategy_type)
  const p = (template.params || {}) as any
  return {
    name: template.name,
    exchange: template.exchange,
    ticker: template.ticker,
    strategyType,
    startPrice: template.start_price ? String(template.start_price) : '',
    endPrice: template.end_price ? String(template.end_price) : '',
    count: String(template.count ?? 0),
    budget: String(strategyType === 'kospi_top_dca' ? (p.monthly_budget ?? template.budget) : template.budget),
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
    dailyFixedBudget: String(p.daily_fixed_budget ?? '150000'),
    tradingDaysPerMonth: String(p.trading_days_per_month ?? '20'),
    cycleAllocMode: p.cycle_alloc_mode === 'target_amount' ? 'target_amount' : 'one_share',
    cycleTargetKrw: String(p.cycle_target_krw ?? '300000'),
    sellProceedsMode: p.sell_proceeds_mode === 'recycle_to_budget' ? 'recycle_to_budget' : 'keep_cash',
    orderPriceMode:
      p.order_price_mode === 'limit_aggressive' || p.order_price_mode === 'market'
        ? p.order_price_mode
        : 'limit_current',
    scheduleEnabled: p.schedule_enabled !== undefined ? Boolean(p.schedule_enabled) : true,
    isDryRun: Boolean(p.is_dry_run),
  }
}

export default function Templates() {
  const toast = useToast()
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 모달 상태
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [form, setForm] = useState<TemplateFormState>(DEFAULT_FORM)
  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // 종목 캐시 & 다운콤보 상태 (한국투자증권 / 토스증권)
  const [stockList, setStockList] = useState<StockCacheRow[]>([])
  const [stockLoading, setStockLoading] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const comboboxRef = useRef<HTMLDivElement>(null)
  const justSelectedRef = useRef<string | null>(null)

  // 실행 확인 모달
  const [executingTemplate, setExecutingTemplate] = useState<Template | null>(null)
  const [executing, setExecuting] = useState(false)

  const isStockExchange = form.exchange === 'kis' || form.exchange === 'toss'

  const loadTemplates = async () => {
    try {
      setLoading(true)
      const data = await fetchTemplates()
      setTemplates(Array.isArray(data) ? data : [])
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '템플릿 목록을 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const loadStockList = async () => {
    if (stockList.length > 0 || stockLoading) return
    try {
      setStockLoading(true)
      const rows = await fetchStockCache('')
      if (Array.isArray(rows)) {
        setStockList(rows)
      }
    } catch {
      // 종목 캐시 조회 실패 시 직접 코드 입력으로 폴백
    } finally {
      setStockLoading(false)
    }
  }

  useEffect(() => {
    loadTemplates()
    loadStockList()
  }, [])

  useEffect(() => {
    if (formOpen && isStockExchange && stockList.length === 0) {
      loadStockList()
    }
  }, [formOpen, isStockExchange])

  useEffect(() => {
    if (!dropdownOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (comboboxRef.current && !comboboxRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
        setHighlightedIndex(-1)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [dropdownOpen])

  const stockNameByCode = useMemo(() => {
    const map: Record<string, string> = {}
    for (const item of stockList) {
      map[item.code.toUpperCase()] = item.name
    }
    return map
  }, [stockList])

  const selectedStock = useMemo(() => {
    if (!isStockExchange) return undefined
    const q = form.ticker.trim().toLowerCase()
    if (!q) return undefined
    return stockList.find((item) => item.code.toLowerCase() === q)
  }, [isStockExchange, form.ticker, stockList])

  const filteredStocks = useMemo(() => {
    if (!isStockExchange) return []
    const q = form.ticker.trim().toLowerCase()
    if (!q) return stockList.slice(0, 50)
    return stockList.filter(
      (item) =>
        item.name.toLowerCase().includes(q) ||
        item.code.toLowerCase().includes(q),
    )
  }, [isStockExchange, form.ticker, stockList])

  const selectStock = (stock: StockCacheRow) => {
    justSelectedRef.current = stock.code
    setTimeout(() => {
      justSelectedRef.current = null
    }, 50)
    setForm((prev) => ({ ...prev, ticker: stock.code }))
    setDropdownOpen(false)
    setHighlightedIndex(-1)
  }

  const handleOpenCreate = () => {
    setEditingId(null)
    setForm(DEFAULT_FORM)
    setFormError(null)
    setDropdownOpen(false)
    setHighlightedIndex(-1)
    setFormOpen(true)
  }

  const handleOpenEdit = (template: Template) => {
    setEditingId(template.id)
    setForm(templateToForm(template))
    setFormError(null)
    setDropdownOpen(false)
    setHighlightedIndex(-1)
    setFormOpen(true)
  }

  const handleDuplicate = async (template: Template) => {
    try {
      await duplicateTemplate(template.id)
      toast.success(`'${template.name}' 템플릿이 복제되었습니다.`)
      loadTemplates()
    } catch (e) {
      toast.error('복제 실패: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  const handleDelete = async (template: Template) => {
    if (!confirm(`'${template.name}' 템플릿을 삭제하시겠습니까?`)) return
    try {
      await deleteTemplate(template.id)
      toast.success('템플릿이 삭제되었습니다.')
      loadTemplates()
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) {
      setFormError('템플릿 이름을 입력하세요.')
      return
    }
    const isTopDca = form.strategyType === 'kospi_top_dca'
    if (!isTopDca && !form.ticker.trim()) {
      setFormError('종목 코드를 입력하세요.')
      return
    }
    if (isTopDca) {
      const rStart = parseInt(form.rankStart, 10)
      const rEnd = parseInt(form.rankEnd, 10)
      if (Number.isNaN(rStart) || Number.isNaN(rEnd) || rStart < 1 || rEnd < rStart || rEnd > 50) {
        setFormError('순위 구간은 1위 ~ 50위 사이에서 시작 순위 ≤ 종료 순위로 설정하세요.')
        return
      }
    }

    let submitForm = form
    if (!isTopDca && isStockExchange) {
      const q = form.ticker.trim().toLowerCase()
      const exactCode = stockList.find((s) => s.code.toLowerCase() === q)
      if (!exactCode) {
        const exactName = stockList.find((s) => s.name.toLowerCase() === q)
        if (exactName) {
          submitForm = { ...form, ticker: exactName.code }
        } else if (filteredStocks.length === 1) {
          submitForm = { ...form, ticker: filteredStocks[0].code }
        }
      }
    }

    setSaving(true)
    setFormError(null)
    try {
      const payload = buildPayload(submitForm)
      if (editingId) {
        await updateTemplate(editingId, payload)
        toast.success('템플릿이 수정되었습니다.')
      } else {
        await createTemplate(payload)
        toast.success('새 전략 템플릿이 생성되었습니다.')
      }
      setFormOpen(false)
      loadTemplates()
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : '저장 중 오류가 발생했습니다.')
    } finally {
      setSaving(false)
    }
  }

  const handleConfirmExecute = async () => {
    if (!executingTemplate) return
    setExecuting(true)
    try {
      const res = await executeTemplate(executingTemplate.id)
      toast.success(res.message || '템플릿 전략이 성공적으로 실행되었습니다.')
      setExecutingTemplate(null)
    } catch (e) {
      toast.error('실행 실패: ' + (e instanceof Error ? e.message : String(e)))
    } finally {
      setExecuting(false)
    }
  }

  const isDcaForm = form.strategyType === 'dca' || form.strategyType === 'sdca'
  const isTopDcaForm = form.strategyType === 'kospi_top_dca'
  const isSellGridForm = form.strategyType === 'sgrid'

  return (
    <div className="space-y-4 pb-8">
      <PageHeader
        {...PAGE_META.templates}
        actions={
          <button
            onClick={handleOpenCreate}
            className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 transition-colors"
          >
            <Plus size={15} />
            <span>신규 전략 템플릿</span>
          </button>
        }
      />

      {error && (
        <div className="flex items-center gap-2 rounded-xl bg-rose-50 p-4 text-xs font-medium text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* 템플릿 카드 그리드 */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
      ) : templates.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 p-12 text-center dark:border-slate-800">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400">
            <Layers size={24} />
          </div>
          <h3 className="mt-3 text-sm font-semibold text-slate-800 dark:text-slate-200">
            등록된 전략 템플릿이 없습니다
          </h3>
          <p className="mt-1 text-xs text-slate-500">자주 사용하는 매매 전략 설정을 템플릿으로 저장해 원클릭으로 실행하세요.</p>
          <button
            onClick={handleOpenCreate}
            className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
          >
            <Plus size={14} /> 템플릿 만들기
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {templates.map((tpl) => {
            const stype = normalizeStrategyType(tpl.strategy_type)
            const isDca = stype === 'dca' || stype === 'sdca'
            const isTopDca = stype === 'kospi_top_dca'
            const isVolumeBased = stype === 'sgrid' || (isDca && tpl.params?.amount_type === 'volume')
            const stockName =
              tpl.exchange === 'kis' || tpl.exchange === 'toss'
                ? stockNameByCode[tpl.ticker.toUpperCase()]
                : undefined
            const p = (tpl.params || {}) as any

            return (
              <div
                key={tpl.id}
                className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-all hover:border-indigo-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-indigo-800"
              >
                <div>
                  {/* 상단: 거래소, 종목, 전략 유형 */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Badge value={tpl.exchange} label={tpl.exchange.toUpperCase()} />
                      <span className="text-sm font-bold text-slate-900 dark:text-white">
                        {tpl.ticker}
                      </span>
                      {stockName && (
                        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                          ({stockName})
                        </span>
                      )}
                    </div>
                    <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      {STRATEGY_BADGE_LABELS[stype] || stype.toUpperCase()}
                    </span>
                  </div>

                  {/* 템플릿 명칭 */}
                  <h4 className="mt-2.5 text-base font-bold text-slate-800 dark:text-slate-100 truncate">
                    {tpl.name}
                  </h4>

                  {/* 파라미터 요약 그리드 */}
                  <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-3 text-xs dark:bg-slate-800/50">
                    <div>
                      <span className="text-[11px] text-slate-400">
                        {stype === 'sgrid'
                          ? '총 매도 수량'
                          : isDca
                          ? '1회 주문 규모'
                          : isTopDca
                          ? p.budget_mode === 'daily'
                            ? '일일 충전 예산'
                            : '월 설정 총예산'
                          : '설정 예산'}
                      </span>
                      <p className="font-mono font-bold text-slate-800 dark:text-slate-200">
                        {isVolumeBased
                          ? `${tpl.budget} (수량)`
                          : isTopDca
                          ? krwFmt(p.budget_mode === 'daily' ? (p.daily_fixed_budget ?? tpl.budget) : (p.monthly_budget ?? tpl.budget))
                          : krwFmt(tpl.budget)}
                      </p>
                    </div>
                    <div>
                      <span className="text-[11px] text-slate-400">
                        {isDca ? '반복 횟수' : isTopDca ? '타겟 순위 구간' : '분할 주문 수'}
                      </span>
                      <p className="font-mono font-bold text-slate-800 dark:text-slate-200">
                        {isDca
                          ? tpl.count > 0
                            ? `총 ${tpl.count}회`
                            : '무기한 반복'
                          : isTopDca
                          ? `${p.rank_start ?? 1}위 ~ ${p.rank_end ?? p.top_n ?? 10}위 (${(p.rank_end ?? p.top_n ?? 10) - (p.rank_start ?? 1) + 1}종목)`
                          : `${tpl.count}분할`}
                      </p>
                    </div>
                    {tpl.start_price > 0 && (
                      <div className="col-span-2 border-t border-slate-200/60 pt-1.5 dark:border-slate-700/60">
                        <span className="text-[11px] text-slate-400">가격 범위</span>
                        <p className="font-mono font-medium text-slate-700 dark:text-slate-300">
                          {tpl.start_price.toLocaleString()} ~ {tpl.end_price.toLocaleString()}원
                        </p>
                      </div>
                    )}
                    {tpl.params?.buy_rsi_range && (
                      <div className="col-span-2 border-t border-slate-200/60 pt-1.5 dark:border-slate-700/60">
                        <span className="text-[11px] text-slate-400">RSI 조건</span>
                        <p className="font-mono font-medium text-slate-700 dark:text-slate-300">
                          매수: {tpl.params.buy_rsi_range} / 매도: {tpl.params.sell_rsi_range || '—'}
                          {tpl.params.weighted ? ' (DCA 가중)' : ''}
                        </p>
                      </div>
                    )}
                    {isDca && (
                      <div className="col-span-2 border-t border-slate-200/60 pt-1.5 dark:border-slate-700/60">
                        <span className="text-[11px] text-slate-400">정기 실행 주기</span>
                        <p className="font-mono font-medium text-slate-700 dark:text-slate-300">
                          {tpl.params?.schedule || '매일'} · {tpl.params?.exec_time || '09:05'} (KST)
                        </p>
                      </div>
                    )}
                    {isTopDca && (
                      <div className="col-span-2 border-t border-slate-200/60 pt-1.5 dark:border-slate-700/60 space-y-0.5">
                        <span className="text-[11px] text-slate-400">회전·이탈 및 자동 실행 설정</span>
                        <p className="font-mono font-medium text-slate-700 dark:text-slate-300">
                          {p.market || 'KOSPI'} · 이탈 유예 +{p.exit_rank_buffer ?? 2}위({p.exit_confirm_days ?? 2}일) → {p.sell_split_days ?? 5}일 분할매도
                        </p>
                        <p className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
                          매일 {p.schedule_time || '09:10'} KST · {p.cycle_alloc_mode === 'target_amount' ? `목표 ${krwFmt(p.cycle_target_krw || 300000)}` : '사이클당 1주'}
                          {p.is_dry_run ? ' · 🧪 Dry-Run(모의)' : ''}
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {/* 하단 액션 버튼 그룹 */}
                <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 dark:border-slate-800">
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleOpenEdit(tpl)}
                      className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                      title="수정"
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      onClick={() => handleDuplicate(tpl)}
                      className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                      title="복제"
                    >
                      <Copy size={14} />
                    </button>
                    <button
                      onClick={() => handleDelete(tpl)}
                      className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/40 dark:hover:text-rose-400"
                      title="삭제"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>

                  <button
                    onClick={() => setExecutingTemplate(tpl)}
                    className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700 transition-colors"
                  >
                    <Play size={13} />
                    <span>즉시 실행</span>
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 템플릿 생성/수정 모달 */}
      {formOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm" onClick={() => !saving && setFormOpen(false)} />
          <div className={`relative z-10 w-full ${isTopDcaForm ? 'max-w-2xl' : 'max-w-lg'} rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800 max-h-[90vh] overflow-y-auto transition-all`}>
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                {editingId ? '전략 템플릿 수정' : '신규 전략 템플릿 만들기'}
              </h3>
              <button
                onClick={() => setFormOpen(false)}
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X size={16} />
              </button>
            </div>

            {formError && (
              <div className="mt-3 rounded-lg bg-rose-50 p-3 text-xs text-rose-600 dark:bg-rose-950/40 dark:text-rose-300">
                {formError}
              </div>
            )}

            <form onSubmit={handleSubmit} className="mt-4 space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">템플릿 이름</label>
                <input
                  type="text"
                  placeholder={
                    isTopDcaForm
                      ? '예: 코스피 시총 TOP 10 순환 모으기 & 5일 분할매도'
                      : '예: 비트코인 매일 5만원 정기매수 / 10분할 거미줄 매수'
                  }
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white focus:border-indigo-500"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">거래소</label>
                  <select
                    aria-label="거래소"
                    value={form.exchange}
                    onChange={(e) => {
                      const nextExchange = e.target.value
                      const nextIsStock = nextExchange === 'kis' || nextExchange === 'toss'
                      const prevIsStock = form.exchange === 'kis' || form.exchange === 'toss'
                      let nextTicker = form.ticker
                      if (nextIsStock && !prevIsStock && form.ticker === 'BTC') {
                        nextTicker = ''
                      } else if (!nextIsStock && prevIsStock && !form.ticker.trim()) {
                        nextTicker = 'BTC'
                      }
                      const nextTopMarket =
                        form.strategyType === 'kospi_top_dca'
                          ? nextIsStock
                            ? form.topMarket === 'KRW_MAJOR'
                              ? 'KOSPI'
                              : form.topMarket
                            : 'KRW_MAJOR'
                          : form.topMarket
                      setForm({ ...form, exchange: nextExchange, ticker: nextTicker, topMarket: nextTopMarket })
                      setDropdownOpen(false)
                      setHighlightedIndex(-1)
                    }}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  >
                    <option value="upbit">Upbit</option>
                    <option value="bithumb">Bithumb</option>
                    <option value="kis">한국투자증권(KIS)</option>
                    <option value="toss">토스증권</option>
                  </select>
                </div>

                {isTopDcaForm ? (
                  <div>
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                      대상 시장 (자동 티커)
                    </label>
                    <select
                      aria-label="대상 시장"
                      value={form.topMarket}
                      onChange={(e) => setForm({ ...form, topMarket: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    >
                      <option value="KOSPI">KOSPI (코스피 시총 상위)</option>
                      <option value="KOSDAQ">KOSDAQ (코스닥 시총 상위)</option>
                      <option value="KRW_MAJOR">KRW_MAJOR (가상자산 원화마켓 상위)</option>
                    </select>
                  </div>
                ) : (
                <div ref={comboboxRef} className="relative">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                    종목 코드 (티커)
                  </label>
                  <div className="relative mt-1">
                    <input
                      type="text"
                      aria-label="종목 코드 (티커)"
                      autoComplete="off"
                      placeholder={isStockExchange ? '종목명 또는 코드 검색 (예: 고려)' : 'BTC / 005930'}
                      value={form.ticker}
                      onFocus={() => {
                        if (isStockExchange && form.ticker.trim() && !selectedStock) {
                          setDropdownOpen(true)
                        }
                      }}
                      onChange={(e) => {
                        if (justSelectedRef.current !== null) return
                        const val = e.target.value
                        setForm((prev) => ({ ...prev, ticker: val }))
                        if (isStockExchange) {
                          setDropdownOpen(true)
                          setHighlightedIndex(-1)
                        }
                      }}
                      onKeyDown={(e) => {
                        if (!isStockExchange) return
                        if (e.key === 'ArrowDown') {
                          e.preventDefault()
                          if (!dropdownOpen) {
                            setDropdownOpen(true)
                            setHighlightedIndex(filteredStocks.length > 0 ? 0 : -1)
                          } else if (filteredStocks.length > 0) {
                            setHighlightedIndex((prev) => (prev + 1) % filteredStocks.length)
                          }
                        } else if (e.key === 'ArrowUp') {
                          e.preventDefault()
                          if (!dropdownOpen) {
                            setDropdownOpen(true)
                            setHighlightedIndex(filteredStocks.length > 0 ? filteredStocks.length - 1 : -1)
                          } else if (filteredStocks.length > 0) {
                            setHighlightedIndex((prev) => (prev <= 0 ? filteredStocks.length - 1 : prev - 1))
                          }
                        } else if (e.key === 'Enter') {
                          if (filteredStocks.length === 1) {
                            e.preventDefault()
                            selectStock(filteredStocks[0])
                          } else if (
                            dropdownOpen &&
                            highlightedIndex >= 0 &&
                            highlightedIndex < filteredStocks.length
                          ) {
                            e.preventDefault()
                            selectStock(filteredStocks[highlightedIndex])
                          } else if (dropdownOpen && filteredStocks.length > 1) {
                            const q = form.ticker.trim().toLowerCase()
                            const exact = filteredStocks.find(
                              (s) => s.name.toLowerCase() === q || s.code.toLowerCase() === q,
                            )
                            e.preventDefault()
                            if (exact) {
                              selectStock(exact)
                            }
                          }
                        } else if (e.key === 'Escape') {
                          if (dropdownOpen) {
                            e.preventDefault()
                            setDropdownOpen(false)
                            setHighlightedIndex(-1)
                          }
                        }
                      }}
                      className={`w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono outline-none focus:border-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white ${
                        isStockExchange ? 'pr-24' : 'uppercase'
                      }`}
                      required
                    />
                    {isStockExchange && (
                      <div className="absolute inset-y-0 right-2 flex items-center gap-1">
                        {selectedStock && (
                          <span className="max-w-[90px] truncate rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-950/70 dark:text-indigo-300">
                            {selectedStock.name}
                          </span>
                        )}
                        <button
                          type="button"
                          tabIndex={-1}
                          aria-label="종목 목록 열기"
                          onClick={() => setDropdownOpen((prev) => !prev)}
                          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                        >
                          <ChevronDown size={14} />
                        </button>
                      </div>
                    )}
                  </div>

                  {isStockExchange && dropdownOpen && (
                    <ul
                      role="listbox"
                      aria-label="종목 검색 결과"
                      className="absolute left-0 right-0 z-30 mt-1 max-h-56 overflow-y-auto rounded-xl border border-slate-200 bg-white py-1 shadow-xl dark:border-slate-700 dark:bg-slate-800"
                    >
                      {stockLoading ? (
                        <li className="px-3 py-2 text-xs text-slate-400">종목 캐시 불러오는 중...</li>
                      ) : filteredStocks.length === 0 ? (
                        <li className="px-3 py-2 text-xs text-slate-400">
                          일치하는 종목이 없습니다 (직접 코드 입력 가능)
                        </li>
                      ) : (
                        filteredStocks.map((item, idx) => {
                          const isSingleMatch = filteredStocks.length === 1
                          const isHighlighted = idx === highlightedIndex || isSingleMatch
                          return (
                            <li
                              key={`${item.code}-${item.name}`}
                              role="option"
                              aria-selected={isHighlighted}
                              onMouseDown={(e) => {
                                e.preventDefault()
                                selectStock(item)
                              }}
                              onMouseEnter={() => setHighlightedIndex(idx)}
                              className={`flex cursor-pointer items-center justify-between px-3 py-2 text-xs transition-colors ${
                                isHighlighted
                                  ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300'
                                  : 'text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-700/50'
                              }`}
                            >
                              <span className="font-medium truncate">{item.name}</span>
                              <div className="flex items-center gap-1.5 shrink-0 ml-2">
                                <span className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
                                  {item.code}
                                </span>
                                {isSingleMatch && (
                                  <span className="rounded bg-indigo-100 px-1 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-900/70 dark:text-indigo-200">
                                    Enter ↵
                                  </span>
                                )}
                              </div>
                            </li>
                          )
                        })
                      )}
                    </ul>
                  )}
                </div>
                )}
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">전략 유형</label>
                <select
                  aria-label="전략 유형"
                  value={form.strategyType}
                  onChange={(e) => {
                    const nextType = e.target.value
                    const isTop = nextType === 'kospi_top_dca'
                    const nextExchange =
                      isTop && (form.exchange === 'upbit' || form.exchange === 'bithumb') && !editingId
                        ? 'toss'
                        : form.exchange
                    const nextBudget =
                      isTop && (form.budget === '100000' || !form.budget) ? '3000000' : form.budget
                    const nextExecTime =
                      isTop && form.dcaExecTime === '09:05' ? '09:10' : form.dcaExecTime
                    setForm({
                      ...form,
                      strategyType: nextType,
                      exchange: nextExchange,
                      budget: nextBudget,
                      dcaExecTime: nextExecTime,
                      count: (nextType === 'dca' || nextType === 'sdca') ? '0' : (form.count === '0' ? '10' : form.count),
                      dcaAmountType: nextType === 'sdca' ? 'volume' : form.dcaAmountType,
                    })
                  }}
                  className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                >
                  <option value="kospi_top_dca">KOSPI/KOSDAQ 시총 상위 TOP N 모으기 & 분할매도 (TOP N 회전)</option>
                  <option value="grid">거미줄 분할 매수 (/grid — 가격 범위 분할 매수)</option>
                  <option value="sgrid">거미줄 분할 매도 (/sgrid — 가격 범위 보유수량 분할 매도)</option>
                  <option value="rsitrade">RSI 조건 순환 매매 (/rsitrade — RSI 분할 매수 + 자동 익절 예약)</option>
                  <option value="dca">정기 적립식 매수 (/dca — 매일·특정요일·매주·매월 정기 매수)</option>
                  <option value="sdca">정기 분할 매도 (/sdca — 매일·특정요일·매주·매월 정기 매도)</option>
                </select>
              </div>

              {isTopDcaForm ? (
                <div className="space-y-4">
                  {/* 섹션 1: 타겟 순위 구간 & 필터 */}
                  <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 space-y-3 dark:border-slate-800 dark:bg-slate-800/40">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                        1. 타겟 순위 구간 및 종목 필터
                      </span>
                      <span className="rounded bg-indigo-100 px-2 py-0.5 font-mono text-[11px] font-semibold text-indigo-700 dark:bg-indigo-950/80 dark:text-indigo-300">
                        자동 티커:{' '}
                        {(parseInt(form.rankStart, 10) || 1) === 1
                          ? `${form.topMarket || 'KOSPI'}_TOP${parseInt(form.rankEnd, 10) || 10}`
                          : `${form.topMarket || 'KOSPI'}_TOP${parseInt(form.rankStart, 10) || 1}_${parseInt(form.rankEnd, 10) || 10}`}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          타겟 시작 순위 (1~50위)
                        </label>
                        <input
                          type="number"
                          aria-label="타겟 시작 순위"
                          min="1"
                          max="50"
                          value={form.rankStart}
                          onChange={(e) => setForm({ ...form, rankStart: e.target.value })}
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                          required
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          타겟 종료 순위 (1~50위)
                        </label>
                        <input
                          type="number"
                          aria-label="타겟 종료 순위"
                          min="1"
                          max="50"
                          value={form.rankEnd}
                          onChange={(e) => setForm({ ...form, rankEnd: e.target.value })}
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                          required
                        />
                      </div>
                    </div>

                    <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={form.excludePreferred}
                        onChange={(e) => setForm({ ...form, excludePreferred: e.target.checked })}
                        className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span>보통주 필터링 적용 (우선주·ETF·ETN·스팩·리츠·스테이블코인 제외)</span>
                    </label>
                  </div>

                  {/* 섹션 2: 구간 이탈 판정 및 분할매도 정책 */}
                  <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 space-y-3 dark:border-slate-800 dark:bg-slate-800/40">
                    <span className="block text-xs font-bold text-slate-800 dark:text-slate-200">
                      2. 순위 이탈 판정 (휩쏘 방지) 및 분할 매도
                    </span>

                    <div>
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                        상위 순위 승격 시 처리 (예: 5~10위 전략에서 4위로 상승 시)
                      </label>
                      <select
                        aria-label="상위 순위 승격 시 처리"
                        value={form.upperExitMode}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            upperExitMode: e.target.value as 'sell_on_any_exit' | 'hold_on_promotion',
                          })
                        }
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      >
                        <option value="sell_on_any_exit">구간 밖 이탈 시 모두 분할매도 (수익 실현)</option>
                        <option value="hold_on_promotion">상위 순위 승격 시 보유 유지 (하락 이탈 시에만 매도)</option>
                      </select>
                    </div>

                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          유예 순위 버퍼 (+위)
                        </label>
                        <input
                          type="number"
                          aria-label="유예 순위 버퍼"
                          min="0"
                          max="20"
                          value={form.exitRankBuffer}
                          onChange={(e) => setForm({ ...form, exitRankBuffer: e.target.value })}
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                          required
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          연속 이탈 확인 (영업일)
                        </label>
                        <input
                          type="number"
                          aria-label="연속 이탈 확인"
                          min="1"
                          max="20"
                          value={form.exitConfirmDays}
                          onChange={(e) => setForm({ ...form, exitConfirmDays: e.target.value })}
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                          required
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          이탈 시 분할매도 (일)
                        </label>
                        <input
                          type="number"
                          aria-label="이탈 시 분할매도"
                          min="1"
                          max="60"
                          value={form.sellSplitDays}
                          onChange={(e) => setForm({ ...form, sellSplitDays: e.target.value })}
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                          required
                        />
                      </div>
                    </div>
                  </div>

                  {/* 섹션 3: 예산 플랜 및 사이클 배분 */}
                  <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 space-y-3 dark:border-slate-800 dark:bg-slate-800/40">
                    <span className="block text-xs font-bold text-slate-800 dark:text-slate-200">
                      3. 예산 플랜 (Budget Plan) 및 사이클 매수 방식
                    </span>

                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          예산 충전 모드
                        </label>
                        <select
                          aria-label="예산 충전 모드"
                          value={form.budgetMode}
                          onChange={(e) =>
                            setForm({ ...form, budgetMode: e.target.value as 'monthly' | 'daily' })
                          }
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                        >
                          <option value="monthly">월 총예산 기준 (동적 분할)</option>
                          <option value="daily">일일 고정 충전액 기준</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          {form.budgetMode === 'daily' ? '월 상한 캡 (0=무제한)' : '월 설정 총예산 (KRW)'}
                        </label>
                        <input
                          type="number"
                          aria-label="월 설정 총예산"
                          step="any"
                          min="0"
                          value={form.budget}
                          onChange={(e) => setForm({ ...form, budget: e.target.value })}
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                          required
                        />
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          {form.budgetMode === 'daily' ? '일일 고정 충전액 (KRW)' : '월 기준 영업일 수'}
                        </label>
                        {form.budgetMode === 'daily' ? (
                          <input
                            type="number"
                            aria-label="일일 고정 충전액"
                            step="any"
                            min="0"
                            value={form.dailyFixedBudget}
                            onChange={(e) => setForm({ ...form, dailyFixedBudget: e.target.value })}
                            className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                            required
                          />
                        ) : (
                          <input
                            type="number"
                            aria-label="월 기준 영업일 수"
                            min="1"
                            max="31"
                            value={form.tradingDaysPerMonth}
                            onChange={(e) => setForm({ ...form, tradingDaysPerMonth: e.target.value })}
                            className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                            required
                          />
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          사이클당 종목 배분 방식
                        </label>
                        <select
                          aria-label="사이클당 종목 배분 방식"
                          value={form.cycleAllocMode}
                          onChange={(e) =>
                            setForm({
                              ...form,
                              cycleAllocMode: e.target.value as 'one_share' | 'target_amount',
                            })
                          }
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                        >
                          <option value="one_share">사이클당 1주씩 순차 매수 (one_share)</option>
                          <option value="target_amount">사이클당 목표 금액 균등 매수 (target_amount)</option>
                        </select>
                      </div>
                      {form.cycleAllocMode === 'target_amount' ? (
                        <div>
                          <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                            종목당 1회 목표 금액 (KRW)
                          </label>
                          <input
                            type="number"
                            aria-label="종목당 1회 목표 금액"
                            step="any"
                            min="1000"
                            value={form.cycleTargetKrw}
                            onChange={(e) => setForm({ ...form, cycleTargetKrw: e.target.value })}
                            className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                            required
                          />
                        </div>
                      ) : (
                        <div>
                          <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                            이탈 매도 대금 처리 방식
                          </label>
                          <select
                            aria-label="이탈 매도 대금 처리 방식"
                            value={form.sellProceedsMode}
                            onChange={(e) =>
                              setForm({
                                ...form,
                                sellProceedsMode: e.target.value as 'keep_cash' | 'recycle_to_budget',
                              })
                            }
                            className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                          >
                            <option value="keep_cash">예수금 보관 (익월 입금 부담 경감)</option>
                            <option value="recycle_to_budget">전략 가용 예산 풀에 자동 재투입</option>
                          </select>
                        </div>
                      )}
                    </div>

                    {form.cycleAllocMode === 'target_amount' && (
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          이탈 매도 대금 처리 방식
                        </label>
                        <select
                          aria-label="이탈 매도 대금 처리 방식"
                          value={form.sellProceedsMode}
                          onChange={(e) =>
                            setForm({
                              ...form,
                              sellProceedsMode: e.target.value as 'keep_cash' | 'recycle_to_budget',
                            })
                          }
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                        >
                          <option value="keep_cash">예수금 보관 (익월 입금 부담 경감)</option>
                          <option value="recycle_to_budget">전략 가용 예산 풀에 자동 재투입</option>
                        </select>
                      </div>
                    )}
                  </div>

                  {/* 섹션 4: 주문 가격 방식 & 스케줄/Dry-Run */}
                  <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 space-y-3 dark:border-slate-800 dark:bg-slate-800/40">
                    <span className="block text-xs font-bold text-slate-800 dark:text-slate-200">
                      4. 주문 집행 및 일일 자동 스케줄
                    </span>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          주문 호가 방식
                        </label>
                        <select
                          aria-label="주문 호가 방식"
                          value={form.orderPriceMode}
                          onChange={(e) =>
                            setForm({
                              ...form,
                              orderPriceMode: e.target.value as
                                | 'limit_current'
                                | 'limit_aggressive'
                                | 'market',
                            })
                          }
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                        >
                          <option value="limit_current">현재가 지정가 (limit_current)</option>
                          <option value="limit_aggressive">체결우선 ±2틱 지정가 (limit_aggressive)</option>
                          <option value="market">시장가 (market)</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          매일 실행 시각 (KST)
                        </label>
                        <input
                          type="text"
                          aria-label="매일 실행 시각"
                          placeholder="09:10"
                          value={form.dcaExecTime}
                          onChange={(e) => setForm({ ...form, dcaExecTime: e.target.value })}
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                          required
                        />
                      </div>
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center gap-3 pt-1">
                      <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={form.scheduleEnabled}
                          onChange={(e) => setForm({ ...form, scheduleEnabled: e.target.checked })}
                          className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span>매일 정규장 스케줄 자동 실행 활성화 (Active)</span>
                      </label>
                      <label className="flex items-center gap-2 text-xs text-amber-700 dark:text-amber-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={form.isDryRun}
                          onChange={(e) => setForm({ ...form, isDryRun: e.target.checked })}
                          className="rounded border-slate-300 text-amber-600 focus:ring-amber-500"
                        />
                        <span>🧪 Dry-Run 모의 실행 (실주문 없이 프리징·원장만 검증)</span>
                      </label>
                    </div>
                  </div>
                </div>
              ) : isDcaForm ? (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">실행 주기</label>
                      <input
                        type="text"
                        placeholder="예: 매일, 매주월, 월수금, 평일, 매월15일"
                        value={form.dcaSchedule}
                        onChange={(e) => setForm({ ...form, dcaSchedule: e.target.value })}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                        required
                      />
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">실행 시각 (KST)</label>
                      <input
                        type="text"
                        placeholder="09:05"
                        value={form.dcaExecTime}
                        onChange={(e) => setForm({ ...form, dcaExecTime: e.target.value })}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                        required
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">1회 주문 기준</label>
                      <select
                        value={form.dcaAmountType}
                        onChange={(e) => setForm({ ...form, dcaAmountType: e.target.value as 'budget' | 'volume' })}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      >
                        <option value="budget">예산 (금액)</option>
                        <option value="volume">수량 (개/주)</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                        {form.dcaAmountType === 'volume' ? '1회 주문 수량' : '1회 주문 예산'}
                      </label>
                      <input
                        type="number"
                        step="any"
                        value={form.budget}
                        onChange={(e) => setForm({ ...form, budget: e.target.value })}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                        required
                      />
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">총 횟수 (0=무기한)</label>
                      <input
                        type="number"
                        min="0"
                        value={form.count}
                        onChange={(e) => setForm({ ...form, count: e.target.value })}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                        required
                      />
                    </div>
                  </div>
                </>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                      {isSellGridForm ? '총 매도 수량 (개/주)' : '투자 예산 (KRW)'}
                    </label>
                    <input
                      type="number"
                      step="any"
                      value={form.budget}
                      onChange={(e) => setForm({ ...form, budget: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      required
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">분할 주문 수</label>
                    <input
                      type="number"
                      min="1"
                      max="50"
                      value={form.count}
                      onChange={(e) => setForm({ ...form, count: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      required
                    />
                  </div>
                </div>
              )}

              {(form.strategyType === 'grid' || form.strategyType === 'sgrid') && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">시작 가격</label>
                    <input
                      type="number"
                      step="any"
                      placeholder={isSellGridForm ? '최저 매도가' : '최저 매수가'}
                      value={form.startPrice}
                      onChange={(e) => setForm({ ...form, startPrice: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      required
                    />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">종료 가격</label>
                    <input
                      type="number"
                      step="any"
                      placeholder={isSellGridForm ? '최고 매도가' : '최고 매수가'}
                      value={form.endPrice}
                      onChange={(e) => setForm({ ...form, endPrice: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      required
                    />
                  </div>
                </div>
              )}

              {(form.strategyType === 'rsitrade' || form.strategyType === 'rsi') && (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">매수 RSI 범위</label>
                      <input
                        type="text"
                        placeholder="25-30"
                        value={form.buyRsiRange}
                        onChange={(e) => setForm({ ...form, buyRsiRange: e.target.value })}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">매도 RSI 범위 (매수만 할 경우 -)</label>
                      <input
                        type="text"
                        placeholder="65-75"
                        value={form.sellRsiRange}
                        onChange={(e) => setForm({ ...form, sellRsiRange: e.target.value })}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      />
                    </div>
                  </div>
                  <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.weighted}
                      onChange={(e) => setForm({ ...form, weighted: e.target.checked })}
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span>DCA 가중 매수 적용 (낮은 RSI 구간에 더 많은 예산 배정)</span>
                  </label>
                </div>
              )}

              <div className="mt-6 flex justify-end gap-2.5 border-t border-slate-100 pt-4 dark:border-slate-800">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => setFormOpen(false)}
                  className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 dark:border-slate-700 dark:text-slate-300"
                >
                  취소
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
                >
                  {saving && <Loader2 size={14} className="animate-spin" />}
                  <span>{saving ? '저장 중...' : '저장하기'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 즉시 실행 확인 모달 */}
      {executingTemplate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm"
            onClick={() => !executing && setExecutingTemplate(null)}
          />
          <div className="relative z-10 w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
            <h3 className="text-base font-bold text-slate-900 dark:text-white">
              전략 템플릿 즉시 실행
            </h3>
            <p className="mt-2 text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              <strong>'{executingTemplate.name}'</strong> 설정으로 거래소에 전략을 즉시 가동합니다.
            </p>
            <div className="mt-3 rounded-xl bg-slate-50 p-3 text-xs font-mono space-y-1 dark:bg-slate-800/60">
              <p>유형: {STRATEGY_TYPE_LABELS[executingTemplate.strategy_type || 'grid'] || executingTemplate.strategy_type}</p>
              <p>종목: {executingTemplate.ticker} ({executingTemplate.exchange.toUpperCase()})</p>
              <p>
                규모: {executingTemplate.strategy_type === 'sgrid' || executingTemplate.params?.amount_type === 'volume'
                  ? `${executingTemplate.budget} (수량)`
                  : krwFmt(executingTemplate.budget)}
              </p>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                disabled={executing}
                onClick={() => setExecutingTemplate(null)}
                className="rounded-xl border border-slate-200 px-3.5 py-1.5 text-xs font-semibold text-slate-600 dark:border-slate-700 dark:text-slate-300"
              >
                취소
              </button>
              <button
                type="button"
                disabled={executing}
                onClick={handleConfirmExecute}
                className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {executing && <Loader2 size={13} className="animate-spin" />}
                <span>{executing ? '실행 중...' : '확인, 즉시 실행'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
