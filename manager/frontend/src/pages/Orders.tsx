import { useCallback, useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { fetchOrders } from '../api/orders'
import type { OrdersData } from '../types'
import Badge from '../components/ui/Badge'
import DateRangePicker, { type DateRangeValue } from '../components/ui/DateRangePicker'
import ErrorBanner from '../components/ui/ErrorBanner'
import FilterBar from '../components/ui/FilterBar'
import PageHeader from '../components/ui/PageHeader'
import ProgressBar from '../components/ui/ProgressBar'
import Spinner from '../components/ui/Spinner'
import { PAGE_META } from '../config/pageMeta'
import { useRealtime } from '../hooks/useRealtime'
import { krwFmt } from '../utils/formatters'

const STATUS_OPTIONS = [
  { value: '', label: '전체 유형' },
  { value: 'open', label: '활성' },
  { value: 'wait', label: '대기' },
  { value: 'partial', label: '부분체결' },
  { value: 'done', label: '완료' },
  { value: 'cancel', label: '취소' },
  { value: 'pending_reorder', label: '재주문대기' },
]

const EXCHANGE_OPTIONS = [
  { value: '', label: '전체 거래소' },
  { value: 'upbit', label: 'Upbit' },
  { value: 'bithumb', label: 'Bithumb' },
  { value: 'kis', label: 'KIS' },
]

const SIDE_OPTIONS = [
  { value: '', label: '전체 구분' },
  { value: 'bid', label: '매수' },
  { value: 'ask', label: '매도' },
]

const DEFAULT_RANGE: DateRangeValue = { mode: 'all', from: '', to: '' }

export default function Orders() {
  const [data, setData] = useState<OrdersData | null>(null)
  const [status, setStatus] = useState('')
  const [exchange, setExchange] = useState('')
  const [side, setSide] = useState('')
  const [dateRange, setDateRange] = useState<DateRangeValue>(DEFAULT_RANGE)
  const [page, setPage] = useState(1)
  const [expandedFilter, setExpandedFilter] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pageSize = 50

  const dateFrom = dateRange.mode === 'custom' ? dateRange.from : undefined
  const dateTo = dateRange.mode === 'custom' ? dateRange.to : undefined

  const loadData = useCallback((showSpinner = false, targetPage = page) => {
    if (showSpinner) setLoading(true)
    fetchOrders(status, exchange, side, dateFrom, dateTo, targetPage, pageSize)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류가 발생했습니다.'))
      .finally(() => {
        if (showSpinner) setLoading(false)
      })
  }, [exchange, page, side, status, dateFrom, dateTo])

  useEffect(() => {
    loadData(true, page)
  }, [loadData, page])

  useRealtime(useCallback(() => loadData(false, page), [loadData, page]))

  const toggleFilter = (name: string) => {
    setExpandedFilter((prev) => (prev === name ? null : name))
  }

  const handleFilterChange = (setter: (value: string) => void) => (value: string) => {
    setter(value)
    setPage(1)
  }

  const handleDateRangeChange = (range: DateRangeValue) => {
    setDateRange(range)
    setPage(1)
  }

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0

  return (
    <div className="space-y-4">
      <PageHeader {...PAGE_META.orders} />

      <div className="flex flex-wrap items-start gap-2">
        <FilterBar collapsible isOpen={expandedFilter === 'status'} onToggle={() => toggleFilter('status')}
          options={STATUS_OPTIONS} value={status} onChange={handleFilterChange(setStatus)} />
        <FilterBar collapsible isOpen={expandedFilter === 'exchange'} onToggle={() => toggleFilter('exchange')}
          options={EXCHANGE_OPTIONS} value={exchange} onChange={handleFilterChange(setExchange)} />
        <FilterBar collapsible isOpen={expandedFilter === 'side'} onToggle={() => toggleFilter('side')}
          options={SIDE_OPTIONS} value={side} onChange={handleFilterChange(setSide)} />
        <DateRangePicker collapsible isOpen={expandedFilter === 'date'} onToggle={() => toggleFilter('date')}
          value={dateRange} onChange={handleDateRangeChange} />
      </div>

      {error && <ErrorBanner message={error} />}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {loading && !data ? (
          <Spinner />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                    <th className="px-4 py-3 text-left font-medium">시간</th>
                    <th className="px-4 py-3 text-left font-medium">거래소</th>
                    <th className="px-4 py-3 text-left font-medium">종목</th>
                    <th className="px-4 py-3 text-left font-medium">주문유형</th>
                    <th className="px-4 py-3 text-left font-medium">전략</th>
                    <th className="px-4 py-3 text-right font-medium">가격</th>
                    <th className="px-4 py-3 text-right font-medium">수량</th>
                    <th className="px-4 py-3 text-right font-medium">금액</th>
                    <th className="w-32 px-4 py-3 text-left font-medium">체결률</th>
                    <th className="px-4 py-3 text-left font-medium">상태</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {!data || data.orders.length === 0 ? (
                    <tr>
                      <td colSpan={10} className="px-4 py-10 text-center text-xs text-slate-400 dark:text-slate-500">
                        주문이 없습니다.
                      </td>
                    </tr>
                  ) : data.orders.map((order, index) => (
                    <tr key={index} className="transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40">
                      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-slate-500 dark:text-slate-400">
                        {order.created_fmt}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge value={order.exchange} label={order.exchange.toUpperCase()} />
                      </td>
                      <td className="px-4 py-2.5 text-xs font-medium text-slate-800 dark:text-slate-200">
                        {order.ticker}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge value={order.side} />
                      </td>
                      <td className="px-4 py-2.5 text-xs text-slate-500 dark:text-slate-400">{order.strategy}</td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-xs text-slate-700 dark:text-slate-300">
                        {order.price?.toLocaleString()}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-xs text-slate-600 dark:text-slate-400">
                        {order.volume?.toFixed(4)}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right font-mono text-xs text-slate-700 dark:text-slate-300">
                        {krwFmt(order.order_value ?? 0)}
                      </td>
                      <td className="w-32 px-4 py-2.5">
                        <ProgressBar value={order.fill_pct} />
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge value={order.status} label={order.status_label} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
          </>
        )}
      </div>

      <p className="text-right text-xs text-slate-400 dark:text-slate-600">총 {data?.total || 0}건</p>
    </div>
  )
}
