import { useCallback, useEffect, useState } from 'react'
import { usePersistedState } from '../hooks/usePersistedState'
import { X, RotateCcw } from 'lucide-react'
import { fetchOrders, cancelOrder } from '../api/orders'
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
import { staggerDelay } from '../utils/animation'
import { krwFmt } from '../utils/formatters'
import Pagination from '../components/ui/Pagination'
import SyncIndicator from '../components/ui/SyncIndicator'

const OPEN_STATUSES = new Set(['wait', 'partial', 'pending_reorder', 'reserved'])

const STATUS_OPTIONS = [
  { value: '', label: '전체 유형' },
  { value: 'open', label: '활성' },
  { value: 'wait', label: '대기' },
  { value: 'partial', label: '부분체결' },
  { value: 'done', label: '완료' },
  { value: 'cancel', label: '취소' },
  { value: 'pending_reorder', label: '재주문대기' },
  { value: 'reserved', label: '예약' },
]

const EXCHANGE_OPTIONS = [
  { value: '', label: '전체 거래소' },
  { value: 'upbit', label: 'Upbit' },
  { value: 'bithumb', label: 'Bithumb' },
  { value: 'kis', label: 'KIS' },
  { value: 'toss', label: '토스증권' },
]

const SIDE_OPTIONS = [
  { value: '', label: '전체 구분' },
  { value: 'bid', label: '매수' },
  { value: 'ask', label: '매도' },
]

const DEFAULT_RANGE: DateRangeValue = { mode: 'all', from: '', to: '' }

