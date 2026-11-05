import { useEffect, useState, useCallback } from 'react'
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
} from 'lucide-react'
import {
  fetchTemplates,
  toggleTemplateHolding,
  executeTemplate,
  stopTemplate,
  manualTopupTemplate,
  type Template,
} from '../api/templates'
import Badge from '../components/ui/Badge'
import PageHeader from '../components/ui/PageHeader'
import SegmentedControl from '../components/ui/SegmentedControl'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'
import TopRotationSection from './reports/TopRotationSection'
import SingleStrategySection from './reports/SingleStrategySection'
import BudgetPlanSection from './reports/BudgetPlanSection'
import BatchTimelineSection from './reports/BatchTimelineSection'
import OrderBatchesSection from './orders/OrderBatchesSection'
import ResponsiveTabs from '../components/ui/ResponsiveTabs'
import { useToast } from '../contexts/ToastContext'
import { krwFmt } from '../utils/formatters'
import type { DateRangeValue } from '../components/ui/DateRangePicker'

const DEFAULT_TIMELINE_RANGE: DateRangeValue = { mode: '30d', from: '', to: '' }

const MAIN_VIEWS = [
  { id: 'workbench', label: '전략 실시간 관제 (워크벤치)' },
  { id: 'list', label: '실행 전략 목록 & 빠른 제어' },
]

