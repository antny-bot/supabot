import { useEffect, useState, useCallback, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
  Activity,
  DollarSign,
  Play,
  RotateCw,
  Plus,
  ShieldAlert,
  AlertTriangle,
  X,
  Loader2,
  Pencil,
  Copy,
  Archive,
  RotateCcw,
  Trash2,
  Layers,
  ArrowLeft,
  ExternalLink,
  ChevronRight,
} from 'lucide-react'
import {
  fetchTemplates,
  toggleTemplateHolding,
  executeTemplate,
  stopTemplate,
  manualTopupTemplate,
  archiveTemplate,
  restoreTemplate,
  deleteTemplate,
  duplicateTemplate,
  type Template,
} from '../api/templates'
import Badge from '../components/ui/Badge'
import PageHeader from '../components/ui/PageHeader'
import SegmentedControl from '../components/ui/SegmentedControl'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'
import TopRotationSection from './reports/TopRotationSection'
import DailySnapshotSection from './reports/DailySnapshotSection'
import SingleStrategySection from './reports/SingleStrategySection'
import BudgetPlanSection from './reports/BudgetPlanSection'
import BatchTimelineSection from './reports/BatchTimelineSection'
import ResponsiveTabs from '../components/ui/ResponsiveTabs'
import FormattedNumberInput from '../components/ui/FormattedNumberInput'
import StrategyFormModal from '../components/strategy/StrategyFormModal'
import { STRATEGY_BADGE_LABELS, hasDcaBudget } from '../components/strategy/strategyTypes'
import { useToast } from '../contexts/ToastContext'
import { krwFmt } from '../utils/formatters'
import { usePersistedState } from '../hooks/usePersistedState'
import type { DateRangeValue } from '../components/ui/DateRangePicker'

const OPERATIONS_EXCHANGE_FILTER_KEY = 'sbm_operations_exchange_filter'
const OPERATIONS_STATUS_FILTER_KEY = 'sbm_operations_status_filter'

function isTemplateActive(tpl: Template): boolean {
  const p = (tpl.params || {}) as any
  return (
    p.strategy_status === 'active' ||
    (p.strategy_status === undefined && p.schedule_enabled !== false)
  )
}

const DEFAULT_TIMELINE_RANGE: DateRangeValue = { mode: '30d', from: '', to: '' }

