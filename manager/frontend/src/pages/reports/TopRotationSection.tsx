import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  RotateCw,
  TrendingUp,
  DollarSign,
  Clock,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  Target,
  Calendar,
  Check,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  ArrowRight,
  X,
  Loader2,
} from 'lucide-react'
import { fetchTemplates, type Template } from '../../api/templates'
import { fetchTopRotationReport, type TopRotationReport } from '../../api/reports'
import { manualTopupTemplate } from '../../api/templates'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { krwFmt, CARD, TH, TD } from './ReportsShared'

interface TopRotationSectionProps {
  templateId?: number | null
}

export default function TopRotationSection({ templateId }: TopRotationSectionProps = {}) {
  const [templates, setTemplates] = useState<Template[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(templateId || null)
  const [report, setReport] = useState<TopRotationReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedGroupNo, setSelectedGroupNo] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [exchangeFilter, setExchangeFilter] = useState<string>('all')
  const [expandedDailyDates, setExpandedDailyDates] = useState<Set<string>>(new Set())
  const [flowFilter, setFlowFilter] = useState<'all' | 'buys' | 'sells'>('all')

  // 수동 충전 모달 상태
  const [topupOpen, setTopupOpen] = useState(false)
  const [topupAmount, setTopupAmount] = useState<number>(100000)
  const [topupMemo, setTopupMemo] = useState<string>('')
  const [topupLoading, setTopupLoading] = useState(false)

  useEffect(() => {
    if (templateId) {
      setSelectedTemplateId(templateId)
      setSelectedGroupNo(null)
    }
  }, [templateId])

  useEffect(() => {
    if (templateId) {
      setSelectedTemplateId(templateId)
      return
    }
    fetchTemplates()
      .then((tpls) => {
        const topTpls = tpls.filter(
          (t) => t.strategy_type === 'kospi_top_dca' || t.name.includes('TOP'),
        )
        setTemplates(topTpls)
        if (topTpls.length > 0) {
          setSelectedTemplateId(topTpls[0].id)
        } else if (tpls.length > 0) {
          setSelectedTemplateId(tpls[0].id)
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : '템플릿 목록 로드 실패'))
      .finally(() => setLoading(false))
  }, [templateId])

  const handleTopup = async () => {
    if (!selectedTemplateId || topupAmount <= 0) return
    setTopupLoading(true)
    try {
      const res = await manualTopupTemplate(selectedTemplateId, topupAmount, topupMemo || '다음 타겟 부족액 즉시 충전')
      if (res.ok) {
        setTopupOpen(false)
        setTopupMemo('')
        // 리포트 새로고침
        const updated = await fetchTopRotationReport(selectedTemplateId, selectedGroupNo)
        setReport(updated)
      } else {
        alert(res.error || '충전에 실패했습니다.')
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : '충전 오류 발생')
    } finally {
      setTopupLoading(false)
    }
  }

  useEffect(() => {
    if (!selectedTemplateId) return
    setLoading(true)
    setError(null)
    fetchTopRotationReport(selectedTemplateId, selectedGroupNo)
      .then((res) => {
        setReport(res)
        // 가장 최근 일자 2개 자동 펼침
        if (res.daily_execution_flow && res.daily_execution_flow.length > 0) {
          const recentDates = res.daily_execution_flow.slice(0, 2).map((d) => d.date)
          setExpandedDailyDates(new Set(recentDates))
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : '리포트 데이터 로드 실패'))
      .finally(() => setLoading(false))
  }, [selectedTemplateId, selectedGroupNo])

  const toggleDailyDate = (date: string) => {
    setExpandedDailyDates((prev) => {
      const next = new Set(prev)
      if (next.has(date)) next.delete(date)
      else next.add(date)
      return next
    })
  }

  const filteredTemplates = templates.filter((t) => {
    if (exchangeFilter !== 'all' && t.exchange.toLowerCase() !== exchangeFilter) {
      return false
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase()
      const matchName = t.name.toLowerCase().includes(q)
      const matchId = String(t.id).includes(q)
      const matchEx = t.exchange.toLowerCase().includes(q)
      return matchName || matchId || matchEx
    }
    return true
  })

  const params = report?.template?.params || {}
  const cycleNo = params.cycle_no || 1
  const carryover = params.carryover_budget || 0
  const monthlySpent = params.monthly_spent || 0
  const monthlyBudget = params.monthly_budget || report?.template?.budget || 3000000
  const lastStatus = params.last_status_message || '정상 대기 중'

  const pipeline = report?.cycle_pipeline
  const nextTarget = pipeline?.next_target
  const dailyFlow = report?.daily_execution_flow || []

  return (
    <div className="space-y-5 break-keep">
      {/* 템플릿 선택 및 상단 컨트롤 바 */}
      {templateId ? (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-xs dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-2">
            <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-bold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
              시총 상위 TOP N 순위 회전 관제
            </span>
            <span className="text-xs text-slate-400">
              실시간 순위 추적 · 이탈 유예 매도 · 익일 사이클 매수 파이프라인
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 dark:text-slate-400">배치 필터:</span>
            <select
              value={selectedGroupNo === null ? '' : selectedGroupNo}
              onChange={(e) => setSelectedGroupNo(e.target.value === '' ? null : Number(e.target.value))}
              className="rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-2 py-1 text-xs text-slate-700 dark:text-slate-200"
            >
              <option value="">전체 배치</option>
              {(params.history || []).map((h: any) => (
                <option key={h.group_no} value={h.group_no}>
                  Batch #{h.group_no} ({h.date})
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                if (selectedTemplateId) {
                  setLoading(true)
                  fetchTopRotationReport(selectedTemplateId, selectedGroupNo)
                    .then(setReport)
                    .finally(() => setLoading(false))
                }
              }}
              className="flex items-center gap-1 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 px-2.5 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200"
            >
              <RotateCw size={13} className={loading ? 'animate-spin' : ''} />
              새로고침
            </button>
          </div>
        </div>
      ) : (
        <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-xs space-y-3">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
            {/* 전략 선택, 거래소 필터, 검색 */}
            <div className="flex flex-1 flex-wrap items-center gap-2">
              <div className="flex items-center gap-1.5 font-semibold text-sm text-slate-700 dark:text-slate-200">
                <Layers size={18} className="text-indigo-600 dark:text-indigo-400" />
                <span>전략:</span>
              </div>

              <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-700/60 p-0.5 rounded-lg text-xs">
                {['all', 'toss', 'kis', 'upbit', 'bithumb'].map((ex) => (
                  <button
                    key={ex}
                    onClick={() => setExchangeFilter(ex)}
                    className={`px-2 py-0.5 rounded-md font-medium transition-colors ${
                      exchangeFilter === ex
                        ? 'bg-white dark:bg-slate-800 text-indigo-600 dark:text-indigo-400 shadow-xs'
                        : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                    }`}
                  >
                    {ex === 'all' ? '전체' : ex.toUpperCase()}
                  </button>
                ))}
              </div>

              <input
                type="text"
                placeholder="전략명/#ID 검색..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-2.5 py-1 text-xs text-slate-800 dark:text-slate-100 placeholder-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500 w-32 sm:w-40"
              />

              <select
                value={selectedTemplateId || ''}
                onChange={(e) => setSelectedTemplateId(Number(e.target.value))}
                className="max-w-[220px] sm:max-w-[300px] truncate rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-1 text-xs sm:text-sm font-medium text-slate-800 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
              >
                {filteredTemplates.length === 0 ? (
                  <option value="" disabled>검색 결과 없음</option>
                ) : (
                  filteredTemplates.map((t) => (
                    <option key={t.id} value={t.id}>
                      #{t.id} {t.name} [{t.exchange.toUpperCase()}]
                    </option>
                  ))
                )}
              </select>
              <span className="text-[11px] text-slate-400">
                ({filteredTemplates.length}/{templates.length}개)
              </span>
            </div>

            {/* 우측 배치 필터 및 새로고침 */}
            <div className="flex items-center gap-2 self-end lg:self-auto">
              <span className="text-xs text-slate-500 dark:text-slate-400">배치 필터:</span>
              <select
                value={selectedGroupNo === null ? '' : selectedGroupNo}
                onChange={(e) => setSelectedGroupNo(e.target.value === '' ? null : Number(e.target.value))}
                className="rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-2 py-1 text-xs text-slate-700 dark:text-slate-200"
              >
                <option value="">전체 배치</option>
                {(params.history || []).map((h: any) => (
                  <option key={h.group_no} value={h.group_no}>
                    Batch #{h.group_no} ({h.date})
                  </option>
                ))}
              </select>
              <button
                onClick={() => {
                  if (selectedTemplateId) {
                    setLoading(true)
                    fetchTopRotationReport(selectedTemplateId, selectedGroupNo)
                      .then(setReport)
                      .finally(() => setLoading(false))
                  }
                }}
                className="flex items-center gap-1 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 px-2.5 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200"
              >
                <RotateCw size={13} className={loading ? 'animate-spin' : ''} />
                새로고침
              </button>
            </div>
          </div>
        </div>
      )}

      {error && <ErrorBanner message={error} />}

      {/* 핵심 상태 KPI 카드 4종 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs">
            <span>이월 잔여 가용 예산</span>
            <DollarSign size={15} className="text-emerald-500" />
          </div>
          <div className="mt-2 text-xl font-bold text-slate-800 dark:text-slate-100 font-mono">
            {krwFmt(carryover)}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            당월 소진: {krwFmt(monthlySpent)} / 월 {krwFmt(monthlyBudget)}
          </div>
        </div>

        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs">
            <span>현재 회전 사이클</span>
            <RotateCw size={15} className="text-indigo-500" />
          </div>
          <div className="mt-2 text-xl font-bold text-slate-800 dark:text-slate-100">
            Cycle #{cycleNo}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            완료: {pipeline?.bought_count ?? (params.current_cycle_bought || []).length} / {pipeline?.total_targets ?? 10}개 종목 ({pipeline?.progress_pct ?? 0}%)
          </div>
        </div>

        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs">
            <span>다음 매수 차례 (Next Target)</span>
            <Target size={15} className="text-amber-500" />
          </div>
          <div className="mt-2 text-base font-bold text-slate-800 dark:text-slate-100 truncate">
            {nextTarget ? `${nextTarget.rank}위 ${nextTarget.name}` : '전 종목 완료 (다음 사이클 준비)'}
          </div>
          <div className="mt-1 text-[11px] text-slate-400">
            {nextTarget ? `필요: ${krwFmt(nextTarget.required_krw)} (${nextTarget.budget_sufficient ? '예산충분' : '부족'})` : '사이클 완주 대기'}
          </div>
        </div>

        <div className={`${CARD} p-4`}>
          <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs">
            <span>전략 운용 상태</span>
            <CheckCircle2 size={15} className="text-blue-500" />
          </div>
          <div className="mt-2 text-base font-bold text-slate-800 dark:text-slate-100">
            {params.strategy_status === 'active' ? '🟢 가동중 (Active)' : '⏸️ 일시보류 (Holding)'}
          </div>
          <div className="mt-1 text-[11px] text-slate-400 truncate" title={lastStatus}>
            {lastStatus}
          </div>
        </div>
      </div>

      {/* =========================================================================
          [1] 🎯 다음 매수 타겟 하이라이트 & 현재 사이클 순환 파이프라인
          ========================================================================= */}
      {pipeline && (
        <div className={`${CARD} p-5 space-y-4`}>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Target size={18} className="text-indigo-600 dark:text-indigo-400" />
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Cycle #{pipeline.cycle_no} 순환 모으기 진행 상황 & 다음 매수 타겟
              </h3>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-500">진행률:</span>
              <div className="h-2 w-28 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-600 dark:bg-indigo-400 rounded-full transition-all duration-300"
                  style={{ width: `${pipeline.progress_pct}%` }}
                />
              </div>
              <span className="font-bold font-mono text-indigo-600 dark:text-indigo-400">
                {pipeline.bought_count}/{pipeline.total_targets}개 ({pipeline.progress_pct}%)
              </span>
            </div>
          </div>

          {/* 다음 매수 타겟 하이라이트 배너 */}
          {nextTarget && (
            <div
              className={`rounded-2xl p-4 border flex flex-col md:flex-row md:items-center justify-between gap-4 transition-all ${
                nextTarget.budget_sufficient
                  ? 'border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/50 dark:bg-emerald-950/20'
                  : 'border-amber-200 bg-amber-50/60 dark:border-amber-900/50 dark:bg-amber-950/20'
              }`}
            >
              <div className="flex items-center gap-3.5">
                <div
                  className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${
                    nextTarget.budget_sufficient
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300'
                      : 'bg-amber-100 text-amber-700 dark:bg-amber-900/60 dark:text-amber-300'
                  }`}
                >
                  <Target size={22} />
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="rounded-md bg-white dark:bg-slate-800 px-2 py-0.5 text-xs font-black shadow-xs">
                      🎯 다음 매수 타겟
                    </span>
                    <span className="font-extrabold text-base text-slate-900 dark:text-white">
                      {nextTarget.rank}위 {nextTarget.name}
                    </span>
                    <span className="text-xs text-slate-400 font-mono">({nextTarget.code})</span>
                    {nextTarget.note && (
                      <span className="text-[11px] text-indigo-600 dark:text-indigo-400 font-medium">
                        · {nextTarget.note}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-300 mt-1">
                    다음 정기 배치(매일 {params.schedule_time || '09:10'}) 실행 시 이 종목을 우선 매수합니다.
                  </p>
                </div>
              </div>

              {/* 금액 및 예산 충족 상태 */}
              <div className="flex items-center gap-4 text-xs font-mono self-end md:self-auto">
                <div className="text-right">
                  <span className="text-slate-400 text-[10px] block">예상 매수단가 × 수량</span>
                  <span className="font-bold text-slate-800 dark:text-slate-100">
                    {krwFmt(nextTarget.price)} × {nextTarget.target_qty}주
                  </span>
                </div>
                <div className="text-right pl-3 border-l border-slate-300 dark:border-slate-700">
                  <span className="text-slate-400 text-[10px] block">필요 주문금액</span>
                  <span className="font-bold text-slate-900 dark:text-white text-sm">
                    {krwFmt(nextTarget.required_krw)}
                  </span>
                </div>
                <div className="pl-3 border-l border-slate-300 dark:border-slate-700">
                  {nextTarget.budget_sufficient ? (
                    <span className="inline-flex items-center gap-1 rounded-lg bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200">
                      <Check size={13} />
                      예산 충분 (가용 {krwFmt(nextTarget.carryover_budget)})
                    </span>
                  ) : (
                    <div className="flex items-center gap-1.5">
                      <span className="inline-flex items-center gap-1 rounded-lg bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-800 dark:bg-amber-900/60 dark:text-amber-200">
                        <AlertTriangle size={13} />
                        부족 {krwFmt(nextTarget.shortfall)}
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          setTopupAmount(Math.ceil((nextTarget.shortfall || 100000) / 10000) * 10000)
                          setTopupMemo(`${nextTarget.name} 매수 부족액 충전`)
                          setTopupOpen(true)
                        }}
                        className="rounded-lg bg-indigo-600 hover:bg-indigo-700 px-2.5 py-1 text-xs font-bold text-white shadow-xs transition-colors shrink-0"
                      >
                        +부족액 즉시 충전
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 1위~10위 타겟 순위별 순환 파이프라인 카드 그리드 */}
          <div>
            <div className="text-xs font-bold text-slate-700 dark:text-slate-300 mb-2">
              타겟 순위 구간 ({pipeline.rank_start}위 ~ {pipeline.rank_end}위) 사이클 상태:
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2.5">
              {pipeline.pipeline.map((item) => {
                const isBought = item.status === 'bought'
                const isNext = item.status === 'next'
                const isHeld = (report?.holdings_status || []).some(
                  (h) => h.ticker === item.code && h.qty > 0,
                )

                return (
                  <div
                    key={item.code}
                    className={`rounded-xl border p-2.5 transition-all text-xs relative ${
                      isNext
                        ? 'border-indigo-500 bg-indigo-50/40 ring-2 ring-indigo-500/20 shadow-xs dark:bg-indigo-950/30'
                        : isBought
                        ? isHeld
                          ? 'border-emerald-200 bg-emerald-50/30 dark:border-emerald-900/40 dark:bg-emerald-950/10'
                          : 'border-violet-200 bg-violet-50/30 dark:border-violet-900/40 dark:bg-violet-950/10'
                        : 'border-slate-200 bg-slate-50/50 dark:border-slate-800 dark:bg-slate-800/30 opacity-70'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="rounded-md bg-white dark:bg-slate-800 px-1.5 py-0.5 text-[10px] font-bold shadow-xs">
                        {item.rank}위
                      </span>
                      {isBought ? (
                        isHeld ? (
                          <span className="inline-flex items-center gap-0.5 text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
                            <Check size={11} /> 매수체결
                          </span>
                        ) : (
                          <span
                            className="inline-flex items-center gap-0.5 text-[10px] font-bold text-violet-600 dark:text-violet-400"
                            title="주문이 발주되어 예약 대기 중입니다. 정규장 개장 후 체결되면 포지션에 반영됩니다."
                          >
                            <Clock size={11} /> 예약대기
                          </span>
                        )
                      ) : isNext ? (
                        <span className="inline-flex items-center gap-0.5 text-[10px] font-bold text-indigo-600 dark:text-indigo-400 animate-pulse">
                          🎯 내일 타겟
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-400 font-medium">대기</span>
                      )}
                    </div>
                    <div className="mt-1.5 font-bold text-slate-900 dark:text-white truncate">
                      {item.name}
                    </div>
                    <div className="mt-0.5 font-mono text-[11px] text-slate-500 dark:text-slate-400 flex items-center justify-between">
                      <span>{krwFmt(item.price)}</span>
                      <span>{item.target_qty}주</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          [2] 📅 일단위 실행 흐름 & 당일 순위/체결 히스토리 (Daily Timeline)
          ========================================================================= */}
      <div className={`${CARD} p-5 space-y-4`}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 dark:border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Calendar size={18} className="text-indigo-600 dark:text-indigo-400" />
            <div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                일단위 실행 흐름 & 당일 순위·체결 히스토리 (최근 {dailyFlow.length}영업일)
              </h3>
              <p className="text-[11px] text-slate-400">
                하루 단위로 어떤 종목이 순위에 있었고 매수/매도되었는지 추적합니다.
              </p>
            </div>
          </div>

          {/* 타임라인 필터 칩 */}
          <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 p-0.5 rounded-xl text-xs self-end sm:self-auto">
            <button
              type="button"
              onClick={() => setFlowFilter('all')}
              className={`px-2.5 py-1 rounded-lg font-medium transition-colors ${
                flowFilter === 'all'
                  ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-300 font-bold shadow-xs'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              전체 ({dailyFlow.length})
            </button>
            <button
              type="button"
              onClick={() => setFlowFilter('buys')}
              className={`px-2.5 py-1 rounded-lg font-medium transition-colors ${
                flowFilter === 'buys'
                  ? 'bg-white dark:bg-slate-700 text-rose-600 font-bold shadow-xs'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              매수 체결일 ({dailyFlow.filter((f) => f.buys && f.buys.length > 0).length})
            </button>
            <button
              type="button"
              onClick={() => setFlowFilter('sells')}
              className={`px-2.5 py-1 rounded-lg font-medium transition-colors ${
                flowFilter === 'sells'
                  ? 'bg-white dark:bg-slate-700 text-blue-600 font-bold shadow-xs'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              이탈 매도일 ({dailyFlow.filter((f) => f.sells && f.sells.length > 0).length})
            </button>
          </div>
        </div>

        {dailyFlow.length === 0 ? (
          <div className="py-8 text-center text-xs text-slate-400">
            아직 실행된 일단위 배치 히스토리가 없습니다. (첫 배치 실행 대기)
          </div>
        ) : (
          <div className="space-y-3">
            {dailyFlow
              .filter((flow) => {
                if (flowFilter === 'buys') return flow.buys && flow.buys.length > 0
                if (flowFilter === 'sells') return flow.sells && flow.sells.length > 0
                return true
              })
              .map((flow) => {
              const isExpanded = expandedDailyDates.has(flow.date)
              const hasBuys = flow.buys && flow.buys.length > 0
              const hasSells = flow.sells && flow.sells.length > 0

              return (
                <div
                  key={`${flow.date}_${flow.group_no}`}
                  className="rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900/60 overflow-hidden transition-all shadow-xs"
                >
                  {/* 일단위 카드 헤더 요약 */}
                  <div
                    onClick={() => toggleDailyDate(flow.date)}
                    className="p-3.5 sm:p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                  >
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <span className="rounded-lg bg-indigo-100 px-2.5 py-1 text-xs font-mono font-bold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                        {flow.date}
                      </span>
                      <span className="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-bold text-slate-700 dark:text-slate-300 font-mono">
                        Batch #{flow.group_no}
                      </span>
                      <span className="text-xs text-slate-400">Cycle #{flow.cycle_no}</span>

                      {/* 당일 매수 성공/매도 결과 뱃지 */}
                      {hasBuys ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-0.5 text-[11px] font-bold text-rose-600 dark:bg-rose-950/40 dark:text-rose-400">
                          <Check size={12} />
                          매수 성공 {flow.buys.length}건 ({flow.buys.map((b) => `${b.name} ${b.volume}주`).join(', ')})
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                          당일 매수 없음 (예산 이월)
                        </span>
                      )}

                      {hasSells && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-[11px] font-bold text-blue-600 dark:bg-blue-950/40 dark:text-blue-400">
                          이탈 매도 {flow.sells.length}건
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-3 self-end sm:self-auto text-xs">
                      <span className="font-mono text-slate-500">
                        잔여 예산: {krwFmt(flow.carryover_budget)}
                      </span>
                      <button
                        type="button"
                        className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                      >
                        <span>{isExpanded ? '순위·상세 접기' : '당일 순위·상세 보기'}</span>
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                    </div>
                  </div>

                  {/* 아코디언 펼침 내용: 당일 TOP 10 순위 스냅샷 + 체결 내역 + 익일 예고 */}
                  {isExpanded && (
                    <div className="border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-4 space-y-3.5 text-xs">
                      {/* 당일 해당 순위에 어떤 종목이 있었는지 (마켓 스냅샷) */}
                      <div>
                        <div className="text-[11px] font-bold text-slate-500 dark:text-slate-400 mb-1.5 flex items-center gap-1">
                          <Layers size={13} />
                          <span>당일 마켓 TOP N 순위 스냅샷:</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {(flow.snapshot_top || []).map((sp) => (
                            <span
                              key={sp.code}
                              className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800 px-2 py-1 font-mono text-[11px]"
                            >
                              <span className="font-bold text-indigo-600 dark:text-indigo-400">
                                {sp.rank}위
                              </span>
                              <span className="font-semibold text-slate-800 dark:text-slate-200">
                                {sp.name}
                              </span>
                              <span className="text-slate-400">({krwFmt(sp.price)})</span>
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* 당일 매수 / 매도 주문 상세 내역 */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-3">
                          <span className="text-[11px] font-bold text-rose-600 dark:text-rose-400 block mb-1.5">
                            🛒 당일 모으기 매수 체결 ({flow.buys.length}건)
                          </span>
                          {flow.buys.length === 0 ? (
                            <p className="text-slate-400 text-[11px]">매수 체결 내역 없음</p>
                          ) : (
                            <div className="space-y-1">
                              {flow.buys.map((b) => (
                                <div
                                  key={b.code}
                                  className="flex items-center justify-between font-mono text-[11px] bg-slate-50 dark:bg-slate-800/60 p-1.5 rounded"
                                >
                                  <span className="font-bold text-slate-800 dark:text-slate-200">
                                    {b.rank ? `${b.rank}위 ` : ''}{b.name} ({b.volume}주)
                                  </span>
                                  <span className="text-slate-600 dark:text-slate-300">
                                    @{krwFmt(b.price)} = {krwFmt(b.cost)}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 p-3">
                          <span className="text-[11px] font-bold text-blue-600 dark:text-blue-400 block mb-1.5">
                            📉 당일 이탈 분할매도 ({flow.sells.length}건)
                          </span>
                          {flow.sells.length === 0 ? (
                            <p className="text-slate-400 text-[11px]">이탈 매도 내역 없음</p>
                          ) : (
                            <div className="space-y-1">
                              {flow.sells.map((s) => (
                                <div
                                  key={s.code}
                                  className="flex items-center justify-between font-mono text-[11px] bg-slate-50 dark:bg-slate-800/60 p-1.5 rounded"
                                >
                                  <span className="font-bold text-slate-800 dark:text-slate-200">
                                    {s.name} ({s.volume}주)
                                  </span>
                                  <span className="text-slate-600 dark:text-slate-300">
                                    {s.remaining_days !== undefined ? `잔여 D-${s.remaining_days}` : ''}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* 당일 배치 종료 후 익일 타겟팅 예고 */}
                      {flow.waiting_next && (
                        <div className="rounded-xl bg-indigo-50/70 dark:bg-indigo-950/30 p-2.5 border border-indigo-100 dark:border-indigo-900/40 flex items-center gap-2 text-indigo-700 dark:text-indigo-300 text-[11px]">
                          <ArrowRight size={13} className="shrink-0" />
                          <span>
                            <strong>당일 배치 후 익일 매수 대기 종목:</strong> {flow.waiting_next.rank}위 {flow.waiting_next.name} (필요액: {krwFmt(flow.waiting_next.required_krw || 0)})
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* [3] 보유 및 이탈 관리 종목 테이블 */}
      <div className={`${CARD} overflow-hidden`}>
        <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp size={16} className="text-indigo-600 dark:text-indigo-400" />
            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">
              전략 전용 포지션 및 이탈 분할매도 현황
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            관리 종목: {(report?.holdings_status || []).length}개
          </span>
        </div>

        {/* 미체결 예약/대기 주문 안내 배너 */}
        {(() => {
          const pendingCount = (report?.orders || []).filter(
            (o) => o.side === 'bid' && ['reserved', 'wait', 'pending_reorder'].includes(o.status),
          ).length
          if (pendingCount === 0) return null
          return (
            <div className="mx-4 mt-3 flex items-center gap-2 rounded-xl border border-violet-200/80 bg-violet-50/70 px-3.5 py-2 text-xs text-violet-700 dark:border-violet-900/60 dark:bg-violet-950/40 dark:text-violet-300">
              <Clock size={14} className="shrink-0 text-violet-600 dark:text-violet-400" />
              <span>
                현재 <strong>체결 대기(예약) 중인 매수 주문이 {pendingCount}건</strong> 있습니다. 정규장 개장 시 거래소에서 실제 체결이 완료되면 이 테이블에 보유 포지션으로 자동 등록됩니다.
              </span>
            </div>
          )
        })()}

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/60">
                <th className={TH}>종목명 (코드)</th>
                <th className={TH}>순위</th>
                <th className={TH}>관리 상태</th>
                <th className={`${TH} text-right`}>보유수량</th>
                <th className={`${TH} text-right`}>평균단가</th>
                <th className={`${TH} text-right`}>현재가</th>
                <th className={`${TH} text-right`}>평가금액</th>
                <th className={`${TH} text-right`}>평가손익 (수익률)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {(report?.holdings_status || []).length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-slate-400">
                    현재 전략으로 보유 중인 포지션이 없습니다. (배치 실행 대기)
                  </td>
                </tr>
              ) : (
                report?.holdings_status.map((item, idx) => {
                  const isUp = item.pnl >= 0
                  return (
                    <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                      <td className={`${TD} font-semibold text-slate-800 dark:text-slate-200`}>
                        {item.name} <span className="text-slate-400 font-normal">({item.ticker})</span>
                      </td>
                      <td className={TD}>{item.rank}</td>
                      <td className={TD}>
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${
                            item.status_code === 'exiting'
                              ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
                              : item.status_code === 'holding_top'
                              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
                              : 'bg-slate-100 text-slate-800 dark:bg-slate-700 dark:text-slate-300'
                          }`}
                        >
                          {item.status_badge}
                        </span>
                      </td>
                      <td className={`${TD} text-right font-mono`}>{item.qty}주</td>
                      <td className={`${TD} text-right font-mono`}>{krwFmt(item.avg_price)}</td>
                      <td className={`${TD} text-right font-mono`}>{krwFmt(item.current_price)}</td>
                      <td className={`${TD} text-right font-mono font-semibold`}>{krwFmt(item.eval_value)}</td>
                      <td className={`${TD} text-right font-mono ${isUp ? 'text-red-500' : 'text-blue-500'}`}>
                        <div className="flex items-center justify-end gap-1">
                          {isUp ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
                          <span>{krwFmt(item.pnl)} ({item.pnl_pct > 0 ? `+${item.pnl_pct}` : item.pnl_pct}%)</span>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* [4] 최근 배치별 예산 흐름 타임라인 */}
      <div className={`${CARD} overflow-hidden`}>
        <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
          <Clock size={16} className="text-indigo-600 dark:text-indigo-400" />
          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">
            배치별 예산 소진 및 실행 타임라인
          </h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/60">
                <th className={TH}>영업일자</th>
                <th className={TH}>배치</th>
                <th className={TH}>회차</th>
                <th className={`${TH} text-right`}>전일 이월금</th>
                <th className={`${TH} text-right`}>당일 충전액</th>
                <th className={`${TH} text-right`}>당일 집행액</th>
                <th className={`${TH} text-right`}>익일 이월금</th>
                <th className={TH}>실행 요약</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {(report?.batch_budget_logs || []).length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-slate-400">
                    배치 실행 이력이 없습니다.
                  </td>
                </tr>
              ) : (
                report?.batch_budget_logs
                  .slice()
                  .reverse()
                  .map((b: any, idx: number) => (
                    <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                      <td className={`${TD} font-mono`}>{b.date}</td>
                      <td className={`${TD} font-semibold`}>#{b.group_no}</td>
                      <td className={TD}>Cycle #{b.cycle_no}</td>
                      <td className={`${TD} text-right font-mono text-slate-500`}>
                        {krwFmt(b.prev_carryover || 0)}
                      </td>
                      <td className={`${TD} text-right font-mono text-emerald-600 dark:text-emerald-400 font-semibold`}>
                        +{krwFmt(b.daily_allowance || 0)}
                      </td>
                      <td className={`${TD} text-right font-mono text-rose-500 font-semibold`}>
                        -{krwFmt(b.spent ?? b.spent_today ?? 0)}
                      </td>
                      <td className={`${TD} text-right font-mono font-semibold`}>
                        {krwFmt(b.new_carryover ?? b.end_carryover ?? 0)}
                      </td>
                      <td className={`${TD} max-w-xs truncate text-slate-600 dark:text-slate-300`} title={b.summary || b.status_summary}>
                        {b.summary || b.status_summary || '-'}
                      </td>
                    </tr>
                  ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      {/* 부족액 수동 충전 모달 */}
      {topupOpen &&
        createPortal(
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div
              className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs"
              onClick={() => !topupLoading && setTopupOpen(false)}
            />
            <div className="relative z-10 w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2.5">
                <h4 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                  <DollarSign size={16} className="text-emerald-500" />
                  <span>가용 예산 즉시 추가 충전</span>
                </h4>
                <button
                  type="button"
                  onClick={() => setTopupOpen(false)}
                  className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                >
                  <X size={15} />
                </button>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-1">
                  충전 금액 (원 단위)
                </label>
                <input
                  type="number"
                  step="10000"
                  min="10000"
                  value={topupAmount}
                  onChange={(e) => setTopupAmount(Number(e.target.value))}
                  className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm font-mono font-bold text-slate-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 block mb-1">
                  충전 사유 / 메모
                </label>
                <input
                  type="text"
                  placeholder="예: 다음 타겟 종목 매수용 충전"
                  value={topupMemo}
                  onChange={(e) => setTopupMemo(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-xs text-slate-900 dark:text-white"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  disabled={topupLoading}
                  onClick={() => setTopupOpen(false)}
                  className="px-3.5 py-1.5 text-xs font-semibold rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50"
                >
                  취소
                </button>
                <button
                  type="button"
                  disabled={topupLoading || topupAmount <= 0}
                  onClick={handleTopup}
                  className="flex items-center gap-1 px-3.5 py-1.5 text-xs font-semibold rounded-xl bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {topupLoading && <Loader2 size={12} className="animate-spin" />}
                  <span>{krwFmt(topupAmount)} 충전</span>
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}
