import { useEffect, useState } from 'react'
import { BarChart2, TrendingUp, TrendingDown, DollarSign } from 'lucide-react'
import { fetchTrades } from '../api/trades'
import type { TradesData } from '../types'
import Badge from '../components/ui/Badge'
import FilterBar from '../components/ui/FilterBar'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'

const PERIOD_OPTIONS = [
  { value: '1d',  label: '1일' },
  { value: '7d',  label: '7일' },
  { value: '30d', label: '30일' },
  { value: 'all', label: '전체' },
]

function krwFmt(n: number) {
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`
  if (n >= 10_000) return `${(n / 10_000).toFixed(0)}만`
  return n.toLocaleString()
}

export default function Trades() {
  const [data, setData] = useState<TradesData | null>(null)
  const [period, setPeriod] = useState('7d')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchTrades(period)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [period])

  const summaryCards = data
    ? [
        { label: '총 거래', value: data.summary.total.toLocaleString(), Icon: BarChart2, bg: 'bg-indigo-500' },
        { label: '매수', value: data.summary.buy.toLocaleString(), Icon: TrendingUp, bg: 'bg-blue-500' },
        { label: '매도', value: data.summary.sell.toLocaleString(), Icon: TrendingDown, bg: 'bg-rose-500' },
        { label: '거래금액', value: krwFmt(data.summary.volume_krw), Icon: DollarSign, bg: 'bg-emerald-500' },
      ]
    : []

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">거래 내역</h1>
        <FilterBar options={PERIOD_OPTIONS} value={period} onChange={setPeriod} />
      </div>

      {error && <ErrorBanner message={error} />}

      {loading && <Spinner />}

      {!loading && data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {summaryCards.map(({ label, value, Icon, bg }) => (
              <div key={label} className="bg-white dark:bg-slate-900 rounded-xl p-4 border border-slate-200 dark:border-slate-800 shadow-sm flex items-center gap-3">
                <div className={`${bg} rounded-lg p-2 text-white shrink-0`}>
                  <Icon size={16} />
                </div>
                <div>
                  <p className="text-xl font-bold text-slate-900 dark:text-white leading-none">{value}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{label}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="grid md:grid-cols-2 gap-4">
            {[
              { title: '거래소별', rows: data.by_exchange },
              { title: '전략별', rows: data.by_strategy },
            ].map(({ title, rows }) => (
              <div key={title} className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
                  <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">{title}</h3>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900">
                      <th className="px-4 py-2.5 text-left font-medium">이름</th>
                      <th className="px-4 py-2.5 text-right font-medium">건수</th>
                      <th className="px-4 py-2.5 text-right font-medium">금액</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {rows.length === 0 ? (
                      <tr><td colSpan={3} className="px-4 py-6 text-center text-slate-400 text-xs">데이터 없음</td></tr>
                    ) : rows.map((r) => (
                      <tr key={r.name} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                        <td className="px-4 py-2.5 text-slate-700 dark:text-slate-300 text-xs font-medium">{r.name}</td>
                        <td className="px-4 py-2.5 text-right text-slate-600 dark:text-slate-400 text-xs">{r.count.toLocaleString()}</td>
                        <td className="px-4 py-2.5 text-right text-slate-600 dark:text-slate-400 font-mono text-xs">{krwFmt(r.krw)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">상세 내역</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                    <th className="px-4 py-2.5 text-left font-medium">체결시간</th>
                    <th className="px-4 py-2.5 text-left font-medium">거래소</th>
                    <th className="px-4 py-2.5 text-left font-medium">종목</th>
                    <th className="px-4 py-2.5 text-left font-medium">방향</th>
                    <th className="px-4 py-2.5 text-left font-medium">전략</th>
                    <th className="px-4 py-2.5 text-right font-medium">가격</th>
                    <th className="px-4 py-2.5 text-right font-medium">수량</th>
                    <th className="px-4 py-2.5 text-right font-medium">금액</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {data.trades.length === 0 ? (
                    <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-400 text-xs">거래 없음</td></tr>
                  ) : data.trades.map((t, i) => (
                    <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                      <td className="px-4 py-2.5 text-slate-500 dark:text-slate-400 font-mono text-xs whitespace-nowrap">{t.executed_fmt}</td>
                      <td className="px-4 py-2.5"><Badge value={t.exchange} label={t.exchange.toUpperCase()} /></td>
                      <td className="px-4 py-2.5 text-slate-800 dark:text-slate-200 font-medium text-xs">{t.ticker}</td>
                      <td className="px-4 py-2.5"><Badge value={t.side} /></td>
                      <td className="px-4 py-2.5 text-slate-500 dark:text-slate-400 text-xs">{t.strategy}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-slate-700 dark:text-slate-300 text-xs">{t.price?.toLocaleString()}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-slate-600 dark:text-slate-400 text-xs">{t.volume?.toFixed(4)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-slate-700 dark:text-slate-300 text-xs">{krwFmt(t.krw)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
