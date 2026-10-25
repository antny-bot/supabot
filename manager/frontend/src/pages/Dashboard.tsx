import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ChevronRight,
  TrendingUp,
  Wallet,
  Coins,
  Activity,
  AlertTriangle,
  PieChart as PieIcon,
  LineChart as ChartIcon,
  ShieldAlert,
  Loader2,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
} from 'lucide-react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts'
import { fetchDashboard } from '../api/dashboard'
import { fetchReportHoldings, fetchReportDaily, fetchReportAllocation } from '../api/reports'
import { fetchTrades } from '../api/trades'
import { cancelAllOrders } from '../api/orders'
import Badge from '../components/ui/Badge'
import type { DateRangeValue } from '../components/ui/DateRangePicker'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import SegmentedControl from '../components/ui/SegmentedControl'
import { StatCardSkeleton, CardSkeleton } from '../components/ui/Skeleton'
import SyncIndicator from '../components/ui/SyncIndicator'
import { PAGE_META } from '../config/pageMeta'
import { useRealtime } from '../hooks/useRealtime'
import { useToast } from '../contexts/ToastContext'
import type { DashboardData, HoldingsReport, Trade, DailyReport, AllocationReport } from '../types'
import { krwFmt, pnlTextClass } from '../utils/formatters'

const RECENT_TRADES_RANGE: DateRangeValue = { mode: '7d', from: '', to: '' }
const CHART_RANGE: DateRangeValue = { mode: '30d', from: '', to: '' }
const ALLOCATION_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#06b6d4']

