import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Receipt, ShoppingCart, TrendingUp, Wallet } from 'lucide-react'
import { fetchDashboard } from '../api/dashboard'
import { fetchReportHoldings } from '../api/reports'
import { fetchTrades } from '../api/trades'
import Badge from '../components/ui/Badge'
import type { DateRangeValue } from '../components/ui/DateRangePicker'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import Spinner from '../components/ui/Spinner'
import StatCard from '../components/ui/StatCard'
import { PAGE_META } from '../config/pageMeta'
import { useRealtime } from '../hooks/useRealtime'
import type { DashboardData, DashboardStats, HoldingsReport, Trade } from '../types'
import { staggerDelay } from '../utils/animation'
import { krwFmt, pnlTextClass } from '../utils/formatters'
import SyncIndicator from '../components/ui/SyncIndicator'

const RECENT_TRADES_RANGE: DateRangeValue = { mode: '7d', from: '', to: '' }

const STAT_CONFIG: { key: keyof DashboardStats; label: string; Icon: React.ElementType; bg: string }[] = [
  { key: 'orders_open', label: '오픈 주문', Icon: ShoppingCart, bg: 'bg-blue-500' },
  { key: 'trades_24h', label: '24h 거래', Icon: TrendingUp, bg: 'bg-violet-500' },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
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

  const loadExtras = useCallback(() => {
    Promise.all([fetchReportHoldings(), fetchTrades(RECENT_TRADES_RANGE, 1, 5)])
      .then(([holdingsRes, tradesRes]) => {
        setHoldings(holdingsRes)
        setRecentTrades(tradesRes.trades)
      })
      .catch(() => {
        setHoldings(null)
        setRecentTrades(null)
      })
  }, [])

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

  if (!data && !error) return <Spinner />

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
            {STAT_CONFIG.map(({ key, label, Icon, bg }, index) => (
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
        </>
      )}
    </div>
  )
}
