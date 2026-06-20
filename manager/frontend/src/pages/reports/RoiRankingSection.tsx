import { useEffect, useState } from 'react'
import { fetchReportRoiRanking } from '../../api/reports'
import type { RoiRankingReport } from '../../types'
import type { DateRangeValue } from '../../components/ui/DateRangePicker'
import Badge from '../../components/ui/Badge'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay } from '../../utils/animation'
import { krwFmt, pctFmt, pctColor, CARD, TH, TD, MEDALS } from './ReportsShared'

export default function RoiRankingSection({ dateRange }: { dateRange: DateRangeValue }) {
  const [data, setData] = useState<RoiRankingReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportRoiRanking(dateRange)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [dateRange])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  return (
    <div className={`${CARD} overflow-hidden`}>
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">수익률 랭킹</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
              <th className={`${TH} text-center`}>#</th>
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
            {data.rows.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-400 text-xs">데이터 없음</td></tr>
            ) : data.rows.map((r, i) => (
              <tr key={r.rank} className="animate-fade-in hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors" style={staggerDelay(i)}>
                <td className={`${TD} text-center text-xs font-bold text-slate-500`}>
                  {r.rank <= 3 ? MEDALS[r.rank - 1] : r.rank}
                </td>
                <td className={TD}><Badge value={r.exchange} label={r.exchange.toUpperCase()} /></td>
                <td className={`${TD} font-medium text-xs text-slate-800 dark:text-slate-200`}>{r.ticker}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.bid_krw)}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.ask_krw)}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-500`}>{krwFmt(r.fee_amount)}</td>
                <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.pnl)}`}>{krwFmt(Math.abs(r.pnl))}</td>
                <td className={`${TD} text-right font-mono text-xs font-bold ${pctColor(r.roi_pct)}`}>{pctFmt(r.roi_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