export default function Dashboard() {
  const navigate = useNavigate()
  const toast = useToast()

  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const [holdings, setHoldings] = useState<HoldingsReport | null>(null)
  const [recentTrades, setRecentTrades] = useState<Trade[] | null>(null)
  const [dailyData, setDailyData] = useState<DailyReport | null>(null)
  const [allocation, setAllocation] = useState<AllocationReport | null>(null)

  // 모바일 탭 스위처: 'holdings' | 'trades'
  const [mobileTab, setMobileTab] = useState<'holdings' | 'trades'>('holdings')

  // 긴급 취소 모달
  const [cancelModalOpen, setCancelModalOpen] = useState(false)
  const [cancellingAll, setCancellingAll] = useState(false)

  const loadData = useCallback(() => {
    setLoading(true)
    fetchDashboard()
      .then((res) => {
        setData(res)
        setLastUpdated(new Date())
        setError(null)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '대시보드 데이터를 불러오지 못했습니다.'))
      .finally(() => setLoading(false))
  }, [])

  const loadExtras = useCallback(() => {
    Promise.all([
      fetchReportHoldings().catch(() => null),
      fetchTrades(RECENT_TRADES_RANGE, 1, 5).catch(() => ({ trades: [], total: 0 })),
      fetchReportDaily(CHART_RANGE).catch(() => null),
      fetchReportAllocation().catch(() => null),
    ])
      .then(([holdingsRes, tradesRes, dailyRes, allocRes]) => {
        if (holdingsRes) setHoldings(holdingsRes)
        if (tradesRes) setRecentTrades(tradesRes.trades)
        if (dailyRes) setDailyData(dailyRes)
        if (allocRes) setAllocation(allocRes)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadData()
    loadExtras()
  }, [loadData, loadExtras])

  useRealtime(
    useCallback(() => {
      loadData()
      loadExtras()
    }, [loadData, loadExtras]),
  )

  const handleConfirmCancelAll = async () => {
    setCancellingAll(true)
    try {
      const res = await cancelAllOrders()
      if (res.ok) {
        toast.success(`활성 주문 ${res.cancelled_count}건이 일괄 취소되었습니다.`)
        if (res.failed_count > 0) {
          toast.warning(`취소 실패: ${res.failed_count}건`)
        }
        setCancelModalOpen(false)
        loadData()
      } else {
        toast.error('주문 일괄 취소에 실패했습니다.')
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '일괄 취소 중 오류가 발생했습니다.')
    } finally {
      setCancellingAll(false)
    }
  }

  // 지표 계산
  const totalValue = holdings?.summary.total_value ?? 0
  const totalPnl = holdings?.summary.total_pnl ?? 0
  const totalRoi = holdings?.summary.total_roi_pct ?? 0
  const totalCost = holdings?.summary.total_cost ?? (totalValue - totalPnl)
  const pnl24h = data?.stats.realized_pnl_24h ?? 0
  const openOrdersCount = data?.stats.orders_open ?? 0
  const botStatus = data?.stats.bot_status ?? 'unknown'

  // 차트 데이터 가공
  const chartRows = dailyData?.rows ? [...dailyData.rows].reverse() : []
  const sparklineData = chartRows.slice(-7)

  // 도넛 데이터 가공
  const donutData =
    allocation?.by_exchange && allocation.by_exchange.length > 0
      ? allocation.by_exchange
      : holdings?.rows.reduce<{ name: string; value: number }[]>((acc, row) => {
          const ex = row.exchange.toUpperCase()
          const found = acc.find((item) => item.name === ex)
          if (found) {
            found.value += row.value_krw
          } else {
            acc.push({ name: ex, value: row.value_krw })
          }
          return acc
        }, []) ?? []

  return (
    <div className="space-y-5 pb-8">
      {/* 최상단 페이지 헤더 및 액션 바 */}
      <PageHeader
        {...PAGE_META.dashboard}
        actions={
          <div className="flex items-center gap-2">
            <SyncIndicator lastUpdated={lastUpdated} loading={loading} error={error} />
            <button
              onClick={() => setCancelModalOpen(true)}
              className="flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-600 transition-colors hover:bg-rose-100 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-400 dark:hover:bg-rose-900/60"
              title="비상시 모든 활성 주문 즉시 취소"
            >
              <ShieldAlert size={14} />
              <span className="hidden sm:inline">긴급 킬스위치</span>
              <span className="sm:hidden">일괄취소</span>
            </button>
          </div>
        }
      />

      {error && <ErrorBanner message={error} />}

      {/* =========================================================================
          [1] 모바일 전용: 3초 룰 통합 히어로 카드 (Glance UI)
          ========================================================================= */}
      <div className="block md:hidden">
        {loading && !data ? (
          <CardSkeleton />
        ) : (
          <div className="relative overflow-hidden rounded-2xl border border-slate-200/80 bg-gradient-to-br from-white to-slate-50 p-5 shadow-sm dark:border-slate-800 dark:from-slate-900 dark:to-slate-900/60">
            {/* 상단: 봇 상태 뱃지 & 실시간 상태 */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">총 평가자산</span>
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                    botStatus === 'online'
                      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                      : botStatus === 'idle'
                      ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300'
                      : 'bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300'
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      botStatus === 'online'
                        ? 'bg-emerald-500 animate-pulse'
                        : botStatus === 'idle'
                        ? 'bg-amber-500'
                        : 'bg-rose-500'
                    }`}
                  />
                  BOT {botStatus.toUpperCase()}
                </span>
              </div>
              <span className="text-[11px] font-mono text-slate-400">
                {openOrdersCount > 0 ? `오픈 주문 ${openOrdersCount}건` : '대기 주문 없음'}
              </span>
            </div>

            {/* 총 평가자산 & 당일 손익 */}
            <div className="mt-2.5">
              <h2 className="text-2xl font-extrabold tracking-tight text-slate-900 dark:text-white font-mono">
                {krwFmt(totalValue)}
              </h2>
              <div className="mt-1 flex items-center gap-2 text-xs font-semibold">
                <span
                  className={`inline-flex items-center gap-0.5 ${
                    totalPnl >= 0 ? 'text-red-500 dark:text-red-400' : 'text-blue-500 dark:text-blue-400'
                  }`}
                >
                  {totalPnl >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                  {totalPnl >= 0 ? '+' : ''}
                  {krwFmt(totalPnl)} ({totalRoi >= 0 ? '+' : ''}
                  {totalRoi}%)
                </span>
                <span className="text-slate-400 font-normal">누적 평가손익</span>
              </div>
            </div>

            {/* 7일 스파크라인 차트 (모바일 전용 간결한 시각화) */}
            {sparklineData.length > 1 && (
              <div className="mt-4 h-14 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={sparklineData} margin={{ top: 2, right: 2, left: 2, bottom: 0 }}>
                    <defs>
                      <linearGradient id="mobileSpark" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#6366f1" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="#6366f1" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <Area
                      type="monotone"
                      dataKey="cumulative_pnl"
                      stroke="#6366f1"
                      strokeWidth={2}
                      fill="url(#mobileSpark)"
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* 3대 서브 메트릭 */}
            <div className="mt-4 grid grid-cols-3 divide-x divide-slate-100 border-t border-slate-100 pt-3 text-center dark:divide-slate-800 dark:border-slate-800">
              <div>
                <p className="text-[10px] text-slate-400">투자원금</p>
                <p className="text-xs font-bold text-slate-700 dark:text-slate-200 font-mono mt-0.5">
                  {krwFmt(totalCost)}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-slate-400">24h 실현손익</p>
                <p className={`text-xs font-bold font-mono mt-0.5 ${pnlTextClass(pnl24h)}`}>
                  {pnl24h >= 0 ? '+' : ''}
                  {krwFmt(pnl24h)}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-slate-400">보유 종목수</p>
                <p className="text-xs font-bold text-slate-700 dark:text-slate-200 font-mono mt-0.5">
                  {holdings?.summary.asset_count ?? 0}개
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* =========================================================================
          [2] 데스크톱 전용: 4대 핵심 지표 요약 바
          ========================================================================= */}
      <div className="hidden md:grid md:grid-cols-4 md:gap-4">
        {loading && !data ? (
          <>
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
          </>
        ) : (
          <>
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">총 평가자산</span>
                <div className="rounded-lg bg-emerald-500/10 p-1.5 text-emerald-600 dark:text-emerald-400">
                  <Wallet size={16} />
                </div>
              </div>
              <p className="mt-2 text-xl font-extrabold text-slate-900 dark:text-white font-mono">
                {krwFmt(totalValue)}
              </p>
              <p className="mt-1 text-xs text-slate-400">원금: {krwFmt(totalCost)}</p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">총 평가손익</span>
                <div
                  className={`rounded-lg p-1.5 ${
                    totalPnl >= 0
                      ? 'bg-red-500/10 text-red-600 dark:text-red-400'
                      : 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
                  }`}
                >
                  <TrendingUp size={16} />
                </div>
              </div>
              <p className={`mt-2 text-xl font-extrabold font-mono ${pnlTextClass(totalPnl)}`}>
                {totalPnl >= 0 ? '+' : ''}
                {krwFmt(totalPnl)}
              </p>
              <p className={`mt-1 text-xs font-semibold ${pnlTextClass(totalRoi)}`}>
                수익률 {totalRoi >= 0 ? '+' : ''}
                {totalRoi}%
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">24시간 실현손익</span>
                <div className="rounded-lg bg-violet-500/10 p-1.5 text-violet-600 dark:text-violet-400">
                  <Coins size={16} />
                </div>
              </div>
              <p className={`mt-2 text-xl font-extrabold font-mono ${pnlTextClass(pnl24h)}`}>
                {pnl24h >= 0 ? '+' : ''}
                {krwFmt(pnl24h)}
              </p>
              <p className="mt-1 text-xs text-slate-400">체결 거래 기준 손익</p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">봇 상태 & 활성 주문</span>
                <div
                  className={`rounded-lg p-1.5 ${
                    botStatus === 'online'
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                      : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                  }`}
                >
                  <Activity size={16} />
                </div>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${
                    botStatus === 'online' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
                  }`}
                />
                <span className="text-lg font-bold uppercase text-slate-800 dark:text-slate-100">
                  {botStatus}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-400">미체결 주문: {openOrdersCount}건</p>
            </div>
          </>
        )}
      </div>

      {/* =========================================================================
          [3] 메인 시각화 그리드 (PC: 3컬럼 모듈 워크벤치 / 모바일: 세그먼트 스위처)
          ========================================================================= */}
      <div className="grid gap-5 md:grid-cols-12">
        {/* 데스크톱 Left Col (7/12 cols): 일별 누적 손익 곡선 + 자산 배분 비중 */}
        <div className="space-y-5 md:col-span-7">
          {/* 일별 누적 손익 추이 */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <ChartIcon size={16} className="text-indigo-500" />
                <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                  일별 누적 실현손익 추이
                </h3>
              </div>
              <span className="text-xs text-slate-400">최근 30일</span>
            </div>

            <div className="mt-4 h-60 w-full">
              {chartRows.length === 0 ? (
                <div className="flex h-full items-center justify-center text-xs text-slate-400">
                  표시할 손익 데이터가 없습니다.
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartRows} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                    <defs>
                      <linearGradient id="pnlGradientDesktop" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                    <YAxis tick={{ fontSize: 10 }} stroke="#94a3b8" tickFormatter={(v) => krwFmt(v)} />
                    <RechartsTooltip
                      formatter={(val: number) => [`${krwFmt(val)}`, '누적 손익']}
                      labelFormatter={(label) => `일자: ${label}`}
                      contentStyle={{
                        backgroundColor: 'rgba(15, 23, 42, 0.95)',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: '8px',
                        color: '#fff',
                        fontSize: '12px',
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="cumulative_pnl"
                      stroke="#6366f1"
                      strokeWidth={2}
                      fillOpacity={1}
                      fill="url(#pnlGradientDesktop)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* 거래소별 자산 배분 비중 (데스크톱 및 모바일 공통) */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <PieIcon size={16} className="text-emerald-500" />
                <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                  거래소별 자산 배분
                </h3>
              </div>
              <button
                onClick={() => navigate('/reports')}
                className="text-xs text-indigo-500 hover:underline flex items-center gap-0.5"
              >
                상세 리포트 <ChevronRight size={14} />
              </button>
            </div>

            <div className="mt-4 h-52 w-full">
              {donutData.length === 0 ? (
                <div className="flex h-full items-center justify-center text-xs text-slate-400">
                  보유 자산이 없습니다.
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={donutData}
                      cx="50%"
                      cy="50%"
                      innerRadius={45}
                      outerRadius={65}
                      paddingAngle={4}
                      dataKey="value"
                    >
                      {donutData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={ALLOCATION_COLORS[index % ALLOCATION_COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip
                      formatter={(val: number) => [`${krwFmt(val)}`, '평가금액']}
                      contentStyle={{
                        backgroundColor: 'rgba(15, 23, 42, 0.95)',
                        border: 'none',
                        borderRadius: '8px',
                        color: '#fff',
                        fontSize: '12px',
                      }}
                    />
                    <Legend
                      verticalAlign="bottom"
                      iconSize={8}
                      formatter={(value) => (
                        <span className="text-xs text-slate-600 dark:text-slate-300">{value}</span>
                      )}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </div>

        {/* 데스크톱 Right Col (5/12 cols) / 모바일 세그먼트 스위처 영역 */}
        <div className="space-y-5 md:col-span-5">
          {/* 모바일 화면에서는 탭 스위처 제공 (보유자산 vs 최근체결) */}
          <div className="flex items-center justify-between md:hidden">
            <SegmentedControl
              options={[
                { id: 'holdings', label: '보유 자산', badge: holdings?.summary.asset_count },
                { id: 'trades', label: '최근 체결', badge: recentTrades?.length },
              ]}
              value={mobileTab}
              onChange={setMobileTab}
            />
            <button
              onClick={() => navigate(mobileTab === 'holdings' ? '/reports' : '/trades')}
              className="text-xs text-indigo-500 font-medium hover:underline flex items-center"
            >
              전체보기 <ChevronRight size={14} />
            </button>
          </div>

          {/* 보유 자산 모듈 (데스크톱 상시 표시, 모바일은 mobileTab === 'holdings' 일 때) */}
          <div
            className={`rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 overflow-hidden ${
              mobileTab !== 'holdings' ? 'hidden md:block' : 'block'
            }`}
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <Wallet size={16} className="text-indigo-500" />
                <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                  보유 자산 요약
                </h3>
              </div>
              <button
                onClick={() => navigate('/reports')}
                className="hidden md:flex items-center gap-0.5 text-xs text-indigo-500 hover:underline"
              >
                전체보기 <ChevronRight size={14} />
              </button>
            </div>

            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {!holdings || holdings.rows.length === 0 ? (
                <div className="py-10 text-center text-xs text-slate-400">보유 자산이 없습니다.</div>
              ) : (
                holdings.rows.slice(0, 5).map((row) => (
                  <div
                    key={`${row.exchange}-${row.ticker}`}
                    className="flex items-center justify-between px-5 py-3 text-xs transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Badge value={row.exchange} label={row.exchange.toUpperCase()} />
                      <span className="font-semibold text-slate-800 dark:text-slate-200 truncate">
                        {row.ticker}
                      </span>
                    </div>
                    <div className="text-right font-mono">
                      <p className="font-semibold text-slate-800 dark:text-slate-200">
                        {krwFmt(row.value_krw)}
                      </p>
                      <p className={`text-[11px] ${pnlTextClass(row.roi_pct)}`}>
                        {row.roi_pct >= 0 ? '+' : ''}
                        {row.roi_pct}%
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* 최근 체결 모듈 (데스크톱 상시 표시, 모바일은 mobileTab === 'trades' 일 때) */}
          <div
            className={`rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 overflow-hidden ${
              mobileTab !== 'trades' ? 'hidden md:block' : 'block'
            }`}
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <Clock size={16} className="text-emerald-500" />
                <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                  최근 체결 내역
                </h3>
              </div>
              <button
                onClick={() => navigate('/trades')}
                className="hidden md:flex items-center gap-0.5 text-xs text-indigo-500 hover:underline"
              >
                전체보기 <ChevronRight size={14} />
              </button>
            </div>

            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {!recentTrades || recentTrades.length === 0 ? (
                <div className="py-10 text-center text-xs text-slate-400">최근 체결 내역이 없습니다.</div>
              ) : (
                recentTrades.slice(0, 5).map((trade, i) => (
                  <div
                    key={trade.id || i}
                    className="flex items-center justify-between px-5 py-3 text-xs transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Badge value={trade.side} />
                      <span className="font-semibold text-slate-800 dark:text-slate-200 truncate">
                        {trade.ticker}
                      </span>
                      <span className="text-[11px] text-slate-400 font-mono">
                        {trade.executed_fmt?.slice(11, 16)}
                      </span>
                    </div>
                    <div className="text-right font-mono">
                      <p className="font-semibold text-slate-800 dark:text-slate-200">
                        {krwFmt(trade.krw ?? (trade.price ?? 0) * (trade.volume ?? 0))}
                      </p>
                      <p className="text-[11px] text-slate-400">
                        {trade.price?.toLocaleString()}원
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 비상 긴급 일괄 취소 확인 모달 */}
      {cancelModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm"
            onClick={() => !cancellingAll && setCancelModalOpen(false)}
          />
          <div className="relative z-10 w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
            <div className="flex items-center gap-3 text-rose-600 dark:text-rose-400">
              <div className="rounded-xl bg-rose-100 p-2.5 dark:bg-rose-950/60">
                <AlertTriangle size={24} />
              </div>
              <h3 className="text-lg font-bold">긴급 일괄 주문 취소</h3>
            </div>
            <p className="mt-3 text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
              현재 활성화된 모든 미체결 주문(대기, 부분체결, 예약 주문 등)을 거래소에서{' '}
              <strong className="text-rose-600 dark:text-rose-400">즉시 일괄 취소</strong>합니다. 계속하시겠습니까?
            </p>
            <div className="mt-6 flex items-center justify-end gap-2.5">
              <button
                type="button"
                disabled={cancellingAll}
                onClick={() => setCancelModalOpen(false)}
                className="rounded-xl border border-slate-200 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                닫기
              </button>
              <button
                type="button"
                disabled={cancellingAll}
                onClick={handleConfirmCancelAll}
                className="flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-rose-700 disabled:opacity-50"
              >
                {cancellingAll && <Loader2 size={14} className="animate-spin" />}
                <span>{cancellingAll ? '취소 처리 중...' : '확인, 즉시 취소 실행'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
