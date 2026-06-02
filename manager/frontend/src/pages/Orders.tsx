import { useEffect, useState, useCallback } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { fetchOrders } from '../api/orders'
import type { OrdersData } from '../types'
import Badge from '../components/ui/Badge'
import FilterBar from '../components/ui/FilterBar'
import ProgressBar from '../components/ui/ProgressBar'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'
import { useRealtime } from '../hooks/useRealtime'

const STATUS_OPTIONS = [
  { value: '',              label: '전체' },
  { value: 'open',          label: '활성' },
  { value: 'wait',          label: '대기' },
  { value: 'partial',       label: '부분체결' },
  { value: 'done',          label: '완료' },
  { value: 'cancel',        label: '취소' },
  { value: 'pending_reorder', label: '재주문대기' },
]

const EXCHANGE_OPTIONS = [
  { value: '',        label: '전체 거래소' },
  { value: 'upbit',   label: 'Upbit' },
  { value: 'bithumb', label: 'Bithumb' },
  { value: 'kis',     label: 'KIS' },
]

export default function Orders() {
  const [data, setData] = useState<OrdersData | null>(null)
  const [status, setStatus] = useState('')
  const [exchange, setExchange] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pageSize = 50

  const loadData = useCallback((showSpinner = false, targetPage = page) => {
    if (showSpinner) setLoading(true)
    fetchOrders(status, exchange, targetPage, pageSize)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => {
        if (showSpinner) setLoading(false)
      })
  }, [status, exchange, page])

  useEffect(() => {
    loadData(true, page)
  }, [loadData, page])

  useRealtime(useCallback(() => loadData(false, page), [loadData, page]))

  const handleFilterChange = (setter: (v: string) => void) => (v: string) => {
    setter(v)
    setPage(1)
  }

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-slate-900 dark:text-white">주문 현황</h1>

      <div className="flex flex-col gap-2">
        <FilterBar options={STATUS_OPTIONS} value={status} onChange={handleFilterChange(setStatus)} />
        <FilterBar options={EXCHANGE_OPTIONS} value={exchange} onChange={handleFilterChange(setExchange)} />
      </div>

      {error && <ErrorBanner message={error} />}

      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        {loading && !data ? (
          <Spinner />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900">
                    <th className="px-4 py-3 text-left font-medium">시간</th>
                    <th className="px-4 py-3 text-left font-medium">거래소</th>
                    <th className="px-4 py-3 text-left font-medium">종목</th>
                    <th className="px-4 py-3 text-left font-medium">방향</th>
                    <th className="px-4 py-3 text-left font-medium">전략</th>
                    <th className="px-4 py-3 text-right font-medium">주문가</th>
                    <th className="px-4 py-3 text-left font-medium w-32">체결률</th>
                    <th className="px-4 py-3 text-left font-medium">상태</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {!data || data.orders.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-10 text-center text-slate-400 dark:text-slate-500 text-xs">
                        주문 없음
                      </td>
                    </tr>
                  ) : data.orders.map((o, i) => (
                    <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                      <td className="px-4 py-2.5 text-slate-500 dark:text-slate-400 font-mono text-xs whitespace-nowrap">
                        {o.created_fmt}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge value={o.exchange} label={o.exchange.toUpperCase()} />
                      </td>
                      <td className="px-4 py-2.5 font-medium text-slate-800 dark:text-slate-200 text-xs">
                        {o.ticker}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge value={o.side} />
                      </td>
                      <td className="px-4 py-2.5 text-slate-500 dark:text-slate-400 text-xs">{o.strategy}</td>
                      <td className="px-4 py-2.5 text-right font-mono text-slate-700 dark:text-slate-300 text-xs whitespace-nowrap">
                        {o.price?.toLocaleString()}
                      </td>
                      <td className="px-4 py-2.5 w-32">
                        <ProgressBar value={o.fill_pct} />
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge value={o.status} label={o.status_label} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* 페이지네이션 컨트롤 */}
            {totalPages > 1 && (
              <div className="px-4 py-3 bg-slate-50 dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <div className="text-xs text-slate-500 dark:text-slate-400">
                  Page <span className="font-semibold text-slate-900 dark:text-white">{page}</span> of {totalPages}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-30 bg-white dark:bg-slate-800 transition-colors"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <button
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-700 disabled:opacity-30 bg-white dark:bg-slate-800 transition-colors"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <p className="text-xs text-slate-400 dark:text-slate-600 text-right">
        총 {data?.total || 0}건
      </p>
    </div>
  )
}
