import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Layers,
  Loader2,
  Plus,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'
import { ApiError } from '../../api/client'
import { fetchStockCache, type StockCacheRow } from '../../api/stockCache'
import { createTemplate, updateTemplate, type Template } from '../../api/templates'
import AdvancedSection from '../ui/AdvancedSection'
import TimePickerInput from '../ui/TimePickerInput'
import { useToast } from '../../contexts/ToastContext'
import { krwFmt, formatWithCommas, stripCommas } from '../../utils/formatters'
import {
  DEFAULT_MULTI_FORM,
  DEFAULT_SINGLE_FORM,
  buildPayload,
  templateToForm,
  normalizeTimeInput,
  isValidTimeInput,
  type TemplateFormState,
} from './strategyTypes'

interface StrategyFormModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  editingTemplate?: Template | null
  initialType?: 'single' | 'multi'
}

export default function StrategyFormModal({
  isOpen,
  onClose,
  onSuccess,
  editingTemplate,
  initialType = 'single',
}: StrategyFormModalProps) {
  const toast = useToast()

  const [form, setForm] = useState<TemplateFormState>(
    initialType === 'multi' ? DEFAULT_MULTI_FORM : DEFAULT_SINGLE_FORM,
  )
  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [topDcaStep, setTopDcaStep] = useState<1 | 2 | 3 | 4>(1)
  const [singleStep, setSingleStep] = useState<1 | 2>(1)

  // 종목 캐시 & 다운콤보 상태 (한국투자증권 / TOSS)
  const [stockList, setStockList] = useState<StockCacheRow[]>([])
  const [stockLoading, setStockLoading] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const comboboxRef = useRef<HTMLDivElement>(null)
  const justSelectedRef = useRef<string | null>(null)
  const lastStepChangeTimeRef = useRef<number>(0)

  const isTopDcaForm = form.strategyType === 'kospi_top_dca'
  const isStockExchange = form.exchange === 'kis' || form.exchange === 'toss'
  const isCrypto = form.exchange === 'upbit' || form.exchange === 'bithumb'
  const isDcaForm = form.strategyType === 'dca' || form.strategyType === 'sdca'
  const isTimeInvalid = useMemo(() => {
    if (!isTopDcaForm && !isDcaForm) return false
    if (!form.dcaExecTime || !form.dcaExecTime.trim()) return true
    return !isValidTimeInput(normalizeTimeInput(form.dcaExecTime))
  }, [isTopDcaForm, isDcaForm, form.dcaExecTime])
  const isSellGridForm = form.strategyType === 'sgrid'

  useEffect(() => {
    if (isOpen) {
      if (editingTemplate) {
        setForm(templateToForm(editingTemplate))
      } else {
        setForm(initialType === 'multi' ? DEFAULT_MULTI_FORM : DEFAULT_SINGLE_FORM)
      }
      setFormError(null)
      setTopDcaStep(1)
      setSingleStep(1)
      setDropdownOpen(false)
      setHighlightedIndex(-1)
    }
  }, [isOpen, editingTemplate, initialType])

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
    if (isOpen && isStockExchange && stockList.length === 0) {
      loadStockList()
    }
  }, [isOpen, isStockExchange])

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
        item.name.toLowerCase().includes(q) || item.code.toLowerCase().includes(q),
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

  const validateTopDcaStep = (stepNumber: number): boolean => {
    if (stepNumber === 1) {
      if (!form.name.trim()) {
        setFormError('템플릿 이름을 입력하세요.')
        return false
      }
      const rStart = parseInt(form.rankStart, 10)
      const rEnd = parseInt(form.rankEnd, 10)
      if (Number.isNaN(rStart) || Number.isNaN(rEnd) || rStart < 1 || rEnd < rStart || rEnd > 50) {
        setFormError('순위 구간은 1위 ~ 50위 사이에서 시작 순위 ≤ 종료 순위로 설정하세요.')
        return false
      }
    } else if (stepNumber === 2) {
      const buffer = parseInt(form.exitRankBuffer, 10)
      const confirmDays = parseInt(form.exitConfirmDays, 10)
      const splitDays = parseInt(form.sellSplitDays, 10)
      if (Number.isNaN(buffer) || buffer < 0 || buffer > 20) {
        setFormError('유예 순위 버퍼는 0~20위 사이로 설정하세요.')
        return false
      }
      if (Number.isNaN(confirmDays) || confirmDays < 1 || confirmDays > 20) {
        setFormError('연속 이탈 확인 일수는 1~20일 사이로 설정하세요.')
        return false
      }
      if (Number.isNaN(splitDays) || splitDays < 1 || splitDays > 60) {
        setFormError('이탈 시 분할 매도 일수는 1~60일 사이로 설정하세요.')
        return false
      }
    } else if (stepNumber === 3) {
      if (form.budgetMode === 'monthly') {
        const b = parseFloat(stripCommas(form.budget))
        const days = parseInt(form.tradingDaysPerMonth, 10)
        if (Number.isNaN(b) || b <= 0) {
          setFormError('월 설정 총예산을 0원보다 크게 입력하세요.')
          return false
        }
        if (Number.isNaN(days) || days < 1 || days > 31) {
          setFormError('월 기준 영업일 수는 1~31일 사이로 설정하세요.')
          return false
        }
      } else {
        const fixed = parseFloat(stripCommas(form.dailyFixedBudget))
        if (Number.isNaN(fixed) || fixed <= 0) {
          setFormError('일일 고정 충전액을 0원보다 크게 입력하세요.')
          return false
        }
      }
      if (form.cycleAllocMode === 'target_amount') {
        const target = parseFloat(stripCommas(form.cycleTargetKrw))
        if (Number.isNaN(target) || target < 1000) {
          setFormError('종목당 1회 목표 금액은 최소 1,000원 이상 입력하세요.')
          return false
        }
      }
    }
    setFormError(null)
    return true
  }

  const handleNextTopDcaStep = (e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }
    if (validateTopDcaStep(topDcaStep)) {
      lastStepChangeTimeRef.current = Date.now()
      setTopDcaStep((prev) => (Math.min(prev + 1, 4) as 1 | 2 | 3 | 4))
    }
  }

  const handleStepJump = (target: 1 | 2 | 3 | 4) => {
    if (target > topDcaStep) {
      for (let s = topDcaStep; s < target; s++) {
        if (!validateTopDcaStep(s)) return
      }
    }
    setFormError(null)
    lastStepChangeTimeRef.current = Date.now()
    setTopDcaStep(target)
  }

  const validateSingleStep = (stepNumber: number): boolean => {
    if (stepNumber === 1) {
      if (!form.name.trim()) {
        setFormError('전략 이름을 입력하세요.')
        return false
      }
      if (!form.ticker.trim()) {
        setFormError('종목 코드(티커)를 선택하거나 입력하세요.')
        return false
      }
      if (isDcaForm) {
        if (form.dcaAmountType === 'budget') {
          const b = parseFloat(stripCommas(form.budget))
          if (Number.isNaN(b) || b <= 0) {
            setFormError('1회 주문 예산을 올바르게 입력하세요 (0원 초과).')
            return false
          }
        } else {
          const v = parseFloat(form.budget)
          if (Number.isNaN(v) || v <= 0) {
            setFormError('1회 주문 수량을 올바르게 입력하세요 (0 초과).')
            return false
          }
        }
        if (isTimeInvalid) {
          setFormError('실행 시각은 올바른 시간 형식(00:00 ~ 23:59)으로 입력해 주세요.')
          return false
        }
      } else if (form.strategyType === 'grid' || form.strategyType === 'sgrid') {
        const b = parseFloat(stripCommas(form.budget))
        if (Number.isNaN(b) || b <= 0) {
          setFormError(isSellGridForm ? '총 매도 수량을 입력하세요.' : '투자 예산을 올바르게 입력하세요.')
          return false
        }
        const sp = parseFloat(stripCommas(form.startPrice))
        const ep = parseFloat(stripCommas(form.endPrice))
        if (Number.isNaN(sp) || sp <= 0 || Number.isNaN(ep) || ep <= 0) {
          setFormError('시작 가격과 종료 가격을 올바르게 입력하세요.')
          return false
        }
      } else if (form.strategyType === 'rsitrade') {
        const b = parseFloat(stripCommas(form.budget))
        if (Number.isNaN(b) || b <= 0) {
          setFormError('투자 예산을 올바르게 입력하세요.')
          return false
        }
      }
    }
    setFormError(null)
    return true
  }

  const handleSingleNextStep = (e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }
    if (validateSingleStep(singleStep)) {
      setSingleStep(2)
    }
  }

  const handleSingleStepJump = (target: 1 | 2) => {
    if (target > singleStep) {
      if (!validateSingleStep(1)) return
    }
    setFormError(null)
    setSingleStep(target)
  }

  const executeSave = async (overrideForm?: TemplateFormState) => {
    const targetForm = overrideForm || form
    if (!targetForm.name.trim()) {
      setFormError('템플릿 이름을 입력하세요.')
      return
    }
    if (!isTopDcaForm && !targetForm.ticker.trim()) {
      setFormError('종목 코드를 입력하세요.')
      return
    }
    if (isTopDcaForm) {
      const rStart = parseInt(targetForm.rankStart, 10)
      const rEnd = parseInt(targetForm.rankEnd, 10)
      if (Number.isNaN(rStart) || Number.isNaN(rEnd) || rStart < 1 || rEnd < rStart || rEnd > 50) {
        setFormError('순위 구간은 1위 ~ 50위 사이에서 시작 순위 ≤ 종료 순위로 설정하세요.')
        return
      }
    }

    let submitForm = targetForm
    if (isTopDcaForm || isDcaForm) {
      const normTime = normalizeTimeInput(targetForm.dcaExecTime)
      if (!isValidTimeInput(normTime)) {
        setFormError('실행 시각은 올바른 시간 형식(00:00 ~ 23:59, 예: 14:30)으로 입력해 주세요.')
        return
      }
      submitForm = { ...submitForm, dcaExecTime: normTime }
    }

    if (!isTopDcaForm && isStockExchange) {
      const q = targetForm.ticker.trim().toLowerCase()
      const exactCode = stockList.find((s) => s.code.toLowerCase() === q)
      if (!exactCode) {
        const exactName = stockList.find((s) => s.name.toLowerCase() === q)
        if (exactName) {
          submitForm = { ...submitForm, ticker: exactName.code }
        } else if (filteredStocks.length === 1) {
          submitForm = { ...submitForm, ticker: filteredStocks[0].code }
        }
      }
    }

    setSaving(true)
    setFormError(null)
    try {
      const payload = buildPayload(submitForm)
      if (editingTemplate) {
        await updateTemplate(editingTemplate.id, payload)
        toast.success('전략 설정이 수정되었습니다.')
      } else {
        await createTemplate(payload)
        toast.success('새 전략이 생성되었습니다.')
      }
      onSuccess()
      onClose()
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : '저장 중 오류가 발생했습니다.')
    } finally {
      setSaving(false)
    }
  }

  const handleQuickDefaultSave = (e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }
    if (isTopDcaForm) {
      if (!validateTopDcaStep(1)) {
        setTopDcaStep(1)
        return
      }
      // 복수 종목: 검증된 기본 세팅으로 바로 실행 (3일 휩쏘, 5일 분할매도, 기본 시간 및 시장가)
      executeSave()
    } else {
      if (!validateSingleStep(1)) {
        setSingleStep(1)
        return
      }
      // 단일 종목: 1단계 입력만으로 검증된 기본 세팅(시장가, 익일이월, 무한예산)으로 바로 실행
      executeSave()
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (isTopDcaForm && topDcaStep < 4) {
      handleNextTopDcaStep()
      return
    }
    if (isTopDcaForm && process.env.NODE_ENV !== 'test' && Date.now() - lastStepChangeTimeRef.current < 350) {
      return
    }
    if (!isTopDcaForm) {
      if (!validateSingleStep(1)) {
        setSingleStep(1)
        return
      }
    }
    await executeSave()
  }

  if (!isOpen) return null

  const rankStartNum = parseInt(form.rankStart, 10) || 1
  const rankEndNum = parseInt(form.rankEnd, 10) || 10
  const totalTargetCount = Math.max(1, rankEndNum - rankStartNum + 1)
  const autoTickerPreview =
    rankStartNum === 1
      ? `${form.topMarket || 'KOSPI'}_TOP${rankEndNum}`
      : `${form.topMarket || 'KOSPI'}_TOP${rankStartNum}_${rankEndNum}`

  const monthlyBudgetNum = parseFloat(stripCommas(form.budget)) || 0
  const tradingDaysNum = parseInt(form.tradingDaysPerMonth, 10) || 20
  const dailyApproxBudget =
    form.budgetMode === 'daily'
      ? parseFloat(stripCommas(form.dailyFixedBudget)) || 150000
      : Math.floor(monthlyBudgetNum / Math.max(1, tradingDaysNum))

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto p-4 sm:p-6 md:p-8 flex items-center justify-center">
      <div
        className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs transition-opacity"
        onClick={() => !saving && onClose()}
      />
      <div
        className={`relative z-10 my-auto flex flex-col w-full ${
          isTopDcaForm ? 'max-w-2xl' : 'max-w-lg'
        } max-h-[85vh] rounded-2xl bg-white shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800 transition-all text-left overflow-hidden`}
      >
        {/* 고정 모달 헤더 */}
        <div className="flex shrink-0 items-center justify-between border-b border-slate-100 px-6 py-4 dark:border-slate-800">
          <div className="flex items-center gap-2.5">
            {isTopDcaForm ? (
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-violet-100 text-violet-600 dark:bg-violet-950/60 dark:text-violet-400">
                <Layers size={16} />
              </span>
            ) : (
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-100 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400">
                <Plus size={16} />
              </span>
            )}
            <div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                {editingTemplate
                  ? isTopDcaForm
                    ? '복수 종목 전략 템플릿 수정'
                    : '단일 종목 전략 템플릿 수정'
                  : isTopDcaForm
                  ? '복수 종목 전략 템플릿 만들기 (시총 TOP N)'
                  : '단일 종목 전략 템플릿 만들기'}
              </h3>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                {isTopDcaForm
                  ? '시가총액 상위 유니버스 기반 순환 모으기 및 분할매도 자동화'
                  : '단일 종목 대상 거미줄(GRID), RSI 조건, 정기 적립식(DCA) 매매'}
              </p>
            </div>
          </div>
          <button
            onClick={() => !saving && onClose()}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
          >
            <X size={16} />
          </button>
        </div>

        {/* 복수 종목(시총 TOP N) 전용 1~4 Step Wizard 헤더 */}
        {isTopDcaForm && (
          <div className="shrink-0 border-b border-slate-100 bg-slate-50/70 px-6 py-3 dark:border-slate-800 dark:bg-slate-900/60">
            <div className="flex items-center justify-between">
              {[
                { step: 1, title: '유니버스', desc: '시장 및 순위 구간' },
                { step: 2, title: '이탈 & 매도', desc: '휩쏘 방지 및 분할' },
                { step: 3, title: '예산 & 배분', desc: '예산 플랜 및 방식' },
                { step: 4, title: '스케줄 & 검토', desc: '주문 집행 및 확인' },
              ].map((s, idx) => {
                const isActive = topDcaStep === s.step
                const isPassed = topDcaStep > s.step
                return (
                  <div key={s.step} className="flex flex-1 items-center">
                    <button
                      type="button"
                      onClick={() => handleStepJump(s.step as 1 | 2 | 3 | 4)}
                      className={`flex items-center gap-2 text-left transition-all ${
                        isActive
                          ? 'opacity-100'
                          : isPassed
                          ? 'opacity-90 hover:opacity-100'
                          : 'opacity-40 hover:opacity-75'
                      }`}
                    >
                      <div
                        className={`flex h-6 w-6 sm:h-7 sm:w-7 items-center justify-center rounded-full text-xs font-bold transition-all ${
                          isActive
                            ? 'bg-violet-600 text-white shadow-xs ring-2 ring-violet-400/30'
                            : isPassed
                            ? 'bg-emerald-500 text-white'
                            : 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                        }`}
                      >
                        {isPassed ? <Check size={13} strokeWidth={3} /> : s.step}
                      </div>
                      <div className="hidden sm:block">
                        <div
                          className={`text-xs font-semibold leading-none ${
                            isActive
                              ? 'text-violet-700 dark:text-violet-300'
                              : 'text-slate-700 dark:text-slate-300'
                          }`}
                        >
                          {s.step}. {s.title}
                        </div>
                        <div className="mt-0.5 text-[10px] text-slate-400 leading-tight">
                          {s.desc}
                        </div>
                      </div>
                    </button>
                    {idx < 3 && (
                      <div
                        className={`mx-2 sm:mx-3 h-0.5 flex-1 transition-all ${
                          topDcaStep > s.step
                            ? 'bg-emerald-400 dark:bg-emerald-600'
                            : 'bg-slate-200 dark:bg-slate-800'
                        }`}
                      />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* 단일 종목 전용 1~2 Step Wizard 헤더 */}
        {!isTopDcaForm && (
          <div className="shrink-0 border-b border-slate-100 bg-slate-50/70 px-6 py-3 dark:border-slate-800 dark:bg-slate-900/60">
            <div className="flex items-center justify-between">
              {[
                { step: 1, title: '핵심 필수 설정', desc: '종목 · 투자금액 · 주기' },
                { step: 2, title: '세부 옵션 & 안전', desc: '주문방식 · 이월 · 원장 (선택)' },
              ].map((s, idx) => {
                const isActive = singleStep === s.step
                const isPassed = singleStep > s.step
                return (
                  <div key={s.step} className="flex flex-1 items-center">
                    <button
                      type="button"
                      onClick={() => handleSingleStepJump(s.step as 1 | 2)}
                      className={`flex items-center gap-2 text-left transition-all ${
                        isActive
                          ? 'opacity-100'
                          : isPassed
                          ? 'opacity-90 hover:opacity-100'
                          : 'opacity-40 hover:opacity-75'
                      }`}
                    >
                      <div
                        className={`flex h-6 w-6 sm:h-7 sm:w-7 items-center justify-center rounded-full text-xs font-bold transition-all ${
                          isActive
                            ? 'bg-indigo-600 text-white shadow-xs ring-2 ring-indigo-400/30'
                            : isPassed
                            ? 'bg-emerald-500 text-white'
                            : 'bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                        }`}
                      >
                        {isPassed ? <Check size={13} strokeWidth={3} /> : s.step}
                      </div>
                      <div className="hidden sm:block">
                        <div
                          className={`text-xs font-semibold leading-none ${
                            isActive
                              ? 'text-indigo-700 dark:text-indigo-300'
                              : 'text-slate-700 dark:text-slate-300'
                          }`}
                        >
                          {s.step}. {s.title}
                        </div>
                        <div className="mt-0.5 text-[10px] text-slate-400 leading-tight">
                          {s.desc}
                        </div>
                      </div>
                    </button>
                    {idx < 1 && (
                      <div
                        className={`mx-2 sm:mx-3 h-0.5 flex-1 transition-all ${
                          singleStep > s.step
                            ? 'bg-emerald-400 dark:bg-emerald-600'
                            : 'bg-slate-200 dark:bg-slate-800'
                        }`}
                      />
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {formError && (
          <div className="mx-6 mt-3 shrink-0 rounded-lg bg-rose-50 p-3 text-xs text-rose-600 dark:bg-rose-950/40 dark:text-rose-300">
            {formError}
          </div>
        )}

        <form
          onSubmit={handleSubmit}
          onKeyDown={(e) => {
            if (isTopDcaForm && e.key === 'Enter' && (e.target as HTMLElement).tagName !== 'TEXTAREA') {
              e.preventDefault()
            }
          }}
          className="flex flex-1 flex-col overflow-hidden"
        >
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            {isTopDcaForm ? (
              <>
                {/* Step 1: 유니버스 선정 */}
                {topDcaStep === 1 && (
                  <div className="space-y-4">
                    <div>
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                        전략 이름
                      </label>
                      <input
                        type="text"
                        placeholder="예: 코스피 시총 TOP 10 순환 모으기 & 5일 분할매도"
                        value={form.name}
                        onChange={(e) => setForm({ ...form, name: e.target.value })}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs outline-hidden dark:border-slate-700 dark:bg-slate-800 dark:text-white focus:border-violet-500"
                        required
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          거래소
                        </label>
                        <select
                          aria-label="거래소"
                          value={form.exchange}
                          onChange={(e) => {
                            const nextExchange = e.target.value
                            const nextIsStock = nextExchange === 'kis' || nextExchange === 'toss'
                            const nextTopMarket = nextIsStock
                              ? form.topMarket === 'KRW_MAJOR'
                                ? 'KOSPI'
                                : form.topMarket
                              : 'KRW_MAJOR'
                            setForm({ ...form, exchange: nextExchange, topMarket: nextTopMarket })
                          }}
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white focus:border-violet-500"
                        >
                          <option value="toss">TOSS</option>
                          <option value="kis">한국투자증권(KIS)</option>
                          <option value="upbit">Upbit</option>
                          <option value="bithumb">Bithumb</option>
                        </select>
                      </div>

                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          대상 시장 (자동 티커)
                        </label>
                        <select
                          aria-label="대상 시장"
                          value={form.topMarket}
                          onChange={(e) => setForm({ ...form, topMarket: e.target.value })}
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white focus:border-violet-500"
                        >
                          <option value="KOSPI">KOSPI (코스피 시총 상위)</option>
                          <option value="KOSDAQ">KOSDAQ (코스닥 시총 상위)</option>
                          <option value="KRW_MAJOR">KRW_MAJOR (가상자산 원화마켓 상위)</option>
                        </select>
                      </div>
                    </div>

                    {/* 타겟 순위 구간 설정 카드 */}
                    <div className="rounded-xl border border-violet-100 bg-violet-50/40 p-4 space-y-3 dark:border-violet-900/40 dark:bg-violet-950/20">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                          타겟 순위 구간 선택 (시총 순위)
                        </span>
                        <span className="rounded-sm bg-violet-100 px-2 py-0.5 text-[11px] font-semibold text-violet-700 dark:bg-violet-900/70 dark:text-violet-300">
                          자동 티커: {autoTickerPreview} ({totalTargetCount}개 종목)
                        </span>
                      </div>

                      {/* 빠른 프리셋 칩 */}
                      <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                        <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                          빠른 프리셋:
                        </span>
                        {[
                          { label: 'TOP 10 (1~10위)', s: '1', e: '10' },
                          { label: 'TOP 20 (1~20위)', s: '1', e: '20' },
                          { label: 'TOP 5~10 (5~10위)', s: '5', e: '10' },
                          { label: 'TOP 11~30 (11~30위)', s: '11', e: '30' },
                        ].map((preset) => {
                          const isSelected = form.rankStart === preset.s && form.rankEnd === preset.e
                          return (
                            <button
                              key={preset.label}
                              type="button"
                              onClick={() => setForm({ ...form, rankStart: preset.s, rankEnd: preset.e })}
                              className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition-colors ${
                                isSelected
                                  ? 'bg-violet-600 text-white shadow-xs'
                                  : 'bg-white border border-slate-200 text-slate-700 hover:bg-violet-50 hover:text-violet-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                              }`}
                            >
                              {preset.label}
                            </button>
                          )
                        })}
                      </div>

                      <div className="grid grid-cols-2 gap-3 pt-1">
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
                            className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
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
                            className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                            required
                          />
                        </div>
                      </div>

                      <label className="flex items-center gap-2 pt-1 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={form.excludePreferred}
                          onChange={(e) => setForm({ ...form, excludePreferred: e.target.checked })}
                          className="rounded-sm border-slate-300 text-violet-600 focus:ring-violet-500"
                        />
                        <span>보통주 필터링 적용 (우선주·ETF·ETN·스팩·리츠·스테이블코인 제외)</span>
                      </label>
                    </div>

                    <div className="flex items-start gap-2.5 rounded-xl bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
                      <Sparkles size={15} className="shrink-0 mt-0.5 text-violet-600 dark:text-violet-400" />
                      <span>
                        선택한 시장과 순위 구간의 대표 보통주를 매일 실시간 시가총액 기준으로 자동 선별하여 분산 매수 포트폴리오를 구성합니다.
                      </span>
                    </div>
                  </div>
                )}

                {/* Step 2: 순위 이탈 판정 & 분할 매도 정책 */}
                {topDcaStep === 2 && (
                  <div className="space-y-4">
                    <div>
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                        상위 순위 승격 시 처리 (목표 구간보다 더 상승했을 때)
                      </label>
                      <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                        <button
                          type="button"
                          onClick={() => setForm({ ...form, upperExitMode: 'sell_on_any_exit' })}
                          className={`flex flex-col text-left p-3 rounded-xl border transition-all ${
                            form.upperExitMode === 'sell_on_any_exit'
                              ? 'border-violet-600 bg-violet-50/70 dark:border-violet-500 dark:bg-violet-950/40 ring-1 ring-violet-500'
                              : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-slate-900 dark:text-white">
                              구간 밖 이탈 시 모두 분할매도
                            </span>
                            <span className="rounded-sm bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700 dark:bg-violet-900/60 dark:text-violet-300">
                              수익 실현
                            </span>
                          </div>
                          <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                            설정 구간 위(상위)로 승격되어도 수익을 실현하고 포트폴리오에서 졸업 처리합니다.
                          </p>
                        </button>

                        <button
                          type="button"
                          onClick={() => setForm({ ...form, upperExitMode: 'hold_on_promotion' })}
                          className={`flex flex-col text-left p-3 rounded-xl border transition-all ${
                            form.upperExitMode === 'hold_on_promotion'
                              ? 'border-violet-600 bg-violet-50/70 dark:border-violet-500 dark:bg-violet-950/40 ring-1 ring-violet-500'
                              : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-slate-900 dark:text-white">
                              상위 승격 시 보유 유지
                            </span>
                            <span className="rounded-sm bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300">
                              추세 홀딩
                            </span>
                          </div>
                          <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                            더 높게 상승한 주도 대장주는 매도하지 않고 계속 들고 갑니다 (하락 이탈 시에만 매도).
                          </p>
                        </button>
                      </div>
                    </div>

                    <AdvancedSection
                      title="고급 설정 · 휩쏘 방지 옵션"
                      summary={`유예 +${form.exitRankBuffer || 0}위 · ${form.exitConfirmDays || 1}영업일 확인 · ${form.sellSplitDays || 5}일 분할매도`}
                    >
                      <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 space-y-3 dark:border-slate-800 dark:bg-slate-800/40">
                        <span className="block text-xs font-bold text-slate-800 dark:text-slate-200">
                          순위 이탈 안전장치 (휩쏘·일시적 등락 방지)
                        </span>

                        <div className="grid grid-cols-2 gap-3">
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
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              required
                            />
                            <p className="mt-1 text-[10px] text-slate-400">
                              +{form.exitRankBuffer || 0}위까지는 일시적 밀림으로 인정해 매도 대기
                            </p>
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
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              required
                            />
                            <p className="mt-1 text-[10px] text-slate-400">
                              {form.exitConfirmDays || 1}영업일 연속 유예를 벗어나야 최종 확정
                            </p>
                          </div>
                        </div>

                        <div className="pt-1">
                          <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                            이탈 시 분할 매도 기간 (영업일)
                          </label>
                          <input
                            type="number"
                            aria-label="이탈 시 분할매도"
                            min="1"
                            max="60"
                            value={form.sellSplitDays}
                            onChange={(e) => setForm({ ...form, sellSplitDays: e.target.value })}
                            className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                            required
                          />
                          <p className="mt-1 text-[10px] text-slate-400">
                            이탈 확정 종목을 {form.sellSplitDays || 5}일에 걸쳐 균등 분할 매도하여 시장 충격을 최소화합니다.
                          </p>
                        </div>
                      </div>
                    </AdvancedSection>

                    <div className="flex items-start gap-2.5 rounded-xl bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-800/60 dark:text-slate-300">
                      <ShieldCheck size={15} className="shrink-0 mt-0.5 text-emerald-600 dark:text-emerald-400" />
                      <span>
                        순위가 며칠간 흔들려도 버퍼와 연속 일수를 확인하므로 잦은 매매 수수료 손실과 섣부른 손절을 방지합니다.
                      </span>
                    </div>
                  </div>
                )}

                {/* Step 3: 예산 플랜 & 사이클 매수 방식 */}
                {topDcaStep === 3 && (
                  <div className="space-y-4">
                    <div>
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                        예산 운용 방식 선택
                      </label>
                      <div className="mt-2 grid grid-cols-2 gap-2.5">
                        <button
                          type="button"
                          onClick={() => setForm({ ...form, budgetMode: 'monthly' })}
                          className={`p-3 rounded-xl border text-left transition-all ${
                            form.budgetMode === 'monthly'
                              ? 'border-violet-600 bg-violet-50/70 dark:border-violet-500 dark:bg-violet-950/40 ring-1 ring-violet-500'
                              : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-slate-900 dark:text-white">
                              월 총예산 분할 모드
                            </span>
                            <span className="rounded-sm bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-700 dark:bg-violet-900/60 dark:text-violet-300">
                              권장
                            </span>
                          </div>
                          <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                            월 총예산을 영업일 수로 나누어 일일 한도를 유연하게 관리합니다.
                          </p>
                        </button>

                        <button
                          type="button"
                          onClick={() => setForm({ ...form, budgetMode: 'daily' })}
                          className={`p-3 rounded-xl border text-left transition-all ${
                            form.budgetMode === 'daily'
                              ? 'border-violet-600 bg-violet-50/70 dark:border-violet-500 dark:bg-violet-950/40 ring-1 ring-violet-500'
                              : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800'
                          }`}
                        >
                          <span className="text-xs font-bold text-slate-900 dark:text-white">
                            일일 고정 충전 모드
                          </span>
                          <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                            매일 고정된 금액을 충전하며 월 최대 한도 캡을 둡니다.
                          </p>
                        </button>
                      </div>
                    </div>

                    <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3.5 space-y-3 dark:border-slate-800 dark:bg-slate-800/40">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                            {form.budgetMode === 'daily' ? '일일 고정 충전액 (KRW)' : '월 설정 총예산 (KRW)'}
                          </label>
                          {form.budgetMode === 'daily' ? (
                            <input
                              type="text"
                              inputMode="numeric"
                              aria-label="일일 고정 충전액"
                              value={formatWithCommas(form.dailyFixedBudget)}
                              onChange={(e) => setForm({ ...form, dailyFixedBudget: stripCommas(e.target.value) })}
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              required
                            />
                          ) : (
                            <input
                              type="text"
                              inputMode="numeric"
                              aria-label="월 설정 총예산"
                              value={formatWithCommas(form.budget)}
                              onChange={(e) => setForm({ ...form, budget: stripCommas(e.target.value) })}
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              required
                            />
                          )}
                        </div>

                        <div>
                          <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                            {form.budgetMode === 'daily' ? '월 상한 캡 (0=무제한)' : '월 기준 영업일 수 (일)'}
                          </label>
                          {form.budgetMode === 'daily' ? (
                            <input
                              type="text"
                              inputMode="numeric"
                              aria-label="월 상한 캡"
                              value={formatWithCommas(form.budget)}
                              onChange={(e) => setForm({ ...form, budget: stripCommas(e.target.value) })}
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
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
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              required
                            />
                          )}
                        </div>
                      </div>

                      <div className="flex items-center justify-between rounded-lg bg-violet-100/60 px-3 py-2 text-xs text-violet-800 dark:bg-violet-950/60 dark:text-violet-300 font-medium">
                        <span>💡 예상 1영업일 당 집행 예산:</span>
                        <span className="font-bold">
                          약 {krwFmt(dailyApproxBudget)} ({dailyApproxBudget.toLocaleString()}원)
                        </span>
                      </div>
                    </div>

                    <AdvancedSection
                      title="고급 설정 · 종목 배분 및 매도금 처리"
                      summary={`${form.cycleAllocMode === 'one_share' ? '1주씩 순차 매수' : '종목당 목표금액 균등'} · ${form.sellProceedsMode === 'keep_cash' ? '예수금 보관' : '예산 풀 재투입'}`}
                    >
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
                            className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white focus:border-violet-500"
                          >
                            <option value="one_share">1주씩 순차 매수 (one_share - 추천)</option>
                            <option value="target_amount">종목당 목표 금액 균등 매수 (target_amount)</option>
                          </select>
                          <p className="mt-1 text-[10px] text-slate-400">
                            {form.cycleAllocMode === 'one_share'
                              ? '유니버스 종목을 매일 1주씩 골고루 모아갑니다.'
                              : '종목마다 정해진 금액을 목표로 균등 분할 매수합니다.'}
                          </p>
                        </div>

                        {form.cycleAllocMode === 'target_amount' ? (
                          <div>
                            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                              종목당 1회 목표 금액 (KRW)
                            </label>
                            <input
                              type="text"
                              inputMode="numeric"
                              aria-label="종목당 1회 목표 금액"
                              value={formatWithCommas(form.cycleTargetKrw)}
                              onChange={(e) => setForm({ ...form, cycleTargetKrw: stripCommas(e.target.value) })}
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
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
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white focus:border-violet-500"
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
                            className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white focus:border-violet-500"
                          >
                            <option value="keep_cash">예수금 보관 (익월 입금 부담 경감)</option>
                            <option value="recycle_to_budget">전략 가용 예산 풀에 자동 재투입</option>
                          </select>
                        </div>
                      )}
                    </AdvancedSection>
                  </div>
                )}

                {/* Step 4: 주문 방식, 스케줄 & 최종 전략 검토 요약 */}
                {topDcaStep === 4 && (
                  <div className="space-y-4">
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
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white focus:border-violet-500"
                        >
                          <option value="limit_current">현재가 지정가 (안정적 추천)</option>
                          <option value="limit_aggressive">체결우선 ±2틱 지정가</option>
                          <option value="market">시장가 (즉시 체결)</option>
                        </select>
                      </div>

                      <div>
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          매일 실행 시각 (KST)
                        </label>
                        <div className="mt-1">
                          <TimePickerInput
                            aria-label="매일 실행 시각"
                            placeholder="15:10"
                            value={form.dcaExecTime}
                            onChange={(val) => setForm({ ...form, dcaExecTime: val })}
                            required
                            presetCategory="buy"
                            showTabSelector={true}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center gap-3 pt-1">
                      <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={form.scheduleEnabled}
                          onChange={(e) => setForm({ ...form, scheduleEnabled: e.target.checked })}
                          className="rounded-sm border-slate-300 text-violet-600 focus:ring-violet-500"
                        />
                        <span>매일 정규장 스케줄 자동 실행 활성화 (Active)</span>
                      </label>
                      <label className="flex items-center gap-2 text-xs text-amber-700 dark:text-amber-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={form.isDryRun}
                          onChange={(e) => setForm({ ...form, isDryRun: e.target.checked })}
                          className="rounded-sm border-slate-300 text-amber-600 focus:ring-amber-500"
                        />
                        <span>🧪 Dry-Run 모의 실행 (실주문 없이 프리징·원장만 검증)</span>
                      </label>
                    </div>

                    <div className="rounded-xl border border-violet-200/80 bg-violet-50/50 p-4 space-y-3 dark:border-violet-900/60 dark:bg-violet-950/30">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <Sparkles size={14} className="text-violet-600 dark:text-violet-400" />
                          <span className="text-xs font-bold text-slate-900 dark:text-white">
                            전략 템플릿 최종 설정 요약
                          </span>
                        </div>
                        <span className="text-[11px] font-semibold text-violet-700 dark:text-violet-300">
                          '{form.name || '무제 전략'}'
                        </span>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
                        <div className="rounded-lg bg-white/80 p-2.5 dark:bg-slate-900/80 border border-slate-100 dark:border-slate-800">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                            1. 대상 유니버스
                          </span>
                          <div className="font-semibold text-slate-800 dark:text-slate-200">
                            {form.exchange.toUpperCase()} • {form.topMarket}
                          </div>
                          <div className="text-[11px] text-slate-500 dark:text-slate-400">
                            {form.rankStart}위 ~ {form.rankEnd}위 ({totalTargetCount}종목, {autoTickerPreview})
                          </div>
                          <div className="text-[10px] text-slate-400 mt-0.5">
                            {form.excludePreferred ? '보통주만 (우선주/ETF 제외)' : '전 종목 대상'}
                          </div>
                        </div>

                        <div className="rounded-lg bg-white/80 p-2.5 dark:bg-slate-900/80 border border-slate-100 dark:border-slate-800">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                            2. 이탈 & 매도 정책
                          </span>
                          <div className="font-semibold text-slate-800 dark:text-slate-200">
                            {form.upperExitMode === 'hold_on_promotion'
                              ? '상위 승격 시 계속 보유'
                              : '구간 밖 이탈 시 모두 매도'}
                          </div>
                          <div className="text-[11px] text-slate-500 dark:text-slate-400">
                            버퍼 +{form.exitRankBuffer}위 / {form.exitConfirmDays}일 연속 이탈 확인
                          </div>
                          <div className="text-[10px] text-slate-400 mt-0.5">
                            이탈 확정 시 {form.sellSplitDays}영업일 균등 분할매도
                          </div>
                        </div>

                        <div className="rounded-lg bg-white/80 p-2.5 dark:bg-slate-900/80 border border-slate-100 dark:border-slate-800">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                            3. 예산 및 매수
                          </span>
                          <div className="font-semibold text-slate-800 dark:text-slate-200">
                            {form.budgetMode === 'monthly'
                              ? `월 ${krwFmt(monthlyBudgetNum)} (일 약 ${krwFmt(dailyApproxBudget)})`
                              : `일 고정 ${krwFmt(parseFloat(stripCommas(form.dailyFixedBudget)) || 0)}`}
                          </div>
                          <div className="text-[11px] text-slate-500 dark:text-slate-400">
                            {form.cycleAllocMode === 'one_share'
                              ? '1주씩 순차 매수'
                              : `목표 금액 ${krwFmt(parseFloat(stripCommas(form.cycleTargetKrw)) || 0)} 균등 매수`}
                          </div>
                          <div className="text-[10px] text-slate-400 mt-0.5">
                            매도 대금: {form.sellProceedsMode === 'recycle_to_budget' ? '예산 자동 재투입' : '예수금 보관'}
                          </div>
                        </div>

                        <div className="rounded-lg bg-white/80 p-2.5 dark:bg-slate-900/80 border border-slate-100 dark:border-slate-800">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                            4. 주문 & 스케줄
                          </span>
                          <div className="font-semibold text-slate-800 dark:text-slate-200">
                            {form.orderPriceMode === 'limit_current'
                              ? '현재가 지정가'
                              : form.orderPriceMode === 'limit_aggressive'
                              ? '체결우선 ±2틱'
                              : '시장가'}
                          </div>
                          <div className="text-[11px] text-slate-500 dark:text-slate-400">
                            매일 {form.dcaExecTime} (KST) 집행
                          </div>
                          <div className="text-[10px] text-slate-400 mt-0.5">
                            {form.scheduleEnabled ? '🟢 자동 스케줄 활성' : '⚪ 스케줄 비활성'} • {form.isDryRun ? '🧪 Dry-Run' : '🚀 실거래'}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </>
            ) : (
              /* 단일 종목 전략 폼 (1~3단계 스텝 위저드) */
              <>
                {/* Step 1: 기본 정보 & 전략 선택 */}
                {singleStep === 1 && (
                  <div className="space-y-4">
                    <div>
                      <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                        <span>전략 이름</span>
                        <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                          필수
                        </span>
                      </label>
                      <input
                        type="text"
                        placeholder="예: 비트코인 매일 5만원 정기매수 / 삼성전자 10분할 거미줄 매수"
                        value={form.name}
                        onChange={(e) => setForm({ ...form, name: e.target.value })}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs outline-hidden dark:border-slate-700 dark:bg-slate-800 dark:text-white focus:border-indigo-500"
                        required
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                          <span>거래소</span>
                          <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                            필수
                          </span>
                        </label>
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
                            setForm({ ...form, exchange: nextExchange, ticker: nextTicker })
                            setDropdownOpen(false)
                            setHighlightedIndex(-1)
                          }}
                          className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                        >
                          <option value="upbit">Upbit (업비트)</option>
                          <option value="bithumb">Bithumb (빗썸)</option>
                          <option value="kis">한국투자증권(KIS)</option>
                          <option value="toss">TOSS (토스증권)</option>
                        </select>
                      </div>

                      <div ref={comboboxRef} className="relative">
                        <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                          <span>종목 코드 (티커)</span>
                          <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                            필수
                          </span>
                        </label>
                        <div className="relative mt-1">
                          <input
                            type="text"
                            aria-label="종목 코드 (티커)"
                            autoComplete="off"
                            placeholder={isStockExchange ? '종목명 또는 코드 검색 (예: 삼성전자, 005930)' : 'BTC, ETH, XRP'}
                            value={form.ticker}
                            onFocus={() => {
                              if (isStockExchange && form.ticker.trim() && !selectedStock) {
                                setDropdownOpen(true)
                              }
                            }}
                            onChange={(e) => {
                              const val = e.target.value
                              if (val === '') {
                                justSelectedRef.current = null
                              } else if (justSelectedRef.current !== null) {
                                return
                              }
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
                            className={`w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs outline-hidden focus:border-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white ${
                              isStockExchange ? 'pr-24' : 'uppercase'
                            }`}
                            required
                          />
                          {isStockExchange && (
                            <div className="absolute inset-y-0 right-2 flex items-center gap-1">
                              {selectedStock && (
                                <span className="max-w-[90px] truncate rounded-sm bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-950/70 dark:text-indigo-300">
                                  {selectedStock.name}
                                </span>
                              )}
                              <button
                                type="button"
                                tabIndex={-1}
                                aria-label="종목 목록 열기"
                                onClick={() => setDropdownOpen((prev) => !prev)}
                                className="rounded-sm p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-700 dark:hover:text-slate-200"
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
                                      <span className="text-[11px] text-slate-500 dark:text-slate-400">
                                        {item.code}
                                      </span>
                                      {isSingleMatch && (
                                        <span className="rounded-sm bg-indigo-100 px-1 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-900/70 dark:text-indigo-200">
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
                    </div>

                    <div>
                      <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                        <span>전략 유형</span>
                        <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                          필수
                        </span>
                      </label>
                      <select
                        aria-label="전략 유형"
                        value={form.strategyType}
                        onChange={(e) => {
                          const nextType = e.target.value
                          setForm({
                            ...form,
                            strategyType: nextType,
                            count: nextType === 'dca' || nextType === 'sdca' ? '0' : form.count === '0' ? '10' : form.count,
                            dcaAmountType: nextType === 'sdca' ? 'volume' : form.dcaAmountType,
                            budgetMode: 'total',
                            sellProceedsMode: nextType === 'rsitrade' ? 'recycle_to_budget' : 'keep_cash',
                          })
                        }}
                        className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      >
                        <option value="dca">🛡️ 정기 적립식 매수 (/dca — 초보 추천! 매일/매주 일정액 자동 분산 매수)</option>
                        <option value="grid">🕸️ 거미줄 분할 매수 (/grid — 설정 가격 범위에 그물망 분할 매수)</option>
                        <option value="rsitrade">📉 RSI 조건 순환 매매 (/rsitrade — 과매도 저점 매수 + 자동 익절)</option>
                        <option value="sgrid">💰 거미줄 분할 매도 (/sgrid — 가격 범위 보유수량 단계별 분할 매도)</option>
                        <option value="sdca">📅 정기 분할 매도 (/sdca — 매일/매주 보유수량 정기 분할 매도)</option>
                      </select>
                    </div>

                    {/* 전략별 핵심 투자 금액 & 주기 설정 */}
                    {isDcaForm ? (
                      <>
                        <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-3.5 space-y-3 dark:border-slate-700 dark:bg-slate-800/40">
                          <div className="flex items-center justify-between">
                            <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                              <span>실행 요일 지정</span>
                              <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                                필수
                              </span>
                            </label>
                            <span className="text-[11px] text-indigo-600 dark:text-indigo-400 font-semibold">
                              설정값: {form.dcaSchedule || '매일'}
                            </span>
                          </div>

                          {/* 빠른 요일 프리셋 */}
                          <div className="flex flex-wrap gap-1.5">
                            <button
                              type="button"
                              onClick={() => setForm({ ...form, dcaSchedule: isCrypto ? '매일' : '월~금' })}
                              className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                                form.dcaSchedule === '매일' || form.dcaSchedule === '월~일' || (!isCrypto && form.dcaSchedule === '월~금')
                                  ? 'bg-indigo-600 text-white font-semibold'
                                  : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
                              }`}
                            >
                              {isCrypto ? '매일 (월~일)' : '평일 (월~금)'}
                            </button>
                            {isCrypto && (
                              <button
                                type="button"
                                onClick={() => setForm({ ...form, dcaSchedule: '월~금' })}
                                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                                  form.dcaSchedule === '월~금' || form.dcaSchedule === '평일'
                                    ? 'bg-indigo-600 text-white font-semibold'
                                    : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
                                }`}
                              >
                                평일만 (월~금)
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => setForm({ ...form, dcaSchedule: '월,수,금' })}
                              className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                                form.dcaSchedule === '월,수,금' || form.dcaSchedule === '월/수/금'
                                  ? 'bg-indigo-600 text-white font-semibold'
                                  : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
                              }`}
                            >
                              월 / 수 / 금
                            </button>
                            {isCrypto && (
                              <button
                                type="button"
                                onClick={() => setForm({ ...form, dcaSchedule: '토,일' })}
                                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                                  form.dcaSchedule === '토,일' || form.dcaSchedule === '주말'
                                    ? 'bg-indigo-600 text-white font-semibold'
                                    : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
                                }`}
                              >
                                주말 (토·일)
                              </button>
                            )}
                          </div>

                          {/* 개별 요일 토글 버튼 그룹 */}
                          <div className="flex items-center gap-1.5 pt-1">
                            {(isCrypto
                              ? ['월', '화', '수', '목', '금', '토', '일']
                              : ['월', '화', '수', '목', '금']
                            ).map((day) => {
                              const sched = form.dcaSchedule.trim()
                              const isAll = sched === '매일' || sched === '월~일'
                              const isWeekdays = sched === '평일' || sched === '월~금'
                              const isWeekend = sched === '주말' || sched === '토,일' || sched === '토~일'
                              const isSelected =
                                isAll ||
                                (isWeekdays && ['월', '화', '수', '목', '금'].includes(day)) ||
                                (isWeekend && ['토', '일'].includes(day)) ||
                                sched.includes(day)

                              return (
                                <button
                                  key={day}
                                  type="button"
                                  onClick={() => {
                                    const allDays = isCrypto
                                      ? ['월', '화', '수', '목', '금', '토', '일']
                                      : ['월', '화', '수', '목', '금']
                                    let curSet = new Set<string>()
                                    if (isAll) {
                                      curSet = new Set(allDays)
                                    } else if (isWeekdays) {
                                      curSet = new Set(['월', '화', '수', '목', '금'])
                                    } else if (isWeekend) {
                                      curSet = new Set(['토', '일'])
                                    } else {
                                      for (const d of allDays) {
                                        if (sched.includes(d)) curSet.add(d)
                                      }
                                    }
                                    if (curSet.has(day)) {
                                      if (curSet.size > 1) curSet.delete(day)
                                    } else {
                                      curSet.add(day)
                                    }
                                    if (curSet.size === allDays.length) {
                                      setForm({ ...form, dcaSchedule: '매일' })
                                    } else if (!isCrypto && curSet.size === 5) {
                                      setForm({ ...form, dcaSchedule: '평일' })
                                    } else {
                                      const sorted = allDays.filter((d) => curSet.has(d))
                                      setForm({ ...form, dcaSchedule: sorted.join(',') })
                                    }
                                  }}
                                  className={`flex-1 rounded-lg py-1.5 text-center text-xs font-semibold transition-all ${
                                    isSelected
                                      ? 'bg-indigo-600 text-white shadow-xs'
                                      : 'border border-slate-200 bg-white text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400'
                                  }`}
                                >
                                  {day}
                                </button>
                              )
                            })}
                          </div>

                          {/* 실행 시각 */}
                          <div className="pt-1">
                            <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                              <span>실행 시각 (KST)</span>
                              <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                                필수
                              </span>
                            </label>
                            <div className="mt-1">
                              <TimePickerInput
                                aria-label="실행 시각"
                                placeholder="15:10"
                                value={form.dcaExecTime}
                                onChange={(val) => setForm({ ...form, dcaExecTime: val })}
                                required
                                presetCategory="buy"
                                showTabSelector={true}
                              />
                            </div>
                          </div>
                        </div>

                        {/* 1회 주문 기준 및 금액 */}
                        <div className="rounded-xl border border-slate-200 bg-white p-3.5 space-y-3 dark:border-slate-700 dark:bg-slate-800/40">
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">1회 주문 기준</label>
                              <select
                                value={form.dcaAmountType}
                                onChange={(e) => setForm({ ...form, dcaAmountType: e.target.value as 'budget' | 'volume' })}
                                className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              >
                                <option value="budget">예산 (금액, KRW)</option>
                                <option value="volume">수량 (개/주)</option>
                              </select>
                            </div>
                            <div>
                              <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                                <span>{form.dcaAmountType === 'volume' ? '1회 주문 수량 (개/주)' : '1회 주문 예산 (KRW)'}</span>
                                <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                                  필수
                                </span>
                              </label>
                              <input
                                type="text"
                                inputMode={form.dcaAmountType === 'volume' ? 'decimal' : 'numeric'}
                                aria-label={form.dcaAmountType === 'volume' ? '1회 주문 수량' : '1회 주문 예산'}
                                value={form.dcaAmountType === 'volume' ? form.budget : formatWithCommas(form.budget)}
                                onChange={(e) => {
                                  const val = e.target.value
                                  setForm({ ...form, budget: form.dcaAmountType === 'volume' ? val : stripCommas(val) })
                                }}
                                className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white font-medium"
                                required
                              />
                            </div>
                          </div>

                          {form.dcaAmountType === 'budget' && (
                            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                              <span className="text-[11px] font-medium text-slate-400">빠른 금액:</span>
                              {[
                                { label: '+5만', val: 50000 },
                                { label: '+10만', val: 100000 },
                                { label: '+30만', val: 300000 },
                                { label: '+50만', val: 500000 },
                                { label: '+100만', val: 1000000 },
                              ].map((chip) => (
                                <button
                                  key={chip.label}
                                  type="button"
                                  onClick={() => {
                                    const cur = parseFloat(stripCommas(form.budget)) || 0
                                    setForm({ ...form, budget: String(cur + chip.val) })
                                  }}
                                  className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 transition-colors"
                                >
                                  {chip.label}
                                </button>
                              ))}
                              {form.budget && !Number.isNaN(parseFloat(stripCommas(form.budget))) && (
                                <span className="ml-auto text-[11px] font-semibold text-indigo-600 dark:text-indigo-400">
                                  ≈ {krwFmt(parseFloat(stripCommas(form.budget)))}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                              <span>{isSellGridForm ? '총 매도 수량 (개/주)' : '투자 예산 (KRW)'}</span>
                              <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                                필수
                              </span>
                            </label>
                            <input
                              type="text"
                              inputMode={isSellGridForm ? 'decimal' : 'numeric'}
                              aria-label={isSellGridForm ? '총 매도 수량' : '투자 예산'}
                              value={isSellGridForm ? form.budget : formatWithCommas(form.budget)}
                              onChange={(e) => {
                                const val = e.target.value
                                setForm({ ...form, budget: isSellGridForm ? val : stripCommas(val) })
                              }}
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              required
                            />
                            {!isSellGridForm && form.budget && !Number.isNaN(parseFloat(stripCommas(form.budget))) && (
                              <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400 font-medium">
                                ≈ {krwFmt(parseFloat(stripCommas(form.budget)))}
                              </p>
                            )}
                          </div>
                          <div>
                            <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                              <span>분할 주문 수</span>
                              <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                                필수
                              </span>
                            </label>
                            <input
                              type="number"
                              min="1"
                              max="50"
                              value={form.count}
                              onChange={(e) => setForm({ ...form, count: e.target.value })}
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              required
                            />
                          </div>
                        </div>

                        {(form.strategyType === 'grid' || form.strategyType === 'sgrid') && (
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                                <span>{isSellGridForm ? '시작 가격 (최저 매도가)' : '시작 가격 (최저 매수가)'}</span>
                                <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                                  필수
                                </span>
                              </label>
                              <input
                                type="text"
                                inputMode="numeric"
                                aria-label="시작 가격"
                                placeholder={isSellGridForm ? '최저 매도가' : '최저 매수가'}
                                value={formatWithCommas(form.startPrice)}
                                onChange={(e) => setForm({ ...form, startPrice: stripCommas(e.target.value) })}
                                className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                                required
                              />
                            </div>
                            <div>
                              <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300">
                                <span>{isSellGridForm ? '종료 가격 (최고 매도가)' : '종료 가격 (최고 매수가)'}</span>
                                <span className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
                                  필수
                                </span>
                              </label>
                              <input
                                type="text"
                                inputMode="numeric"
                                aria-label="종료 가격"
                                placeholder={isSellGridForm ? '최고 매도가' : '최고 매수가'}
                                value={formatWithCommas(form.endPrice)}
                                onChange={(e) => setForm({ ...form, endPrice: stripCommas(e.target.value) })}
                                className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                                required
                              />
                            </div>
                          </div>
                        )}

                        {(form.strategyType === 'rsitrade' || form.strategyType === 'rsi') && (
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">매수 RSI 범위</label>
                              <input
                                type="text"
                                placeholder="25-30"
                                value={form.buyRsiRange}
                                onChange={(e) => setForm({ ...form, buyRsiRange: e.target.value })}
                                className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              />
                            </div>
                            <div>
                              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">매도 RSI 범위</label>
                              <input
                                type="text"
                                placeholder="65-75"
                                value={form.sellRsiRange}
                                onChange={(e) => setForm({ ...form, sellRsiRange: e.target.value })}
                                className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              />
                            </div>
                          </div>
                        )}
                      </>
                    )}

                    <div className="flex items-start gap-2.5 rounded-xl border border-emerald-100 bg-emerald-50/60 p-3.5 text-xs dark:border-emerald-900/40 dark:bg-emerald-950/20">
                      <ShieldCheck size={16} className="shrink-0 mt-0.5 text-emerald-600 dark:text-emerald-400" />
                      <div>
                        <span className="font-semibold text-emerald-900 dark:text-emerald-200">
                          ⚡ 초보자 안심 퀵 스타트
                        </span>
                        <p className="mt-0.5 text-[11px] text-slate-600 dark:text-slate-300">
                          세부 옵션을 설정하지 않고 <strong>[⚡ 기본 세팅으로 바로 저장]</strong>을 누르면,
                          시장가 체결과 휴장일 자동 이월 등 검증된 최적 안전 규칙으로 즉시 실행됩니다.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Step 2: 세부 옵션 & 안전 설정 (선택 사항 — 기본값 제공) */}
                {singleStep === 2 && (
                  <div className="space-y-4">
                    <div className="rounded-xl border border-emerald-100 bg-emerald-50/70 p-3.5 text-xs dark:border-emerald-900/40 dark:bg-emerald-950/30">
                      <div className="flex items-start gap-2.5">
                        <ShieldCheck size={16} className="text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
                        <div>
                          <p className="font-semibold text-emerald-800 dark:text-emerald-200">
                            기본 권장 세팅이 적용되어 있습니다
                          </p>
                          <p className="mt-0.5 text-[11px] text-slate-600 dark:text-slate-300">
                            특별한 조건(호가 지정가, 특정 이월 정책, 예산 원장 한도 등)을 맞춤 변경하고 싶을 때만 아래 옵션을 조정하세요. 그대로 저장해도 안전하게 동작합니다.
                          </p>
                        </div>
                      </div>
                    </div>

                    {isDcaForm ? (
                      <>
                        {/* 주문 가격 방식 & 이월 처리 */}
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <div className="flex items-center justify-between">
                              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">주문 가격 방식</label>
                              <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">선택</span>
                            </div>
                            <select
                              value={form.dcaOrderType}
                              onChange={(e) => setForm({ ...form, dcaOrderType: e.target.value as 'limit' | 'market' })}
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-medium dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                            >
                              <option value="market">⚡ 시장가 (권장: 미체결 없는 즉시 전량 체결)</option>
                              <option value="limit">🎯 지정가 (현재가 호가 버퍼 주문)</option>
                            </select>
                            <p className="mt-1 text-[10px] text-slate-400">
                              {form.dcaOrderType === 'market'
                                ? '호가 밀림 없이 즉시 체결되어 미체결 누락을 방지합니다.'
                                : '현재가 기준으로 지정가 주문을 발행합니다.'}
                            </p>
                          </div>
                          <div>
                            <div className="flex items-center justify-between">
                              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">휴장 / 사이드카 이월</label>
                              <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">선택</span>
                            </div>
                            <select
                              value={form.dcaCarryoverMode}
                              onChange={(e) => setForm({ ...form, dcaCarryoverMode: e.target.value as 'next_day' | 'delay_20m' | 'skip' })}
                              className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-medium dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                            >
                              <option value="next_day">📅 다음 거래일 이월 (공휴일/휴장일 권장)</option>
                              <option value="delay_20m">⏱️ +20분 뒤 재시도 (사이드카/서킷 대기)</option>
                              <option value="skip">⏭️ 이번 회차 건너뛰기 (다음 주기로)</option>
                            </select>
                            <p className="mt-1 text-[10px] text-slate-400">
                              휴장일이나 사이드카 발동 시 주문을 처리하는 안전 정책입니다.
                            </p>
                          </div>
                        </div>

                        {/* 총 횟수 제한 */}
                        <div>
                          <div className="flex items-center justify-between">
                            <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">총 횟수 제한 (0 = 무기한 계속 실행)</label>
                            <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">선택</span>
                          </div>
                          <input
                            type="number"
                            min="0"
                            value={form.count}
                            onChange={(e) => setForm({ ...form, count: e.target.value })}
                            className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                          />
                        </div>

                        {/* 통합 예산 플랜 설정 */}
                        {form.strategyType === 'dca' && (
                          <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-3.5 space-y-2.5 dark:border-slate-700 dark:bg-slate-800/40">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                                통합 예산 플랜 (예산 원장 연동)
                              </span>
                              <span className="rounded-sm bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-900/60 dark:text-indigo-300">
                                선택 사항
                              </span>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                              <div>
                                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">예산 운용 방식</label>
                                <select
                                  aria-label="DCA 예산 운용 방식"
                                  value={form.budgetMode}
                                  onChange={(e) => setForm({ ...form, budgetMode: e.target.value as 'total' | 'monthly' | 'daily' | 'unlimited' })}
                                  className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                                >
                                  <option value="unlimited">무한 예산 모드 (권장: 계좌 예수금으로 매수)</option>
                                  <option value="total">총예산 풀 차감 모드 (배정 예산 소진 시 정지)</option>
                                  <option value="monthly">월 예산 분할 충전 모드</option>
                                </select>
                              </div>
                              {form.budgetMode !== 'unlimited' ? (
                                <div>
                                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                                    {form.budgetMode === 'monthly' ? '월 배정 총예산 (KRW)' : '전략 배정 총예산 (KRW)'}
                                  </label>
                                  <input
                                    type="text"
                                    inputMode="numeric"
                                    aria-label="DCA 배정 총예산"
                                    value={formatWithCommas(form.dcaPlanBudget)}
                                    onChange={(e) => setForm({ ...form, dcaPlanBudget: stripCommas(e.target.value) })}
                                    className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                                  />
                                </div>
                              ) : (
                                <div className="flex items-center text-xs text-slate-400 pt-5">
                                  예산 풀 제한 없이 계좌 예수금 내에서 스케줄대로 매수합니다.
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </>
                    ) : (
                      <>
                        {(form.strategyType === 'rsitrade' || form.strategyType === 'rsi') && (
                          <div className="space-y-3">
                            <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={form.weighted}
                                onChange={(e) => setForm({ ...form, weighted: e.target.checked })}
                                className="rounded-sm border-slate-300 text-indigo-600 focus:ring-indigo-500"
                              />
                              <span>DCA 가중 매수 적용 (낮은 RSI 구간에 더 많은 예산 배정)</span>
                            </label>
                            <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-3 space-y-2 dark:border-indigo-900/40 dark:bg-indigo-950/20">
                              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                                익절 매도 대금 처리 방식
                              </label>
                              <select
                                aria-label="익절 매도 대금 처리 방식"
                                value={form.sellProceedsMode}
                                onChange={(e) =>
                                  setForm({
                                    ...form,
                                    sellProceedsMode: e.target.value as 'keep_cash' | 'recycle_to_budget',
                                  })
                                }
                                className="w-full rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                              >
                                <option value="recycle_to_budget">전략 가용 예산 풀에 자동 재투입 (순환매매 권장)</option>
                                <option value="keep_cash">예수금 보관 (가용 예산에 합산하지 않음)</option>
                              </select>
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          {/* 고정 모달 푸터 */}
          <div className="shrink-0 flex items-center justify-between border-t border-slate-100 bg-slate-50/50 px-6 py-3.5 dark:border-slate-800 dark:bg-slate-900/50">
            {isTopDcaForm ? (
              <>
                <div>
                  {topDcaStep > 1 ? (
                    <button
                      type="button"
                      onClick={() => {
                        setFormError(null)
                        setTopDcaStep((prev) => (prev - 1) as any)
                      }}
                      className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 transition-colors"
                    >
                      <ChevronLeft size={14} />
                      <span>이전 단계</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={saving || (topDcaStep === 4 && isTimeInvalid)}
                      onClick={onClose}
                      className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                    >
                      취소
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {topDcaStep < 4 ? (
                    <>
                      <button
                        key="top-dca-quick-btn"
                        type="button"
                        onClick={handleQuickDefaultSave}
                        className="flex items-center gap-1.5 rounded-xl border border-violet-200 bg-violet-50/70 px-3.5 py-2 text-xs font-semibold text-violet-700 hover:bg-violet-100 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-300 transition-colors shadow-xs"
                        title="3일 휩쏘 방지, 5일 분할매도 등 표준 안전 기본값으로 바로 완료합니다"
                      >
                        <ShieldCheck size={14} />
                        <span className="hidden sm:inline">⚡ 기본 세팅으로 바로 완료</span>
                        <span className="sm:hidden">기본값 완료</span>
                      </button>

                      <button
                        key="top-dca-next-btn"
                        type="button"
                        onClick={handleNextTopDcaStep}
                        className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-violet-700 transition-colors"
                      >
                        <span>다음 단계</span>
                        <ChevronRight size={14} />
                      </button>
                    </>
                  ) : (
                    <button
                      key="top-dca-submit-btn"
                      type="submit"
                      disabled={saving || isTimeInvalid}
                      className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-5 py-2 text-xs font-semibold text-white shadow-xs hover:bg-violet-700 disabled:opacity-50 transition-colors"
                    >
                      {saving && <Loader2 size={14} className="animate-spin" />}
                      <span>
                        {saving
                          ? '저장 중...'
                          : editingTemplate
                          ? '전략 수정 저장하기'
                          : '전략 저장하기'}
                      </span>
                    </button>
                  )}
                </div>
              </>
            ) : (
              <>
                <div>
                  {singleStep > 1 ? (
                    <button
                      type="button"
                      onClick={() => {
                        setFormError(null)
                        setSingleStep((prev) => (prev - 1) as any)
                      }}
                      className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700 transition-colors"
                    >
                      <ChevronLeft size={14} />
                      <span>이전 단계</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={saving}
                      onClick={onClose}
                      className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                    >
                      취소
                    </button>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {singleStep === 1 && (
                    <>
                      <button
                        type="button"
                        onClick={handleQuickDefaultSave}
                        className="flex items-center gap-1.5 rounded-xl border border-emerald-200 bg-emerald-50/80 px-3.5 py-2 text-xs font-semibold text-emerald-700 hover:bg-emerald-100 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300 transition-colors shadow-xs"
                        title="시장가 체결, 익일 이월 등 표준 안전 세팅으로 즉시 생성합니다"
                      >
                        <ShieldCheck size={14} />
                        <span className="hidden sm:inline">
                          {editingTemplate ? '수정 저장하기' : '⚡ 기본 세팅으로 저장하기'}
                        </span>
                        <span className="sm:hidden">
                          {editingTemplate ? '수정 저장' : '기본값 저장하기'}
                        </span>
                      </button>

                      <button
                        type="button"
                        onClick={handleSingleNextStep}
                        className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-indigo-700 transition-colors"
                      >
                        <span>세부 옵션 설정</span>
                        <ChevronRight size={14} />
                      </button>
                    </>
                  )}

                  {singleStep === 2 && (
                    <button
                      type="submit"
                      disabled={saving || (isDcaForm && isTimeInvalid)}
                      className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-5 py-2 text-xs font-semibold text-white shadow-xs hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                    >
                      {saving && <Loader2 size={14} className="animate-spin" />}
                      <span>
                        {saving
                          ? '저장 중...'
                          : editingTemplate
                          ? '전략 수정 저장하기'
                          : '전략 저장하기'}
                      </span>
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </form>
      </div>
    </div>,
    document.body,
  )
}
