import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell, LineChart, Line
} from 'recharts'
import { fetchReportDaily } from '../../api/reports'
import type { DailyReport } from '../../types'
import type { DateRangeValue } from '../../components/ui/DateRangePicker'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay, staggerDelayMs } from '../../utils/animation'
import { krwFmt, pctColor, PNL_UP_HEX, PNL_DOWN_HEX, CARD, TH, TD } from './ReportsShared'

export default function DailySection({ dateRange }: { dateRange: DateRangeValue }) {
  const [data, setData] = useState<DailyReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportDaily(dateRange)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [dateRange])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  // 막대 폭은 일별 손익 절대값 대비 비율로 계산
  const maxAbs = Math.max(1, ...data.rows.map(r => Math.abs(r.pnl)))
  const chartData = data.rows.map(r => ({
    name: r.date.slice(5),  // MM-DD
    '손익': r.pnl,
    '누적손익': r.cumulative_pnl,
  }))

  return (
    <div className="space-y-4">
      <p className="text-[11px] text-slate-400 dark:text-slate-500">
        ※ 원화 기준 일별 실현 손익입니다. 토스 해외(USD) 종목은 환산 없이 합산됩니다.
      </p>

      {chartData.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className={`${CARD} animate-fade-in-up p-4 h-72`} style={staggerDelay(0)}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">일별 실현 손익</h4>
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
                <Line type="monotone" dataKey="누적손익" stroke="#6366f1" strokeWidth={3} dot={{ r: 3 }} activeDot={{ r: 6 }} animationBegin={staggerDelayMs(1)} animationDuration={600} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className={`${CARD} animate-fade-in-up overflow-hidden`} style={staggerDelay(2)}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">일별 손익</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left`}>날짜</th>
                <th className={`${TH} text-right`}>실현원가</th>
                <th className={`${TH} text-right`}>매도금액</th>
                <th className={`${TH} text-right`}>수수료</th>
                <th className={`${TH} text-right`}>손익</th>
                <th className={`${TH} text-right`}>누적손익</th>
                <th className={`${TH} text-left`} style={{ minWidth: 160 }}>막대</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.rows.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-400 text-xs">데이터 없음</td></tr>
              ) : [...data.rows].reverse().map((r, i) => (
                <tr key={r.date} className="animate-fade-in hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors" style={staggerDelay(i)}>
                  <td className={`${TD} font-mono text-xs font-medium text-slate-700 dark:text-slate-300`}>{r.date}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.bid_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.ask_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-500`}>{krwFmt(r.fee_amount)}</td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.pnl)}`}>
                    {r.pnl >= 0 ? '+' : '-'}{krwFmt(Math.abs(r.pnl))}
                  </td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.cumulative_pnl)}`}>
                    {r.cumulative_pnl >= 0 ? '+' : '-'}{krwFmt(Math.abs(r.cumulative_pnl))}
                  </td>
                  <td className={TD}>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-slate-200 dark:bg-slate-700 rounded h-2 overflow-hidden">
                        <div
                          className={`h-full rounded ${r.pnl >= 0 ? 'bg-up-500' : 'bg-down-500'}`}
                          style={{ width: `${Math.round(Math.abs(r.pnl) / maxAbs * 100)}%` }}
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
