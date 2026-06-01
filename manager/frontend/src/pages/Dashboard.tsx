import { useEffect, useState } from 'react'
import { Users, UserCheck, Clock, ShoppingCart, TrendingUp, AlertTriangle } from 'lucide-react'
import { fetchDashboard } from '../api/dashboard'
import type { DashboardData } from '../types'
import StatCard from '../components/ui/StatCard'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'

const STAT_CONFIG = [
  { key: 'users_total',   label: '전체 유저',   Icon: Users,         bg: 'bg-indigo-500' },
  { key: 'users_active',  label: '활성 유저',   Icon: UserCheck,     bg: 'bg-emerald-500' },
  { key: 'users_pending', label: '대기 유저',   Icon: Clock,         bg: 'bg-amber-500' },
  { key: 'orders_open',   label: '활성 주문',   Icon: ShoppingCart,  bg: 'bg-blue-500' },
  { key: 'trades_24h',    label: '24h 거래',    Icon: TrendingUp,    bg: 'bg-violet-500' },
  { key: 'errors_24h',    label: '24h 오류',    Icon: AlertTriangle, bg: 'bg-rose-500' },
] as const

function fmtTime(s: string) {
  return s ? s.slice(0, 19).replace('T', ' ') : '—'
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchDashboard()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
  }, [])

  if (!data && !error) return <Spinner />

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-slate-900 dark:text-white">대시보드</h1>

      {error && <ErrorBanner message={error} />}

      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
            {STAT_CONFIG.map(({ key, label, Icon, bg }) => (
              <StatCard
                key={key}
                label={label}
                value={data.stats[key]}
                icon={<Icon size={16} />}
                iconBg={bg}
              />
            ))}
          </div>

          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800">
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">최근 이벤트</h2>
            </div>
            <div className="overflow-x-auto">
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
                        이벤트 없음
                      </td>
                    </tr>
                  ) : data.recent_events.map((ev, i) => (
                    <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
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
          </div>
        </>
      )}
    </div>
  )
}
