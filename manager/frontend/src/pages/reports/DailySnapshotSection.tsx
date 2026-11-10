import { useEffect, useMemo, useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend,
} from 'recharts'
import {
  BarChart3,
  Calendar,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  RotateCw,
  CheckCircle2,
} from 'lucide-react'
import {
  fetchTopRotationReport,
  type DailySnapshotEntry,
  type TopRotationReport,
} from '../../api/reports'
import ErrorBanner from '../../components/ui/ErrorBanner'
import Spinner from '../../components/ui/Spinner'
import { CARD, TH, TD, krwFmt } from './ReportsShared'

export type SnapshotPeriodMode = '30d' | '3m' | '6m' | '1y'

const PERIOD_OPTIONS: { id: SnapshotPeriodMode; label: string; days: number }[] = [
  { id: '30d', label: '30일', days: 30 },
  { id: '3m', label: '3개월', days: 90 },
  { id: '6m', label: '6개월', days: 180 },
  { id: '1y', label: '1년', days: 365 },
]

const RANK_COLORS = [
  '#4f46e5', // 1위 indigo-600
  '#6366f1', // 2위 indigo-500
  '#7c3aed', // 3위 violet-600
  '#8b5cf6', // 4위 violet-500
  '#2563eb', // 5위 blue-600
  '#3b82f6', // 6위 blue-500
  '#0891b2', // 7위 cyan-600
  '#06b6d4', // 8위 cyan-500
  '#0d9488', // 9위 teal-600
  '#14b8a6', // 10위 teal-500
]

interface DailySnapshotSectionProps {
  templateId: number | null
  initialReport?: TopRotationReport | null
}

