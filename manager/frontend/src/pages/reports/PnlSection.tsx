import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, DollarSign, Award } from 'lucide-react'
import { fetchReportPnl } from '../../api/reports'
import type { PnlReport } from '../../types'
import type { DateRangeValue } from '../../components/ui/DateRangePicker'
import Badge from '../../components/ui/Badge'
import { StatCardSkeleton, TableRowSkeleton } from '../../components/ui/Skeleton'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay } from '../../utils/animation'
import { krwFmt, formatKrw, pctFmt, pctColor, CARD, TH, TD } from './ReportsShared'

interface Props {
  dateRange: DateRangeValue
  exchange?: string
}

export default function PnlSection({ dateRange, exchange }: Props) {
  const [data, setData] = useState<PnlReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportPnl(dateRange, exchange)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [dateRange, exchange])

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <StatCardSkeleton key={i} />
          ))}
        </div>
        <div className={`${CARD} overflow-hidden`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                <th className={`${TH} text-left`}>거래소</th>
                <th className={`${TH} text-left`}>종목</th>
                <th className={`${TH} text-right`}>실현원가</th>
                <th className={`${TH} text-right`}>매도금액</th>
                <th className={`${TH} text-right`}>수수료</th>
                <th className={`${TH} text-right`}>손익</th>
                <th className={`${TH} text-right`}>수익률</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {Array.from({ length: 5 }).map((_, i) => (
                <TableRowSkeleton key={i} cols={7} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  const { summary, rows } = data
  const summaryCards = [
    { label: '총 실현원가', value: krwFmt(summary.total_bid), Icon: TrendingUp, bg: 'bg-up-500' },
    { label: '총 매도금액', value: krwFmt(summary.total_ask), Icon: TrendingDown, bg: 'bg-down-500' },
    { label: '총 수수료', value: krwFmt(summary.total_fee), Icon: DollarSign, bg: 'bg-amber-500' },
    { label: '실현 손익', value: `${summary.total_pnl >= 0 ? '+' : '-'}${krwFmt(Math.abs(summary.total_pnl))}`, Icon: Award,
      bg: summary.total_pnl >= 0 ? 'bg-up-500' : 'bg-down-500',
      extra: pctFmt(summary.total_bid ? summary.total_pnl / summary.total_bid * 100 : 0),
      extraColor: pctColor(summary.total_pnl),
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
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 break-keep">{label}</p>
            </div>
          </div>
        ))}
      </div>

      <div className={`${CARD} animate-fade-in-up overflow-hidden`} style={staggerDelay(4)}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 break-keep">종목별 실현 손익</h3>
          <span className="text-xs text-slate-400">총 {rows.length}개 종목</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left break-keep`}>거래소</th>
                <th className={`${TH} text-left break-keep`}>종목</th>
                <th className={`${TH} text-right break-keep`}>실현원가</th>
                <th className={`${TH} text-right break-keep`}>매도금액</th>
                <th className={`${TH} text-right break-keep`}>수수료</th>
                <th className={`${TH} text-right break-keep`}>손익</th>
                <th className={`${TH} text-right break-keep`}>수익률</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {rows.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-400 text-xs">데이터 없음</td></tr>
              ) : rows.map((r, i) => (
                <tr key={`${r.exchange}-${r.ticker}-${i}`} className="animate-fade-in hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors" style={staggerDelay(i)}>
                  <td className={TD}><Badge value={r.exchange} label={r.exchange.toUpperCase()} /></td>
                  <td className={`${TD} font-medium text-xs text-slate-800 dark:text-slate-200 whitespace-nowrap`}>{r.ticker}</td>
                  <td className={`${TD} text-right text-xs text-slate-600 dark:text-slate-400 font-mono`}>{formatKrw(r.bid_krw)}</td>
                  <td className={`${TD} text-right text-xs text-slate-600 dark:text-slate-400 font-mono`}>{formatKrw(r.ask_krw)}</td>
                  <td className={`${TD} text-right text-xs text-slate-500 dark:text-slate-500 font-mono`}>{formatKrw(r.fee_amount)}</td>
                  <td className={`${TD} text-right text-xs font-semibold font-mono ${pctColor(r.pnl)}`}>
                    {r.pnl >= 0 ? '+' : '-'}{formatKrw(Math.abs(r.pnl))}
                  </td>
                  <td className={`${TD} text-right text-xs font-semibold font-mono ${pctColor(r.roi_pct)}`}>{pctFmt(r.roi_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
