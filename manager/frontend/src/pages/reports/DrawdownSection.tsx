import { useCallback, useEffect, useState } from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts'
import {
  ShieldAlert,
  TrendingDown,
  Award,
  AlertTriangle,
  Scale,
  Percent,
} from 'lucide-react'
import { fetchReportDrawdown } from '../../api/reports'
import type { DateRangeValue } from '../../components/ui/DateRangePicker'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import StatCard from '../../components/ui/StatCard'
import type { DrawdownReport } from '../../types'
import { krwFmt } from '../../utils/formatters'
import { staggerDelay } from '../../utils/animation'

interface Props {
  dateRange: DateRangeValue
}

export default function DrawdownSection({ dateRange }: Props) {
  const [data, setData] = useState<DrawdownReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    fetchReportDrawdown(dateRange)
      .then((res) => {
        setData(res)
        setError(null)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'MDD 분석 조회 실패'))
      .finally(() => setLoading(false))
  }, [dateRange])

  useEffect(() => {
    load()
  }, [load])

  if (loading && !data) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data || !data.series || data.series.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-xs text-slate-400 dark:border-slate-800 dark:bg-slate-900">
        선택한 기간 내 분석할 체결 데이터가 없습니다.
      </div>
    )
  }

  const { metrics, series } = data

  return (
    <div className="space-y-5">
      {/* 핵심 리스크 지표 카드 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <div className="animate-fade-in-up" style={staggerDelay(0)}>
          <StatCard
            label="최대 낙폭 (MDD)"
            value={`-${krwFmt(metrics.mdd)}`}
            subtext={`-${metrics.mdd_pct}%`}
            icon={<ShieldAlert size={16} />}
            iconBg="bg-rose-500"
          />
        </div>

        <div className="animate-fade-in-up" style={staggerDelay(1)}>
          <StatCard
            label="현재 낙폭 (DD)"
            value={metrics.current_drawdown > 0 ? `-${krwFmt(metrics.current_drawdown)}` : '0원'}
            subtext={metrics.current_drawdown > 0 ? `-${metrics.current_drawdown_pct}%` : '고점 유지중'}
            icon={<TrendingDown size={16} />}
            iconBg="bg-amber-500"
          />
        </div>

        <div className="animate-fade-in-up" style={staggerDelay(2)}>
          <StatCard
            label="손익비 (Profit Factor)"
            value={`${metrics.profit_factor}`}
            subtext="총이익 / 총손실"
            icon={<Scale size={16} />}
            iconBg="bg-indigo-500"
          />
        </div>

        <div className="animate-fade-in-up" style={staggerDelay(3)}>
          <StatCard
            label="승률 (Win Rate)"
            value={`${metrics.win_rate}%`}
            subtext={`${metrics.win_count}승 ${metrics.loss_count}패`}
            icon={<Percent size={16} />}
            iconBg="bg-emerald-500"
          />
        </div>

        <div className="animate-fade-in-up" style={staggerDelay(4)}>
          <StatCard
            label="최대 이익 거래"
            value={`+${krwFmt(metrics.max_win)}`}
            icon={<Award size={16} />}
            iconBg="bg-blue-500"
          />
        </div>

        <div className="animate-fade-in-up" style={staggerDelay(5)}>
          <StatCard
            label="최대 손실 거래"
            value={metrics.max_loss < 0 ? krwFmt(metrics.max_loss) : '0원'}
            icon={<AlertTriangle size={16} />}
            iconBg="bg-slate-700"
          />
        </div>
      </div>

      {/* 언더워터 차트 (고점 대비 하락폭 Underwater Chart) */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
          <div>
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">언더워터 차트 (고점 대비 낙폭)</h3>
            <p className="mt-0.5 text-app-caption text-slate-400">자산 고점 대비 하락률(%) 추이</p>
          </div>
          <span className="text-app-caption text-rose-500 font-bold">최대 {metrics.mdd_pct}%</span>
        </div>

        <div className="mt-4 h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="drawdownGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#f43f5e" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#94a3b8" />
              <YAxis
                tick={{ fontSize: 10 }}
                stroke="#94a3b8"
                tickFormatter={(v) => `-${v}%`}
                domain={[0, 'auto']}
              />
              <Tooltip
                formatter={(val: number) => [`-${val}%`, '고점 대비 낙폭']}
                labelFormatter={(label) => `체결 시점: ${label}`}
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
                dataKey="drawdown_pct"
                stroke="#f43f5e"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#drawdownGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 누적 손익 곡선 vs 최고점 곡선 */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
          <div>
            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">고점(Peak) 대비 누적 실현손익 추이</h3>
            <p className="mt-0.5 text-app-caption text-slate-400">자산의 전고점 갱신 및 회복 궤적</p>
          </div>
          <span className="text-app-caption text-indigo-500 font-bold">최고 누적: {krwFmt(metrics.peak_pnl)}</span>
        </div>

        <div className="mt-4 h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={series} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="peakGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 10 }} stroke="#94a3b8" tickFormatter={(v) => krwFmt(v)} />
              <Tooltip
                formatter={(val: number, name: string) => [
                  krwFmt(val),
                  name === 'peak' ? '최고점 (Peak)' : '누적 실현손익',
                ]}
                labelFormatter={(label) => `시점: ${label}`}
                contentStyle={{
                  backgroundColor: 'rgba(15, 23, 42, 0.9)',
                  border: 'none',
                  borderRadius: '8px',
                  color: '#fff',
                  fontSize: '12px',
                }}
              />
              <Area
                type="stepAfter"
                dataKey="peak"
                stroke="#10b981"
                strokeWidth={1.5}
                strokeDasharray="4 4"
                fill="none"
              />
              <Area
                type="monotone"
                dataKey="cumulative_pnl"
                stroke="#6366f1"
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#peakGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
