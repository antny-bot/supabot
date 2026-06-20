import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, PieChart, Pie, Cell
} from 'recharts'
import { fetchReportStrategy } from '../../api/reports'
import type { StrategyReport } from '../../types'
import type { DateRangeValue } from '../../components/ui/DateRangePicker'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import ProgressBar from '../../components/ui/ProgressBar'
import { staggerDelay, staggerDelayMs } from '../../utils/animation'
import { krwFmt, pctFmt, pctColor, PNL_UP_HEX, PNL_DOWN_HEX, CARD, TH, TD } from './ReportsShared'

export default function StrategySection({ dateRange }: { dateRange: DateRangeValue }) {
  const [data, setData] = useState<StrategyReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportStrategy(dateRange)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [dateRange])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  const chartData = data.rows.map(r => ({
    name: r.strategy,
    value: Math.max(0, r.pnl),
    '손익': r.pnl,
    '거래수': r.trade_count
  }))

  const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#3b82f6', '#8b5cf6']

  return (
    <div className="space-y-4">
      {chartData.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className={`${CARD} animate-fade-in-up p-4 h-64`} style={staggerDelay(0)}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">전략별 손익 비교</h4>
            <ResponsiveContainer width="100%" height="90%">
              <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 5, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
                <XAxis type="number" stroke="#64748b" fontSize={11} tickFormatter={(v) => krwFmt(v)} />
                <YAxis dataKey="name" type="category" stroke="#64748b" fontSize={11} width={80} tickLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  itemStyle={{ color: '#fff', fontSize: '12px' }}
                  formatter={(value: any) => [`${krwFmt(Number(value))}원`, '손익']}
                />
                <ReferenceLine x={0} stroke="#64748b" />
                <Bar dataKey="손익" radius={[0, 4, 4, 0]} animationBegin={staggerDelayMs(0)} animationDuration={600}>
                  {chartData.map((entry: any, index: number) => {
                    const color = entry['손익'] >= 0 ? PNL_UP_HEX : PNL_DOWN_HEX;
                    return <Cell key={`cell-${index}`} fill={color} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className={`${CARD} animate-fade-in-up p-4 h-64`} style={staggerDelay(1)}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">전략별 거래 비중 (거래건수)</h4>
            <ResponsiveContainer width="100%" height="90%">
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="거래수"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={65}
                  label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                  labelLine={false}
                  animationBegin={staggerDelayMs(1)}
                  animationDuration={600}
                >
                  {chartData.map((_, index) => (
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
        </div>
      )}

      <div className={`${CARD} animate-fade-in-up overflow-hidden`} style={staggerDelay(2)}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">전략별 손익</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left`}>전략</th>
                <th className={`${TH} text-right`}>거래수</th>
                <th className={`${TH} text-right`}>실현원가</th>
                <th className={`${TH} text-right`}>매도금액</th>
                <th className={`${TH} text-right`}>수수료</th>
                <th className={`${TH} text-right`}>손익</th>
                <th className={`${TH} text-right`}>수익률</th>
                <th className={`${TH} text-left`} style={{ minWidth: 120 }}>승률</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.rows.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-400 text-xs">데이터 없음</td></tr>
              ) : data.rows.map((r, i) => (
                <tr key={i} className="animate-fade-in hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors" style={staggerDelay(i)}>
                  <td className={`${TD} text-xs font-medium text-slate-700 dark:text-slate-300`}>{r.strategy}</td>
                  <td className={`${TD} text-right text-xs text-slate-500`}>{r.trade_count.toLocaleString()}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.bid_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.ask_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-500`}>{krwFmt(r.fee_amount)}</td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.pnl)}`}>{krwFmt(Math.abs(r.pnl))}</td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.roi_pct)}`}>{pctFmt(r.roi_pct)}</td>
                  <td className={TD}><ProgressBar value={r.win_rate} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
