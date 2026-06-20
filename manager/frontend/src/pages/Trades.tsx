import { useCallback, useEffect, useState } from 'react'
import { usePersistedState } from '../hooks/usePersistedState'
import { BarChart2, DollarSign, TrendingDown, TrendingUp, RotateCcw } from 'lucide-react'
import { fetchTrades } from '../api/trades'
import type { TradesData } from '../types'
import Badge from '../components/ui/Badge'
import DateRangePicker, { type DateRangeValue } from '../components/ui/DateRangePicker'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import Spinner from '../components/ui/Spinner'
import { PAGE_META } from '../config/pageMeta'
import { useRealtime } from '../hooks/useRealtime'
import { staggerDelay } from '../utils/animation'
import { krwFmt } from '../utils/formatters'
import Pagination from '../components/ui/Pagination'
import SyncIndicator from '../components/ui/SyncIndicator'

const DEFAULT_RANGE: DateRangeValue = { mode: '7d', from: '', to: '' }

export default function Trades() {
  const [data, setData] = useState<TradesData | null>(null)
  const [dateRange, setDateRange] = usePersistedState<DateRangeValue>('filter:trades:dateRange', DEFAULT_RANGE)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = usePersistedState('filter:trades:pageSize', 50)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const loadData = useCallback((showSpinner = false, targetPage = page, targetPageSize = pageSize) => {
    if (showSpinner) setLoading(true)
    fetchTrades(dateRange, targetPage, targetPageSize)
      .then((res) => {
        setData(res)
        setLastUpdated(new Date())
        setError(null)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류가 발생했습니다.'))
      .finally(() => {
        if (showSpinner) setLoading(false)
      })
  }, [dateRange, page, pageSize])

  useEffect(() => {
    loadData(true, page, pageSize)
  }, [loadData, page, pageSize])

  useRealtime(useCallback(() => loadData(false, page, pageSize), [loadData, page, pageSize]))

  const handleRangeChange = (range: DateRangeValue) => {
    setDateRange(range)
    setPage(1)
  }

  const handleResetFilters = () => {
    setDateRange(DEFAULT_RANGE)
    setPage(1)
  }

  const isFilterModified = dateRange.mode !== DEFAULT_RANGE.mode || dateRange.from !== DEFAULT_RANGE.from || dateRange.to !== DEFAULT_RANGE.to

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0

  const summaryCards = data
    ? [
        { label: '전체 거래(기간)', value: data.total.toLocaleString(), Icon: BarChart2, bg: 'bg-primary-500' },
        { label: '매수(현재)', value: data.summary.buy.toLocaleString(), Icon: TrendingUp, bg: 'bg-up-500' },
        { label: '매도(현재)', value: data.summary.sell.toLocaleString(), Icon: TrendingDown, bg: 'bg-down-500' },
        { label: '거래액(현재)', value: krwFmt(data.summary.volume_krw), Icon: DollarSign, bg: 'bg-emerald-500' },
      ]
    : []

  return (
    <div className="space-y-5">
      <PageHeader
        {...PAGE_META.trades}
        actions={<SyncIndicator lastUpdated={lastUpdated} loading={loading} error={error} />}
      />

      <div className="flex flex-wrap items-center gap-2">
        <DateRangePicker value={dateRange} onChange={handleRangeChange} />
        {isFilterModified && (
          <button
            onClick={handleResetFilters}
            className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-600 px-2.5 py-1.5 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700 text-xs transition-colors"
            title="필터 초기화"
          >
            <RotateCcw size={12} />
            <span>필터 초기화</span>
          </button>
        )}
      </div>

      {error && <ErrorBanner message={error} />}

      {loading && !data && <Spinner />}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {summaryCards.map(({ label, value, Icon, bg }, index) => (
              <div key={label} className="animate-fade-in-up flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900" style={staggerDelay(index)}>
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
            ].map(({ title, rows }, sectionIndex) => (
              <div key={title} className="animate-fade-in-up overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900" style={staggerDelay(4 + sectionIndex)}>
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
                    ) : rows.map((row, index) => (
                      <tr key={row.name} className="animate-fade-in transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40" style={staggerDelay(index)}>
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

          <div className="animate-fade-in-up overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900" style={staggerDelay(6)}>
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
                    <tr key={index} className="animate-fade-in transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40" style={staggerDelay(index)}>
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
                <div key={index} className="animate-fade-in-up space-y-3 p-4 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40" style={staggerDelay(index)}>
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

            <Pagination
              currentPage={page}
              totalPages={totalPages}
              pageSize={pageSize}
              totalCount={data.total}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size)
                setPage(1)
              }}
            />
          </div>
        </>
      )}
    </div>
  )
}
