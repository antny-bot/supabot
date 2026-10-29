import { useEffect, useState, type FormEvent } from 'react'
import {
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
}

const STRATEGY_TYPE_LABELS: Record<string, string> = {
  grid: '거미줄 분할 매수 (/grid)',
  sgrid: '거미줄 분할 매도 (/sgrid)',
  rsitrade: 'RSI 순환 매매 (/rsitrade)',
  rsi: 'RSI 순환 매매 (/rsitrade)',
  dca: '정기 적립식 매수 (/dca)',
  sdca: '정기 분할 매도 (/sdca)',
}

const STRATEGY_BADGE_LABELS: Record<string, string> = {
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
  }

  return payload
}

function templateToForm(template: Template): TemplateFormState {
  const strategyType = normalizeStrategyType(template.strategy_type)
  return {
    name: template.name,
    exchange: template.exchange,
    ticker: template.ticker,
    strategyType,
    startPrice: template.start_price ? String(template.start_price) : '',
    endPrice: template.end_price ? String(template.end_price) : '',
    count: String(template.count ?? 0),
    budget: String(template.budget),
    buyRsiRange: template.params?.buy_rsi_range || '25-30',
    sellRsiRange: template.params?.sell_rsi_range || '65-75',
    weighted: Boolean(template.params?.weighted),
    dcaSchedule: template.params?.schedule || '매일',
    dcaExecTime: template.params?.exec_time || '09:05',
    dcaAmountType: template.params?.amount_type || (strategyType === 'sdca' ? 'volume' : 'budget'),
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

  // 실행 확인 모달
  const [executingTemplate, setExecutingTemplate] = useState<Template | null>(null)
  const [executing, setExecuting] = useState(false)

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

  useEffect(() => {
    loadTemplates()
  }, [])

  const handleOpenCreate = () => {
    setEditingId(null)
    setForm(DEFAULT_FORM)
    setFormError(null)
    setFormOpen(true)
  }

  const handleOpenEdit = (template: Template) => {
    setEditingId(template.id)
    setForm(templateToForm(template))
    setFormError(null)
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
    if (!form.ticker.trim()) {
      setFormError('종목 코드를 입력하세요.')
      return
    }

    setSaving(true)
    setFormError(null)
    try {
      const payload = buildPayload(form)
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
            const isVolumeBased = stype === 'sgrid' || (isDca && tpl.params?.amount_type === 'volume')

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
                        {stype === 'sgrid' ? '총 매도 수량' : isDca ? '1회 주문 규모' : '설정 예산'}
                      </span>
                      <p className="font-mono font-bold text-slate-800 dark:text-slate-200">
                        {isVolumeBased ? `${tpl.budget} (수량)` : krwFmt(tpl.budget)}
                      </p>
                    </div>
                    <div>
                      <span className="text-[11px] text-slate-400">
                        {isDca ? '반복 횟수' : '분할 주문 수'}
                      </span>
                      <p className="font-mono font-bold text-slate-800 dark:text-slate-200">
                        {isDca ? (tpl.count > 0 ? `총 ${tpl.count}회` : '무기한 반복') : `${tpl.count}분할`}
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
          <div className="relative z-10 w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800 max-h-[90vh] overflow-y-auto">
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
                  placeholder="예: 비트코인 매일 5만원 정기매수 / 10분할 거미줄 매수"
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
                    value={form.exchange}
                    onChange={(e) => setForm({ ...form, exchange: e.target.value })}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  >
                    <option value="upbit">Upbit</option>
                    <option value="bithumb">Bithumb</option>
                    <option value="kis">한국투자증권(KIS)</option>
                    <option value="toss">토스증권</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">종목 코드 (티커)</label>
                  <input
                    type="text"
                    placeholder="BTC / 005930"
                    value={form.ticker}
                    onChange={(e) => setForm({ ...form, ticker: e.target.value })}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs uppercase font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">전략 유형</label>
                <select
                  value={form.strategyType}
                  onChange={(e) => {
                    const nextType = e.target.value
                    setForm({
                      ...form,
                      strategyType: nextType,
                      count: (nextType === 'dca' || nextType === 'sdca') ? '0' : (form.count === '0' ? '10' : form.count),
                      dcaAmountType: nextType === 'sdca' ? 'volume' : form.dcaAmountType,
                    })
                  }}
                  className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                >
                  <option value="grid">거미줄 분할 매수 (/grid — 가격 범위 분할 매수)</option>
                  <option value="sgrid">거미줄 분할 매도 (/sgrid — 가격 범위 보유수량 분할 매도)</option>
                  <option value="rsitrade">RSI 조건 순환 매매 (/rsitrade — RSI 분할 매수 + 자동 익절 예약)</option>
                  <option value="dca">정기 적립식 매수 (/dca — 매일·특정요일·매주·매월 정기 매수)</option>
                  <option value="sdca">정기 분할 매도 (/sdca — 매일·특정요일·매주·매월 정기 매도)</option>
                </select>
              </div>

              {isDcaForm ? (
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