export default function DailySnapshotSection({
  templateId,
  initialReport,
}: DailySnapshotSectionProps) {
  const [report, setReport] = useState<TopRotationReport | null>(initialReport || null)
  const [loading, setLoading] = useState(!initialReport)
  const [error, setError] = useState<string | null>(null)
  const [period, setPeriod] = useState<SnapshotPeriodMode>('30d')
  const [selectedDate, setSelectedDate] = useState<string>('')
  const [seriesView, setSeriesView] = useState<'stacked' | 'total'>('stacked')
  const [isTableOpen, setIsTableOpen] = useState(false)

  const loadSnapshotData = async (tplId: number) => {
    try {
      setLoading(true)
      setError(null)
      const res = await fetchTopRotationReport(tplId)
      setReport(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : '스냅샷 데이터를 불러오지 못했습니다.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (initialReport && initialReport.template?.id === templateId) {
      setReport(initialReport)
      setLoading(false)
      return
    }
    if (templateId) {
      loadSnapshotData(templateId)
    }
  }, [templateId, initialReport])

  // 백엔드 daily_snapshots 또는 daily_execution_flow 폴백에서 기록된 스냅샷 추출 (오름차순: 기록 시작일부터)
  const allSnapshots: DailySnapshotEntry[] = useMemo(() => {
    if (!report) return []
    if (report.daily_snapshots && report.daily_snapshots.length > 0) {
      return [...report.daily_snapshots].sort((a, b) => a.date.localeCompare(b.date))
    }

    const byDate = new Map<string, DailySnapshotEntry>()
    const flows = report.daily_execution_flow || []
    for (const fl of [...flows].reverse()) {
      if (!fl.date || !fl.snapshot_top || fl.snapshot_top.length === 0) continue
      const boughtSet = new Set((fl.buys || []).map((b) => b.code))
      const items = fl.snapshot_top.map((sp, i) => ({
        rank: sp.rank || i + 1,
        code: sp.code,
        name: sp.name,
        price: Number(sp.price || 0),
        is_bought: boughtSet.has(sp.code),
      }))
      const total = items.reduce((acc, it) => acc + it.price, 0)
      const spent = (fl.buys || []).reduce((acc, b) => acc + Number(b.cost || 0), 0)
      byDate.set(fl.date, {
        date: fl.date,
        group_no: fl.group_no,
        cycle_no: fl.cycle_no,
        total_price: Math.round(total),
        avg_price: items.length > 0 ? Math.round(total / items.length) : 0,
        spent_krw: Math.round(spent),
        carryover_budget: Math.round(Number(fl.carryover_budget || 0)),
        items,
      })
    }

    if (byDate.size === 0 && report.cycle_pipeline?.pipeline?.length) {
      const todayStr = new Date().toISOString().slice(0, 10)
      const items = report.cycle_pipeline.pipeline.map((p) => ({
        rank: p.rank,
        code: p.code,
        name: p.name,
        price: Number(p.price || 0),
        is_bought: p.status === 'bought',
      }))
      const total = items.reduce((acc, it) => acc + it.price, 0)
      byDate.set(todayStr, {
        date: todayStr,
        group_no: report.template?.params?.last_group_no ?? null,
        cycle_no: report.cycle_pipeline.cycle_no,
        total_price: Math.round(total),
        avg_price: items.length > 0 ? Math.round(total / items.length) : 0,
        spent_krw: 0,
        carryover_budget: Math.round(Number(report.template?.params?.carryover_budget || 0)),
        items,
      })
    }

    return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date))
  }, [report])

  // 기록이 시작된 일자
  const firstRecordedDate = allSnapshots.length > 0 ? allSnapshots[0].date : null
  const latestRecordedDate =
    allSnapshots.length > 0 ? allSnapshots[allSnapshots.length - 1].date : null

  // 기간 필터(30일, 3개월, 6개월, 1년) 적용 — 기록 시작일 이후 데이터만 표시
  const filteredSnapshots = useMemo(() => {
    if (allSnapshots.length === 0) return []
    const opt = PERIOD_OPTIONS.find((o) => o.id === period) || PERIOD_OPTIONS[0]
    const anchorStr = latestRecordedDate || new Date().toISOString().slice(0, 10)
    const anchorDate = new Date(`${anchorStr}T00:00:00`)
    const cutoffDate = new Date(anchorDate.getTime() - (opt.days - 1) * 24 * 60 * 60 * 1000)
    const cutoffStr = cutoffDate.toISOString().slice(0, 10)

    const list = allSnapshots.filter((s) => s.date >= cutoffStr)
    return list.length > 0 ? list : allSnapshots
  }, [allSnapshots, period, latestRecordedDate])

  // 기본 선택 일자: 최신 기록 일자
  useEffect(() => {
    if (filteredSnapshots.length === 0) {
      setSelectedDate('')
      return
    }
    const exists = filteredSnapshots.some((s) => s.date === selectedDate)
    if (!selectedDate || !exists) {
      setSelectedDate(filteredSnapshots[filteredSnapshots.length - 1].date)
    }
  }, [filteredSnapshots, selectedDate])

  const activeSnapshot = useMemo(() => {
    if (filteredSnapshots.length === 0) return null
    return (
      filteredSnapshots.find((s) => s.date === selectedDate) ||
      filteredSnapshots[filteredSnapshots.length - 1]
    )
  }, [filteredSnapshots, selectedDate])

  const activeIndex = useMemo(() => {
    if (!activeSnapshot) return -1
    return filteredSnapshots.findIndex((s) => s.date === activeSnapshot.date)
  }, [filteredSnapshots, activeSnapshot])

  // 1) 선택 일자 1~10순위 Bar 차트 데이터
  const rankBarData = useMemo(() => {
    if (!activeSnapshot) return []
    return activeSnapshot.items.slice(0, 10).map((it) => ({
      rankLabel: `${it.rank}위 ${it.name}`,
      shortLabel: `${it.rank}위`,
      rank: it.rank,
      code: it.code,
      name: it.name,
      price: it.price,
      isBought: Boolean(it.is_bought),
    }))
  }, [activeSnapshot])

  // 2) 시계열 Bar 차트 데이터 (기록 시작일부터 선택 기간 내 일자별 1~10순위 금액)
  const timeSeriesData = useMemo(() => {
    return filteredSnapshots.map((snap) => {
      const row: Record<string, any> = {
        date: snap.date,
        shortDate: snap.date.slice(5),
        group_no: snap.group_no,
        total_price: snap.total_price,
        avg_price: snap.avg_price,
        spent_krw: snap.spent_krw,
      }
      snap.items.slice(0, 10).forEach((it, idx) => {
        const rKey = `rank_${idx + 1}`
        row[rKey] = it.price
        row[`${rKey}_name`] = `${it.rank}위 ${it.name}`
      })
      return row
    })
  }, [filteredSnapshots])

  if (!templateId) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-xs text-slate-400 dark:border-slate-700">
        전략을 먼저 선택해주세요.
      </div>
    )
  }

  if (loading && !report) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    )
  }

  if (error) return <ErrorBanner message={error} />

  const rankStart = report?.cycle_pipeline?.rank_start ?? 1
  const rankEnd = report?.cycle_pipeline?.rank_end ?? 10

  return (
    <div className="space-y-4 break-keep animate-fade-in">
      {/* 상단 컨트롤 바: 기록 시작일 안내 & 기간 선택기 (30일, 3개월, 6개월, 1년) */}
      <div className={`${CARD} p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3`}>
        <div className="flex items-center gap-2.5 flex-wrap">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400">
            <BarChart3 size={16} />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                일단위 TOP {rankStart}~{rankEnd}순위 스냅샷 & 시계열 차트
              </h3>
              {firstRecordedDate && (
                <span className="rounded-full bg-slate-100 dark:bg-slate-800 px-2.5 py-0.5 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                  기록 시작일: {firstRecordedDate} ({filteredSnapshots.length}일 표시)
                </span>
              )}
            </div>
          </div>
        </div>

        {/* 우측: 기간 선택 버튼 (30일, 3개월, 6개월, 1년) & 새로고침 */}
        <div className="flex items-center gap-2 self-end sm:self-auto">
          <div
            className="inline-flex items-center rounded-xl bg-slate-100 p-1 dark:bg-slate-800"
            role="tablist"
            aria-label="스냅샷 조회 기간"
          >
            {PERIOD_OPTIONS.map((opt) => {
              const active = period === opt.id
              return (
                <button
                  key={opt.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setPeriod(opt.id)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-all whitespace-nowrap break-keep ${
                    active
                      ? 'bg-white text-indigo-600 shadow-2xs dark:bg-slate-900 dark:text-indigo-400'
                      : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
                  }`}
                >
                  {opt.label}
                </button>
              )
            })}
          </div>

          <button
            type="button"
            onClick={() => loadSnapshotData(templateId)}
            className="flex items-center gap-1 rounded-xl border border-slate-200 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
            title="스냅샷 새로고침"
          >
            <RotateCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {filteredSnapshots.length === 0 ? (
        <div className={`${CARD} p-12 text-center text-xs text-slate-400`}>
          기록된 일단위 스냅샷 데이터가 없습니다. 첫 배치가 실행되면 기록 시작일부터 차트가 표시됩니다.
        </div>
      ) : (
        <>
          {/* ===================================================================
              [차트 1] 선택 일자 1~10순위 종목별 금액(단가) Bar 차트
              =================================================================== */}
          {activeSnapshot && (
            <div className={`${CARD} p-4 sm:p-5 space-y-4`}>
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 dark:border-slate-800 pb-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold text-slate-800 dark:text-slate-100">
                    📊 순위별 종목 금액 Bar 차트 (1~10순위)
                  </span>
                  <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-[11px] font-bold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                    1주 합산: {krwFmt(activeSnapshot.total_price)}원 · 평균: {krwFmt(activeSnapshot.avg_price)}원
                  </span>
                </div>

                {/* 일자 탐색 컨트롤 (< 이전일 | 날짜 선택 | 다음일 >) */}
                <div className="flex items-center gap-1.5 self-end sm:self-auto">
                  <button
                    type="button"
                    disabled={activeIndex <= 0}
                    onClick={() => {
                      if (activeIndex > 0) {
                        setSelectedDate(filteredSnapshots[activeIndex - 1].date)
                      }
                    }}
                    className="rounded-lg border border-slate-200 p-1 text-slate-600 hover:bg-slate-50 disabled:opacity-30 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                    title="이전 기록 일자"
                  >
                    <ChevronLeft size={14} />
                  </button>

                  <select
                    aria-label="스냅샷 기준 일자 선택"
                    value={activeSnapshot.date}
                    onChange={(e) => setSelectedDate(e.target.value)}
                    className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-bold text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                  >
                    {[...filteredSnapshots].reverse().map((s) => (
                      <option key={s.date} value={s.date}>
                        {s.date}
                        {s.group_no ? ` (Batch #${s.group_no})` : ''}
                      </option>
                    ))}
                  </select>

                  <button
                    type="button"
                    disabled={activeIndex < 0 || activeIndex >= filteredSnapshots.length - 1}
                    onClick={() => {
                      if (activeIndex >= 0 && activeIndex < filteredSnapshots.length - 1) {
                        setSelectedDate(filteredSnapshots[activeIndex + 1].date)
                      }
                    }}
                    className="rounded-lg border border-slate-200 p-1 text-slate-600 hover:bg-slate-50 disabled:opacity-30 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                    title="다음 기록 일자"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>

              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={rankBarData}
                    margin={{ top: 10, right: 16, left: 10, bottom: 20 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.12} />
                    <XAxis
                      dataKey="rankLabel"
                      stroke="#64748b"
                      fontSize={11}
                      interval={0}
                      angle={-15}
                      textAnchor="end"
                      height={48}
                    />
                    <YAxis
                      stroke="#64748b"
                      fontSize={11}
                      tickFormatter={(v) => krwFmt(Number(v))}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        border: 'none',
                        borderRadius: '10px',
                        color: '#fff',
                        fontSize: '12px',
                      }}
                      formatter={(value: any, _name: any, props: any) => {
                        const p = props?.payload
                        const statusTxt = p?.isBought ? ' (당일 매수)' : ''
                        return [`${krwFmt(Number(value))}원${statusTxt}`, `${p?.rank}위 ${p?.name} (${p?.code})`]
                      }}
                    />
                    <Bar dataKey="price" name="종목 금액(단가)" radius={[6, 6, 0, 0]}>
                      {rankBarData.map((entry, idx) => (
                        <Cell
                          key={entry.code}
                          fill={entry.isBought ? '#10b981' : RANK_COLORS[idx % RANK_COLORS.length]}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400 pt-1">
                <div className="flex items-center gap-3">
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2.5 w-2.5 rounded-xs bg-indigo-600 inline-block" />
                    <span>순위별 기준 단가</span>
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="h-2.5 w-2.5 rounded-xs bg-emerald-500 inline-block" />
                    <span>해당일 매수 체결·발주 종목</span>
                  </span>
                </div>
                <span>하단 시계열 차트의 막대를 클릭하면 해당 일자의 1~10순위 차트로 즉시 전환됩니다.</span>
              </div>
            </div>
          )}

          {/* ===================================================================
              [차트 2] 시계열 스냅샷 추이 Bar 차트 (기록 시작일부터 ~ 선택 기간)
              =================================================================== */}
          <div className={`${CARD} p-4 sm:p-5 space-y-4`}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Calendar size={16} className="text-indigo-600 dark:text-indigo-400" />
                <div>
                  <h4 className="text-xs font-bold text-slate-800 dark:text-slate-100">
                    일단위 스냅샷 시계열 추이 ({filteredSnapshots[0]?.date} ~{' '}
                    {filteredSnapshots[filteredSnapshots.length - 1]?.date})
                  </h4>
                </div>
              </div>

              <div className="inline-flex items-center rounded-lg bg-slate-100 p-0.5 text-[11px] dark:bg-slate-800 self-end sm:self-auto">
                <button
                  type="button"
                  onClick={() => setSeriesView('stacked')}
                  className={`rounded-md px-2.5 py-1 font-semibold transition-colors ${
                    seriesView === 'stacked'
                      ? 'bg-white text-indigo-600 shadow-2xs dark:bg-slate-900 dark:text-indigo-400'
                      : 'text-slate-500 hover:text-slate-700 dark:text-slate-400'
                  }`}
                >
                  1~10순위 종목 누적 Bar
                </button>
                <button
                  type="button"
                  onClick={() => setSeriesView('total')}
                  className={`rounded-md px-2.5 py-1 font-semibold transition-colors ${
                    seriesView === 'total'
                      ? 'bg-white text-indigo-600 shadow-2xs dark:bg-slate-900 dark:text-indigo-400'
                      : 'text-slate-500 hover:text-slate-700 dark:text-slate-400'
                  }`}
                >
                  합산 금액 · 당일 매수액
                </button>
              </div>
            </div>

            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                {seriesView === 'stacked' ? (
                  <BarChart
                    data={timeSeriesData}
                    margin={{ top: 10, right: 16, left: 10, bottom: 5 }}
                    onClick={(state: any) => {
                      if (state?.activePayload?.[0]?.payload?.date) {
                        setSelectedDate(state.activePayload[0].payload.date)
                      }
                    }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.12} />
                    <XAxis dataKey="shortDate" stroke="#64748b" fontSize={11} />
                    <YAxis
                      stroke="#64748b"
                      fontSize={11}
                      tickFormatter={(v) => krwFmt(Number(v))}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        border: 'none',
                        borderRadius: '10px',
                        color: '#fff',
                        fontSize: '11px',
                      }}
                      labelFormatter={(_label, payload) => {
                        const row = payload?.[0]?.payload
                        return row
                          ? `${row.date}${row.group_no ? ` (Batch #${row.group_no})` : ''} — 합산 ${krwFmt(row.total_price)}원`
                          : ''
                      }}
                      formatter={(value: any, name: any, props: any) => {
                        const customName = props?.payload?.[`${name}_name`] || name
                        return [`${krwFmt(Number(value))}원`, customName]
                      }}
                    />
                    {Array.from({ length: 10 }).map((_, idx) => (
                      <Bar
                        key={`rank_${idx + 1}`}
                        dataKey={`rank_${idx + 1}`}
                        name={`${idx + 1}위`}
                        stackId="ranks"
                        fill={RANK_COLORS[idx % RANK_COLORS.length]}
                        cursor="pointer"
                      />
                    ))}
                  </BarChart>
                ) : (
                  <BarChart
                    data={timeSeriesData}
                    margin={{ top: 10, right: 16, left: 10, bottom: 5 }}
                    onClick={(state: any) => {
                      if (state?.activePayload?.[0]?.payload?.date) {
                        setSelectedDate(state.activePayload[0].payload.date)
                      }
                    }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.12} />
                    <XAxis dataKey="shortDate" stroke="#64748b" fontSize={11} />
                    <YAxis
                      stroke="#64748b"
                      fontSize={11}
                      tickFormatter={(v) => krwFmt(Number(v))}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0f172a',
                        border: 'none',
                        borderRadius: '10px',
                        color: '#fff',
                        fontSize: '12px',
                      }}
                      formatter={(value: any, name: any) => [`${krwFmt(Number(value))}원`, name]}
                    />
                    <Legend wrapperStyle={{ fontSize: '11px' }} />
                    <Bar
                      dataKey="total_price"
                      name="1~10순위 1주 합산 금액"
                      fill="#6366f1"
                      radius={[4, 4, 0, 0]}
                      cursor="pointer"
                    />
                    <Bar
                      dataKey="spent_krw"
                      name="당일 매수 집행 금액"
                      fill="#10b981"
                      radius={[4, 4, 0, 0]}
                      cursor="pointer"
                    />
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>

            {/* 아코디언: 선택 일자 스냅샷 상세 수치 표 (기본 접힘) */}
            {activeSnapshot && (
              <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
                <button
                  type="button"
                  onClick={() => setIsTableOpen((v) => !v)}
                  className="flex w-full items-center justify-between rounded-xl bg-slate-50 px-3.5 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 dark:bg-slate-800/60 dark:text-slate-200 dark:hover:bg-slate-800 transition-colors"
                >
                  <span>
                    📋 {activeSnapshot.date} 스냅샷 순위별 상세 수치 표 ({activeSnapshot.items.length}개 종목)
                  </span>
                  <span className="inline-flex items-center gap-1 text-slate-400">
                    <span>{isTableOpen ? '접기' : '펼치기'}</span>
                    {isTableOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </span>
                </button>

                {isTableOpen && (
                  <div className="mt-3 overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-200 bg-slate-50/80 text-slate-500 dark:border-slate-800 dark:bg-slate-800/60">
                          <th className={TH}>순위</th>
                          <th className={TH}>종목명 (코드)</th>
                          <th className={`${TH} text-right`}>기준 단가 (1주 금액)</th>
                          <th className={TH}>당일 매수 여부</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                        {activeSnapshot.items.map((it) => (
                          <tr
                            key={it.code}
                            className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40"
                          >
                            <td className={`${TD} font-bold text-indigo-600 dark:text-indigo-400`}>
                              {it.rank}위
                            </td>
                            <td className={`${TD} font-semibold text-slate-800 dark:text-slate-200`}>
                              {it.name}{' '}
                              <span className="font-normal text-slate-400">({it.code})</span>
                            </td>
                            <td className={`${TD} text-right font-semibold text-slate-800 dark:text-slate-100`}>
                              {krwFmt(it.price)}원
                            </td>
                            <td className={TD}>
                              {it.is_bought ? (
                                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400">
                                  <CheckCircle2 size={11} />
                                  매수 집행
                                </span>
                              ) : (
                                <span className="text-slate-400 text-[11px]">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
