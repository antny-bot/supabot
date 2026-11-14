import { useEffect, useState } from 'react'
import { fetchReportPairs } from '../../api/reports'
import type { PairsReport } from '../../types'
import type { DateRangeValue } from '../../components/ui/DateRangePicker'
import Badge from '../../components/ui/Badge'
import { TableRowSkeleton } from '../../components/ui/Skeleton'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay } from '../../utils/animation'
import { formatKrw, pctFmt, pctColor, CARD, TH, TD } from './ReportsShared'

interface Props {
  dateRange: DateRangeValue
  exchange?: string
}

export default function PairsSection({ dateRange, exchange }: Props) {
  const [data, setData] = useState<PairsReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportPairs(dateRange, exchange)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [dateRange, exchange])

  if (loading) {
    return (
      <div className={`${CARD} overflow-hidden`}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 break-keep">거래 페어</h3>
          <p className="text-xs text-slate-400 mt-0.5 break-keep">평단 기준 실현 매도 이벤트</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left break-keep`}>종목</th>
                <th className={`${TH} text-left break-keep`}>거래소</th>
                <th className={`${TH} text-left break-keep`}>전략</th>
                <th className={`${TH} text-right break-keep`}>매수가</th>
                <th className={`${TH} text-right break-keep`}>매도가</th>
                <th className={`${TH} text-right break-keep`}>수량</th>
                <th className={`${TH} text-right break-keep`}>보유기간</th>
                <th className={`${TH} text-right break-keep`}>손익</th>
                <th className={`${TH} text-right break-keep`}>수익률</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {Array.from({ length: 6 }).map((_, i) => (
                <TableRowSkeleton key={i} cols={9} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  return (
    <div className={`${CARD} overflow-hidden`}>
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center">
        <div>
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 break-keep">거래 페어 상세</h3>
          <p className="text-xs text-slate-400 mt-0.5 break-keep">진입 평단 대비 실현 청산 내역 (총 {data.pairs.length}건)</p>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
              <th className={`${TH} text-left break-keep`}>종목</th>
              <th className={`${TH} text-left break-keep`}>거래소</th>
              <th className={`${TH} text-left break-keep`}>전략</th>
              <th className={`${TH} text-right break-keep`}>매수가</th>
              <th className={`${TH} text-right break-keep`}>매도가</th>
              <th className={`${TH} text-right break-keep`}>수량</th>
              <th className={`${TH} text-right break-keep`}>보유기간</th>
              <th className={`${TH} text-right break-keep`}>손익</th>
              <th className={`${TH} text-right break-keep`}>수익률</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {data.pairs.length === 0 ? (
              <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-400 text-xs">연결된 거래 페어 없음</td></tr>
            ) : data.pairs.map((p, i) => (
              <tr key={i} className="animate-fade-in hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors" style={staggerDelay(i)}>
                <td className={`${TD} font-medium text-xs text-slate-800 dark:text-slate-200 whitespace-nowrap`}>{p.ticker}</td>
                <td className={TD}><Badge value={p.exchange} label={p.exchange.toUpperCase()} /></td>
                <td className={`${TD} text-xs text-slate-500 dark:text-slate-400`}>{p.strategy}</td>
                <td className={`${TD} text-right text-xs text-slate-600 dark:text-slate-400 font-mono`}>{p.buy_price.toLocaleString()}</td>
                <td className={`${TD} text-right text-xs text-slate-600 dark:text-slate-400 font-mono`}>{p.sell_price.toLocaleString()}</td>
                <td className={`${TD} text-right text-xs text-slate-500 font-mono`}>{p.volume.toFixed(4)}</td>
                <td className={`${TD} text-right text-xs text-slate-500 dark:text-slate-400 font-mono`}>{p.hold_time_fmt}</td>
                <td className={`${TD} text-right text-xs font-semibold font-mono ${pctColor(p.pnl)}`}>
                  {p.pnl >= 0 ? '+' : '-'}{formatKrw(Math.abs(p.pnl))}
                </td>
                <td className={`${TD} text-right text-xs font-bold font-mono ${pctColor(p.roi_pct)}`}>{pctFmt(p.roi_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
