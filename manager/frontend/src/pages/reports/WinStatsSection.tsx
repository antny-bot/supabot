import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell, PieChart, Pie
} from 'recharts'
import { fetchReportWinStats } from '../../api/reports'
import type { WinStatsReport } from '../../types'
import type { DateRangeValue } from '../../components/ui/DateRangePicker'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay, staggerDelayMs } from '../../utils/animation'
import { pctFmt, pctColor, PNL_UP_HEX, PNL_DOWN_HEX, CARD } from './ReportsShared'

export default function WinStatsSection({ dateRange }: { dateRange: DateRangeValue }) {
  const [data, setData] = useState<WinStatsReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportWinStats(dateRange)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [dateRange])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  const { stats } = data

  const countCards = [
    { label: '총 페어', value: stats.total_pairs.toLocaleString(), bg: 'bg-primary-500' },
    { label: '수익 거래', value: stats.win_count.toLocaleString(), bg: 'bg-up-500' },
    { label: '손실 거래', value: stats.loss_count.toLocaleString(), bg: 'bg-down-500' },
    { label: '승률', value: `${stats.win_rate}%`, bg: stats.win_rate >= 50 ? 'bg-up-500' : 'bg-amber-500' },
  ]

  const pieData = [
    { name: '수익 거래', value: stats.win_count },
    { name: '손실 거래', value: stats.loss_count },
  ]

  const barData = [
    { name: '평균수익', '수익률': stats.avg_win_pct },
    { name: '평균손실', '수익률': stats.avg_loss_pct },
  ]

  const COLORS = [PNL_UP_HEX, PNL_DOWN_HEX]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {countCards.map(({ label, value, bg }, index) => (
          <div key={label} className={`${CARD} animate-fade-in-up p-4`} style={staggerDelay(index)}>
            <p className={`text-xs font-medium text-white ${bg} w-fit px-2 py-0.5 rounded-md mb-2`}>{label}</p>
            <p className="text-2xl font-bold text-slate-900 dark:text-white">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-3 gap-3">
        {[
          { label: '평균 수익률 (win)', value: pctFmt(stats.avg_win_pct), color: pctColor(stats.avg_win_pct), desc: '수익 거래 평균' },
          { label: '평균 손실률 (loss)', value: pctFmt(stats.avg_loss_pct), color: pctColor(stats.avg_loss_pct), desc: '손실 거래 평균' },
          { label: 'RR 비율', value: `${stats.rr_ratio}`, color: stats.rr_ratio >= 1 ? 'text-up-600 dark:text-up-400' : 'text-down-600 dark:text-down-400', desc: '평균수익 / 평균손실' },
        ].map(({ label, value, color, desc }, index) => (
          <div key={label} className={`${CARD} animate-fade-in-up p-4`} style={staggerDelay(4 + index)}>
            <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
            <p className={`text-3xl font-bold mt-1 ${color}`}>{value}</p>
            <p className="text-xs text-slate-400 mt-1">{desc}</p>
          </div>
        ))}
      </div>

      {stats.total_pairs > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className={`${CARD} animate-fade-in-up p-4 h-72`} style={staggerDelay(7)}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">거래 승률 비중</h4>
            <ResponsiveContainer width="100%" height="90%">
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={65}
                  label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                  labelLine={false}
                  animationBegin={staggerDelayMs(7)}
                  animationDuration={600}
                >
                  {pieData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  itemStyle={{ color: '#fff', fontSize: '12px' }}
                  formatter={(value: any) => [`${value}건`, '거래수']}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className={`${CARD} animate-fade-in-up p-4 h-72`} style={staggerDelay(8)}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">평균 수익/손실 비교</h4>
            <ResponsiveContainer width="100%" height="90%">
              <BarChart data={barData} margin={{ top: 5, right: 5, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
                <XAxis dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} tickFormatter={(v) => `${v}%`} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  itemStyle={{ color: '#fff', fontSize: '12px' }}
                  formatter={(value: any) => [`${value >= 0 ? '+' : ''}${Number(value).toFixed(2)}%`, '수익률']}
                />
                <ReferenceLine y={0} stroke="#64748b" />
                <Bar dataKey="수익률" radius={4} animationBegin={staggerDelayMs(8)} animationDuration={600}>
                  {barData.map((entry: any, index: number) => {
                    const color = entry['수익률'] >= 0 ? PNL_UP_HEX : PNL_DOWN_HEX;
                    return <Cell key={`cell-${index}`} fill={color} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}