export default function Operations() {
  const toast = useToast()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const viewParam = searchParams.get('view')
  const tabParam = searchParams.get('tab')
  const templateIdParam = searchParams.get('template_id')

  // 기존 중복 '전략 배치 주문 묶음(batches)' 탭 접근 시 주문 관리 > 전략 배치 묶음으로 일원화 리다이렉트
  useEffect(() => {
    if (tabParam === 'batches') {
      const nextParams = new URLSearchParams()
      nextParams.set('tab', 'batches')
      if (templateIdParam) nextParams.set('template_id', templateIdParam)
      navigate(`/orders?${nextParams.toString()}`, { replace: true })
    }
  }, [tabParam, templateIdParam, navigate])

  const [viewMode, setViewMode] = useState<'management' | 'workbench'>(() => {
    if (viewParam === 'workbench' || tabParam === 'snapshot' || tabParam === 'ledger' || tabParam === 'timeline') {
      return 'workbench'
    }
    return 'management'
  })

  // 전략 관리 탭 내 서브필터: 'active' (운용 중) | 'archived' (보관함)
  const [subFilter, setSubFilter] = useState<'active' | 'archived'>('active')

  // 운용 전략 필터 (거래소 다운콤보, 모두|On|Off) - localStorage에 조건 기억
  const [exchangeFilter, setExchangeFilter] = usePersistedState<string>(
    OPERATIONS_EXCHANGE_FILTER_KEY,
    'all',
  )
  const [statusFilter, setStatusFilter] = usePersistedState<'all' | 'on' | 'off'>(
    OPERATIONS_STATUS_FILTER_KEY,
    'all',
  )

  const [activeTab, setActiveTab] = useState(() => {
    return tabParam && ['rotation', 'snapshot', 'ledger', 'timeline'].includes(tabParam)
      ? tabParam
      : 'rotation'
  })

  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(
    templateIdParam ? Number(templateIdParam) : null,
  )
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [togglingId, setTogglingId] = useState<number | null>(null)
  const [executingId, setExecutingId] = useState<number | null>(null)

  // ── 전략 생성/수정 모달 상태 ───────────────────────────────────────────
  const [modalState, setModalState] = useState<{
    isOpen: boolean
    type: 'single' | 'multi'
    editingTemplate: Template | null
  }>({
    isOpen: false,
    type: 'single',
    editingTemplate: null,
  })

  // ── 수동 예산 충전(Top-up) 모달 상태 ──────────────────────────────────────────
  const [topupTargetTpl, setTopupTargetTpl] = useState<Template | null>(null)
  const [topupAmount, setTopupAmount] = useState<number>(300000)
  const [topupMemo, setTopupMemo] = useState<string>('')
  const [topupLoading, setTopupLoading] = useState(false)

  // ── 3단계 정지/청산 제어 모달 상태 ───────────────────────────────────────────
  const [stopTargetTpl, setStopTargetTpl] = useState<Template | null>(null)
  const [stopMode, setStopMode] = useState<'pause' | 'stop_and_cancel' | 'terminate_and_liquidate'>('pause')
  const [liquidateConfirmText, setLiquidateConfirmText] = useState('')
  const [stopLoading, setStopLoading] = useState(false)

  const loadTemplates = useCallback(async () => {
    try {
      setLoading(true)
      const list = await fetchTemplates()
      setTemplates(list)
      if (!selectedTemplateId && list.length > 0) {
        const defaultTpl = list.find((t) => t.strategy_type === 'kospi_top_dca') || list[0]
        setSelectedTemplateId(defaultTpl.id)
      }
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '전략 목록 로드 실패')
    } finally {
      setLoading(false)
    }
  }, [selectedTemplateId])

  useEffect(() => {
    loadTemplates()
  }, [loadTemplates])

  // URL 파라미터 동기화
  useEffect(() => {
    if (tabParam === 'batches') return
    const params = new URLSearchParams(searchParams)
    let changed = false
    if (viewMode && params.get('view') !== viewMode) {
      params.set('view', viewMode)
      changed = true
    }
    if (activeTab && params.get('tab') !== activeTab) {
      params.set('tab', activeTab)
      changed = true
    }
    if (selectedTemplateId && params.get('template_id') !== String(selectedTemplateId)) {
      params.set('template_id', String(selectedTemplateId))
      changed = true
    }
    if (changed) {
      setSearchParams(params, { replace: true })
    }
  }, [viewMode, activeTab, selectedTemplateId, tabParam, searchParams, setSearchParams])

  const activeTemplates = useMemo(
    () => templates.filter((t) => !(t.params as any)?.is_archived),
    [templates],
  )
  const archivedTemplates = useMemo(
    () => templates.filter((t) => (t.params as any)?.is_archived === true),
    [templates],
  )
  const exchangeOptions = useMemo(() => {
    const baseExchanges = [
      { value: 'all', label: '전체 거래소' },
      { value: 'upbit', label: 'Upbit' },
      { value: 'bithumb', label: 'Bithumb' },
      { value: 'kis', label: 'KIS' },
      { value: 'toss', label: 'TOSS' },
    ]
    const known = new Set(baseExchanges.map((o) => o.value.toLowerCase()))
    const extraExchanges: { value: string; label: string }[] = []
    templates.forEach((t) => {
      const ex = (t.exchange || '').toLowerCase().trim()
      if (ex && !known.has(ex)) {
        known.add(ex)
        extraExchanges.push({ value: ex, label: ex.toUpperCase() })
      }
    })
    return [...baseExchanges, ...extraExchanges]
  }, [templates])

  const filteredActiveTemplates = useMemo(() => {
    return activeTemplates.filter((tpl) => {
      if (exchangeFilter && exchangeFilter !== 'all') {
        if ((tpl.exchange || '').toLowerCase() !== exchangeFilter.toLowerCase()) {
          return false
        }
      }
      const active = isTemplateActive(tpl)
      if (statusFilter === 'on' && !active) return false
      if (statusFilter === 'off' && active) return false
      return true
    })
  }, [activeTemplates, exchangeFilter, statusFilter])

  const displayedTemplates = subFilter === 'active' ? filteredActiveTemplates : archivedTemplates
  const isFiltered = exchangeFilter !== 'all' || statusFilter !== 'all'

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId)
  const isTopDca =
    selectedTemplate?.strategy_type === 'kospi_top_dca' ||
    selectedTemplate?.params?.universe_type === 'market_top_n' ||
    selectedTemplate?.params?.progression_mode === 'top_n_rotation' ||
    selectedTemplate?.params?.progression_mode === 'batch_all' ||
    selectedTemplate?.ticker === 'TOP10' ||
    selectedTemplate?.ticker === 'TOP_N'

  // 단일 전략으로 전환 시 스냅샷 탭에 있었다면 기본 탭(rotation)으로 복귀
  useEffect(() => {
    if (selectedTemplate && !isTopDca && activeTab === 'snapshot') {
      setActiveTab('rotation')
    }
  }, [selectedTemplate, isTopDca, activeTab])

  const workbenchTabs = useMemo(() => {
    if (isTopDca) {
      return [
        { id: 'rotation', label: '운용 현황' },
        { id: 'snapshot', label: '일단위 스냅샷 (차트)' },
        { id: 'ledger', label: '예산 · 감사원장' },
        { id: 'timeline', label: '체결 타임라인' },
      ]
    }
    return [
      { id: 'rotation', label: '운용 현황' },
      { id: 'ledger', label: '예산 · 감사원장' },
      { id: 'timeline', label: '체결 타임라인' },
    ]
  }, [isTopDca])

  // 전략 가동 ON/OFF 토글 핸들러
  const handleToggleHolding = async (tpl: Template, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    const currentActive = isTemplateActive(tpl)
    const nextHolding = currentActive

    setTogglingId(tpl.id)
    try {
      const res = await toggleTemplateHolding(tpl.id, nextHolding)
      if (res.ok) {
        toast.success(
          `전략 #${tpl.id} [${tpl.name}]가 ${!nextHolding ? '가동(ON)' : '일시정지(OFF)'} 상태로 변경되었습니다.`,
        )
        setTemplates((prev) =>
          prev.map((item) =>
            item.id === tpl.id
              ? {
                  ...item,
                  params: {
                    ...item.params,
                    strategy_status: !nextHolding ? 'active' : 'paused',
                    schedule_enabled: !nextHolding,
                  },
                }
              : item,
          ),
        )
      } else {
        toast.error('전략 상태 변경에 실패했습니다.')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '전략 상태 변경 중 오류가 발생했습니다.')
    } finally {
      setTogglingId(null)
    }
  }

  // 1회 즉시 실행 핸들러
  const handleExecuteNow = async (tpl: Template, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    if (!confirm(`전략 #${tpl.id} [${tpl.name}]를 지금 1회 즉시 실행하시겠습니까?`)) {
      return
    }

    setExecutingId(tpl.id)
    try {
      const res = await executeTemplate(tpl.id)
      if (res && !res.error) {
        toast.success(res.message || '전략 배치가 성공적으로 실행되었습니다.')
        loadTemplates()
      } else {
        toast.error(res?.error || '실행에 실패했습니다.')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '실행 중 오류가 발생했습니다.')
    } finally {
      setExecutingId(null)
    }
  }

  // 전략 복제 핸들러
  const handleDuplicate = async (tpl: Template, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    try {
      await duplicateTemplate(tpl.id)
      toast.success(`'${tpl.name}' 전략이 복제되었습니다.`)
      loadTemplates()
    } catch (err) {
      toast.error('복제 실패: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  // 전략 보관함 이동 핸들러
  const handleArchive = async (tpl: Template, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    const isActive = isTemplateActive(tpl)

    if (isActive) {
      toast.error('실행 중(Active)인 전략은 보관할 수 없습니다. 전략을 먼저 OFF로 일시정지해주세요.')
      return
    }

    if (
      !confirm(
        `'${tpl.name}' 전략을 보관함으로 이동하시겠습니까?\n보관된 전략은 자동 실행이 중지되며 언제든 복원하거나 삭제할 수 있습니다.`,
      )
    ) {
      return
    }

    try {
      await archiveTemplate(tpl.id)
      toast.success('전략이 보관함으로 이동되었습니다.')
      loadTemplates()
    } catch (err) {
      toast.error('보관 실패: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  // 보관함에서 복원 핸들러
  const handleRestore = async (tpl: Template, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    try {
      await restoreTemplate(tpl.id)
      toast.success(`'${tpl.name}' 전략이 운용 목록으로 복원되었습니다.`)
      loadTemplates()
    } catch (err) {
      toast.error('복원 실패: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  // 보관함 전략 영구 삭제 핸들러
  const handleDelete = async (tpl: Template, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    const p = (tpl.params || {}) as any
    if (!p.is_archived) {
      toast.error('일반 운용 상태의 전략은 즉시 삭제할 수 없습니다. 먼저 보관함으로 이동해주세요.')
      return
    }

    if (
      !confirm(
        `'${tpl.name}' 전략을 영구 삭제하시겠습니까?\n이 작업은 되돌릴 수 없으며, 모든 설정이 완전히 삭제됩니다.`,
      )
    ) {
      return
    }

    try {
      await deleteTemplate(tpl.id)
      toast.success('전략이 영구 삭제되었습니다.')
      loadTemplates()
    } catch (err) {
      toast.error('삭제 실패: ' + (err instanceof Error ? err.message : String(err)))
    }
  }

  // 예산 수동 충전 핸들러
  const handleTopupSubmit = async () => {
    if (!topupTargetTpl) return
    if (topupAmount <= 0) {
      toast.error('충전 금액은 0원보다 커야 합니다.')
      return
    }

    setTopupLoading(true)
    try {
      const res = await manualTopupTemplate(topupTargetTpl.id, topupAmount, topupMemo)
      if (res.ok) {
        toast.success(
          `전략 #${topupTargetTpl.id}에 ${krwFmt(topupAmount)}이(가) 즉시 충전되었습니다. (감사원장에 반영됨)`,
        )
        setTopupTargetTpl(null)
        loadTemplates()
      } else {
        toast.error(res.error || '충전에 실패했습니다.')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '충전 처리 중 오류가 발생했습니다.')
    } finally {
      setTopupLoading(false)
    }
  }

  // 전략 3단계 정지/청산 제어 실행 핸들러
  const handleStopSubmit = async () => {
    if (!stopTargetTpl) return
    if (stopMode === 'terminate_and_liquidate' && liquidateConfirmText.trim() !== '전량청산') {
      toast.error('청산 실행을 위해 확인 문구 "전량청산"을 정확히 입력해주세요.')
      return
    }

    setStopLoading(true)
    try {
      const res = await stopTemplate(stopTargetTpl.id, stopMode)
      if (res.ok) {
        if (stopMode === 'pause') {
          toast.success(`전략 #${stopTargetTpl.id}이(가) 일시정지되었습니다.`)
        } else if (stopMode === 'stop_and_cancel') {
          toast.warning(
            `전략 #${stopTargetTpl.id} 중지 완료: 미체결 주문 ${res.data?.cancelled_orders ?? 0}건이 거래소에서 일괄 취소되었습니다.`,
          )
        } else {
          toast.error(
            `전략 #${stopTargetTpl.id} 청산 발주 완료: 모든 미체결 취소 및 보유 주식 현재가 청산 주문이 접수되었습니다.`,
          )
        }
        setStopTargetTpl(null)
        setLiquidateConfirmText('')
        loadTemplates()
      } else {
        toast.error(res.error || '정지 처리에 실패했습니다.')
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '제어 명령 실행 중 오류가 발생했습니다.')
    } finally {
      setStopLoading(false)
    }
  }

  const openStrategyDetail = (tplId: number, initialTab = 'rotation') => {
    setSelectedTemplateId(tplId)
    setActiveTab(initialTab)
    setViewMode('workbench')
  }

  return (
    <div className="space-y-5 pb-12 break-keep animate-fade-in-up">
      {/* 최상단 페이지 헤더 */}
      <PageHeader
        title={viewMode === 'workbench' ? '전략 상세 관제' : '전략 운용'}
        Icon={Activity}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => loadTemplates()}
              className="flex items-center gap-1.5 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
            >
              <RotateCw size={13} className={loading ? 'animate-spin' : ''} />
              <span>새로고침</span>
            </button>
            <button
              onClick={() =>
                setModalState({ isOpen: true, type: 'single', editingTemplate: null })
              }
              className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-indigo-700 transition-colors"
            >
              <Plus size={14} />
              <span>단일 종목 전략</span>
            </button>
            <button
              onClick={() =>
                setModalState({ isOpen: true, type: 'multi', editingTemplate: null })
              }
              className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-violet-700 transition-colors"
            >
              <Layers size={14} />
              <span>복수 종목 (TOP N) 전략</span>
            </button>
          </div>
        }
      />

      {error && <ErrorBanner message={error} />}

      {/* =========================================================================
          [1] 1차 화면: 전략 카드 목록 (단순·직관적인 카드 그리드, 클릭 시 상세 진입)
          ========================================================================= */}
      {viewMode === 'management' && (
        <div className="space-y-4">
          {/* 운용 중 vs 보관함 서브 탭 및 필터 바 */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 pb-2">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setSubFilter('active')}
                className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors ${
                  subFilter === 'active'
                    ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                    : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <span>운용 전략</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                    subFilter === 'active'
                      ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300'
                      : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                  }`}
                >
                  {isFiltered && subFilter === 'active'
                    ? `${filteredActiveTemplates.length}/${activeTemplates.length}`
                    : activeTemplates.length}
                </span>
              </button>
              <button
                type="button"
                onClick={() => setSubFilter('archived')}
                className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors ${
                  subFilter === 'archived'
                    ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                    : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                <Archive size={13} />
                <span>보관함</span>
                {archivedTemplates.length > 0 && (
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                      subFilter === 'archived'
                        ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300'
                        : 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300'
                    }`}
                  >
                    {archivedTemplates.length}
                  </span>
                )}
              </button>
            </div>

            {subFilter === 'active' ? (
              <div className="flex flex-wrap items-center gap-2">
                <select
                  value={exchangeFilter}
                  onChange={(e) => setExchangeFilter(e.target.value)}
                  className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 outline-none transition-colors hover:border-slate-300 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
                  aria-label="거래소 필터"
                >
                  {exchangeOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>

                <SegmentedControl
                  size="sm"
                  options={[
                    { id: 'all', label: '모두' },
                    { id: 'on', label: 'On' },
                    { id: 'off', label: 'Off' },
                  ]}
                  value={statusFilter}
                  onChange={(v) => setStatusFilter(v as 'all' | 'on' | 'off')}
                />

                {isFiltered && (
                  <button
                    type="button"
                    onClick={() => {
                      setExchangeFilter('all')
                      setStatusFilter('all')
                    }}
                    className="text-[11px] font-medium text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 underline underline-offset-2 ml-0.5 whitespace-nowrap break-keep"
                    title="필터 조건 초기화"
                  >
                    초기화
                  </button>
                )}
              </div>
            ) : (
              <div className="text-xs text-slate-400 hidden sm:block">
                보관된 전략은 자동 실행이 중지되며 언제든 복원하거나 삭제할 수 있습니다.
              </div>
            )}
          </div>

          {loading && displayedTemplates.length === 0 ? (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          ) : displayedTemplates.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 p-12 text-center dark:border-slate-800">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400">
                {subFilter === 'archived' ? <Archive size={24} /> : <Activity size={24} />}
              </div>
              <h3 className="mt-3 text-sm font-semibold text-slate-800 dark:text-slate-200">
                {subFilter === 'archived'
                  ? '보관된 전략이 없습니다.'
                  : isFiltered
                  ? '필터 조건에 일치하는 운용 전략이 없습니다.'
                  : '등록된 운용 전략이 없습니다.'}
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                {subFilter === 'archived'
                  ? '완료되었거나 사용하지 않는 전략을 보관함으로 이동해 보관하거나 영구 삭제할 수 있습니다.'
                  : isFiltered
                  ? '거래소 또는 On/Off 필터 조건을 변경하거나 초기화해 보세요.'
                  : '상단의 [단일 종목 전략] 또는 [복수 종목 전략]을 클릭하여 새로운 자동매매 전략을 등록하세요.'}
              </p>
              {subFilter === 'active' && isFiltered && (
                <div className="mt-4">
                  <button
                    type="button"
                    onClick={() => {
                      setExchangeFilter('all')
                      setStatusFilter('all')
                    }}
                    className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                  >
                    필터 초기화
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {displayedTemplates.map((tpl) => {
                const p = (tpl.params || {}) as any
                const isActive = isTemplateActive(tpl)
                const isDca = tpl.strategy_type === 'dca' || tpl.strategy_type === 'sdca'
                const isTop =
                  tpl.strategy_type === 'kospi_top_dca' ||
                  p.universe_type === 'market_top_n' ||
                  p.progression_mode === 'top_n_rotation' ||
                  p.progression_mode === 'batch_all' ||
                  tpl.ticker === 'TOP10' ||
                  tpl.ticker === 'TOP_N'
                const isVolume =
                  tpl.strategy_type === 'sgrid' ||
                  tpl.strategy_type === 'sdca' ||
                  (isDca && p.amount_type === 'volume')
                const dcaBudgetActive = hasDcaBudget(tpl)
                const isVolumeOnly =
                  tpl.strategy_type === 'sgrid' ||
                  tpl.strategy_type === 'sdca' ||
                  (isDca && p.amount_type === 'volume' && !dcaBudgetActive)
                const supportsCarryover = !isVolumeOnly

                return (
                  <div
                    key={tpl.id}
                    onClick={() => openStrategyDetail(tpl.id, 'rotation')}
                    className="group relative flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 shadow-xs transition-all cursor-pointer hover:border-indigo-400 hover:shadow-md dark:border-slate-800 dark:bg-slate-900 dark:hover:border-indigo-500/70"
                  >
                    <div>
                      {/* 상단: 거래소, 티커, 전략 유형 배지 & ON/OFF 토글 */}
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <Badge value={tpl.exchange} label={tpl.exchange.toUpperCase()} />
                          <span className="text-xs font-bold text-slate-600 dark:text-slate-300">
                            {tpl.ticker}
                          </span>
                          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                            {STRATEGY_BADGE_LABELS[tpl.strategy_type || 'grid'] ||
                              (tpl.strategy_type || 'GRID').toUpperCase()}
                          </span>
                          {subFilter === 'archived' && (
                            <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
                              보관됨
                            </span>
                          )}
                        </div>

                        {subFilter === 'active' && (
                          <div
                            className="flex items-center gap-1.5"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              type="button"
                              disabled={togglingId === tpl.id}
                              onClick={(e) => handleToggleHolding(tpl, e)}
                              className={`relative inline-flex h-5 w-10 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                                isActive ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'
                              } ${togglingId === tpl.id ? 'opacity-50' : ''}`}
                              title={
                                isActive
                                  ? '전략 가동중 (클릭 시 일시정지 OFF)'
                                  : '전략 일시정지 (클릭 시 가동 ON)'
                              }
                            >
                              <span
                                className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-xs ring-0 transition duration-200 ease-in-out ${
                                  isActive ? 'translate-x-5' : 'translate-x-0'
                                }`}
                              />
                            </button>
                            <span
                              className={`text-[10px] font-extrabold w-6 text-center ${
                                isActive
                                  ? 'text-emerald-600 dark:text-emerald-400'
                                  : 'text-slate-400'
                              }`}
                            >
                              {isActive ? 'ON' : 'OFF'}
                            </span>
                          </div>
                        )}
                      </div>

                      {/* 전략 명칭 */}
                      <div className="mt-2.5 flex items-center justify-between gap-2">
                        <h4 className="text-sm font-bold text-slate-900 dark:text-white truncate group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                          <span className="text-slate-400 font-semibold mr-1">#{tpl.id}</span>
                          {tpl.name}
                        </h4>
                        <ChevronRight
                          size={15}
                          className="shrink-0 text-slate-300 group-hover:text-indigo-500 transition-colors"
                        />
                      </div>

                      {/* 핵심 2대 수치만 심플하게 표시 */}
                      <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-slate-50 px-3 py-2 text-xs dark:bg-slate-800/50">
                        <div>
                          <span className="text-[10px] text-slate-400 block">
                            {isTop
                              ? '설정 총예산'
                              : isDca && p.amount_type === 'volume'
                              ? '정기 매수'
                              : isVolume
                              ? '설정 수량'
                              : '설정 예산'}
                          </span>
                          <span className="font-bold text-slate-800 dark:text-slate-200">
                            {isDca && p.amount_type === 'volume'
                              ? `${p.schedule || '매일'} ${tpl.budget}주`
                              : isVolume
                              ? `${tpl.budget}주`
                              : krwFmt(isTop ? (p.monthly_budget ?? tpl.budget) : tpl.budget)}
                          </span>
                        </div>
                        <div>
                          <div className="flex items-center justify-between text-[10px] text-slate-400">
                            <span>가용 예산</span>
                            {subFilter === 'active' && supportsCarryover && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setTopupTargetTpl(tpl)
                                  setTopupAmount(300000)
                                  setTopupMemo('가용 예산 보충')
                                }}
                                className="text-indigo-600 dark:text-indigo-400 font-bold hover:underline"
                                title="예산 즉시 수동 추가 충전"
                              >
                                +충전
                              </button>
                            )}
                          </div>
                          <span className="font-bold text-slate-800 dark:text-slate-200">
                            {supportsCarryover ? (
                              krwFmt(
                                p.carryover_budget ??
                                  (tpl.strategy_type === 'rsitrade' ||
                                  tpl.strategy_type === 'rsi' ||
                                  tpl.strategy_type === 'grid'
                                    ? tpl.budget
                                    : 0),
                              )
                            ) : (
                              <span className="text-slate-400 font-normal text-[11px]">—</span>
                            )}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* 하단 간결 액션 바 */}
                    <div
                      className="mt-3 flex items-center justify-between border-t border-slate-100 pt-2.5 dark:border-slate-800"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {subFilter === 'active' ? (
                        <>
                          <div className="flex items-center gap-0.5">
                            <button
                              type="button"
                              onClick={() =>
                                setModalState({
                                  isOpen: true,
                                  type: isTop ? 'multi' : 'single',
                                  editingTemplate: tpl,
                                })
                              }
                              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                              title="전략 설정 수정"
                            >
                              <Pencil size={13} />
                            </button>
                            <button
                              type="button"
                              onClick={(e) => handleDuplicate(tpl, e)}
                              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                              title="전략 복제"
                            >
                              <Copy size={13} />
                            </button>
                            <button
                              type="button"
                              disabled={isActive}
                              onClick={(e) => handleArchive(tpl, e)}
                              className={`rounded-lg p-1.5 transition-colors ${
                                isActive
                                  ? 'cursor-not-allowed opacity-30 text-slate-400'
                                  : 'text-slate-400 hover:bg-amber-50 hover:text-amber-600 dark:hover:bg-amber-950/40 dark:hover:text-amber-400'
                              }`}
                              title={
                                isActive
                                  ? '가동 중(ON)인 전략은 보관할 수 없습니다. 먼저 OFF로 일시정지하세요.'
                                  : '보관함으로 이동'
                              }
                            >
                              <Archive size={13} />
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setStopTargetTpl(tpl)
                                setStopMode('pause')
                                setLiquidateConfirmText('')
                              }}
                              className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/40 dark:hover:text-rose-400"
                              title="비상 제어 / 주문 취소 / 전량 청산"
                            >
                              <ShieldAlert size={13} />
                            </button>
                          </div>

                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              disabled={executingId === tpl.id}
                              onClick={(e) => handleExecuteNow(tpl, e)}
                              className="flex items-center gap-1 rounded-xl bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                            >
                              <Play
                                size={11}
                                className={executingId === tpl.id ? 'animate-spin' : ''}
                              />
                              <span>즉시 실행</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => openStrategyDetail(tpl.id, 'rotation')}
                              className="rounded-xl bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/60 dark:text-indigo-300 transition-colors"
                            >
                              상세 보기
                            </button>
                          </div>
                        </>
                      ) : (
                        <div className="flex w-full items-center justify-between">
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              onClick={(e) => handleRestore(tpl, e)}
                              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 transition-colors"
                            >
                              <RotateCcw size={13} className="text-indigo-500" />
                              <span>복원</span>
                            </button>
                            <button
                              type="button"
                              onClick={(e) => handleDelete(tpl, e)}
                              className="flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50/50 px-2.5 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-100 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-400 dark:hover:bg-rose-900/50 transition-colors"
                            >
                              <Trash2 size={13} />
                              <span>영구 삭제</span>
                            </button>
                          </div>
                          <span className="text-[11px] font-medium text-slate-400">보관 중</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          [2] 전략 상세 화면 (카드 클릭 시 이동 — 탭 간소화 & 배치 묶음 중복 제거)
          ========================================================================= */}
      {viewMode === 'workbench' && (
        <div className="space-y-4">
          {/* 상단 통합 전략 헤더 바 */}
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
            <div className="flex flex-1 flex-wrap items-center gap-2.5">
              <button
                type="button"
                onClick={() => setViewMode('management')}
                className="inline-flex items-center gap-1.5 rounded-xl border border-indigo-200 bg-indigo-50/70 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 dark:border-indigo-800 dark:bg-indigo-950/50 dark:text-indigo-300 transition-colors shadow-xs"
                title="전체 전략 목록으로 돌아가기"
              >
                <ArrowLeft size={13} className="shrink-0" />
                <span className="whitespace-nowrap break-keep">전체 전략 목록</span>
              </button>

              <select
                value={selectedTemplateId || ''}
                onChange={(e) => setSelectedTemplateId(Number(e.target.value))}
                aria-label="관제 대상 전략 선택"
                className="max-w-[260px] sm:max-w-[320px] truncate rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs sm:text-sm font-bold text-slate-800 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
              >
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    #{t.id} {t.name} [{t.exchange.toUpperCase()}]
                  </option>
                ))}
              </select>

              {selectedTemplate && (
                <>
                  <Badge
                    value={selectedTemplate.exchange}
                    label={selectedTemplate.exchange.toUpperCase()}
                  />
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {isTopDca ? '시총 TOP N' : (selectedTemplate.strategy_type || '').toUpperCase()}
                  </span>

                  {/* 가동 상태 토글 스위치 */}
                  {(() => {
                    const isActive = isTemplateActive(selectedTemplate)
                    return (
                      <div className="flex items-center gap-1.5 pl-1">
                        <button
                          type="button"
                          disabled={togglingId === selectedTemplate.id}
                          onClick={(e) => handleToggleHolding(selectedTemplate, e)}
                          className={`relative inline-flex h-5 w-10 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                            isActive ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'
                          } ${togglingId === selectedTemplate.id ? 'opacity-50' : ''}`}
                          title={
                            isActive
                              ? '전략 가동중 (클릭 시 일시정지 OFF)'
                              : '전략 일시정지 (클릭 시 가동 ON)'
                          }
                        >
                          <span
                            className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-xs ring-0 transition duration-200 ease-in-out ${
                              isActive ? 'translate-x-5' : 'translate-x-0'
                            }`}
                          />
                        </button>
                        <span
                          className={`text-[10px] font-extrabold ${
                            isActive ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400'
                          }`}
                        >
                          {isActive ? 'ON' : 'OFF'}
                        </span>
                      </div>
                    )
                  })()}
                </>
              )}
            </div>

            {/* 우측: 빠른 제어 & 주문 관리 배치 묶음 바로가기 */}
            {selectedTemplate && (
              <div className="flex flex-wrap items-center gap-1.5 self-end lg:self-auto">
                <button
                  type="button"
                  onClick={() =>
                    navigate(`/orders?tab=batches&template_id=${selectedTemplate.id}`)
                  }
                  className="flex items-center gap-1 rounded-xl border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                  title="주문 관리 > 전략 배치 묶음 화면으로 이동"
                >
                  <span>배치 주문 묶음</span>
                  <ExternalLink size={11} />
                </button>

                <button
                  type="button"
                  onClick={() =>
                    setModalState({
                      isOpen: true,
                      type: selectedTemplate.strategy_type === 'kospi_top_dca' ? 'multi' : 'single',
                      editingTemplate: selectedTemplate,
                    })
                  }
                  className="flex items-center gap-1 rounded-xl border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                >
                  <Pencil size={12} />
                  <span>설정 수정</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setTopupTargetTpl(selectedTemplate)
                    setTopupAmount(300000)
                    setTopupMemo('가용 예산 보충')
                  }}
                  className="flex items-center gap-1 rounded-xl border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                >
                  <Plus size={12} />
                  <span>충전</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setStopTargetTpl(selectedTemplate)
                    setStopMode('pause')
                    setLiquidateConfirmText('')
                  }}
                  className="flex items-center gap-1 rounded-xl border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-rose-50 hover:text-rose-600 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-rose-950/40 dark:hover:text-rose-400 transition-colors"
                >
                  <ShieldAlert size={12} />
                  <span>비상 제어</span>
                </button>

                <button
                  type="button"
                  disabled={executingId === selectedTemplate.id}
                  onClick={(e) => handleExecuteNow(selectedTemplate, e)}
                  className="flex items-center gap-1 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                >
                  <Play
                    size={11}
                    className={executingId === selectedTemplate.id ? 'animate-spin' : ''}
                  />
                  <span>즉시 실행</span>
                </button>
              </div>
            )}
          </div>

          {/* 상세 탭 네비게이션 */}
          <div className="space-y-4">
            <ResponsiveTabs
              tabs={workbenchTabs}
              activeTab={activeTab}
              onChange={setActiveTab}
            />

            <div className="min-w-0">
              {activeTab === 'rotation' &&
                (selectedTemplate ? (
                  isTopDca ? (
                    <TopRotationSection
                      templateId={selectedTemplateId}
                      onOpenSnapshot={() => setActiveTab('snapshot')}
                    />
                  ) : (
                    <SingleStrategySection templateId={selectedTemplateId!} />
                  )
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-xs text-slate-400 dark:border-slate-700">
                    전략을 선택해주세요.
                  </div>
                ))}

              {activeTab === 'snapshot' && isTopDca && (
                <DailySnapshotSection templateId={selectedTemplateId} />
              )}

              {activeTab === 'ledger' && (
                <BudgetPlanSection templateId={selectedTemplateId} />
              )}

              {activeTab === 'timeline' && (
                <BatchTimelineSection
                  dateRange={DEFAULT_TIMELINE_RANGE}
                  templateId={selectedTemplateId ?? undefined}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          [모달 1] 전략 생성/수정 모달 (StrategyFormModal)
          ========================================================================= */}
      <StrategyFormModal
        isOpen={modalState.isOpen}
        onClose={() => setModalState((prev) => ({ ...prev, isOpen: false }))}
        onSuccess={loadTemplates}
        editingTemplate={modalState.editingTemplate}
        initialType={modalState.type}
      />

      {/* =========================================================================
          [모달 2] 수동 예산 추가 충전 (Manual Top-up) 모달
          ========================================================================= */}
      {topupTargetTpl &&
        createPortal(
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div
              className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs"
              onClick={() => !topupLoading && setTopupTargetTpl(null)}
            />
            <div className="relative z-10 w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <DollarSign size={18} className="text-emerald-500" />
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    가용 예산 수동 추가 충전 (+추경)
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setTopupTargetTpl(null)}
                  className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="rounded-xl bg-slate-50 p-3 text-xs dark:bg-slate-800/60 space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-400">대상 전략:</span>
                  <span className="font-bold text-slate-800 dark:text-slate-200">
                    #{topupTargetTpl.id} {topupTargetTpl.name}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">현재 이월 가용예산:</span>
                  <span className="font-bold text-indigo-600 dark:text-indigo-400">
                    {krwFmt((topupTargetTpl.params as any)?.carryover_budget ?? 0)}
                  </span>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-1">
                    추가 충전 금액 (천단위 콤마 자동 서식화)
                  </label>
                  <FormattedNumberInput
                    value={topupAmount}
                    onChange={setTopupAmount}
                    step={10000}
                    min={10000}
                    quickAmounts={[100000, 300000, 500000, 1000000]}
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                    충전 사유 / 메모
                  </label>
                  <input
                    type="text"
                    placeholder="예: 월간 추경 예산 투입, 급락장 추가 매수 지원"
                    value={topupMemo}
                    onChange={(e) => setTopupMemo(e.target.value)}
                    className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-white focus:outline-hidden focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  disabled={topupLoading}
                  onClick={() => setTopupTargetTpl(null)}
                  className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                >
                  취소
                </button>
                <button
                  type="button"
                  disabled={topupLoading}
                  onClick={handleTopupSubmit}
                  className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                >
                  {topupLoading && <Loader2 size={13} className="animate-spin" />}
                  <span>즉시 {krwFmt(topupAmount)} 충전하기</span>
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {/* =========================================================================
          [모달 3] 3단계 정지/청산 제어 모달
          ========================================================================= */}
      {stopTargetTpl &&
        createPortal(
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div
              className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs"
              onClick={() => !stopLoading && setStopTargetTpl(null)}
            />
            <div className="relative z-10 w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
                <div className="flex items-center gap-2">
                  <ShieldAlert size={18} className="text-rose-500" />
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    전략 비상 제어 및 정지/청산 단계 선택
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setStopTargetTpl(null)}
                  className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                >
                  <X size={16} />
                </button>
              </div>

              <div className="rounded-xl bg-slate-50 p-3 text-xs dark:bg-slate-800/60 space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-400">제어 대상:</span>
                  <span className="font-bold text-slate-800 dark:text-slate-200">
                    #{stopTargetTpl.id} {stopTargetTpl.name} [{stopTargetTpl.exchange.toUpperCase()}]
                  </span>
                </div>
              </div>

              <div className="space-y-2.5">
                <label
                  className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-colors ${
                    stopMode === 'pause'
                      ? 'border-indigo-500 bg-indigo-50/40 dark:border-indigo-500 dark:bg-indigo-950/20'
                      : 'border-slate-200 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/40'
                  }`}
                >
                  <input
                    type="radio"
                    name="stopMode"
                    value="pause"
                    checked={stopMode === 'pause'}
                    onChange={() => setStopMode('pause')}
                    className="mt-0.5 text-indigo-600 focus:ring-indigo-500"
                  />
                  <div>
                    <div className="text-xs font-bold text-slate-900 dark:text-white">
                      1단계: 단순 일시정지 (Pause)
                    </div>
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                      다음 자동 스케줄 발주를 일시 중단합니다. 이미 나간 미체결 주문과 보유 주식은 그대로 유지됩니다.
                    </div>
                  </div>
                </label>

                <label
                  className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-colors ${
                    stopMode === 'stop_and_cancel'
                      ? 'border-amber-500 bg-amber-50/40 dark:border-amber-500 dark:bg-amber-950/20'
                      : 'border-slate-200 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/40'
                  }`}
                >
                  <input
                    type="radio"
                    name="stopMode"
                    value="stop_and_cancel"
                    checked={stopMode === 'stop_and_cancel'}
                    onChange={() => setStopMode('stop_and_cancel')}
                    className="mt-0.5 text-amber-600 focus:ring-amber-500"
                  />
                  <div>
                    <div className="text-xs font-bold text-amber-700 dark:text-amber-400">
                      2단계: 가동 중지 + 거래소 미체결 일괄 취소 (Stop & Cancel)
                    </div>
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                      스케줄을 끄고 거래소에 접수되어 있는 모든 미체결 매수/매도 주문을 즉시 일괄 취소합니다. 보유 주식은 보존됩니다.
                    </div>
                  </div>
                </label>

                <label
                  className={`flex items-start gap-3 rounded-xl border p-3 cursor-pointer transition-colors ${
                    stopMode === 'terminate_and_liquidate'
                      ? 'border-rose-500 bg-rose-50/40 dark:border-rose-500 dark:bg-rose-950/20'
                      : 'border-slate-200 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/40'
                  }`}
                >
                  <input
                    type="radio"
                    name="stopMode"
                    value="terminate_and_liquidate"
                    checked={stopMode === 'terminate_and_liquidate'}
                    onChange={() => setStopMode('terminate_and_liquidate')}
                    className="mt-0.5 text-rose-600 focus:ring-rose-500"
                  />
                  <div>
                    <div className="text-xs font-bold text-rose-700 dark:text-rose-400">
                      3단계: 비상 종료 + 전량 시장가 청산 (Terminate & Liquidate)
                    </div>
                    <div className="text-[11px] text-rose-600/80 dark:text-rose-400/80 mt-0.5">
                      미체결 취소 후, 이 전략으로 보유 중인 모든 주식을 현재가/시장가로 즉시 전량 매도하여 현금화합니다.
                    </div>
                  </div>
                </label>
              </div>

              {stopMode === 'terminate_and_liquidate' && (
                <div className="rounded-xl border border-rose-200 bg-rose-50/60 p-3 dark:border-rose-900/60 dark:bg-rose-950/30 space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-rose-700 dark:text-rose-400">
                    <AlertTriangle size={14} />
                    <span>경고: 즉시 청산 확인</span>
                  </div>
                  <p className="text-[11px] text-rose-600 dark:text-rose-300">
                    실제 계좌의 모든 보유 수량이 매도 주문 처리됩니다. 실행하시려면 아래에{' '}
                    <strong>전량청산</strong>을 입력하세요.
                  </p>
                  <input
                    type="text"
                    placeholder="전량청산"
                    value={liquidateConfirmText}
                    onChange={(e) => setLiquidateConfirmText(e.target.value)}
                    className="w-full rounded-xl border border-rose-300 bg-white p-2 text-xs font-bold text-rose-700 focus:outline-hidden focus:ring-2 focus:ring-rose-500 dark:border-rose-700 dark:bg-slate-800 dark:text-rose-300"
                  />
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  disabled={stopLoading}
                  onClick={() => setStopTargetTpl(null)}
                  className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                >
                  취소
                </button>
                <button
                  type="button"
                  disabled={
                    stopLoading ||
                    (stopMode === 'terminate_and_liquidate' &&
                      liquidateConfirmText.trim() !== '전량청산')
                  }
                  onClick={handleStopSubmit}
                  className={`flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-semibold text-white shadow-xs disabled:opacity-50 transition-colors ${
                    stopMode === 'terminate_and_liquidate'
                      ? 'bg-rose-600 hover:bg-rose-700'
                      : stopMode === 'stop_and_cancel'
                      ? 'bg-amber-600 hover:bg-amber-700'
                      : 'bg-indigo-600 hover:bg-indigo-700'
                  }`}
                >
                  {stopLoading && <Loader2 size={13} className="animate-spin" />}
                  <span>
                    {stopMode === 'terminate_and_liquidate'
                      ? '확인, 즉시 전량 청산 집행'
                      : stopMode === 'stop_and_cancel'
                      ? '가동 중지 & 미체결 취소'
                      : '전략 일시정지'}
                  </span>
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}
