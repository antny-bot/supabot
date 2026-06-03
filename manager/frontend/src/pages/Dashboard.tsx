import { useEffect, useState, useCallback } from 'react'
import { Users, UserCheck, Clock, ShoppingCart, TrendingUp, AlertTriangle, Shield } from 'lucide-react'
import { fetchDashboard } from '../api/dashboard'
import type { DashboardData, DashboardStats } from '../types'
import { useAuthContext } from '../contexts/AuthContext'
import { useRealtime } from '../hooks/useRealtime'
import StatCard from '../components/ui/StatCard'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'

const STAT_CONFIG: {
  key: keyof DashboardStats
  label: string
  Icon: React.ElementType
  bg: string
  adminOnly: boolean
}[] = [
  { key: 'users_total', label: '전체 사용자', Icon: Users, bg: 'bg-indigo-500', adminOnly: true },
  { key: 'users_active', label: '활성 사용자', Icon: UserCheck, bg: 'bg-emerald-500', adminOnly: true },
  { key: 'users_pending', label: '승인 대기', Icon: Clock, bg: 'bg-amber-500', adminOnly: true },
  { key: 'orders_open', label: '오픈 주문', Icon: ShoppingCart, bg: 'bg-blue-500', adminOnly: false },
  { key: 'trades_24h', label: '24h 거래', Icon: TrendingUp, bg: 'bg-violet-500', adminOnly: false },
  { key: 'errors_24h', label: '24h 오류', Icon: AlertTriangle, bg: 'bg-rose-500', adminOnly: true },
]

function fmtTime(s: string) {
  return s ? s.slice(0, 19).replace('T', ' ') : '--'
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

  const visibleStats = STAT_CONFIG.filter((c) => !c.adminOnly || user?.is_admin)
  const mfaSummary = data?.mfa_enabled ?? user?.mfa_enabled ?? false

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-slate-900 dark:text-white">대시보드</h1>

      {error && <ErrorBanner message={error} />}

      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
            {visibleStats.map(({ key, label, Icon, bg }) => (
              <StatCard
                key={key}
                label={label}
                value={data.stats[key] ?? 0}
                icon={<Icon size={16} />}
                iconBg={bg}
              />
            ))}
            <StatCard
              label="2차 인증"
              value={mfaSummary ? '활성' : '비활성'}
              icon={<Shield size={16} />}
              iconBg={mfaSummary ? 'bg-emerald-500' : 'bg-slate-500'}
            />
          </div>

          {user?.is_admin && (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800">
                <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">최근 미확인 이벤트</h2>
              </div>
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-slate-500 dark:text-slate-400 border-b border-slate-100 dark:border-slate-800">
                      <th className="px-4 py-2.5 text-left font-medium">시간</th>
                      <th className="px-4 py-2.5 text-left font-medium">레벨</th>
                      <th className="px-4 py-2.5 text-left font-medium">소스</th>
                      <th className="px-4 py-2.5 text-left font-medium">메시지</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {data.recent_events.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-4 py-8 text-center text-slate-400 dark:text-slate-500 text-xs">
                          미확인 이벤트가 없습니다.
                        </td>
                      </tr>
                    ) : data.recent_events.map((ev) => (
                      <tr key={ev.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                        <td className="px-4 py-2.5 text-slate-500 dark:text-slate-400 font-mono text-xs whitespace-nowrap">
                          {fmtTime(String(ev.created_at))}
                        </td>
                        <td className="px-4 py-2.5">
                          <Badge value={ev.level} />
                        </td>
                        <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300 text-xs">{ev.source}</td>
                        <td className="px-4 py-2.5 text-slate-700 dark:text-slate-200 text-xs max-w-xs truncate">
                          {ev.message}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="block md:hidden divide-y divide-slate-100 dark:divide-slate-800">
                {data.recent_events.length === 0 ? (
                  <div className="px-4 py-8 text-center text-slate-400 dark:text-slate-500 text-xs">
                    미확인 이벤트가 없습니다.
                  </div>
                ) : data.recent_events.map((ev) => (
                  <div key={ev.id} className="p-3 space-y-1.5 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-slate-500 dark:text-slate-400 font-mono">{fmtTime(String(ev.created_at))}</span>
                      <Badge value={ev.level} />
                    </div>
                    <div className="text-xs font-semibold text-slate-600 dark:text-slate-300">[{ev.source || 'system'}]</div>
                    <div className="text-xs text-slate-700 dark:text-slate-200 break-words">{ev.message}</div>
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