export default function Orders() {
  const [data, setData] = useState<OrdersData | null>(null)
  const [status, setStatus] = usePersistedState('filter:orders:status', '')
  const [exchange, setExchange] = usePersistedState('filter:orders:exchange', '')
  const [side, setSide] = usePersistedState('filter:orders:side', '')
  const [dateRange, setDateRange] = usePersistedState<DateRangeValue>('filter:orders:dateRange', DEFAULT_RANGE)
  const [groupNoFilter, setGroupNoFilter] = useState<number | undefined>(undefined)
  const [groupNoInput, setGroupNoInput] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = usePersistedState('filter:orders:pageSize', 50)
  const [expandedFilter, setExpandedFilter] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [cancellingUuid, setCancellingUuid] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const dateFrom = dateRange.mode === 'custom' ? dateRange.from : undefined
  const dateTo = dateRange.mode === 'custom' ? dateRange.to : undefined

  const loadData = useCallback((showSpinner = false, targetPage = page, targetPageSize = pageSize) => {
    if (showSpinner) setLoading(true)
    fetchOrders(status, exchange, side, dateFrom, dateTo, targetPage, targetPageSize, groupNoFilter)
      .then((res) => {
        setData(res)
        setLastUpdated(new Date())
        setError(null)
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류가 발생했습니다.'))
      .finally(() => {
        if (showSpinner) setLoading(false)
      })
  }, [exchange, status, side, dateFrom, dateTo, groupNoFilter, page, pageSize])

  useEffect(() => {
    loadData(true, page, pageSize)
  }, [loadData, page, pageSize])

  useRealtime(useCallback(() => loadData(false, page, pageSize), [loadData, page, pageSize]))

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

  const handleGroupNoClick = (gno: number) => {
    setGroupNoFilter(gno)
    setGroupNoInput(String(gno))
    setPage(1)
  }

  const handleGroupNoInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    setGroupNoInput(val)
    const n = parseInt(val, 10)
    if (!val) {
      setGroupNoFilter(undefined)
      setPage(1)
    } else if (!isNaN(n) && n > 0) {
      setGroupNoFilter(n)
      setPage(1)
    }
  }

  const clearGroupNoFilter = () => {
    setGroupNoFilter(undefined)
    setGroupNoInput('')
    setPage(1)
  }

  const handleCancelOrder = async (uuid: string) => {
    if (!confirm('이 주문을 취소하시겠습니까?')) return
    setCancellingUuid(uuid)
    try {
      const res = await cancelOrder(uuid)
      if (res.ok) {
        loadData(false, page, pageSize)
      } else {
        alert(`취소 실패: ${res.error || '알 수 없는 오류'}`)
      }
    } catch (e) {
      alert(`취소 오류: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setCancellingUuid(null)
    }
  }

  const hasAnyFilter = status !== '' || exchange !== '' || side !== '' || dateRange.mode !== 'all' || groupNoFilter !== undefined

  const handleResetFilters = () => {
    setStatus('')
    setExchange('')
    setSide('')
    setDateRange(DEFAULT_RANGE)
    clearGroupNoFilter()
    setPage(1)
  }

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0

  return (
    <div className="space-y-4">
      <PageHeader
        {...PAGE_META.orders}
        actions={<SyncIndicator lastUpdated={lastUpdated} loading={loading} error={error} />}
      />

      <div className="flex flex-wrap items-center gap-2">
        <FilterBar
          label="상태"
          collapsible
          isOpen={expandedFilter === 'status'}
          onToggle={() => toggleFilter('status')}
          options={STATUS_OPTIONS}
          value={status}
          onChange={handleFilterChange(setStatus)}
        />
        <FilterBar
          label="거래소"
          collapsible
          isOpen={expandedFilter === 'exchange'}
          onToggle={() => toggleFilter('exchange')}
          options={EXCHANGE_OPTIONS}
          value={exchange}
          onChange={handleFilterChange(setExchange)}
        />
        <FilterBar
          label="구분"
          collapsible
          isOpen={expandedFilter === 'side'}
          onToggle={() => toggleFilter('side')}
          options={SIDE_OPTIONS}
          value={side}
          onChange={handleFilterChange(setSide)}
        />
        <DateRangePicker
          label="기간"
          collapsible
          isOpen={expandedFilter === 'date'}
          onToggle={() => toggleFilter('date')}
          value={dateRange}
          onChange={handleDateRangeChange}
        />
        <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-800">
          <span className="text-xs text-slate-500 dark:text-slate-400">#배치</span>
          <input
            type="number"
            min={1}
            value={groupNoInput}
            onChange={handleGroupNoInputChange}
            placeholder="번호"
            className="w-16 bg-transparent text-xs text-slate-700 outline-none dark:text-slate-300 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
          />
          {groupNoFilter !== undefined && (
            <button onClick={clearGroupNoFilter} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
              <X size={12} />
            </button>
          )}
        </div>

        {hasAnyFilter && (
          <button
            onClick={handleResetFilters}
            className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700"
            title="필터 초기화"
          >
            <RotateCcw size={12} />
            <span>필터 초기화</span>
          </button>
        )}
      </div>

      {error && <ErrorBanner message={error} />}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {loading && !data ? (
          <Spinner />
        ) : (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                    <th className="px-4 py-3 text-left font-medium">#배치</th>
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
                    <th className="px-4 py-3 text-left font-medium">취소</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {!data || data.orders.length === 0 ? (
                    <tr>
                      <td colSpan={12} className="px-4 py-10 text-center text-xs text-slate-400 dark:text-slate-500">
                        주문이 없습니다.
                      </td>
                    </tr>
                  ) : data.orders.map((order, index) => (
                    <tr key={index} className="animate-fade-in transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40" style={staggerDelay(index)}>
                      <td className="px-4 py-2.5">
                        {order.group_no != null ? (
                          <button
                            onClick={() => handleGroupNoClick(order.group_no!)}
                            className="rounded-md bg-primary-50 px-2 py-0.5 text-xs font-semibold text-primary-600 hover:bg-primary-100 dark:bg-primary-900/30 dark:text-primary-400 dark:hover:bg-primary-900/50"
                            title={`#${order.group_no} 배치만 필터링`}
                          >
                            #{order.group_no}
                          </button>
                        ) : (
                          <span className="text-xs text-slate-300 dark:text-slate-600">—</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-slate-500 dark:text-slate-400">
                        {order.created_fmt}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge value={order.exchange} label={order.exchange.toUpperCase()} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-xs font-medium text-slate-800 dark:text-slate-200">
                        {order.ticker}
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5">
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
                      <td className="whitespace-nowrap px-4 py-2.5">
                        <Badge value={order.status} label={order.status_label} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5">
                        {OPEN_STATUSES.has(order.status) ? (
                          <button
                            onClick={() => handleCancelOrder(order.uuid)}
                            disabled={cancellingUuid === order.uuid}
                            className="rounded-md border border-red-200 px-2 py-0.5 text-xs text-red-500 hover:bg-red-50 disabled:opacity-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20"
                            title="주문 취소"
                          >
                            {cancellingUuid === order.uuid ? '…' : '취소'}
                          </button>
                        ) : (
                          <span className="text-xs text-slate-300 dark:text-slate-600">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="block divide-y divide-slate-100 dark:divide-slate-800 md:hidden">
              {!data || data.orders.length === 0 ? (
                <div className="px-4 py-10 text-center text-xs text-slate-400 dark:text-slate-500">
                  주문이 없습니다.
                </div>
              ) : data.orders.map((order, index) => (
                <div key={index} className="animate-fade-in space-y-2.5 p-4 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40" style={staggerDelay(index)}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Badge value={order.exchange} label={order.exchange.toUpperCase()} />
                      <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">{order.ticker}</span>
                      {order.group_no != null && (
                        <button
                          onClick={() => handleGroupNoClick(order.group_no!)}
                          className="rounded bg-primary-50 px-1.5 py-0.5 text-[10px] font-semibold text-primary-600 hover:bg-primary-100 dark:bg-primary-900/30 dark:text-primary-400"
                        >
                          #{order.group_no}
                        </button>
                      )}
                    </div>
                    <Badge value={order.status} label={order.status_label} />
                  </div>

                  <div className="flex items-center justify-between text-xs">
                    <div className="flex gap-1.5 text-slate-500 dark:text-slate-400">
                      <span className="font-mono">{order.created_fmt}</span>
                      <span>•</span>
                      <span>{order.strategy}</span>
                    </div>
                    <Badge value={order.side} />
                  </div>

                  <div className="flex items-center justify-between pt-1 text-xs">
                    <span className="text-slate-500 dark:text-slate-400">가격 / 수량</span>
                    <span className="font-mono text-slate-800 dark:text-slate-200">
                      {order.price?.toLocaleString()}원 / {order.volume?.toFixed(4)}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-500 dark:text-slate-400">체결률 / 주문 금액</span>
                    <span className="font-mono text-slate-800 dark:text-slate-200">
                      {(order.fill_pct * 100).toFixed(0)}% / {krwFmt(order.order_value ?? 0)}
                    </span>
                  </div>

                  {OPEN_STATUSES.has(order.status) && (
                    <div className="flex justify-end pt-1.5">
                      <button
                        onClick={() => handleCancelOrder(order.uuid)}
                        disabled={cancellingUuid === order.uuid}
                        className="w-full rounded-lg border border-red-200 py-1.5 text-center text-xs text-red-500 hover:bg-red-50 disabled:opacity-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20"
                      >
                        {cancellingUuid === order.uuid ? '취소 중...' : '주문 취소'}
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <Pagination
              currentPage={page}
              totalPages={totalPages}
              pageSize={pageSize}
              totalCount={data?.total ?? 0}
              onPageChange={setPage}
              onPageSizeChange={(size) => {
                setPageSize(size)
                setPage(1)
              }}
            />
          </>
        )}
      </div>
    </div>
  )
}
