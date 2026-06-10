import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Clock, ShoppingCart, TrendingUp, UserCheck, Users } from 'lucide-react'
import { fetchDashboard } from '../api/dashboard'
import Badge from '../components/ui/Badge'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import Spinner from '../components/ui/Spinner'
import StatCard from '../components/ui/StatCard'
import { PAGE_META } from '../config/pageMeta'
import { useAuthContext } from '../contexts/AuthContext'
import { useRealtime } from '../hooks/useRealtime'
import type { DashboardData, DashboardStats } from '../types'

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

  const loadData = useCallback(() => {
    fetchDashboard()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류가 발생했습니다.'))
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  useRealtime(loadData)

  if (!data && !error) return <Spinner />

  const visibleStats = STAT_CONFIG.filter((item) => !item.adminOnly || user?.is_admin)

  return (
    <div className="space-y-6">
      <PageHeader {...PAGE_META.dashboard} />

      {error && <ErrorBanner message={error} />}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            {visibleStats.map(({ key, label, Icon, bg }) => (
              <StatCard
                key={key}
                label={label}
                value={data.stats[key] ?? 0}
                icon={<Icon size={16} />}
                iconBg={bg}
              />
            ))}

          </div>

          {user?.is_admin && (
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
                <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">최근 미확인 이벤트</h2>
              </div>

              <div className="hidden overflow-x-auto md:block">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
                      <th className="px-4 py-2.5 text-left font-medium">시간</th>
                      <th className="px-4 py-2.5 text-left font-medium">레벨</th>
                      <th className="px-4 py-2.5 text-left font-medium">소스</th>
                      <th className="px-4 py-2.5 text-left font-medium">메시지</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {data.recent_events.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-4 py-8 text-center text-xs text-slate-400 dark:text-slate-500">
                          미확인 이벤트가 없습니다.
                        </td>
                      </tr>
                    ) : data.recent_events.map((event) => (
                      <tr key={event.id} className="transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50">
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
                ) : data.recent_events.map((event) => (
                  <div key={event.id} className="space-y-1.5 p-3 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-mono text-slate-500 dark:text-slate-400">{fmtTime(String(event.created_at))}</span>
                      <Badge value={event.level} />
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