export default function Operations() {
  const toast = useToast()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const viewParam = searchParams.get('view')
  const tabParam = searchParams.get('tab')
  const templateIdParam = searchParams.get('template_id')

  const [viewMode, setViewMode] = useState<'workbench' | 'list'>(() => {
    return viewParam === 'list' ? 'list' : 'workbench'
  })

  const [activeTab, setActiveTab] = useState(() => {
    return tabParam && ['rotation', 'ledger', 'batches', 'timeline'].includes(tabParam)
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
      setError(e instanceof Error ? e.message : '전략 템플릿 목록 로드 실패')
    } finally {
      setLoading(false)
    }
  }, [selectedTemplateId])

  useEffect(() => {
    loadTemplates()
  }, [loadTemplates])

  // URL 파라미터 동기화
  useEffect(() => {
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
  }, [viewMode, activeTab, selectedTemplateId, searchParams, setSearchParams])

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId)
  const isTopDca = selectedTemplate?.strategy_type === 'kospi_top_dca'

  const workbenchTabs = [
    { id: 'rotation', label: isTopDca ? '포지션 & 순위 회전' : '포지션 & 전략 지표' },
    { id: 'ledger', label: '예산 플랜 & 감사원장' },
    { id: 'batches', label: '전략 배치 주문 묶음' },
    { id: 'timeline', label: '배치 실행 타임라인' },
  ]

  const handleToggleHolding = async (tpl: Template, e: React.MouseEvent) => {
    e.stopPropagation()
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
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '전략 상태 변경 중 오류가 발생했습니다.')
    } finally {
      setTogglingId(null)
    }
  }

  const handleExecuteNow = async (tpl: Template, e: React.MouseEvent) => {
    e.stopPropagation()
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

  return (
    <div className="space-y-6 pb-12 break-keep animate-fade-in-up">
      {/* 최상단 페이지 헤더 */}
      <PageHeader
        title="전략 운용 모니터링"
        Icon={Activity}
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => loadTemplates()}
              className="flex items-center gap-1.5 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
            >
              <RotateCw size={13} className={loading ? 'animate-spin' : ''} />
              <span>새로고침</span>
            </button>
            <button
              onClick={() => navigate('/templates')}
              className="flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-indigo-700 transition-colors"
            >
              <Plus size={14} />
              <span>새 전략 설정</span>
            </button>
          </div>
        }
      />

      {error && <ErrorBanner message={error} />}

      {/* 2대 메인 모드 분리 탭 (실시간 관제 워크벤치 vs 등록 전략 총괄 제어) */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 pb-3">
        <SegmentedControl
          options={MAIN_VIEWS}
          value={viewMode}
          onChange={(v) => setViewMode(v as 'workbench' | 'list')}
        />
        <div className="text-xs text-slate-400">
          {viewMode === 'workbench'
            ? '선택된 전략의 실시간 포지션/지표 및 감사원장을 집중 관제합니다.'
            : '전체 전략의 On/Off 가동 상태 및 비상 제어를 총괄 관리합니다.'}
        </div>
      </div>

      {/* =========================================================================
          [1] 뷰 1: 등록 전략 목록 및 총괄 빠른 제어 (카드 그리드 대시보드)
          ========================================================================= */}
      {viewMode === 'list' && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                실행 등록 전략 목록 ({templates.length}개)
              </h3>
              <span className="text-xs text-slate-400">
                카드의 [상세 관제]를 클릭하여 실시간 워크벤치를 확인하세요.
              </span>
            </div>
          </div>

          {loading && templates.length === 0 ? (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          ) : templates.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 p-8 text-center text-xs text-slate-400 dark:border-slate-700">
              등록된 전략이 없습니다. [새 전략 설정]에서 전략을 생성해주세요.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {templates.map((tpl) => {
                const p = (tpl.params || {}) as any
                const isSelected = tpl.id === selectedTemplateId
                const isActive =
                  p.strategy_status === 'active' ||
                  (p.strategy_status === undefined && p.schedule_enabled !== false)

                return (
                  <div
                    key={tpl.id}
                    onClick={() => {
                      setSelectedTemplateId(tpl.id)
                      setViewMode('workbench')
                    }}
                    className={`relative flex flex-col justify-between rounded-2xl border p-4 transition-all cursor-pointer ${
                      isSelected
                        ? 'border-indigo-500 bg-indigo-50/20 shadow-md ring-2 ring-indigo-500/20 dark:border-indigo-500 dark:bg-indigo-950/20'
                        : 'border-slate-200 bg-white shadow-xs hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700'
                    }`}
                  >
                    <div>
                      {/* 상단: 거래소, 종목 & ON/OFF 토글 스위치 */}
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <Badge value={tpl.exchange} label={tpl.exchange.toUpperCase()} />
                          <span className="text-xs font-extrabold text-slate-900 dark:text-white">
                            #{tpl.id}
                          </span>
                          <span className="text-xs text-slate-400 font-mono">
                            {tpl.strategy_type === 'kospi_top_dca' ? '시총 TOP N' : tpl.strategy_type}
                          </span>
                        </div>

                        {/* On / Off 스위치 */}
                        <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                          <button
                            type="button"
                            disabled={togglingId === tpl.id}
                            onClick={(e) => handleToggleHolding(tpl, e)}
                            className={`relative inline-flex h-5 w-10 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                              isActive ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'
                            } ${togglingId === tpl.id ? 'opacity-50' : ''}`}
                            title={isActive ? '전략 가동중 (클릭 시 일시정지 OFF)' : '전략 일시정지 (클릭 시 가동 ON)'}
                          >
                            <span
                              className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-xs ring-0 transition duration-200 ease-in-out ${
                                isActive ? 'translate-x-5' : 'translate-x-0'
                              }`}
                            />
                          </button>
                          <span
                            className={`text-[10px] font-extrabold font-mono w-6 text-center ${
                              isActive ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400'
                            }`}
                          >
                            {isActive ? 'ON' : 'OFF'}
                          </span>
                        </div>
                      </div>

                      {/* 전략 명칭 */}
                      <h4 className="mt-2 text-sm font-bold text-slate-900 dark:text-white truncate">
                        {tpl.name}
                      </h4>

                      {/* 독립적 지표 요약 그리드 */}
                      <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-slate-50 p-2.5 text-xs dark:bg-slate-800/50">
                        <div>
                          <div className="flex items-center justify-between text-[10px] text-slate-400">
                            <span>이월 가용 예산</span>
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
                          </div>
                          <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
                            {krwFmt(p.carryover_budget ?? 0)}
                          </span>
                        </div>
                        <div>
                          <span className="text-[10px] text-slate-400 block">당월 누적 소진</span>
                          <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
                            {krwFmt(p.monthly_spent ?? 0)}
                          </span>
                        </div>
                        <div className="col-span-2 pt-1 border-t border-slate-200/60 dark:border-slate-700/60 flex items-center justify-between text-[11px]">
                          <span className="text-slate-400">
                            {p.last_group_no ? `최근 실행: Batch #${p.last_group_no}` : '실행 대기중'}
                          </span>
                          <span className="font-mono text-slate-500">
                            스케줄: 매일 {p.schedule_time || '09:10'}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* 하단 제어 액션 바 */}
                    <div className="mt-3.5 flex items-center justify-between border-t border-slate-100 pt-2.5 dark:border-slate-800">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          setStopTargetTpl(tpl)
                          setStopMode('pause')
                          setLiquidateConfirmText('')
                        }}
                        className="flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-semibold text-slate-500 hover:bg-slate-100 hover:text-rose-600 dark:hover:bg-slate-800 dark:hover:text-rose-400 transition-colors"
                        title="비상 일시정지, 주문 취소 또는 전량 청산"
                      >
                        <ShieldAlert size={12} />
                        <span>제어/청산</span>
                      </button>

                      <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          disabled={executingId === tpl.id}
                          onClick={(e) => handleExecuteNow(tpl, e)}
                          className="flex items-center gap-1 rounded-xl bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                        >
                          <Play size={11} className={executingId === tpl.id ? 'animate-spin' : ''} />
                          <span>즉시 실행</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedTemplateId(tpl.id)
                            setViewMode('workbench')
                          }}
                          className="flex items-center gap-1 rounded-xl bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/60 dark:text-indigo-300 transition-colors"
                        >
                          <span>관제 열기 →</span>
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          [2] 뷰 2: 선택된 전략별 실시간 관제 워크벤치
          ========================================================================= */}
      {viewMode === 'workbench' && (
        <div className="space-y-4">
          {/* 슬림 전략 선택 & 빠른 제어 바 */}
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
            {/* 좌측: 전략 셀렉터 & 기본 식별 정보 */}
            <div className="flex flex-1 flex-wrap items-center gap-2.5">
              <span className="text-xs font-bold text-slate-500 dark:text-slate-400 shrink-0">
                관제 대상 전략:
              </span>
              <select
                value={selectedTemplateId || ''}
                onChange={(e) => setSelectedTemplateId(Number(e.target.value))}
                className="max-w-[280px] sm:max-w-[340px] truncate rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-1.5 text-xs sm:text-sm font-bold text-slate-800 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
              >
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    #{t.id} {t.name} [{t.exchange.toUpperCase()}] ({t.strategy_type === 'kospi_top_dca' ? 'TOP N' : t.strategy_type})
                  </option>
                ))}
              </select>

              {selectedTemplate && (
                <>
                  <Badge value={selectedTemplate.exchange} label={selectedTemplate.exchange.toUpperCase()} />
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-bold text-slate-600 dark:bg-slate-800 dark:text-slate-300 font-mono">
                    {isTopDca ? '시총 TOP N DCA' : (selectedTemplate.strategy_type || '').toUpperCase()}
                  </span>

                  {/* 가동 상태 토글 스위치 */}
                  {(() => {
                    const p = (selectedTemplate.params || {}) as any
                    const isActive =
                      p.strategy_status === 'active' ||
                      (p.strategy_status === undefined && p.schedule_enabled !== false)
                    return (
                      <div className="flex items-center gap-1.5 pl-1">
                        <button
                          type="button"
                          disabled={togglingId === selectedTemplate.id}
                          onClick={(e) => handleToggleHolding(selectedTemplate, e)}
                          className={`relative inline-flex h-5 w-10 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                            isActive ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'
                          } ${togglingId === selectedTemplate.id ? 'opacity-50' : ''}`}
                          title={isActive ? '전략 가동중 (클릭 시 일시정지 OFF)' : '전략 일시정지 (클릭 시 가동 ON)'}
                        >
                          <span
                            className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-xs ring-0 transition duration-200 ease-in-out ${
                              isActive ? 'translate-x-5' : 'translate-x-0'
                            }`}
                          />
                        </button>
                        <span
                          className={`text-[10px] font-extrabold font-mono ${
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

            {/* 우측: 인라인 예산 요약 & 빠른 제어 버튼 */}
            {selectedTemplate && (
              <div className="flex flex-wrap items-center gap-2 self-end lg:self-auto">
                <div className="hidden sm:flex items-center gap-3 rounded-xl bg-slate-50 px-3 py-1.5 text-xs dark:bg-slate-800/60 font-mono">
                  <div>
                    <span className="text-[10px] text-slate-400 block">이월 가용예산</span>
                    <span className="font-bold text-slate-700 dark:text-slate-200">
                      {krwFmt((selectedTemplate.params as any)?.carryover_budget ?? 0)}
                    </span>
                  </div>
                  <div className="border-l border-slate-200 dark:border-slate-700 pl-3">
                    <span className="text-[10px] text-slate-400 block">당월 소진</span>
                    <span className="font-bold text-slate-700 dark:text-slate-200">
                      {krwFmt((selectedTemplate.params as any)?.monthly_spent ?? 0)}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    setTopupTargetTpl(selectedTemplate)
                    setTopupAmount(300000)
                    setTopupMemo('가용 예산 보충')
                  }}
                  className="flex items-center gap-1 rounded-xl border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                  title="예산 즉시 수동 추가 충전"
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
                  title="비상 일시정지, 주문 취소 또는 전량 청산"
                >
                  <ShieldAlert size={12} />
                  <span>제어/청산</span>
                </button>

                <button
                  type="button"
                  disabled={executingId === selectedTemplate.id}
                  onClick={(e) => handleExecuteNow(selectedTemplate, e)}
                  className="flex items-center gap-1 rounded-xl bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                >
                  <Play size={11} className={executingId === selectedTemplate.id ? 'animate-spin' : ''} />
                  <span>즉시 실행</span>
                </button>

                <button
                  type="button"
                  onClick={() => setViewMode('list')}
                  className="flex items-center gap-1 rounded-xl border border-indigo-200 px-2.5 py-1.5 text-xs font-semibold text-indigo-600 hover:bg-indigo-50 dark:border-indigo-800 dark:text-indigo-400 dark:hover:bg-indigo-950/40 transition-colors"
                >
                  <span>목록 보기</span>
                </button>
              </div>
            )}
          </div>

          {/* 4대 탭 네비게이션 */}
          <div className="space-y-4">
            <ResponsiveTabs
              tabs={workbenchTabs}
              activeTab={activeTab}
              onChange={setActiveTab}
            />

            {/* 탭별 컨텐츠 섹션 (전략 타입에 따라 적응형 렌더링) */}
            <div className="min-w-0">
              {activeTab === 'rotation' && (
                selectedTemplate ? (
                  isTopDca ? (
                    <TopRotationSection templateId={selectedTemplateId} />
                  ) : (
                    <SingleStrategySection templateId={selectedTemplateId!} />
                  )
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-xs text-slate-400 dark:border-slate-700">
                    전략을 선택해주세요.
                  </div>
                )
              )}

              {activeTab === 'ledger' && (
                <BudgetPlanSection templateId={selectedTemplateId} />
              )}

              {activeTab === 'batches' && (
                selectedTemplateId ? (
                  <OrderBatchesSection
                    key={selectedTemplateId}
                    templateId={selectedTemplateId}
                    initialGroupNo={
                      (selectedTemplate?.params as any)?.last_group_no
                        ? Number((selectedTemplate?.params as any)?.last_group_no)
                        : undefined
                    }
                    onSelectGroupNo={(g) => navigate(`/orders?group_no=${g}`)}
                  />
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-xs text-slate-400 dark:border-slate-700">
                    전략을 선택해주세요.
                  </div>
                )
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
          [모달 1] 수동 예산 추가 충전 (Manual Top-up) 모달
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
                  className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                >
                  <X size={16} />
                </button>
              </div>

              <p className="text-xs text-slate-500 dark:text-slate-400">
                전략 <strong>#{topupTargetTpl.id} {topupTargetTpl.name}</strong>의 이월 가용 예산(carryover_budget)을 즉시 충전합니다. 감사원장에 <code>MANUAL_TOPUP</code> 내역으로 안전하게 영구 기록됩니다.
              </p>

              {/* 빠른 금액 선택 칩 */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  충전 금액 선택
                </label>
                <div className="grid grid-cols-4 gap-2">
                  {[100000, 300000, 500000, 1000000].map((amt) => (
                    <button
                      key={amt}
                      type="button"
                      onClick={() => setTopupAmount(amt)}
                      className={`py-1.5 text-xs rounded-xl font-mono font-semibold border transition-all ${
                        topupAmount === amt
                          ? 'border-emerald-500 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
                          : 'border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300'
                      }`}
                    >
                      +{krwFmt(amt)}
                    </button>
                  ))}
                </div>
              </div>

              {/* 직접 입력 인풋 */}
              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-1">
                  직접 입력 (원 단위)
                </label>
                <input
                  type="number"
                  step="10000"
                  min="10000"
                  value={topupAmount}
                  onChange={(e) => setTopupAmount(Number(e.target.value))}
                  className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2 text-sm font-mono font-bold text-slate-900 dark:text-white focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-1">
                  충전 사유 / 메모
                </label>
                <input
                  type="text"
                  placeholder="예: 다음 타겟 종목 부족액 긴급 보충"
                  value={topupMemo}
                  onChange={(e) => setTopupMemo(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3.5 py-2 text-xs text-slate-900 dark:text-white"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  disabled={topupLoading}
                  onClick={() => setTopupTargetTpl(null)}
                  className="px-4 py-2 text-xs font-semibold rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50"
                >
                  취소
                </button>
                <button
                  type="button"
                  disabled={topupLoading || topupAmount <= 0}
                  onClick={handleTopupSubmit}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {topupLoading && <Loader2 size={13} className="animate-spin" />}
                  <span>{krwFmt(topupAmount)} 즉시 충전</span>
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {/* =========================================================================
          [모달 2] 전략 3단계 긴급 정지 및 청산 제어 모달
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
              <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
                <ShieldAlert size={20} />
                <h3 className="text-base font-bold">
                  전략 운용 긴급 제어: #{stopTargetTpl.id} {stopTargetTpl.name}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setStopTargetTpl(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X size={16} />
              </button>
            </div>

            <p className="text-xs text-slate-500 dark:text-slate-400">
              상황에 맞춰 원하는 정지 및 자산 청산 단계를 선택하세요.
            </p>

            {/* 3단계 모드 선택 라디오 박스 */}
            <div className="space-y-2.5">
              <label
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                  stopMode === 'pause'
                    ? 'border-amber-500 bg-amber-50/40 dark:bg-amber-950/20'
                    : 'border-slate-200 dark:border-slate-800'
                }`}
              >
                <input
                  type="radio"
                  name="stopMode"
                  value="pause"
                  checked={stopMode === 'pause'}
                  onChange={() => setStopMode('pause')}
                  className="mt-1"
                />
                <div>
                  <span className="font-bold text-xs text-slate-900 dark:text-white block">
                    1단계: 단순 일시정지 (Pause)
                  </span>
                  <span className="text-[11px] text-slate-500">
                    스케줄 자동 매매만 일시 중단합니다. 기존 보유 주식과 이미 나가 있는 대기 주문은 그대로 보존됩니다.
                  </span>
                </div>
              </label>

              <label
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                  stopMode === 'stop_and_cancel'
                    ? 'border-rose-500 bg-rose-50/40 dark:bg-rose-950/20'
                    : 'border-slate-200 dark:border-slate-800'
                }`}
              >
                <input
                  type="radio"
                  name="stopMode"
                  value="stop_and_cancel"
                  checked={stopMode === 'stop_and_cancel'}
                  onChange={() => setStopMode('stop_and_cancel')}
                  className="mt-1"
                />
                <div>
                  <span className="font-bold text-xs text-rose-600 dark:text-rose-400 block">
                    2단계: 전략 정지 & 미체결 주문 일괄 취소 (Stop & Cancel)
                  </span>
                  <span className="text-[11px] text-slate-500">
                    자동 매매를 중단하고, 거래소에 걸려있는 이 전략의 모든 미체결 매수/매도 주문을 거래소에서 즉시 일괄 취소합니다. (보유 주식은 유지)
                  </span>
                </div>
              </label>

              <label
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                  stopMode === 'terminate_and_liquidate'
                    ? 'border-red-600 bg-red-50/60 dark:bg-red-950/30 ring-2 ring-red-600/20'
                    : 'border-slate-200 dark:border-slate-800'
                }`}
              >
                <input
                  type="radio"
                  name="stopMode"
                  value="terminate_and_liquidate"
                  checked={stopMode === 'terminate_and_liquidate'}
                  onChange={() => setStopMode('terminate_and_liquidate')}
                  className="mt-1"
                />
                <div>
                  <span className="font-bold text-xs text-red-600 dark:text-red-400 block">
                    🚨 3단계: 전략 완전 종료 & 기보유 주식 전량 시장가 청산 매도
                  </span>
                  <span className="text-[11px] text-slate-500">
                    모든 미체결 주문을 취소하고, <strong>현재 전략으로 보유 중인 모든 종목을 현재가로 즉시 전량 매도 청산</strong>하여 현금화합니다.
                  </span>
                </div>
              </label>
            </div>

            {/* 3단계 전량 청산 선택 시 안전 확인 인풋 */}
            {stopMode === 'terminate_and_liquidate' && (
              <div className="rounded-xl bg-rose-50 dark:bg-rose-950/40 p-3 border border-rose-200 dark:border-rose-900 space-y-2">
                <span className="text-xs font-bold text-rose-700 dark:text-rose-300 flex items-center gap-1">
                  <AlertTriangle size={14} />
                  보유 주식 실시간 전량 청산 주의
                </span>
                <p className="text-[11px] text-rose-600 dark:text-rose-400">
                  실거래 계좌의 주식이 즉시 매도 발주됩니다. 실행하시려면 아래 입력창에 <strong>"전량청산"</strong>을 정확히 입력해주세요.
                </p>
                <input
                  type="text"
                  placeholder="전량청산"
                  value={liquidateConfirmText}
                  onChange={(e) => setLiquidateConfirmText(e.target.value)}
                  className="w-full rounded-lg border border-rose-300 dark:border-rose-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-xs font-bold text-rose-600 focus:ring-2 focus:ring-rose-500"
                />
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                disabled={stopLoading}
                onClick={() => setStopTargetTpl(null)}
                className="px-4 py-2 text-xs font-semibold rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50"
              >
                닫기
              </button>
              <button
                type="button"
                disabled={
                  stopLoading ||
                  (stopMode === 'terminate_and_liquidate' && liquidateConfirmText.trim() !== '전량청산')
                }
                onClick={handleStopSubmit}
                className={`flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-xl text-white disabled:opacity-50 shadow-xs ${
                  stopMode === 'terminate_and_liquidate'
                    ? 'bg-red-600 hover:bg-red-700'
                    : stopMode === 'stop_and_cancel'
                    ? 'bg-rose-600 hover:bg-rose-700'
                    : 'bg-amber-600 hover:bg-amber-700'
                }`}
              >
                {stopLoading && <Loader2 size={13} className="animate-spin" />}
                <span>
                  {stopMode === 'terminate_and_liquidate'
                    ? '확인, 기보유 전량 청산 매도 실행'
                    : stopMode === 'stop_and_cancel'
                    ? '확인, 주문 취소 및 전략 정지'
                    : '확인, 일시정지'}
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
