import { useEffect, useState, type FormEvent } from 'react'
import { Copy, Loader2, Pencil, Play, Plus, Trash2, X } from 'lucide-react'
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
import PageHeader from '../components/ui/PageHeader'
import SectionCard from '../components/ui/SectionCard'
import { PAGE_META } from '../config/pageMeta'

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
    startPrice: strategyType === 'grid' || strategyType === 'sgrid' ? String(template.start_price) : '',
    endPrice: strategyType === 'grid' || strategyType === 'sgrid' ? String(template.end_price) : '',
    count: String(template.count),
    budget: String(template.budget),
    buyRsiRange: template.params?.buy_rsi_range || '25-30',
    sellRsiRange: template.params?.sell_rsi_range || '65-75',
    weighted: template.params?.weighted || false,
  }
}

export default function Templates() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<Template | null>(null)
  const [executeTargetTemplate, setExecuteTargetTemplate] = useState<Template | null>(null)
  const [form, setForm] = useState<TemplateFormState>(DEFAULT_FORM)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  useEffect(() => {
    void loadTemplates()
  }, [])

  async function loadTemplates() {
    try {
      setLoading(true)
      setTemplates(await fetchTemplates())
    } catch (caughtError) {
      if (caughtError instanceof ApiError) {
        setError(caughtError.message)
      } else {
        setError('템플릿을 불러오는 중 오류가 발생했습니다.')
      }
    } finally {
      setLoading(false)
    }
  }

  function resetForm() {
    setForm(DEFAULT_FORM)
    setEditingTemplate(null)
    setFormOpen(false)
  }

  function openCreateForm() {
    setError(null)
    setSuccessMessage(null)
    setEditingTemplate(null)
    setForm(DEFAULT_FORM)
    setFormOpen((current) => !current)
  }

  function openEditForm(template: Template) {
    setError(null)
    setSuccessMessage(null)
    setEditingTemplate(template)
    setForm(templateToForm(template))
    setFormOpen(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSuccessMessage(null)

    if (!form.name.trim()) {
      setError('템플릿 이름을 입력해 주세요.')
      return
    }

    setSubmitting(true)

    try {
      const payload = buildPayload(form)
      if (editingTemplate) {
        await updateTemplate(editingTemplate.id, payload)
        setSuccessMessage('템플릿이 수정되었습니다.')
      } else {
        await createTemplate(payload)
        setSuccessMessage('템플릿이 저장되었습니다.')
      }

      resetForm()
      await loadTemplates()
    } catch (caughtError) {
      if (caughtError instanceof ApiError) {
        setError(caughtError.message)
      } else {
        setError('템플릿을 저장하는 중 오류가 발생했습니다.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(templateId: number) {
    if (!confirm('정말로 이 템플릿을 삭제하시겠습니까?')) return

    setActionLoadingId(templateId)
    setError(null)
    setSuccessMessage(null)

    try {
      await deleteTemplate(templateId)
      setSuccessMessage('템플릿이 삭제되었습니다.')
      await loadTemplates()
    } catch (caughtError) {
      if (caughtError instanceof ApiError) {
        setError(caughtError.message)
      } else {
        setError('템플릿을 삭제하는 중 오류가 발생했습니다.')
      }
    } finally {
      setActionLoadingId(null)
    }
  }

  async function handleDuplicate(templateId: number) {
    setActionLoadingId(templateId)
    setError(null)
    setSuccessMessage(null)

    try {
      await duplicateTemplate(templateId)
      setSuccessMessage('템플릿이 복제되었습니다.')
      await loadTemplates()
    } catch (caughtError) {
      if (caughtError instanceof ApiError) {
        setError(caughtError.message)
      } else {
        setError('템플릿을 복제하는 중 오류가 발생했습니다.')
      }
    } finally {
      setActionLoadingId(null)
    }
  }

  async function confirmExecute() {
    if (!executeTargetTemplate) return

    setActionLoadingId(executeTargetTemplate.id)
    setError(null)
    setSuccessMessage(null)

    try {
      const result = await executeTemplate(executeTargetTemplate.id)
      setSuccessMessage(result.message || '전략 주문이 성공적으로 가동되었습니다.')
    } catch (caughtError) {
      if (caughtError instanceof ApiError) {
        setError(caughtError.message)
      } else {
        setError('템플릿을 실행하는 중 오류가 발생했습니다.')
      }
    } finally {
      setActionLoadingId(null)
      setExecuteTargetTemplate(null)
    }
  }

  const isGridStrategy = form.strategyType === 'grid' || form.strategyType === 'sgrid'

  return (
    <div className="mx-auto max-w-screen-xl space-y-6 px-4 pb-20">
      <PageHeader
        {...PAGE_META.templates}
        actions={(
          <button
            type="button"
            onClick={openCreateForm}
            className="flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-primary-700"
          >
            {formOpen && !editingTemplate ? <X size={14} /> : <Plus size={14} />}
            {formOpen && !editingTemplate ? '닫기' : '템플릿 생성'}
          </button>
        )}
      />

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-600 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-400">
          {error}
        </div>
      ) : null}

      {successMessage ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-600 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-400">
          {successMessage}
        </div>
      ) : null}

      {formOpen ? (
        <SectionCard
          title={editingTemplate ? '템플릿 수정' : '새 템플릿 생성'}
          subtitle="그리드와 RSI 전략 템플릿을 저장하고 재사용할 수 있습니다."
          contentClassName="p-4"
        >
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">템플릿 이름</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm((current) => ({ ...current, name: e.target.value }))}
                  placeholder="예: 비트코인 RSI 순환매"
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-900 focus:outline-none focus:ring-1 focus:ring-primary-500 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">거래소</label>
                  <select
                    value={form.exchange}
                    onChange={(e) => setForm((current) => ({ ...current, exchange: e.target.value }))}
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  >
                    <option value="upbit">Upbit</option>
                    <option value="bithumb">Bithumb</option>
                    <option value="kis">한국투자증권 (KIS)</option>
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">종목</label>
                  <input
                    type="text"
                    value={form.ticker}
                    onChange={(e) => setForm((current) => ({ ...current, ticker: e.target.value }))}
                    placeholder="BTC"
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    required
                  />
                </div>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">전략 유형</label>
              <select
                value={form.strategyType}
                onChange={(e) => setForm((current) => ({ ...current, strategyType: e.target.value }))}
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              >
                <option value="grid">Grid</option>
                <option value="sgrid">Smart Grid</option>
                <option value="rsitrade">RSI Trade</option>
              </select>
            </div>

            {isGridStrategy ? (
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">시작 가격</label>
                  <input
                    type="number"
                    value={form.startPrice}
                    onChange={(e) => setForm((current) => ({ ...current, startPrice: e.target.value }))}
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">종료 가격</label>
                  <input
                    type="number"
                    value={form.endPrice}
                    onChange={(e) => setForm((current) => ({ ...current, endPrice: e.target.value }))}
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                    required
                  />
                </div>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">매수 RSI 구간</label>
                  <input
                    type="text"
                    value={form.buyRsiRange}
                    onChange={(e) => setForm((current) => ({ ...current, buyRsiRange: e.target.value }))}
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">매도 RSI 구간</label>
                  <input
                    type="text"
                    value={form.sellRsiRange}
                    onChange={(e) => setForm((current) => ({ ...current, sellRsiRange: e.target.value }))}
                    className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  />
                </div>
                <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
                  <input
                    type="checkbox"
                    checked={form.weighted}
                    onChange={(e) => setForm((current) => ({ ...current, weighted: e.target.checked }))}
                  />
                  가중 매수 사용
                </label>
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">주문 개수</label>
                <input
                  type="number"
                  value={form.count}
                  onChange={(e) => setForm((current) => ({ ...current, count: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  required
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">예산</label>
                <input
                  type="number"
                  value={form.budget}
                  onChange={(e) => setForm((current) => ({ ...current, budget: e.target.value }))}
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                  required
                />
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={submitting}
                className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-primary-700 disabled:opacity-60"
              >
                {submitting ? <Loader2 size={14} className="animate-spin" /> : null}
                {editingTemplate ? '수정 저장' : '템플릿 저장'}
              </button>
              <button
                type="button"
                onClick={resetForm}
                className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                취소
              </button>
            </div>
          </form>
        </SectionCard>
      ) : null}

      <SectionCard
        title="저장된 템플릿"
        subtitle="자주 쓰는 전략 설정을 저장하고 재실행할 수 있습니다."
        contentClassName="p-4"
      >
        {loading ? (
          <div className="flex justify-center py-10">
            <Loader2 size={18} className="animate-spin text-primary-600" />
          </div>
        ) : templates.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
            저장된 템플릿이 없습니다.
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {templates.map((template) => (
              <article
                key={template.id}
                className="rounded-xl border border-slate-200 p-4 shadow-sm transition-colors hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/40"
              >
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{template.name}</h3>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      {template.exchange.toUpperCase()} · {template.ticker}
                    </p>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {template.strategy_type || 'grid'}
                  </span>
                </div>

                <dl className="space-y-1 text-xs text-slate-600 dark:text-slate-300">
                  <div className="flex justify-between gap-3">
                    <dt>주문 수</dt>
                    <dd>{template.count}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt>예산</dt>
                    <dd>{template.budget.toLocaleString()}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt>가격 범위</dt>
                    <dd>
                      {template.start_price} ~ {template.end_price}
                    </dd>
                  </div>
                </dl>

                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setExecuteTargetTemplate(template)}
                    disabled={actionLoadingId === template.id}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-primary-700 disabled:opacity-60"
                  >
                    <Play size={14} />
                    실행
                  </button>
                  <button
                    type="button"
                    onClick={() => openEditForm(template)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    <Pencil size={14} />
                    수정
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDuplicate(template.id)}
                    disabled={actionLoadingId === template.id}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    <Copy size={14} />
                    복제
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(template.id)}
                    disabled={actionLoadingId === template.id}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 px-3 py-1.5 text-xs font-semibold text-rose-600 transition-colors hover:bg-rose-50 dark:border-rose-900/40 dark:text-rose-400 dark:hover:bg-rose-950/20"
                  >
                    <Trash2 size={14} />
                    삭제
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </SectionCard>

      {executeTargetTemplate ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-800 dark:bg-slate-900">
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">템플릿 실행 확인</h2>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              <span className="font-semibold text-slate-700 dark:text-slate-200">{executeTargetTemplate.name}</span>
              {' '}템플릿으로 전략 주문을 실행하시겠습니까?
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setExecuteTargetTemplate(null)}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                취소
              </button>
              <button
                type="button"
                onClick={() => void confirmExecute()}
                className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary-700"
              >
                실행
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
