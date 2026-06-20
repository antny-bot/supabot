import { useEffect, useState } from 'react'
import { fetchReportPairs } from '../../api/reports'
import type { PairsReport } from '../../types'
import type { DateRangeValue } from '../../components/ui/DateRangePicker'
import Badge from '../../components/ui/Badge'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay } from '../../utils/animation'
import { krwFmt, pctFmt, pctColor, CARD, TH, TD } from './ReportsShared'

export default function PairsSection({ dateRange }: { dateRange: DateRangeValue }) {
  const [data, setData] = useState<PairsReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportPairs(dateRange)
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
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">거래 페어</h3>
        <p className="text-xs text-slate-400 mt-0.5">평단 기준 실현 매도 이벤트</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
              <th className={`${TH} text-left`}>종목</th>
              <th className={`${TH} text-left`}>거래소</th>
              <th className={`${TH} text-left`}>전략</th>
              <th className={`${TH} text-right`}>매수가</th>
              <th className={`${TH} text-right`}>매도가</th>
              <th className={`${TH} text-right`}>수량</th>
              <th className={`${TH} text-right`}>보유기간</th>
              <th className={`${TH} text-right`}>손익</th>
              <th className={`${TH} text-right`}>수익률</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {data.pairs.length === 0 ? (
              <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-400 text-xs">연결된 거래 페어 없음</td></tr>
            ) : data.pairs.map((p, i) => (
              <tr key={i} className="animate-fade-in hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors" style={staggerDelay(i)}>
                <td className={`${TD} font-medium text-xs text-slate-800 dark:text-slate-200`}>{p.ticker}</td>
                <td className={TD}><Badge value={p.exchange} label={p.exchange.toUpperCase()} /></td>
                <td className={`${TD} text-xs text-slate-500 dark:text-slate-400`}>{p.strategy}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{p.buy_price.toLocaleString()}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{p.sell_price.toLocaleString()}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-500`}>{p.volume.toFixed(4)}</td>
                <td className={`${TD} text-right text-xs text-slate-500 dark:text-slate-400`}>{p.hold_time_fmt}</td>
                <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(p.pnl)}`}>
                  {p.pnl >= 0 ? '+' : '-'}{krwFmt(Math.abs(p.pnl))}
                </td>
                <td className={`${TD} text-right font-mono text-xs font-bold ${pctColor(p.roi_pct)}`}>{pctFmt(p.roi_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
