import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Clock, ShoppingCart, TrendingUp, UserCheck, Users, Check } from 'lucide-react'
import { fetchDashboard } from '../api/dashboard'
import { markEventRead } from '../api/events'
import Badge from '../components/ui/Badge'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import Spinner from '../components/ui/Spinner'
import StatCard from '../components/ui/StatCard'
import { PAGE_META } from '../config/pageMeta'
import { useAuthContext } from '../contexts/AuthContext'
import { useRealtime } from '../hooks/useRealtime'
import type { DashboardData, DashboardStats } from '../types'
import { staggerDelay } from '../utils/animation'
import SyncIndicator from '../components/ui/SyncIndicator'

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
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [pendingEventId, setPendingEventId] = useState<number | null>(null)

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

  useEffect(() => {
    loadData()
  }, [loadData])

  useRealtime(loadData)

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
