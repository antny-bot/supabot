import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ChevronRight, Clock, Receipt, ShoppingCart, TrendingUp, UserCheck, Users, Check, Wallet } from 'lucide-react'
import { fetchDashboard } from '../api/dashboard'
import { fetchReportHoldings } from '../api/reports'
import { fetchTrades } from '../api/trades'
import { markEventRead } from '../api/events'
import Badge from '../components/ui/Badge'
import type { DateRangeValue } from '../components/ui/DateRangePicker'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import Spinner from '../components/ui/Spinner'
import StatCard from '../components/ui/StatCard'
import { PAGE_META } from '../config/pageMeta'
import { useAuthContext } from '../contexts/AuthContext'
import { useRealtime } from '../hooks/useRealtime'
import type { DashboardData, DashboardStats, HoldingsReport, Trade } from '../types'
import { staggerDelay } from '../utils/animation'
import { krwFmt, pnlTextClass } from '../utils/formatters'
import SyncIndicator from '../components/ui/SyncIndicator'

const RECENT_TRADES_RANGE: DateRangeValue = { mode: '7d', from: '', to: '' }

const STAT_CONFIG: {
  key: keyof DashboardStats
  label: string
  Icon: React.ElementType
  bg: string
  adminOnly: boolean
}[] = [
  { key: 'users_total', label: '전체 사용자', Icon: Users, bg: 'bg-primary-500', adminOnly: true },
  { key: 'users_active', label: '활성 사용자', Icon: UserCheck, bg: 'bg-emerald-500', adminOnly: true },
  { key: 'users_pending', label: '승인 대기', Icon: Clock, bg: 'bg-amber-500', adminOnly: true },
  { key: 'orders_open', label: '오픈 주문', Icon: ShoppingCart, bg: 'bg-blue-500', adminOnly: false },
  { key: 'trades_24h', label: '24h 거래', Icon: TrendingUp, bg: 'bg-violet-500', adminOnly: false },
  { key: 'errors_24h', label: '24h 오류', Icon: AlertTriangle, bg: 'bg-rose-500', adminOnly: true },
]

function fmtTime(value: string) {
  return value ? value.slice(0, 19).replace('T', ' ') : '--'
}

