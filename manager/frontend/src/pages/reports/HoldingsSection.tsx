import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, DollarSign, Award } from 'lucide-react'
import { fetchReportHoldings } from '../../api/reports'
import type { HoldingsReport } from '../../types'
import Badge from '../../components/ui/Badge'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay } from '../../utils/animation'
import { krwFmt, pctFmt, pctColor, CARD, TH, TD } from './ReportsShared'

export default function HoldingsSection() {
  const [data, setData] = useState<HoldingsReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportHoldings()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  const { summary, rows } = data
  const summaryCards = [
    { label: '보유원가', value: krwFmt(summary.total_cost), Icon: TrendingUp, bg: 'bg-blue-500' },
    { label: '평가금액', value: krwFmt(summary.total_value), Icon: DollarSign, bg: 'bg-slate-700' },
    {
      label: '평가손익',
      value: `${summary.total_pnl >= 0 ? '+' : '-'}${krwFmt(Math.abs(summary.total_pnl))}`,
      Icon: Award,
      bg: summary.total_pnl >= 0 ? 'bg-up-500' : 'bg-down-500',
      extra: pctFmt(summary.total_roi_pct),
      extraColor: pctColor(summary.total_pnl),
    },
    {
      label: '투자 종목',
      value: summary.asset_count.toLocaleString(),
      Icon: TrendingDown,
      bg: 'bg-primary-500',
      extra: summary.oversold_count > 0 ? `oversell ${summary.oversold_count}건` : undefined,
      extraColor: summary.oversold_count > 0 ? 'text-amber-600 dark:text-amber-400' : undefined,
    },
  ]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {summaryCards.map(({ label, value, Icon, bg, extra, extraColor }, index) => (
          <div key={label} className={`${CARD} animate-fade-in-up p-4 flex items-center gap-3`} style={staggerDelay(index)}>
            <div className={`${bg} rounded-lg p-2 text-white shrink-0`}><Icon size={16} /></div>
            <div>
              <p className="text-xl font-bold text-slate-900 dark:text-white leading-none">{value}</p>
              {extra && <p className={`text-xs font-medium mt-0.5 ${extraColor}`}>{extra}</p>}
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{label}</p>
            </div>
          </div>
        ))}
      </div>

      <div className={`${CARD} animate-fade-in-up overflow-hidden`} style={staggerDelay(4)}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">현재 투자중인 자산</h3>
          <p className="text-xs text-slate-400 mt-0.5">supabot 트랜잭션 이력 기준 포지션</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left`}>거래소</th>
                <th className={`${TH} text-left`}>종목</th>
                <th className={`${TH} text-right`}>보유수량</th>
                <th className={`${TH} text-right`}>평단가</th>
                <th className={`${TH} text-right`}>보유원가</th>
                <th className={`${TH} text-right`}>현재가</th>
                <th className={`${TH} text-right`}>평가금액</th>
                <th className={`${TH} text-right`}>평가손익</th>
                <th className={`${TH} text-right`}>평가수익률</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {rows.length === 0 ? (
                <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-400 text-xs">현재 투자중인 자산 없음</td></tr>
              ) : rows.map((row, index) => (
                <tr key={`${row.exchange}-${row.ticker}-${index}`} className="animate-fade-in hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors" style={staggerDelay(index)}>
                  <td className={TD}><Badge value={row.exchange} label={row.exchange.toUpperCase()} /></td>
                  <td className={`${TD} font-medium text-xs text-slate-800 dark:text-slate-200`}>
                    <div className="flex items-center gap-2">
                      <span>{row.ticker}</span>
                      {row.oversold && <Badge value="warning" label="oversell" />}
                    </div>
                  </td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{row.quantity.toFixed(4)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(row.avg_price)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(row.cost_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>
                    {row.current_price > 0 ? krwFmt(row.current_price) : '—'}
                  </td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>
                    {row.current_price > 0 ? krwFmt(row.value_krw) : '—'}
                  </td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(row.pnl)}`}>
                    {row.current_price > 0 ? `${row.pnl >= 0 ? '+' : '-'}${krwFmt(Math.abs(row.pnl))}` : '—'}
                  </td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(row.roi_pct)}`}>
                    {row.current_price > 0 ? pctFmt(row.roi_pct) : '—'}
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
