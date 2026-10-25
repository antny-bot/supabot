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
}

function buildPayload(form: TemplateFormState) {
  const payload = {
    name: form.name.trim(),
    exchange: form.exchange,
    ticker: form.ticker.trim().toUpperCase(),
    start_price: 0,
    end_price: 0,
    count: parseInt(form.count, 10),
    budget: parseFloat(form.budget),
    strategy_type: form.strategyType,
    params: {} as {
      buy_rsi_range?: string
      sell_rsi_range?: string
      weighted?: boolean
    },
  }

  if (form.strategyType === 'grid' || form.strategyType === 'sgrid') {
    payload.start_price = parseFloat(form.startPrice)
    payload.end_price = parseFloat(form.endPrice)
  } else {
    payload.params = {
      buy_rsi_range: form.buyRsiRange.trim(),
      sell_rsi_range: form.sellRsiRange.trim(),
      weighted: form.weighted,
    }
  }

  return payload
}

function templateToForm(template: Template): TemplateFormState {
  const strategyType = template.strategy_type || 'grid'
  return {
    name: template.name,
    exchange: template.exchange,
    ticker: template.ticker,
    strategyType,
    startPrice: template.start_price ? String(template.start_price) : '',
    endPrice: template.end_price ? String(template.end_price) : '',
    count: String(template.count),
    budget: String(template.budget),
    buyRsiRange: template.params?.buy_rsi_range || '25-30',
    sellRsiRange: template.params?.sell_rsi_range || '65-75',
    weighted: Boolean(template.params?.weighted),
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
          {templates.map((tpl) => (
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
                    {tpl.strategy_type || 'GRID'}
                  </span>
                </div>

                {/* 템플릿 명칭 */}
                <h4 className="mt-2.5 text-base font-bold text-slate-800 dark:text-slate-100 truncate">
                  {tpl.name}
                </h4>

                {/* 파라미터 요약 그리드 */}
                <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-3 text-xs dark:bg-slate-800/50">
                  <div>
                    <span className="text-[11px] text-slate-400">설정 예산</span>
                    <p className="font-mono font-bold text-slate-800 dark:text-slate-200">
                      {krwFmt(tpl.budget)}
                    </p>
                  </div>
                  <div>
                    <span className="text-[11px] text-slate-400">분할 주문 수</span>
                    <p className="font-mono font-bold text-slate-800 dark:text-slate-200">
                      {tpl.count}분할
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
          ))}
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
                  placeholder="예: 비트코인 10분할 거미줄 매수"
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
                  onChange={(e) => setForm({ ...form, strategyType: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                >
                  <option value="grid">그리드 (Grid)</option>
                  <option value="sgrid">스마트 그리드 (Smart Grid)</option>
                  <option value="rsi">RSI 조건 분할 매매</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">투자 예산 (KRW)</label>
                  <input
                    type="number"
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

              {form.strategyType === 'grid' || form.strategyType === 'sgrid' ? (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">시작 가격</label>
                    <input
                      type="number"
                      placeholder="최저 매수가"
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
                      placeholder="최고 매도가"
                      value={form.endPrice}
                      onChange={(e) => setForm({ ...form, endPrice: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      required
                    />
                  </div>
                </div>
              ) : (
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
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">매도 RSI 범위</label>
                    <input
                      type="text"
                      placeholder="65-75"
                      value={form.sellRsiRange}
                      onChange={(e) => setForm({ ...form, sellRsiRange: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    />
                  </div>
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
              <strong>'{executingTemplate.name}'</strong> 설정으로 거래소에 즉시 분할 주문을 발주합니다.
            </p>
            <div className="mt-3 rounded-xl bg-slate-50 p-3 text-xs font-mono dark:bg-slate-800/60">
              <p>종목: {executingTemplate.ticker} ({executingTemplate.exchange.toUpperCase()})</p>
              <p>예산: {krwFmt(executingTemplate.budget)} ({executingTemplate.count}분할)</p>
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
                <span>{executing ? '주문 발주 중...' : '확인, 즉시 발주'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