export default function Dashboard() {
  const { user } = useAuthContext()
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [pendingEventId, setPendingEventId] = useState<number | null>(null)
  const [holdings, setHoldings] = useState<HoldingsReport | null>(null)
  const [recentTrades, setRecentTrades] = useState<Trade[] | null>(null)

  const loadData = useCallback(() => {
    setLoading(true)
    fetchDashboard()
      .then((res) => {
        setData(res)
        setLastUpdated(new Date())
        setError(null)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류가 발생했습니다.'))
      .finally(() => setLoading(false))
  }, [])

  const isAdmin = user?.is_admin ?? false

  const loadExtras = useCallback(() => {
    if (isAdmin) return
    Promise.all([fetchReportHoldings(), fetchTrades(RECENT_TRADES_RANGE, 1, 5)])
      .then(([holdingsRes, tradesRes]) => {
        setHoldings(holdingsRes)
        setRecentTrades(tradesRes.trades)
      })
      .catch(() => {
        setHoldings(null)
        setRecentTrades(null)
      })
  }, [isAdmin])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    loadExtras()
  }, [loadExtras])

  useRealtime(useCallback(() => {
    loadData()
    loadExtras()
  }, [loadData, loadExtras]))

  const handleMarkAsRead = async (eventId: number) => {
    setPendingEventId(eventId)
    try {
      await markEventRead(eventId)
      // Refresh dashboard data after marking event as read
      loadData()
    } catch (e) {
      alert(e instanceof Error ? e.message : '이벤트 확인 처리에 실패했습니다.')
    } finally {
      setPendingEventId(null)
    }
  }

  if (!data && !error) return <Spinner />

  const visibleStats = STAT_CONFIG.filter((item) => !item.adminOnly || user?.is_admin)

  return (
    <div className="space-y-6">
      <PageHeader
        {...PAGE_META.dashboard}
        actions={<SyncIndicator lastUpdated={lastUpdated} loading={loading} error={error} />}
      />

      {error && <ErrorBanner message={error} />}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            {visibleStats.map(({ key, label, Icon, bg }, index) => (
              <div key={key} className="animate-fade-in-up" style={staggerDelay(index)}>
                <StatCard
                  label={label}
                  value={data.stats[key] ?? 0}
                  icon={<Icon size={16} />}
                  iconBg={bg}
                />
              </div>
            ))}
          </div>

          {!isAdmin && (
            <div className="grid gap-4 md:grid-cols-2">
              <div
                role="button"
                tabIndex={0}
                onClick={() => navigate('/reports')}
                onKeyDown={(e) => { if (e.key === 'Enter') navigate('/reports') }}
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
                        <p className="text-app-metric font-bold text-slate-900 dark:text-white">{krwFmt(holdings.summary.total_value)}</p>
                        <p className="mt-0.5 text-app-caption text-slate-500 dark:text-slate-400">평가금액</p>
                      </div>
                      <div>
                        <p className={`text-app-metric font-bold ${pnlTextClass(holdings.summary.total_pnl)}`}>
                          {holdings.summary.total_pnl >= 0 ? '+' : '-'}{krwFmt(Math.abs(holdings.summary.total_pnl))}
                        </p>
                        <p className="mt-0.5 text-app-caption text-slate-500 dark:text-slate-400">
                          평가손익 ({holdings.summary.total_roi_pct >= 0 ? '+' : ''}{holdings.summary.total_roi_pct}%)
                        </p>
                      </div>
                      <div>
                        <p className="text-app-metric font-bold text-slate-900 dark:text-white">{holdings.summary.asset_count}</p>
                        <p className="mt-0.5 text-app-caption text-slate-500 dark:text-slate-400">투자 종목</p>
                      </div>
                    </div>

                    <div className="divide-y divide-slate-100 dark:divide-slate-800">
                      {holdings.rows.length === 0 ? (
                        <div className="px-4 py-6 text-center text-xs text-slate-400 dark:text-slate-500">보유중인 자산이 없습니다.</div>
                      ) : holdings.rows.slice(0, 5).map((row, index) => (
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
                            <span className={row.current_price > 0 ? pnlTextClass(row.roi_pct) : 'text-slate-400 dark:text-slate-500'}>
                              {row.current_price > 0 ? `${row.roi_pct >= 0 ? '+' : ''}${row.roi_pct}%` : '—'}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <div
                role="button"
                tabIndex={0}
                onClick={() => navigate('/trades')}
                onKeyDown={(e) => { if (e.key === 'Enter') navigate('/trades') }}
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
                    ) : recentTrades.map((trade, index) => (
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
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {user?.is_admin && (
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-800 flex justify-between items-center">
                <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">최근 미확인 이벤트</h2>
                <span className="text-[10px] text-slate-400 font-mono">총 {data.recent_events.length}건</span>
              </div>

              <div className="hidden overflow-x-auto md:block">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
                      <th className="px-4 py-2.5 text-left font-medium">시간</th>
                      <th className="px-4 py-2.5 text-left font-medium">레벨</th>
                      <th className="px-4 py-2.5 text-left font-medium">소스</th>
                      <th className="px-4 py-2.5 text-left font-medium">메시지</th>
                      <th className="px-4 py-2.5 text-center font-medium w-20">작업</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {data.recent_events.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="px-4 py-8 text-center text-xs text-slate-400 dark:text-slate-500">
                          미확인 이벤트가 없습니다.
                        </td>
                      </tr>
                    ) : data.recent_events.map((event, index) => (
                      <tr key={event.id} className="animate-fade-in transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50" style={staggerDelay(index)}>
                        <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-slate-500 dark:text-slate-400">
                          {fmtTime(String(event.created_at))}
                        </td>
                        <td className="px-4 py-2.5">
                          <Badge value={event.level} />
                        </td>
                        <td className="px-4 py-2.5 text-xs text-slate-600 dark:text-slate-300">{event.source}</td>
                        <td className="max-w-xs truncate px-4 py-2.5 text-xs text-slate-700 dark:text-slate-200">
                          {event.message}
                        </td>
                        <td className="px-4 py-2.5 text-center whitespace-nowrap">
                          <button
                            onClick={() => handleMarkAsRead(event.id)}
                            disabled={pendingEventId === event.id}
                            className="inline-flex items-center gap-1 rounded bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-600 hover:bg-emerald-100 disabled:opacity-50 dark:bg-emerald-950/30 dark:text-emerald-400 dark:hover:bg-emerald-900/40"
                            title="확인 처리"
                          >
                            <Check size={12} />
                            <span>확인</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="block divide-y divide-slate-100 dark:divide-slate-800 md:hidden">
                {data.recent_events.length === 0 ? (
                  <div className="px-4 py-8 text-center text-xs text-slate-400 dark:text-slate-500">
                    미확인 이벤트가 없습니다.
                  </div>
                ) : data.recent_events.map((event, index) => (
                  <div key={event.id} className="animate-fade-in-up space-y-1.5 p-3 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50" style={staggerDelay(index)}>
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-mono text-slate-500 dark:text-slate-400">{fmtTime(String(event.created_at))}</span>
                      <div className="flex items-center gap-2">
                        <Badge value={event.level} />
                        <button
                          onClick={() => handleMarkAsRead(event.id)}
                          disabled={pendingEventId === event.id}
                          className="inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-600 hover:bg-emerald-100 disabled:opacity-50 dark:bg-emerald-950/30 dark:text-emerald-400"
                        >
                          <Check size={10} />
                          <span>확인</span>
                        </button>
                      </div>
                    </div>
                    <div className="text-xs font-semibold text-slate-600 dark:text-slate-300">[{event.source || 'system'}]</div>
                    <div className="break-words text-xs text-slate-700 dark:text-slate-200">{event.message}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
