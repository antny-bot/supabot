import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createPortal } from 'react-dom'
import {
  Activity,
  Archive,
  Copy,
  Layers,
  Loader2,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Trash2,
} from 'lucide-react'
import {
  archiveTemplate,
  deleteTemplate,
  duplicateTemplate,
  executeTemplate,
  fetchTemplates,
  restoreTemplate,
  toggleTemplateHolding,
  type Template,
} from '../api/templates'
import Badge from '../components/ui/Badge'
import PageHeader from '../components/ui/PageHeader'
import { Skeleton } from '../components/ui/Skeleton'
import StrategyFormModal from '../components/strategy/StrategyFormModal'
import { STRATEGY_BADGE_LABELS, STRATEGY_TYPE_LABELS, normalizeStrategyType } from '../components/strategy/strategyTypes'
import { PAGE_META } from '../config/pageMeta'
import { useToast } from '../contexts/ToastContext'
import { krwFmt } from '../utils/formatters'

export default function Templates() {
  const toast = useToast()
  const navigate = useNavigate()
  const [templates, setTemplates] = useState<Template[]>([])
  const [viewTab, setViewTab] = useState<'active' | 'archived'>('active')
  const [togglingId, setTogglingId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 모달 상태
  const [modalState, setModalState] = useState<{
    isOpen: boolean
    type: 'single' | 'multi'
    editingTemplate: Template | null
  }>({
    isOpen: false,
    type: 'single',
    editingTemplate: null,
  })

  // 즉시 실행 확인 모달
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

  const activeTemplates = useMemo(
    () => templates.filter((t) => !(t.params as any)?.is_archived),
    [templates],
  )
  const archivedTemplates = useMemo(
    () => templates.filter((t) => (t.params as any)?.is_archived === true),
    [templates],
  )
  const displayedTemplates = viewTab === 'active' ? activeTemplates : archivedTemplates

  const handleToggleHolding = async (tpl: Template) => {
    const p = (tpl.params || {}) as any
    const currentActive =
      p.strategy_status === 'active' ||
      (p.strategy_status === undefined && p.schedule_enabled !== false)
    const nextHolding = currentActive

    setTogglingId(tpl.id)
    try {
      const res = await toggleTemplateHolding(tpl.id, nextHolding)
      if (res.ok) {
        toast.success(
          `전략 #${tpl.id} [${tpl.name}] 가 ${!nextHolding ? '가동(ON)' : '일시정지(OFF)'} 상태로 변경되었습니다.`,
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
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '전략 상태 변경 중 오류가 발생했습니다.')
    } finally {
      setTogglingId(null)
    }
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

  const handleArchive = async (template: Template) => {
    const p = (template.params || {}) as Record<string, any>
    const isActive =
      p.strategy_status === 'active' ||
      (p.strategy_status === undefined && p.schedule_enabled !== false)

    if (isActive) {
      toast.error('실행 중(Active)인 전략은 보관할 수 없습니다. 전략을 먼저 중지(OFF)해주세요.')
      return
    }

    if (
      !confirm(
        `'${template.name}' 전략을 보관함으로 이동하시겠습니까?\n보관된 전략은 자동 실행이 중지되며 보관함에서 언제든 복원하거나 삭제할 수 있습니다.`,
      )
    ) {
      return
    }
    try {
      await archiveTemplate(template.id)
      toast.success('전략이 보관함으로 이동되었습니다.')
      loadTemplates()
    } catch (e) {
      toast.error('보관 실패: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  const handleRestore = async (template: Template) => {
    try {
      await restoreTemplate(template.id)
      toast.success(`'${template.name}' 전략이 운용 목록으로 복원되었습니다.`)
      loadTemplates()
    } catch (e) {
      toast.error('복원 실패: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  const handleDelete = async (template: Template) => {
    const p = (template.params || {}) as Record<string, any>
    if (!p.is_archived) {
      toast.error('일반 운용 상태의 전략은 즉시 삭제할 수 없습니다. 먼저 보관함으로 이동해주세요.')
      return
    }

    if (
      !confirm(
        `'${template.name}' 전략을 영구 삭제하시겠습니까?\n이 작업은 되돌릴 수 없으며, 모든 설정이 완전히 삭제됩니다.`,
      )
    ) {
      return
    }
    try {
      await deleteTemplate(template.id)
      toast.success('전략이 영구 삭제되었습니다.')
      loadTemplates()
    } catch (e) {
      toast.error('삭제 실패: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  const handleConfirmExecute = async () => {
    if (!executingTemplate) return
    setExecuting(true)
    try {
      const res = await executeTemplate(executingTemplate.id)
      const groupNo = (res as any)?.data?.group_no
      const baseMsg = res.message || '템플릿 전략이 성공적으로 실행되었습니다.'
      toast.success(groupNo ? `${baseMsg} (주문 현황 > '전략 배치 묶음'에서 확인 가능)` : baseMsg)
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
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() =>
                setModalState({ isOpen: true, type: 'single', editingTemplate: null })
              }
              className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-indigo-700 transition-colors"
            >
              <Plus size={15} />
              <span>단일 종목 템플릿</span>
            </button>
            <button
              onClick={() =>
                setModalState({ isOpen: true, type: 'multi', editingTemplate: null })
              }
              className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-violet-700 transition-colors"
            >
              <Layers size={15} />
              <span>복수 종목 (TOP N) 템플릿</span>
            </button>
          </div>
        }
      />

      {/* 탭 네비게이션: 운용 전략 vs 보관함 */}
      <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setViewTab('active')}
            className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors ${
              viewTab === 'active'
                ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            <span>운용 전략</span>
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                viewTab === 'active'
                  ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300'
                  : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
              }`}
            >
              {activeTemplates.length}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setViewTab('archived')}
            className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors ${
              viewTab === 'archived'
                ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            <Archive size={13} />
            <span>보관함</span>
            {archivedTemplates.length > 0 && (
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  viewTab === 'archived'
                    ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300'
                    : 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300'
                }`}
              >
                {archivedTemplates.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-xl bg-rose-50 p-4 text-xs font-medium text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
          <span>{error}</span>
        </div>
      )}

      {/* 템플릿 카드 그리드 */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-xs dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex items-start justify-between">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <Skeleton className="h-5 w-14 rounded-md" />
                    <Skeleton className="h-5 w-20 rounded-md" />
                  </div>
                  <Skeleton className="h-5 w-32" />
                </div>
                <Skeleton className="h-8 w-8 rounded-lg" />
              </div>
            </div>
          ))}
        </div>
      ) : displayedTemplates.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 p-12 text-center dark:border-slate-800">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400">
            {viewTab === 'archived' ? <Archive size={24} /> : <Layers size={24} />}
          </div>
          <h3 className="mt-3 text-sm font-semibold text-slate-800 dark:text-slate-200">
            {viewTab === 'archived' ? '보관된 전략이 없습니다' : '등록된 운용 전략 템플릿이 없습니다'}
          </h3>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {displayedTemplates.map((tpl) => {
            const stype = normalizeStrategyType(tpl.strategy_type)
            const isDca = stype === 'dca' || stype === 'sdca'
            const isTopDca = stype === 'kospi_top_dca'
            const isVolumeBased = stype === 'sgrid' || (isDca && tpl.params?.amount_type === 'volume')
            const p = (tpl.params || {}) as any
            const isActive =
              p.strategy_status === 'active' ||
              (p.strategy_status === undefined && p.schedule_enabled !== false)

            return (
              <div
                key={tpl.id}
                className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-xs transition-all hover:border-indigo-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-indigo-800"
              >
                <div>
                  {/* 상단: 거래소, 종목, 전략 유형 및 ON/OFF 토글 */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Badge value={tpl.exchange} label={tpl.exchange.toUpperCase()} />
                      <span className="text-sm font-bold text-slate-900 dark:text-white">
                        {tpl.ticker}
                      </span>
                      <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                        {STRATEGY_BADGE_LABELS[stype] || stype.toUpperCase()}
                      </span>
                      {viewTab === 'archived' && (
                        <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
                          보관됨
                        </span>
                      )}
                    </div>

                    {viewTab === 'active' && (
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          disabled={togglingId === tpl.id}
                          onClick={() => handleToggleHolding(tpl)}
                          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                            isActive ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'
                          } ${togglingId === tpl.id ? 'opacity-50' : ''}`}
                          title={isActive ? '전략 가동 중 (클릭 시 일시정지 OFF)' : '전략 일시정지됨 (클릭 시 가동 ON)'}
                        >
                          <span
                            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-xs ring-0 transition duration-200 ease-in-out ${
                              isActive ? 'translate-x-5' : 'translate-x-0'
                            }`}
                          />
                        </button>
                        <span
                          className={`text-[11px] font-extrabold font-mono w-7 text-center ${
                            isActive ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400'
                          }`}
                        >
                          {isActive ? 'ON' : 'OFF'}
                        </span>
                      </div>
                    )}
                  </div>

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
                          ? `${krwFmt(p.budget_mode === 'daily' ? (p.daily_fixed_budget ?? tpl.budget) : (p.monthly_budget ?? tpl.budget))}`
                          : `${krwFmt(tpl.budget)}`}
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
                          ? `${p.rank_start ?? 1}위 ~ ${p.rank_end ?? p.top_n ?? 10}위`
                          : `${tpl.count}분할`}
                      </p>
                    </div>
                  </div>
                </div>

                {/* 하단 액션 버튼 그룹 */}
                <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 dark:border-slate-800">
                  {viewTab === 'active' ? (
                    <>
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() =>
                            setModalState({
                              isOpen: true,
                              type: isTopDca ? 'multi' : 'single',
                              editingTemplate: tpl,
                            })
                          }
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
                          onClick={() => handleArchive(tpl)}
                          disabled={isActive}
                          className={`rounded-lg p-1.5 transition-colors ${
                            isActive
                              ? 'cursor-not-allowed opacity-30 text-slate-400'
                              : 'text-slate-400 hover:bg-amber-50 hover:text-amber-600 dark:hover:bg-amber-950/40 dark:hover:text-amber-400'
                          }`}
                          title={
                            isActive
                              ? '실행 중인 전략은 보관할 수 없습니다. 먼저 중지(OFF)하세요.'
                              : '보관함으로 이동'
                          }
                        >
                          <Archive size={14} />
                        </button>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => navigate(`/operations?template_id=${tpl.id}&tab=rotation`)}
                          className="flex items-center gap-1 rounded-xl border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                          title="전략 전용 포지션 및 감사원장 관제"
                        >
                          <Activity size={13} className="text-indigo-500" />
                          <span>모니터링</span>
                        </button>
                        <button
                          onClick={() => setExecutingTemplate(tpl)}
                          className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700 transition-colors"
                        >
                          <Play size={13} />
                          <span>즉시 실행</span>
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleRestore(tpl)}
                          className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700 transition-colors"
                          title="운용 목록으로 복원"
                        >
                          <RotateCcw size={13} className="text-indigo-500" />
                          <span>복원</span>
                        </button>
                        <button
                          onClick={() => handleDelete(tpl)}
                          className="flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50/50 px-2.5 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-100 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-400 dark:hover:bg-rose-900/50 transition-colors"
                          title="영구 삭제"
                        >
                          <Trash2 size={13} />
                          <span>영구 삭제</span>
                        </button>
                      </div>
                      <span className="text-[11px] font-medium text-slate-400">
                        보관 중
                      </span>
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 전략 생성/수정 모달 */}
      <StrategyFormModal
        isOpen={modalState.isOpen}
        onClose={() => setModalState((prev) => ({ ...prev, isOpen: false }))}
        onSuccess={loadTemplates}
        editingTemplate={modalState.editingTemplate}
        initialType={modalState.type}
      />

      {/* 즉시 실행 확인 모달 */}
      {executingTemplate &&
        createPortal(
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div
              className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs"
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
                <p>
                  유형: {STRATEGY_TYPE_LABELS[executingTemplate.strategy_type || 'grid'] || executingTemplate.strategy_type}
                </p>
                <p>
                  종목: {executingTemplate.ticker} ({executingTemplate.exchange.toUpperCase()})
                </p>
                <p>
                  규모:{' '}
                  {executingTemplate.strategy_type === 'sgrid' || executingTemplate.params?.amount_type === 'volume'
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
          </div>,
          document.body,
        )}
    </div>
  )
}
