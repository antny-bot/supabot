import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell, LineChart, Line
} from 'recharts'
import { fetchReportMonthly } from '../../api/reports'
import type { MonthlyReport } from '../../types'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay, staggerDelayMs } from '../../utils/animation'
import { krwFmt, pctColor, PNL_UP_HEX, PNL_DOWN_HEX, CARD, TH, TD } from './ReportsShared'

export default function MonthlySection() {
  const [data, setData] = useState<MonthlyReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportMonthly()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  let cumulative = 0;
  const chartData = data.rows.map(r => {
    cumulative += r.pnl;
    return {
      name: r.month,
      '손익': r.pnl,
      '누적손익': cumulative,
      '원가': r.bid_krw,
      '매도': r.ask_krw
    };
  })

  return (
    <div className="space-y-4">
      {chartData.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className={`${CARD} animate-fade-in-up p-4 h-72`} style={staggerDelay(0)}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">월별 실현 손익 추이</h4>
            <ResponsiveContainer width="100%" height="90%">
              <BarChart data={chartData} margin={{ top: 5, right: 5, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
                <XAxis dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} tickFormatter={(v) => krwFmt(v)} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  labelStyle={{ color: '#94a3b8', fontSize: '12px', fontWeight: 'bold' }}
                  itemStyle={{ color: '#fff', fontSize: '12px' }}
                  formatter={(value: any) => [`${krwFmt(Number(value))}원`, '손익']}
                />
                <ReferenceLine y={0} stroke="#64748b" />
                <Bar dataKey="손익" radius={[4, 4, 0, 0]} animationBegin={staggerDelayMs(0)} animationDuration={600}>
                  {chartData.map((entry: any, index: number) => {
                    const color = entry['손익'] >= 0 ? PNL_UP_HEX : PNL_DOWN_HEX;
                    return <Cell key={`cell-${index}`} fill={color} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className={`${CARD} animate-fade-in-up p-4 h-72`} style={staggerDelay(1)}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">누적 자산 성장 곡선 (Cumulative PnL)</h4>
            <ResponsiveContainer width="100%" height="90%">
              <LineChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
                <XAxis dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} tickFormatter={(v) => krwFmt(v)} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  labelStyle={{ color: '#94a3b8', fontSize: '12px', fontWeight: 'bold' }}
                  itemStyle={{ color: '#fff', fontSize: '12px' }}
                  formatter={(value: any) => [`${krwFmt(Number(value))}원`, '누적 손익']}
                />
                <ReferenceLine y={0} stroke="#64748b" />
                <Line type="monotone" dataKey="누적손익" stroke="#6366f1" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} animationBegin={staggerDelayMs(1)} animationDuration={600} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className={`${CARD} animate-fade-in-up overflow-hidden`} style={staggerDelay(2)}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">월별 손익</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left`}>월</th>
                <th className={`${TH} text-right`}>실현원가</th>
                <th className={`${TH} text-right`}>매도금액</th>
                <th className={`${TH} text-right`}>수수료</th>
                <th className={`${TH} text-right`}>손익</th>
                <th className={`${TH} text-left`} style={{ minWidth: 160 }}>막대</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.rows.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400 text-xs">데이터 없음</td></tr>
              ) : [...data.rows].reverse().map((r, i) => (
                <tr key={r.month} className="animate-fade-in hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors" style={staggerDelay(i)}>
                  <td className={`${TD} font-mono text-xs font-medium text-slate-700 dark:text-slate-300`}>{r.month}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.bid_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.ask_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-500`}>{krwFmt(r.fee_amount)}</td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.pnl)}`}>
                    {r.pnl >= 0 ? '+' : '-'}{krwFmt(Math.abs(r.pnl))}
                  </td>
                  <td className={TD}>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-slate-200 dark:bg-slate-700 rounded h-2 overflow-hidden">
                        <div
                          className={`h-full rounded ${r.pnl >= 0 ? 'bg-up-500' : 'bg-down-500'}`}
                          style={{ width: `${r.bar_pct}%` }}
                        />
                      </div>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
