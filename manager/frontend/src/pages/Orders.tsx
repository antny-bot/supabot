import { useCallback, useEffect, useState } from 'react'
import {
  RotateCcw,
  RefreshCw,
  Download,
  ShieldAlert,
  Filter,
  CheckCircle2,
  Clock,
} from 'lucide-react'
import { fetchOrders, cancelOrder, cancelAllOrders, syncOrder, forceUpdateOrder } from '../api/orders'
import type { OrdersData, Order } from '../types'
import Badge from '../components/ui/Badge'
import BottomSheet from '../components/ui/BottomSheet'
import type { DateRangeValue } from '../components/ui/DateRangePicker'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import Pagination from '../components/ui/Pagination'
import ProgressBar from '../components/ui/ProgressBar'
import SegmentedControl from '../components/ui/SegmentedControl'
import { CardSkeleton } from '../components/ui/Skeleton'
import SyncIndicator from '../components/ui/SyncIndicator'
import { PAGE_META } from '../config/pageMeta'
import { usePersistedState } from '../hooks/usePersistedState'
import { useRealtime } from '../hooks/useRealtime'
import { useToast } from '../contexts/ToastContext'
import { exportToCsv } from '../utils/csv'
import { krwFmt } from '../utils/formatters'

const OPEN_STATUSES = new Set(['wait', 'partial', 'pending_reorder', 'reserved'])

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
  const toast = useToast()

  // 듀얼 뷰 모드: 'open' (활성 주문) | 'history' (체결/취소 이력)
  const [viewMode, setViewMode] = usePersistedState<'open' | 'history'>('orders:view_mode', 'open')

  // 데이터 상태
  const [data, setData] = useState<OrdersData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  // 필터 상태
  const [exchange, setExchange] = usePersistedState('filter:orders:exchange', '')
  const [side, setSide] = usePersistedState('filter:orders:side', '')
  const [dateRange, setDateRange] = usePersistedState<DateRangeValue>('filter:orders:dateRange', DEFAULT_RANGE)
  const [groupNoFilter, setGroupNoFilter] = useState<number | undefined>(undefined)
  const [groupNoInput, setGroupNoInput] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = usePersistedState('filter:orders:pageSize', 50)

  // 모바일 통합 필터 바텀시트
  const [isFilterSheetOpen, setIsFilterSheetOpen] = useState(false)

  // 주문 개별 액션 상태
  const [cancellingUuid, setCancellingUuid] = useState<string | null>(null)
  const [syncingUuid, setSyncingUuid] = useState<string | null>(null)

  // 수동 수정 모달
  const [isEditModalOpen, setIsEditModalOpen] = useState(false)
  const [editingOrder, setEditingOrder] = useState<any | null>(null)
  const [editState, setEditState] = useState('done')
  const [editFilledVolume, setEditFilledVolume] = useState('0')
  const [editLoading, setEditLoading] = useState(false)

  // viewMode에 따른 status 쿼리 결정
  // open 모드일 때는 백엔드에 'open' (또는 wait,partial 등) 요청
  const queryStatus = viewMode === 'open' ? 'open' : ''
  const dateFrom = dateRange.mode === 'custom' ? dateRange.from : undefined
  const dateTo = dateRange.mode === 'custom' ? dateRange.to : undefined

  const loadData = useCallback(
    (showSpinner = false, targetPage = page, targetPageSize = pageSize) => {
      if (showSpinner) setLoading(true)
      fetchOrders(queryStatus, exchange, side, dateFrom, dateTo, targetPage, targetPageSize, groupNoFilter)
        .then((res) => {
          setData(res)
          setLastUpdated(new Date())
          setError(null)
        })
        .catch((e: unknown) => setError(e instanceof Error ? e.message : '주문 목록을 불러오지 못했습니다.'))
        .finally(() => {
          if (showSpinner) setLoading(false)
        })
    },
    [queryStatus, exchange, side, dateFrom, dateTo, groupNoFilter, page, pageSize],
  )

  useEffect(() => {
    loadData(true, page, pageSize)
  }, [loadData, page, pageSize])

  useRealtime(
    useCallback(() => {
      loadData(false, page, pageSize)
    }, [loadData, page, pageSize]),
  )

  // 주문 취소
  const handleCancelOrder = async (uuid: string) => {
    if (!confirm('해당 주문을 거래소에서 취소하시겠습니까?')) return
    setCancellingUuid(uuid)
    try {
      const res = await cancelOrder(uuid)
      if (res.ok) {
        toast.success('주문 취소 요청이 완료되었습니다.')
        loadData(false, page, pageSize)
      } else {
        toast.error(`취소 실패: ${res.error || '알 수 없는 오류'}`)
      }
    } catch (e) {
      toast.error(`취소 오류: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setCancellingUuid(null)
    }
  }

  // 주문 거래소 상태 동기화
  const handleSyncOrder = async (uuid: string) => {
    setSyncingUuid(uuid)
    try {
      const res = await syncOrder(uuid)
      if (res.ok) {
        loadData(false, page, pageSize)
        toast.success('거래소와 최신 상태가 동기화되었습니다.')
      } else {
        toast.error(`동기화 실패: ${res.error || '거래소 응답 없음'}`)
      }
    } catch (e) {
      toast.error(`동기화 오류: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setSyncingUuid(null)
    }
  }

  // 활성 주문 일괄 동기화
  const handleSyncAllOpen = async () => {
    if (!data || data.orders.length === 0) return
    const openOrders = data.orders.filter((o) => OPEN_STATUSES.has(o.status))
    if (openOrders.length === 0) {
      toast.info('동기화할 활성 주문이 없습니다.')
      return
    }
    if (!confirm(`현재 화면의 활성 주문 ${openOrders.length}건을 일괄 동기화하시겠습니까?`)) return

    setLoading(true)
    let successCount = 0
    let failCount = 0

    for (const order of openOrders) {
      try {
        const res = await syncOrder(order.uuid)
        if (res.ok) successCount++
        else failCount++
      } catch {
        failCount++
      }
    }

    loadData(false, page, pageSize)
    toast.success(`일괄 동기화 완료 (성공: ${successCount}건, 실패: ${failCount}건)`)
  }

  // 활성 주문 일괄 취소
  const handleCancelAll = async () => {
    if (!confirm('현재 활성화된 모든 미체결 주문을 일괄 취소하시겠습니까?')) return
    setLoading(true)
    try {
      const res = await cancelAllOrders()
      if (res.ok) {
        toast.success(`오픈 주문 ${res.cancelled_count}건이 일괄 취소되었습니다.`)
        loadData(false, page, pageSize)
      } else {
        toast.error('일괄 취소 중 오류가 발생했습니다.')
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '취소 요청 실패')
    } finally {
      setLoading(false)
    }
  }

  // CSV 내보내기
  const handleExportCsv = () => {
    if (!data || data.orders.length === 0) {
      toast.info('내보낼 주문 데이터가 없습니다.')
      return
    }
    const headers = [
      { key: 'group_no', label: '배치' },
      { key: 'created_fmt', label: '시간' },
      { key: 'exchange', label: '거래소' },
      { key: 'ticker', label: '종목' },
      { key: 'side', label: '구분' },
      { key: 'strategy', label: '전략' },
      { key: 'price', label: '주문가' },
      { key: 'volume', label: '수량' },
      { key: 'order_value', label: '주문금액' },
      { key: 'status_label', label: '상태' },
    ]
    exportToCsv(`orders_${viewMode}`, headers, data.orders)
    toast.success('주문 목록이 CSV로 저장되었습니다.')
  }

  const openEditModal = (order: Order) => {
    setEditingOrder(order)
    setEditState(order.status)
    setEditFilledVolume(String(order.filled_volume || 0))
    setIsEditModalOpen(true)
  }

  const handleForceUpdate = async () => {
    if (!editingOrder) return
    const vol = parseFloat(editFilledVolume)
    if (isNaN(vol) || vol < 0) {
      toast.warning('올바른 체결 수량을 입력하세요.')
      return
    }

    setEditLoading(true)
    try {
      const res = await forceUpdateOrder(editingOrder.uuid, editState, vol)
      if (res.ok) {
        setIsEditModalOpen(false)
        loadData(false, page, pageSize)
        toast.success('주문 상태가 수동 업데이트되었습니다.')
      } else {
        toast.error(`업데이트 실패: ${res.error || '알 수 없는 오류'}`)
      }
    } catch (e) {
      toast.error(`업데이트 오류: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setEditLoading(false)
    }
  }

  const handleResetFilters = () => {
    setExchange('')
    setSide('')
    setDateRange(DEFAULT_RANGE)
    setGroupNoFilter(undefined)
    setGroupNoInput('')
    setPage(1)
  }

  const activeFiltersCount =
    (exchange ? 1 : 0) + (side ? 1 : 0) + (dateRange.mode !== 'all' ? 1 : 0) + (groupNoFilter !== undefined ? 1 : 0)

  return (
    <div className="space-y-4 pb-8">
      {/* 최상단 페이지 헤더 */}
      <PageHeader
        {...PAGE_META.orders}
        actions={
          <div className="flex items-center gap-2">
            <SyncIndicator lastUpdated={lastUpdated} loading={loading} error={error} />
            {viewMode === 'open' ? (
              <>
                <button
                  onClick={handleSyncAllOpen}
                  className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors shadow-sm"
                  title="표시된 오픈 주문 거래소 일괄 동기화"
                >
                  <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                  <span className="hidden sm:inline">일괄 동기화</span>
                </button>
                <button
                  onClick={handleCancelAll}
                  className="flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-100 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-400 dark:hover:bg-rose-900/60 transition-colors shadow-sm"
                  title="모든 오픈 주문 즉시 취소"
                >
                  <ShieldAlert size={14} />
                  <span>일괄 취소</span>
                </button>
              </>
            ) : (
              <button
                onClick={handleExportCsv}
                className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors shadow-sm"
              >
                <Download size={14} />
                <span>CSV</span>
              </button>
            )}
          </div>
        }
      />

      {error && <ErrorBanner message={error} />}

      {/* 듀얼 뷰 세그먼트 컨트롤 & 필터 바 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <SegmentedControl
          options={[
            {
              id: 'open',
              label: '활성 주문 (오픈)',
              icon: <Clock size={15} />,
              badge: viewMode === 'open' ? data?.total : undefined,
            },
            {
              id: 'history',
              label: '주문 이력 (히스토리)',
              icon: <CheckCircle2 size={15} />,
              badge: viewMode === 'history' ? data?.total : undefined,
            },
          ]}
          value={viewMode}
          onChange={(mode) => {
            setViewMode(mode)
            setPage(1)
          }}
        />

        {/* 필터 조작: 모바일에서는 바텀시트 열기 버튼, PC에서는 인라인 필터 */}
        <div className="flex items-center gap-2">
          {/* 모바일 필터 열기 버튼 */}
          <button
            onClick={() => setIsFilterSheetOpen(true)}
            className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 sm:hidden"
          >
            <Filter size={14} />
            <span>필터</span>
            {activeFiltersCount > 0 && (
              <span className="rounded-full bg-indigo-500 px-1.5 py-0.2 text-[10px] font-bold text-white">
                {activeFiltersCount}
              </span>
            )}
          </button>

          {/* 데스크톱 인라인 필터 */}
          <div className="hidden sm:flex items-center gap-2">
            <select
              value={exchange}
              onChange={(e) => {
                setExchange(e.target.value)
                setPage(1)
              }}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 outline-none dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
            >
              {EXCHANGE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            <select
              value={side}
              onChange={(e) => {
                setSide(e.target.value)
                setPage(1)
              }}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 outline-none dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
            >
              {SIDE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs dark:border-slate-800 dark:bg-slate-900">
              <span className="text-slate-400">#배치</span>
              <input
                type="number"
                min={1}
                placeholder="번호"
                value={groupNoInput}
                onChange={(e) => {
                  const val = e.target.value
                  setGroupNoInput(val)
                  const n = parseInt(val, 10)
                  setGroupNoFilter(val && !isNaN(n) && n > 0 ? n : undefined)
                  setPage(1)
                }}
                className="w-12 bg-transparent outline-none dark:text-slate-200"
              />
            </div>

            {activeFiltersCount > 0 && (
              <button
                onClick={handleResetFilters}
                className="flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-500 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                title="필터 초기화"
              >
                <RotateCcw size={12} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 주문 리스트 본문 (데스크톱: 고밀도 테이블 / 모바일: 슬림 카드 뷰) */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {loading && !data ? (
          <div className="p-4 space-y-3">
            <CardSkeleton />
            <CardSkeleton />
          </div>
        ) : (
          <>
            {/* [1] 데스크톱 테이블 뷰 (md+) */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 font-semibold text-slate-500 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400">
                    <th className="px-4 py-3">#배치</th>
                    <th className="px-4 py-3">시간</th>
                    <th className="px-4 py-3">거래소</th>
                    <th className="px-4 py-3">종목</th>
                    <th className="px-4 py-3">구분</th>
                    <th className="px-4 py-3">전략</th>
                    <th className="px-4 py-3 text-right">주문가격</th>
                    <th className="px-4 py-3 text-right">수량</th>
                    <th className="px-4 py-3 text-right">주문금액</th>
                    <th className="w-28 px-4 py-3">체결률</th>
                    <th className="px-4 py-3">상태</th>
                    <th className="px-4 py-3 text-right">제어</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-mono">
                  {!data || data.orders.length === 0 ? (
                    <tr>
                      <td colSpan={12} className="py-12 text-center text-xs text-slate-400 font-sans">
                        {viewMode === 'open' ? '현재 활성화된 오픈 주문이 없습니다.' : '주문 이력이 없습니다.'}
                      </td>
                    </tr>
                  ) : (
                    data.orders.map((order) => (
                      <tr
                        key={order.uuid}
                        className="transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                      >
                        <td className="px-4 py-2.5">
                          {order.group_no ? (
                            <button
                              onClick={() => {
                                setGroupNoFilter(order.group_no!)
                                setGroupNoInput(String(order.group_no))
                                setPage(1)
                              }}
                              className="rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] font-bold text-indigo-600 hover:bg-indigo-100 dark:bg-indigo-950 dark:text-indigo-400"
                            >
                              #{order.group_no}
                            </button>
                          ) : (
                            <span className="text-slate-300 dark:text-slate-600">—</span>
                          )}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2.5 text-slate-500 dark:text-slate-400">
                          {order.created_fmt}
                        </td>
                        <td className="px-4 py-2.5 font-sans">
                          <Badge value={order.exchange} label={order.exchange.toUpperCase()} />
                        </td>
                        <td className="whitespace-nowrap px-4 py-2.5 font-semibold text-slate-800 dark:text-slate-200 font-sans">
                          {order.ticker}
                        </td>
                        <td className="px-4 py-2.5 font-sans">
                          <Badge value={order.side} />
                        </td>
                        <td className="px-4 py-2.5 text-slate-500 font-sans">
                          {(order as any).order_kind && (order as any).order_kind !== '일반' ? (
                            <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              (order as any).order_kind === '모으기 매수'
                                ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300'
                                : 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300'
                            }`}>
                              {(order as any).order_kind}
                            </span>
                          ) : (
                            order.strategy
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-700 dark:text-slate-300">
                          {order.price?.toLocaleString()}원
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-600 dark:text-slate-400">
                          {order.volume?.toFixed(4)}
                        </td>
                        <td className="px-4 py-2.5 text-right font-semibold text-slate-800 dark:text-slate-200">
                          {krwFmt(order.order_value ?? 0)}
                        </td>
                        <td className="px-4 py-2.5 font-sans">
                          <ProgressBar value={order.fill_pct} />
                        </td>
                        <td className="px-4 py-2.5 font-sans">
                          <Badge value={order.status} label={order.status_label} />
                        </td>
                        <td className="whitespace-nowrap px-4 py-2.5 text-right font-sans">
                          <div className="flex items-center justify-end gap-1.5">
                            {OPEN_STATUSES.has(order.status) && (
                              <button
                                onClick={() => handleCancelOrder(order.uuid)}
                                disabled={cancellingUuid === order.uuid}
                                className="rounded-md border border-rose-200 bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-600 hover:bg-rose-100 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-400"
                              >
                                {cancellingUuid === order.uuid ? '…' : '취소'}
                              </button>
                            )}
                            <button
                              onClick={() => handleSyncOrder(order.uuid)}
                              disabled={syncingUuid === order.uuid}
                              className="rounded-md border border-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                            >
                              {syncingUuid === order.uuid ? '…' : '동기화'}
                            </button>
                            <button
                              onClick={() => openEditModal(order)}
                              className="rounded-md border border-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
                            >
                              수정
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* [2] 모바일 슬림 카드 뷰 (<md) */}
            <div className="block divide-y divide-slate-100 p-3 md:hidden dark:divide-slate-800">
              {!data || data.orders.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-400">
                  {viewMode === 'open' ? '현재 활성화된 오픈 주문이 없습니다.' : '주문 이력이 없습니다.'}
                </div>
              ) : (
                data.orders.map((order) => (
                  <div key={order.uuid} className="py-3.5 space-y-2.5">
                    {/* 상단: 거래소, 종목, 구분, 상태 */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <Badge value={order.exchange} label={order.exchange.toUpperCase()} />
                        <span className="text-sm font-bold text-slate-900 dark:text-white">
                          {order.ticker}
                        </span>
                        <Badge value={order.side} />
                        {order.group_no && (
                          <span className="rounded bg-indigo-50 px-1.5 py-0.2 text-[10px] font-bold text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400">
                            #{order.group_no}
                          </span>
                        )}
                      </div>
                      <Badge value={order.status} label={order.status_label} />
                    </div>

                    {/* 중단: 가격, 수량, 주문금액 */}
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                      <div>
                        <span className="text-slate-400 font-sans text-[11px]">주문가 / 수량</span>
                        <p className="font-semibold text-slate-800 dark:text-slate-200">
                          {order.price?.toLocaleString()}원 / {order.volume?.toFixed(4)}
                        </p>
                      </div>
                      <div className="text-right">
                        <span className="text-slate-400 font-sans text-[11px]">주문 총액</span>
                        <p className="font-semibold text-slate-800 dark:text-slate-200">
                          {krwFmt(order.order_value ?? 0)}
                        </p>
                      </div>
                    </div>

                    {/* 하단: 체결률 바 & 제어 버튼 */}
                    <div className="flex items-center justify-between gap-3 pt-1">
                      <div className="flex-1">
                        <ProgressBar value={order.fill_pct} />
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {OPEN_STATUSES.has(order.status) && (
                          <button
                            onClick={() => handleCancelOrder(order.uuid)}
                            disabled={cancellingUuid === order.uuid}
                            className="rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-600 hover:bg-rose-100 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-400"
                          >
                            취소
                          </button>
                        )}
                        <button
                          onClick={() => handleSyncOrder(order.uuid)}
                          disabled={syncingUuid === order.uuid}
                          className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                        >
                          동기화
                        </button>
                        <button
                          onClick={() => openEditModal(order)}
                          className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-400"
                        >
                          수정
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        )}

        {/* 페이지네이션 */}
        {data && data.total > pageSize && (
          <Pagination
            currentPage={page}
            totalPages={Math.ceil(data.total / pageSize)}
            pageSize={pageSize}
            totalCount={data.total}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        )}
      </div>

      {/* 모바일 통합 필터 바텀시트 */}
      <BottomSheet
        isOpen={isFilterSheetOpen}
        onClose={() => setIsFilterSheetOpen(false)}
        title="주문 검색 필터"
        footer={
          <div className="flex items-center justify-between gap-2">
            <button
              onClick={handleResetFilters}
              className="flex items-center gap-1.5 rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-semibold text-slate-600 dark:border-slate-700 dark:text-slate-300"
            >
              <RotateCcw size={14} /> 초기화
            </button>
            <button
              onClick={() => setIsFilterSheetOpen(false)}
              className="flex-1 rounded-xl bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
            >
              필터 적용하기
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">거래소</label>
            <div className="mt-1.5 grid grid-cols-2 gap-2">
              {EXCHANGE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setExchange(opt.value)}
                  className={`rounded-lg border p-2 text-xs font-medium transition-colors ${
                    exchange === opt.value
                      ? 'border-indigo-600 bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
                      : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">주문 구분</label>
            <div className="mt-1.5 grid grid-cols-3 gap-2">
              {SIDE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setSide(opt.value)}
                  className={`rounded-lg border p-2 text-xs font-medium transition-colors ${
                    side === opt.value
                      ? 'border-indigo-600 bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300'
                      : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </BottomSheet>

      {/* 수동 주문 상태 수정 모달 */}
      {isEditModalOpen && editingOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm"
            onClick={() => !editLoading && setIsEditModalOpen(false)}
          />
          <div className="relative z-10 w-full max-w-sm rounded-2xl bg-white p-5 shadow-2xl dark:bg-slate-900 border border-slate-200 dark:border-slate-800">
            <h3 className="text-base font-bold text-slate-900 dark:text-white">주문 수동 수정</h3>
            <p className="mt-1 text-xs text-slate-500 font-mono">
              {editingOrder.ticker} ({editingOrder.exchange.toUpperCase()})
            </p>
            <div className="mt-4 space-y-3">
              <div>
                <label className="text-xs font-medium text-slate-600 dark:text-slate-300">상태 변경</label>
                <select
                  value={editState}
                  onChange={(e) => setEditState(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                >
                  <option value="done">체결 완료 (done)</option>
                  <option value="cancel">취소됨 (cancel)</option>
                  <option value="wait">대기중 (wait)</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-medium text-slate-600 dark:text-slate-300">체결 수량</label>
                <input
                  type="number"
                  step="any"
                  value={editFilledVolume}
                  onChange={(e) => setEditFilledVolume(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white p-2 text-xs font-mono dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                />
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                disabled={editLoading}
                onClick={() => setIsEditModalOpen(false)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:border-slate-700 dark:text-slate-300"
              >
                닫기
              </button>
              <button
                type="button"
                disabled={editLoading}
                onClick={handleForceUpdate}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {editLoading ? '저장 중...' : '저장하기'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
