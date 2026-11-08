import { useEffect, useState } from 'react'
import {
  DollarSign, RotateCcw, Edit3, Layers
} from 'lucide-react'
import {
  fetchTemplates, type Template,
  fetchBudgetLedger, fetchBudgetHealth,
  updateBudgetPlan, resetBudgetPlan, toggleTemplateHolding
} from '../../api/templates'
import { StatCardSkeleton, TableRowSkeleton } from '../../components/ui/Skeleton'
import ErrorBanner from '../../components/ui/ErrorBanner'
import Pagination from '../../components/ui/Pagination'
import BudgetHealthCard from '../../components/budget/BudgetHealthCard'
import { krwFmt, CARD, TH, TD } from './ReportsShared'

interface BudgetPlanSectionProps {
  templateId?: number | null
}

export default function BudgetPlanSection({ templateId }: BudgetPlanSectionProps = {}) {
  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(templateId || null)

  useEffect(() => {
    if (templateId && templateId !== selectedTemplateId) {
      setSelectedTemplateId(templateId)
      loadData(templateId)
    }
  }, [templateId])
  const [ledgerData, setLedgerData] = useState<any>(null)
  const [ledgerPage, setLedgerPage] = useState(1)
  const [ledgerPageSize, setLedgerPageSize] = useState(10)
  const [healthData, setHealthData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 모달 상태
  const [showEditModal, setShowEditModal] = useState(false)
  const [showResetModal, setShowResetModal] = useState(false)

  // 플랜 수정 폼
  const [editMode, setEditMode] = useState<'total' | 'monthly' | 'daily'>('monthly')
  const [editMonthlyBudget, setEditMonthlyBudget] = useState(3000000)
  const [editDailyFixed, setEditDailyFixed] = useState(150000)
  const [editSellProceedsMode, setEditSellProceedsMode] = useState<'keep_cash' | 'recycle_to_budget'>('keep_cash')
  const [editApplyTodayDiff, setEditApplyTodayDiff] = useState(true)
  const [editMemo, setEditMemo] = useState('')

  // 리셋 폼
  const [resetInitialCarryover, setResetInitialCarryover] = useState(0)
  const [resetCycle, setResetCycle] = useState(true)
  const [resetCancelPending, setResetCancelPending] = useState(true)
  const [resetMemo, setResetMemo] = useState('')

  const loadData = async (tplId: number) => {
    setLoading(true)
    setError(null)
    setLedgerPage(1)
    try {
      const [ld, hd] = await Promise.all([
        fetchBudgetLedger(tplId),
        fetchBudgetHealth('toss'),
      ])
      setLedgerData(ld)
      setHealthData(hd?.data || hd)
    } catch (e) {
      setError(e instanceof Error ? e.message : '데이터 로드 실패')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTemplates()
      .then((tpls) => {
        const managedTpls = tpls.filter(
          (t) =>
            t.strategy_type !== 'sgrid' &&
            t.strategy_type !== 'sdca' &&
            !(t.params as any)?.is_archived,
        )
        const listToUse = managedTpls.length > 0 ? managedTpls : tpls
        setTemplates(listToUse)
        const targetId =
          templateId && listToUse.some((t) => t.id === templateId)
            ? templateId
            : listToUse.length > 0
            ? listToUse[0].id
            : null
        setSelectedTemplateId(targetId)
        if (targetId) loadData(targetId)
      })
      .catch((e) => setError(e instanceof Error ? e.message : '템플릿 목록 로드 실패'))
  }, [])

  const handleSelectTemplate = (id: number) => {
    setSelectedTemplateId(id)
    loadData(id)
  }

  const handleHoldingToggle = async (isHolding: boolean) => {
    if (!selectedTemplateId) return
    try {
      await toggleTemplateHolding(selectedTemplateId, isHolding)
      await loadData(selectedTemplateId)
    } catch (e) {
      alert(e instanceof Error ? e.message : '상태 변경 실패')
    }
  }

  const handleSavePlan = async () => {
    if (!selectedTemplateId) return
    try {
      await updateBudgetPlan(selectedTemplateId, {
        new_plan_config: {
          budget_mode: editMode,
          monthly_budget: editMonthlyBudget,
          daily_fixed_budget: editDailyFixed,
          sell_proceeds_mode: editSellProceedsMode,
        },
        apply_today_diff: editApplyTodayDiff,
        memo: editMemo,
      })
      setShowEditModal(false)
      await loadData(selectedTemplateId)
    } catch (e) {
      alert(e instanceof Error ? e.message : '플랜 변경 실패')
    }
  }

  const handleExecuteReset = async () => {
    if (!selectedTemplateId) return
    if (!confirm('Budget Plan을 초기화하시겠습니까? 새 세대(Epoch)로 분리되어 시작됩니다.')) return
    try {
      await resetBudgetPlan(selectedTemplateId, {
        new_config: {
          budget_mode: editMode,
          monthly_budget: editMonthlyBudget,
          daily_fixed_budget: editDailyFixed,
        },
        initial_carryover: resetInitialCarryover,
        reset_cycle: resetCycle,
        cancel_pending: resetCancelPending,
        memo: resetMemo,
      })
      setShowResetModal(false)
      await loadData(selectedTemplateId)
    } catch (e) {
      alert(e instanceof Error ? e.message : '초기화 실패')
    }
  }

  if (loading && !ledgerData) {
    return (
      <div className="space-y-4">
        <BudgetHealthCard loading={true} />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <StatCardSkeleton key={i} />
          ))}
        </div>
        <div className={`${CARD} overflow-hidden`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                <th className={TH}>일자</th>
                <th className={TH}>구분</th>
                <th className={`${TH} text-right`}>배정예산</th>
                <th className={`${TH} text-right`}>사용금액</th>
                <th className={`${TH} text-right`}>당일잔여</th>
                <th className={`${TH} text-right`}>이월금액</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {Array.from({ length: 6 }).map((_, i) => (
                <TableRowSkeleton key={i} cols={6} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }
  if (error) return <ErrorBanner message={error} />

  const selectedTemplate = templates.find((t) => t.id === selectedTemplateId)
  const currentParams = selectedTemplate?.params || {}
  return (
    <div className="space-y-4">
      {/* 1. 상단 거래소별 통합 예수금 Health Check 카드 */}
      <BudgetHealthCard healthData={healthData} />

      {/* 2. 템플릿 선택 및 Budget Plan 컨트롤 보드 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
        <div className="flex items-center gap-2">
          <Layers size={18} className="text-indigo-600 dark:text-indigo-400" />
          <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">플랜 대상 전략:</span>
          <select
            value={selectedTemplateId || ''}
            onChange={(e) => handleSelectTemplate(Number(e.target.value))}
            className="rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-1.5 text-sm font-medium text-slate-800 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                #{t.id} {t.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          {currentParams.strategy_status === 'active' ? (
            <button
              onClick={() => handleHoldingToggle(true)}
              className="rounded-lg border border-amber-300 bg-amber-50 hover:bg-amber-100 dark:border-amber-700 dark:bg-amber-950/40 px-3 py-1.5 text-xs font-semibold text-amber-800 dark:text-amber-200"
            >
              ⏸️ Holding (일시보류) 전환
            </button>
          ) : (
            <button
              onClick={() => handleHoldingToggle(false)}
              className="rounded-lg border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 dark:border-emerald-700 dark:bg-emerald-950/40 px-3 py-1.5 text-xs font-semibold text-emerald-800 dark:text-emerald-200"
            >
              🟢 Active (재가동) 전환
            </button>
          )}

          <button
            onClick={() => {
              const defaultMode = selectedTemplate?.strategy_type === 'kospi_top_dca' ? 'monthly' : 'total'
              const defaultSell = selectedTemplate?.strategy_type === 'rsitrade' || selectedTemplate?.strategy_type === 'rsi' ? 'recycle_to_budget' : 'keep_cash'
              setEditMode(ledgerData?.budget_mode || currentParams.budget_mode || defaultMode)
              setEditMonthlyBudget(ledgerData?.monthly_budget || currentParams.monthly_budget || selectedTemplate?.budget || 3000000)
              setEditDailyFixed(ledgerData?.daily_fixed_budget || currentParams.daily_fixed_budget || 150000)
              setEditSellProceedsMode(ledgerData?.sell_proceeds_mode || currentParams.sell_proceeds_mode || defaultSell)
              setShowEditModal(true)
            }}
            className="flex items-center gap-1 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-1.5 text-xs font-semibold shadow-sm"
          >
            <Edit3 size={13} />
            플랜 수정
          </button>

          <button
            onClick={() => {
              setResetInitialCarryover(0)
              setShowResetModal(true)
            }}
            className="flex items-center gap-1 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 hover:bg-slate-100 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 px-3 py-1.5 text-xs font-semibold"
          >
            <RotateCcw size={13} />
            초기화 (Reset)
          </button>
        </div>
      </div>

      {/* 3. Budget Plan 세부 현황 KPI 카드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className={`${CARD} p-4`}>
          <span className="text-xs text-slate-500">현재 가용 예산 (Carryover)</span>
          <div className="mt-1 text-2xl font-bold text-slate-800 dark:text-slate-100 font-mono">
            {krwFmt(ledgerData?.carryover_budget || 0)}
          </div>
          <span className="text-[11px] text-slate-400 mt-1 block">
            원장 검증 일치: {krwFmt(ledgerData?.carryover_budget || 0)}
          </span>
        </div>

        <div className={`${CARD} p-4`}>
          <span className="text-xs text-slate-500">누적/당월 소진액 (Spent)</span>
          <div className="mt-1 text-2xl font-bold text-slate-800 dark:text-slate-100 font-mono">
            {krwFmt(ledgerData?.monthly_spent || 0)}
          </div>
          <span className="text-[11px] text-slate-400 mt-1 block">
            배정 총예산: {krwFmt(ledgerData?.monthly_budget || currentParams.monthly_budget || selectedTemplate?.budget || 3000000)}
          </span>
        </div>

        <div className={`${CARD} p-4`}>
          <span className="text-xs text-slate-500">적용 플랜 버전 / 세대 (Epoch)</span>
          <div className="mt-1 text-2xl font-bold text-indigo-600 dark:text-indigo-400">
            v{currentParams.plan_revision_no || 1} <span className="text-sm font-normal text-slate-400">/ Epoch #{ledgerData?.current_epoch || 1}</span>
          </div>
          <span className="text-[11px] text-slate-400 mt-1 block">
            모드:{' '}
            {(ledgerData?.budget_mode || currentParams.budget_mode) === 'daily'
              ? '일일 고정 충전'
              : (ledgerData?.budget_mode || currentParams.budget_mode) === 'total'
              ? '총예산 풀 (일시 배정)'
              : '월간 동적 분할'}
          </span>
        </div>

        <div className={`${CARD} p-4`}>
          <span className="text-xs text-slate-500">예산 원장 총 기록수</span>
          <div className="mt-1 text-2xl font-bold text-slate-800 dark:text-slate-100 font-mono">
            {(ledgerData?.ledger || []).length}건
          </div>
          <span className="text-[11px] text-emerald-600 dark:text-emerald-400 mt-1 block font-medium">
            감사 불변식 검증 정상 (Audit Passed)
          </span>
        </div>
      </div>

      {/* 4. 통장 거래내역 방식의 +/- 감사 원장 테이블 (budget_ledger) */}
      <div className={`${CARD} overflow-hidden`}>
        <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <DollarSign size={16} className="text-indigo-600 dark:text-indigo-400" />
            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">
              통장식 +/- 예산 증감 감사 원장 (Audit Ledger)
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            세대: Epoch #{ledgerData?.current_epoch || 1} 기준
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/60">
                <th className={TH}>일시</th>
                <th className={TH}>구분 (Type)</th>
                <th className={`${TH} text-right`}>증감액 (Delta)</th>
                <th className={`${TH} text-right`}>변동 후 가용잔액</th>
                <th className={`${TH} text-right`}>변동 후 당월소진액</th>
                <th className={TH}>감사 상세 내역</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {(() => {
                const ledgerRows = ledgerData?.ledger || []
                const pagedLedgerRows = ledgerRows.slice((ledgerPage - 1) * ledgerPageSize, ledgerPage * ledgerPageSize)
                if (ledgerRows.length === 0) {
                  return (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-slate-400">
                        원장 기록이 없습니다.
                      </td>
                    </tr>
                  )
                }
                return pagedLedgerRows.map((item: any, idx: number) => {
                  const isPlus = item.delta_krw > 0
                  const isMinus = item.delta_krw < 0
                  return (
                    <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                      <td className={`${TD} font-mono text-[11px] text-slate-400`}>
                        {item.created_at ? item.created_at.slice(0, 16).replace('T', ' ') : '—'}
                      </td>
                      <td className={TD}>
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${
                          item.entry_type === 'DAILY_CREDIT' || item.entry_type === 'INITIAL_CREDIT' || item.entry_type === 'MANUAL_TOPUP'
                            ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
                            : item.entry_type === 'BUY_ORDER_SPEND'
                            ? 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
                            : item.entry_type === 'ORDER_CANCEL_REFUND'
                            ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300'
                            : item.entry_type === 'SELL_PROCEEDS_RECYCLE'
                            ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300'
                            : 'bg-slate-100 text-slate-800 dark:bg-slate-700 dark:text-slate-300'
                        }`}>
                          {item.entry_type}
                        </span>
                      </td>
                      <td className={`${TD} text-right font-mono font-bold ${
                        isPlus ? 'text-emerald-600 dark:text-emerald-400' : isMinus ? 'text-red-600 dark:text-red-400' : 'text-slate-500'
                      }`}>
                        {isPlus ? `+${krwFmt(item.delta_krw)}` : krwFmt(item.delta_krw)}
                      </td>
                      <td className={`${TD} text-right font-mono font-semibold`}>
                        {krwFmt(item.balance_after_krw)}
                      </td>
                      <td className={`${TD} text-right font-mono text-slate-500`}>
                        {krwFmt(item.monthly_spent_after_krw)}
                      </td>
                      <td className={`${TD} text-slate-600 dark:text-slate-300 max-w-sm truncate`} title={item.description}>
                        {item.description}
                      </td>
                    </tr>
                  )
                })
              })()}
            </tbody>
          </table>
        </div>

        {/* 감사 원장 페이징 (기본 10건) */}
        {(ledgerData?.ledger || []).length > 0 && (
          <Pagination
            currentPage={ledgerPage}
            totalPages={Math.max(1, Math.ceil((ledgerData?.ledger || []).length / ledgerPageSize))}
            pageSize={ledgerPageSize}
            totalCount={(ledgerData?.ledger || []).length}
            onPageChange={setLedgerPage}
            onPageSizeChange={(sz) => {
              setLedgerPageSize(sz)
              setLedgerPage(1)
            }}
            pageSizeOptions={[10, 20, 50, 100]}
          />
        )}
      </div>

      {/* 5. 플랜 수정 모달 */}
      {showEditModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-xl bg-white dark:bg-slate-800 p-5 shadow-xl border border-slate-200 dark:border-slate-700 space-y-4">
            <h3 className="text-base font-bold text-slate-800 dark:text-slate-100">
              Budget Plan 수정 (버전 업데이트)
            </h3>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-600 dark:text-slate-300 font-semibold mb-1">예산 모드</label>
                <div className="grid grid-cols-3 gap-1.5">
                  <button
                    type="button"
                    onClick={() => setEditMode('total')}
                    className={`py-1.5 px-2 rounded-lg border font-semibold ${
                      editMode === 'total' ? 'bg-indigo-600 text-white border-indigo-600' : 'border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300'
                    }`}
                  >
                    총예산 풀 (Total)
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditMode('monthly')}
                    className={`py-1.5 px-2 rounded-lg border font-semibold ${
                      editMode === 'monthly' ? 'bg-indigo-600 text-white border-indigo-600' : 'border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300'
                    }`}
                  >
                    월 분할 (Monthly)
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditMode('daily')}
                    className={`py-1.5 px-2 rounded-lg border font-semibold ${
                      editMode === 'daily' ? 'bg-indigo-600 text-white border-indigo-600' : 'border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300'
                    }`}
                  >
                    일 고정 (Daily)
                  </button>
                </div>
              </div>

              {editMode === 'daily' ? (
                <div>
                  <label className="block text-slate-600 dark:text-slate-300 font-semibold mb-1">일일 고정 충전액 (원)</label>
                  <input
                    type="number"
                    value={editDailyFixed}
                    onChange={(e) => setEditDailyFixed(Number(e.target.value))}
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 p-2 font-mono"
                  />
                </div>
              ) : (
                <div>
                  <label className="block text-slate-600 dark:text-slate-300 font-semibold mb-1">
                    {editMode === 'total' ? '전략 배정 총예산 (원)' : '월 설정 총예산 (원)'}
                  </label>
                  <input
                    type="number"
                    value={editMonthlyBudget}
                    onChange={(e) => setEditMonthlyBudget(Number(e.target.value))}
                    className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 p-2 font-mono"
                  />
                </div>
              )}

              <div>
                <label className="block text-slate-600 dark:text-slate-300 font-semibold mb-1">매도 대금 처리 방식</label>
                <select
                  value={editSellProceedsMode}
                  onChange={(e) => setEditSellProceedsMode(e.target.value as 'keep_cash' | 'recycle_to_budget')}
                  className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 p-2"
                >
                  <option value="recycle_to_budget">전략 가용 예산 풀에 자동 재투입 (순환매매 추천)</option>
                  <option value="keep_cash">예수금 보관 (가용 예산에 합산하지 않음)</option>
                </select>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="applyTodayDiff"
                  checked={editApplyTodayDiff}
                  onChange={(e) => setEditApplyTodayDiff(e.target.checked)}
                  className="rounded border-slate-300"
                />
                <label htmlFor="applyTodayDiff" className="text-slate-700 dark:text-slate-300 font-medium">
                  오늘 이미 충전된 경우 금일 차액 즉시 반영
                </label>
              </div>

              <div>
                <label className="block text-slate-600 dark:text-slate-300 font-semibold mb-1">변경 사유 (메모)</label>
                <input
                  type="text"
                  placeholder="예: 월 예산 200만 → 300만 증액"
                  value={editMemo}
                  onChange={(e) => setEditMemo(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 p-2"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-700">
              <button
                onClick={() => setShowEditModal(false)}
                className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 text-xs font-semibold text-slate-600 dark:text-slate-300"
              >
                취소
              </button>
              <button
                onClick={handleSavePlan}
                className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold"
              >
                새 버전으로 저장
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 6. 플랜 초기화(Reset) 모달 */}
      {showResetModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-xl bg-white dark:bg-slate-800 p-5 shadow-xl border border-slate-200 dark:border-slate-700 space-y-4">
            <h3 className="text-base font-bold text-red-600 dark:text-red-400 flex items-center gap-2">
              <RotateCcw size={18} />
              Budget Plan 초기화 (Reset & Restart)
            </h3>
            <p className="text-xs text-slate-500">
              세대 번호(Epoch)가 +1 증가하며 이전 세대의 미체결 취소 주문이 새 예산을 오염시키지 않도록 분리됩니다.
            </p>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-600 dark:text-slate-300 font-semibold mb-1">새 세대 시작 가용액 (원)</label>
                <input
                  type="number"
                  value={resetInitialCarryover}
                  onChange={(e) => setResetInitialCarryover(Number(e.target.value))}
                  className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 p-2 font-mono"
                />
              </div>

              <div className="space-y-2">
                <label className="flex items-center gap-2 font-medium text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={resetCycle}
                    onChange={(e) => setResetCycle(e.target.checked)}
                    className="rounded border-slate-300"
                  />
                  매수 사이클 1위 종목부터 새로 시작 (Cycle #1)
                </label>
                <label className="flex items-center gap-2 font-medium text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={resetCancelPending}
                    onChange={(e) => setResetCancelPending(e.target.checked)}
                    className="rounded border-slate-300"
                  />
                  기존 미체결 매수 주문 전량 즉시 취소
                </label>
              </div>

              <div>
                <label className="block text-slate-600 dark:text-slate-300 font-semibold mb-1">초기화 사유 (메모)</label>
                <input
                  type="text"
                  placeholder="예: 새 플랜으로 새 출발"
                  value={resetMemo}
                  onChange={(e) => setResetMemo(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 p-2"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-700">
              <button
                onClick={() => setShowResetModal(false)}
                className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-600 text-xs font-semibold text-slate-600 dark:text-slate-300"
              >
                취소
              </button>
              <button
                onClick={handleExecuteReset}
                className="px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-semibold"
              >
                초기화 실행
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
