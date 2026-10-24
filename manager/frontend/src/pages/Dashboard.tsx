import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ChevronRight,
  Receipt,
  ShoppingCart,
  TrendingUp,
  Wallet,
  Coins,
  Activity,
  AlertTriangle,
  PieChart as PieIcon,
  LineChart as ChartIcon,
  ShieldAlert,
  Loader2,
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
import Spinner from '../components/ui/Spinner'
import StatCard from '../components/ui/StatCard'
import { PAGE_META } from '../config/pageMeta'
import { useRealtime } from '../hooks/useRealtime'
import { useToast } from '../contexts/ToastContext'
import type { DashboardData, HoldingsReport, Trade, DailyReport, AllocationReport } from '../types'
import { staggerDelay } from '../utils/animation'
import { krwFmt, pnlTextClass } from '../utils/formatters'
import SyncIndicator from '../components/ui/SyncIndicator'

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
      fetchReportHoldings(),
      fetchTrades(RECENT_TRADES_RANGE, 1, 5),
      fetchReportDaily(CHART_RANGE),
      fetchReportAllocation().catch(() => null),
    ])
      .then(([holdingsRes, tradesRes, dailyRes, allocRes]) => {
        setHoldings(holdingsRes)
        setRecentTrades(tradesRes.trades)
        setDailyData(dailyRes)
        setAllocation(allocRes)
      })
      .catch(() => {
        // 보조 데이터 실패 시에도 메인 화면은 유지
      })
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    loadExtras()
  }, [loadExtras])

  useRealtime(
    useCallback(() => {
      loadData()
      loadExtras()
    }, [loadData, loadExtras]),
  )

  const handleEmergencyCancel = async () => {
    setCancellingAll(true)
    try {
      const res = await cancelAllOrders()
      if (res.ok) {
        toast.success(`오픈 주문 ${res.cancelled_count}건이 일괄 취소되었습니다.`)
        if (res.failed_count > 0) {
          toast.warning(`실패한 주문: ${res.failed_count}건`)
        }
      } else {
        toast.error('주문 일괄 취소 중 오류가 발생했습니다.')
      }
      setCancelModalOpen(false)
      loadData()
      loadExtras()
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : '취소 요청 실패')
    } finally {
      setCancellingAll(false)
    }
  }

  if (!data && !error) return <Spinner />

  const totalCost = holdings?.summary.total_cost ?? 0
  const totalValue = holdings?.summary.total_value ?? 0
  const totalPnl = holdings?.summary.total_pnl ?? 0
  const totalRoi = holdings?.summary.total_roi_pct ?? 0
  const pnl24h = data?.stats.realized_pnl_24h ?? 0
  const botStatus = data?.stats.bot_status ?? 'online'

  // 차트 데이터 구성
  const chartRows = dailyData?.rows && dailyData.rows.length > 0 ? dailyData.rows : []

  // 자산 배분 데이터 (Allocation API 우선, 없으면 Holdings 기반)
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
    <div className="space-y-6">
      <PageHeader
        {...PAGE_META.dashboard}
        actions={
          <div className="flex items-center gap-2">
            <SyncIndicator lastUpdated={lastUpdated} loading={loading} error={error} />
            <button
              onClick={() => setCancelModalOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900 rounded-lg hover:bg-rose-100 dark:hover:bg-rose-900/60 transition-colors shadow-sm"
              title="비상시 모든 활성 주문 즉시 취소"
            >
              <ShieldAlert size={14} />
              <span>긴급 일괄 취소</span>
            </button>
          </div>
        }
      />

      {error && <ErrorBanner message={error} />}

      {/* 6대 핵심 통계 카드 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <div className="animate-fade-in-up" style={staggerDelay(0)}>
          <StatCard
            label="총 평가자산"
            value={totalValue > 0 ? krwFmt(totalValue) : '0원'}
            icon={<Wallet size={16} />}
            iconBg="bg-emerald-500"
          />
        </div>

        <div className="animate-fade-in-up" style={staggerDelay(1)}>
          <StatCard
            label="총 투자원금"
            value={totalCost > 0 ? krwFmt(totalCost) : '0원'}
            icon={<Coins size={16} />}
            iconBg="bg-slate-600"
          />
        </div>

        <div className="animate-fade-in-up" style={staggerDelay(2)}>
          <StatCard
            label="총 평가손익"
            value={`${totalPnl >= 0 ? '+' : ''}${krwFmt(totalPnl)}`}
            subtext={`${totalRoi >= 0 ? '+' : ''}${totalRoi}%`}
            icon={<TrendingUp size={16} />}
            iconBg={totalPnl >= 0 ? 'bg-red-500' : 'bg-blue-500'}
          />
        </div>

        <div className="animate-fade-in-up" style={staggerDelay(3)}>
          <StatCard
            label="24h 실현손익"
            value={`${pnl24h >= 0 ? '+' : ''}${krwFmt(pnl24h)}`}
            icon={<TrendingUp size={16} />}
            iconBg="bg-violet-500"
          />
        </div>

        <div className="animate-fade-in-up" style={staggerDelay(4)}>
          <StatCard
            label="활성 주문"
            value={`${data?.stats.orders_open ?? 0}건`}
            icon={<ShoppingCart size={16} />}
            iconBg="bg-blue-500"
          />
        </div>

        <div className="animate-fade-in-up" style={staggerDelay(5)}>
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="text-app-label text-slate-500 dark:text-slate-400">봇 상태</span>
              <div
                className={`p-1.5 rounded-lg text-white ${
                  botStatus === 'online' ? 'bg-emerald-500' : botStatus === 'idle' ? 'bg-amber-500' : 'bg-rose-500'
                }`}
              >
                <Activity size={16} />
              </div>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <span
                className={`inline-block h-2.5 w-2.5 rounded-full ${
                  botStatus === 'online'
                    ? 'bg-emerald-500 animate-pulse'
                    : botStatus === 'idle'
                    ? 'bg-amber-500'
                    : 'bg-rose-500'
                }`}
              />
              <span className="text-app-body font-bold text-slate-800 dark:text-slate-100 uppercase">
                {botStatus}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 시각화 차트 섹션: 최근 누적 손익 곡선 & 거래소별 자산 배분 비중 */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* 누적 손익 면적 차트 (2 cols on md+) */}
        <div className="md:col-span-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 dark:text-slate-300">
              <ChartIcon size={14} /> 일별 누적 실현손익 추이
            </h2>
            <span className="text-app-caption text-slate-400">최근 30일</span>
          </div>

          <div className="mt-4 h-56 w-full">
            {chartRows.length === 0 ? (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">
                표시할 손익 데이터가 없습니다.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartRows} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                  <YAxis tick={{ fontSize: 10 }} stroke="#94a3b8" tickFormatter={(v) => krwFmt(v)} />
                  <RechartsTooltip
                    formatter={(val: number) => [`${krwFmt(val)}`, '누적 손익']}
                    labelFormatter={(label) => `일자: ${label}`}
                    contentStyle={{
                      backgroundColor: 'rgba(15, 23, 42, 0.9)',
                      border: 'none',
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
                    fill="url(#pnlGradient)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* 자산 배분 비중 도넛 차트 (1 col on md+) */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 dark:text-slate-300">
              <PieIcon size={14} /> 거래소별 자산 배분
            </h2>
            <button
              onClick={() => navigate('/reports')}
              className="text-app-caption text-indigo-500 hover:underline"
            >
              상세보기
            </button>
          </div>

          <div className="mt-4 h-56 w-full">
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
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {donutData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={ALLOCATION_COLORS[index % ALLOCATION_COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    formatter={(val: number) => [`${krwFmt(val)}`, '평가금액']}
                    contentStyle={{
                      backgroundColor: 'rgba(15, 23, 42, 0.9)',
                      border: 'none',
                      borderRadius: '8px',
                      color: '#fff',
                      fontSize: '12px',
                    }}
                  />
                  <Legend
                    verticalAlign="bottom"
                    iconSize={8}
                    formatter={(value) => <span className="text-xs text-slate-600 dark:text-slate-300">{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* 하단 요약 카드 (보유자산 & 최근 체결) */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* 보유자산 요약 */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => navigate('/reports')}
          onKeyDown={(e) => {
            if (e.key === 'Enter') navigate('/reports')
          }}
          className="cursor-pointer overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition-colors hover:border-primary-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-primary-700"
        >
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 dark:text-slate-300">
              <Wallet size={14} /> 보유자산 요약
            </h2>
            <ChevronRight size={16} className="text-slate-400 dark:text-slate-500" />
          </div>

          {!holdings ? (
            <div className="px-4 py-8 text-center text-xs text-slate-400 dark:text-slate-500">불러오는 중...</div>
          ) : (
            <>
              <div className="grid grid-cols-3 divide-x divide-slate-100 border-b border-slate-100 py-3 text-center dark:divide-slate-800 dark:border-slate-800">
                <div>
                  <p className="text-app-metric font-bold text-slate-900 dark:text-white">
                    {krwFmt(holdings.summary.total_value)}
                  </p>
                  <p className="mt-0.5 text-app-caption text-slate-500 dark:text-slate-400">평가금액</p>
                </div>
                <div>
                  <p className={`text-app-metric font-bold ${pnlTextClass(holdings.summary.total_pnl)}`}>
                    {holdings.summary.total_pnl >= 0 ? '+' : '-'}
                    {krwFmt(Math.abs(holdings.summary.total_pnl))}
                  </p>
                  <p className="mt-0.5 text-app-caption text-slate-500 dark:text-slate-400">
                    평가손익 ({holdings.summary.total_roi_pct >= 0 ? '+' : ''}
                    {holdings.summary.total_roi_pct}%)
                  </p>
                </div>
                <div>
                  <p className="text-app-metric font-bold text-slate-900 dark:text-white">
                    {holdings.summary.asset_count}
                  </p>
                  <p className="mt-0.5 text-app-caption text-slate-500 dark:text-slate-400">투자 종목</p>
                </div>
              </div>

              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {holdings.rows.length === 0 ? (
                  <div className="px-4 py-6 text-center text-xs text-slate-400 dark:text-slate-500">
                    보유중인 자산이 없습니다.
                  </div>
                ) : (
                  holdings.rows.slice(0, 5).map((row, index) => (
                    <div
                      key={`${row.exchange}-${row.ticker}`}
                      className="animate-fade-in flex items-center justify-between px-4 py-2.5 text-xs"
                      style={staggerDelay(index)}
                    >
                      <div className="flex min-w-0 items-center gap-1.5">
                        <Badge value={row.exchange} label={row.exchange.toUpperCase()} />
                        <span className="truncate font-medium text-slate-700 dark:text-slate-200">{row.ticker}</span>
                      </div>
                      <div className="flex shrink-0 items-center gap-2 font-mono">
                        <span className="text-slate-600 dark:text-slate-400">
                          {row.current_price > 0 ? krwFmt(row.value_krw) : '—'}
                        </span>
                        <span
                          className={
                            row.current_price > 0 ? pnlTextClass(row.roi_pct) : 'text-slate-400 dark:text-slate-500'
                          }
                        >
                          {row.current_price > 0 ? `${row.roi_pct >= 0 ? '+' : ''}${row.roi_pct}%` : '—'}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>

        {/* 최근 체결 내역 */}
        <div
          role="button"
          tabIndex={0}
          onClick={() => navigate('/trades')}
          onKeyDown={(e) => {
            if (e.key === 'Enter') navigate('/trades')
          }}
          className="cursor-pointer overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition-colors hover:border-primary-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-primary-700"
        >
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 dark:text-slate-300">
              <Receipt size={14} /> 최근 체결
            </h2>
            <ChevronRight size={16} className="text-slate-400 dark:text-slate-500" />
          </div>

          {!recentTrades ? (
            <div className="px-4 py-8 text-center text-xs text-slate-400 dark:text-slate-500">불러오는 중...</div>
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {recentTrades.length === 0 ? (
                <div className="px-4 py-8 text-center text-xs text-slate-400 dark:text-slate-500">
                  최근 체결 내역이 없습니다.
                </div>
              ) : (
                recentTrades.map((trade, index) => (
                  <div
                    key={`${trade.executed_at}-${trade.ticker}-${index}`}
                    className="animate-fade-in flex items-center justify-between px-4 py-2.5 text-xs"
                    style={staggerDelay(index)}
                  >
                    <div className="flex min-w-0 items-center gap-1.5">
                      <Badge value={trade.side} />
                      <Badge value={trade.exchange} label={trade.exchange.toUpperCase()} />
                      <span className="truncate font-medium text-slate-700 dark:text-slate-200">{trade.ticker}</span>
                    </div>
                    <div className="flex shrink-0 items-center gap-2 font-mono text-slate-600 dark:text-slate-400">
                      <span>{krwFmt(trade.krw)}</span>
                      <span className="text-slate-400 dark:text-slate-500">{trade.executed_fmt}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* 비상 긴급 주문 일괄 취소 확인 모달 */}
      {cancelModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800 animate-fade-in">
            <div className="flex items-center gap-3 text-rose-600 dark:text-rose-400">
              <div className="p-2.5 bg-rose-100 dark:bg-rose-950/60 rounded-xl">
                <AlertTriangle size={24} />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900 dark:text-white">긴급 주문 일괄 취소</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">오픈 상태의 모든 주문 취소</p>
              </div>
            </div>

            <p className="mt-4 text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              현재 활성화된 <strong className="text-rose-600 dark:text-rose-400">{data?.stats.orders_open ?? 0}건</strong>의 대기 및 부분체결 주문을 각 거래소에 요청하여 즉시 취소합니다. 계속하시겠습니까?
            </p>

            <div className="mt-6 flex justify-end gap-2.5">
              <button
                type="button"
                onClick={() => setCancelModalOpen(false)}
                disabled={cancellingAll}
                className="px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
              >
                닫기
              </button>
              <button
                type="button"
                onClick={handleEmergencyCancel}
                disabled={cancellingAll}
                className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-sm transition-colors disabled:opacity-50"
              >
                {cancellingAll ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    취소 처리 중...
                  </>
                ) : (
                  '네, 전체 취소합니다'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
