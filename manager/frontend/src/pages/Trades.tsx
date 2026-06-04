import { useCallback, useEffect, useState } from 'react'
import { usePersistedState } from '../hooks/usePersistedState'
import { BarChart2, ChevronLeft, ChevronRight, DollarSign, TrendingDown, TrendingUp } from 'lucide-react'
import { fetchTrades } from '../api/trades'
import type { TradesData } from '../types'
import Badge from '../components/ui/Badge'
import DateRangePicker, { type DateRangeValue } from '../components/ui/DateRangePicker'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import Spinner from '../components/ui/Spinner'
import { PAGE_META } from '../config/pageMeta'
import { useRealtime } from '../hooks/useRealtime'
import { krwFmt } from '../utils/formatters'

const DEFAULT_RANGE: DateRangeValue = { mode: '7d', from: '', to: '' }

export default function Trades() {
  const [data, setData] = useState<TradesData | null>(null)
  const [dateRange, setDateRange] = usePersistedState<DateRangeValue>('filter:trades:dateRange', DEFAULT_RANGE)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pageSize = 50

  const loadData = useCallback((showSpinner = false, targetPage = page) => {
    if (showSpinner) setLoading(true)
    fetchTrades(dateRange, targetPage, pageSize)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류가 발생했습니다.'))
      .finally(() => {
        if (showSpinner) setLoading(false)
      })
  }, [page, dateRange])

  useEffect(() => {
    loadData(true, page)
  }, [loadData, page])

  useRealtime(useCallback(() => loadData(false, page), [loadData, page]))

  const handleRangeChange = (range: DateRangeValue) => {
    setDateRange(range)
    setPage(1)
  }

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0

  const summaryCards = data
    ? [
        { label: '전체 거래(기간)', value: data.total.toLocaleString(), Icon: BarChart2, bg: 'bg-indigo-500' },
        { label: '매수(현재)', value: data.summary.buy.toLocaleString(), Icon: TrendingUp, bg: 'bg-blue-500' },
        { label: '매도(현재)', value: data.summary.sell.toLocaleString(), Icon: TrendingDown, bg: 'bg-rose-500' },
        { label: '거래액(현재)', value: krwFmt(data.summary.volume_krw), Icon: DollarSign, bg: 'bg-emerald-500' },
      ]
    : []

  return (
    <div className="space-y-5">
      <PageHeader {...PAGE_META.trades} />

      <DateRangePicker value={dateRange} onChange={handleRangeChange} />

      {error && <ErrorBanner message={error} />}

      {loading && !data && <Spinner />}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {summaryCards.map(({ label, value, Icon, bg }) => (
              <div key={label} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <div className={`${bg} rounded-lg p-2 text-white shrink-0`}>
                  <Icon size={16} />
                </div>
                <div>
                  <p className="text-xl font-bold leading-none text-slate-900 dark:text-white">{value}</p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{label}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {[
              { title: '거래소별 집계 (현재 페이지)', rows: data.by_exchange },
              { title: '전략별 집계 (현재 페이지)', rows: data.by_strategy },
            ].map(({ title, rows }) => (
              <div key={title} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <div className="border-b border-slate-100 px-4 py-3 dark:border-slate-800">
                  <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">{title}</h3>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50 text-xs text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                      <th className="px-4 py-2.5 text-left font-medium">이름</th>
                      <th className="px-4 py-2.5 text-right font-medium">건수</th>
                      <th className="px-4 py-2.5 text-right font-medium">금액</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {rows.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="px-4 py-6 text-center text-xs text-slate-400">데이터가 없습니다.</td>
                      </tr>
                    ) : rows.map((row) => (
                      <tr key={row.name} className="transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40">
                        <td className="px-4 py-2.5 text-xs font-medium text-slate-700 dark:text-slate-300">{row.name}</td>
                        <td className="px-4 py-2.5 text-right text-xs text-slate-600 dark:text-slate-400">{row.count.toLocaleString()}</td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs text-slate-600 dark:text-slate-400">{krwFmt(row.krw)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3 dark:border-slate-800">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">상세 내역</h3>
              <span className="font-mono text-[10px] text-slate-400">Total: {data.total.toLocaleString()}</span>
            </div>

            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                    <th className="px-4 py-2.5 text-left font-medium">체결시간</th>
                    <th className="px-4 py-2.5 text-left font-medium">거래소</th>
                    <th className="px-4 py-2.5 text-left font-medium">종목</th>
                    <th className="px-4 py-2.5 text-left font-medium">주문유형</th>
                    <th className="px-4 py-2.5 text-left font-medium">전략</th>
                    <th className="px-4 py-2.5 text-right font-medium">가격</th>
                    <th className="px-4 py-2.5 text-right font-medium">수량</th>
                    <th className="px-4 py-2.5 text-right font-medium">금액</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {data.trades.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-10 text-center text-xs text-slate-400">거래가 없습니다.</td>
                    </tr>
                  ) : data.trades.map((trade, index) => (
                    <tr key={index} className="transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40">
                      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-slate-500 dark:text-slate-400">{trade.executed_fmt}</td>
                      <td className="px-4 py-2.5"><Badge value={trade.exchange} label={trade.exchange.toUpperCase()} /></td>
                      <td className="px-4 py-2.5 text-xs font-medium text-slate-800 dark:text-slate-200">{trade.ticker}</td>
                      <td className="px-4 py-2.5"><Badge value={trade.side} /></td>
                      <td className="px-4 py-2.5 text-xs text-slate-500 dark:text-slate-400">{trade.strategy}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-slate-700 dark:text-slate-300">{trade.price?.toLocaleString()}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-slate-600 dark:text-slate-400">{trade.volume?.toFixed(4)}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-xs text-slate-700 dark:text-slate-300">{krwFmt(trade.krw)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="block divide-y divide-slate-100 dark:divide-slate-800 md:hidden">
              {data.trades.length === 0 ? (
                <div className="px-4 py-10 text-center text-xs text-slate-400">거래가 없습니다.</div>
              ) : data.trades.map((trade, index) => (
                <div key={index} className="space-y-3 p-4 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono text-slate-500 dark:text-slate-400">{trade.executed_fmt}</span>
                    <Badge value={trade.side} />
                  </div>
                  <div className="flex items-baseline justify-between">
                    <div className="flex items-center gap-1.5">
                      <Badge value={trade.exchange} label={trade.exchange.toUpperCase()} />
                      <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">{trade.ticker}</span>
                    </div>
                    <span className="font-mono text-xs font-bold text-slate-900 dark:text-white">{trade.price?.toLocaleString()}원</span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                    <span>전략: {trade.strategy}</span>
                    <span>수량: <span className="font-mono font-medium text-slate-800 dark:text-slate-200">{trade.volume?.toFixed(4)}</span></span>
                  </div>
                  <div className="flex justify-end text-xs font-semibold text-slate-700 dark:text-slate-300">
                    금액 {trade.krw?.toLocaleString()}원
                  </div>
                </div>
              ))}
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
                <div className="text-xs text-slate-500 dark:text-slate-400">
                  Page <span className="font-semibold text-slate-900 dark:text-white">{page}</span> of {totalPages}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage((current) => Math.max(1, current - 1))}
                    disabled={page === 1}
                    className="rounded-lg border border-slate-200 bg-white p-1.5 transition-colors disabled:opacity-30 dark:border-slate-700 dark:bg-slate-800"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <button
                    onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                    disabled={page === totalPages}
                    className="rounded-lg border border-slate-200 bg-white p-1.5 transition-colors disabled:opacity-30 dark:border-slate-700 dark:bg-slate-800"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
