import { useCallback, useEffect, useState } from 'react'
import {
  RotateCcw,
  Download,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react'
import { fetchTrades } from '../api/trades'
import type { TradesData } from '../types'
import Badge from '../components/ui/Badge'
import DateRangePicker, { type DateRangeValue } from '../components/ui/DateRangePicker'
import ErrorBanner from '../components/ui/ErrorBanner'
import PageHeader from '../components/ui/PageHeader'
import Pagination from '../components/ui/Pagination'
import { StatCardSkeleton, CardSkeleton } from '../components/ui/Skeleton'
import SyncIndicator from '../components/ui/SyncIndicator'
import { PAGE_META } from '../config/pageMeta'
import { usePersistedState } from '../hooks/usePersistedState'
import { useRealtime } from '../hooks/useRealtime'
import { useToast } from '../contexts/ToastContext'
import { exportToCsv } from '../utils/csv'
import { krwFmt } from '../utils/formatters'

const DEFAULT_RANGE: DateRangeValue = { mode: '7d', from: '', to: '' }

export default function Trades() {
  const toast = useToast()
  const [data, setData] = useState<TradesData | null>(null)
  const [dateRange, setDateRange] = usePersistedState<DateRangeValue>('filter:trades:dateRange', DEFAULT_RANGE)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = usePersistedState('filter:trades:pageSize', 50)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const loadData = useCallback(
    (showSpinner = false, targetPage = page, targetPageSize = pageSize) => {
      if (showSpinner) setLoading(true)
      fetchTrades(dateRange, targetPage, targetPageSize)
        .then((res) => {
          setData(res)
          setLastUpdated(new Date())
          setError(null)
        })
        .catch((e: unknown) => setError(e instanceof Error ? e.message : '체결 내역을 불러오지 못했습니다.'))
        .finally(() => {
          if (showSpinner) setLoading(false)
        })
    },
    [dateRange, page, pageSize],
  )

  useEffect(() => {
    loadData(true, page, pageSize)
  }, [loadData, page, pageSize])

  useRealtime(
    useCallback(() => {
      loadData(false, page, pageSize)
    }, [loadData, page, pageSize]),
  )

  const handleRangeChange = (range: DateRangeValue) => {
    setDateRange(range)
    setPage(1)
  }

  const handleExportCsv = () => {
    if (!data || data.trades.length === 0) return
    const headers = [
      { key: 'executed_fmt', label: '체결시간' },
      { key: 'exchange', label: '거래소' },
      { key: 'ticker', label: '종목' },
      { key: 'side', label: '구분' },
      { key: 'price', label: '체결단가' },
      { key: 'volume', label: '체결수량' },
      { key: 'krw', label: '체결금액' },
      { key: 'fee_amount', label: '수수료' },
      { key: 'strategy', label: '전략' },
    ]
    exportToCsv('trades_list', headers, data.trades)
    toast.success('거래 내역이 CSV로 저장되었습니다.')
  }

  const handleResetFilters = () => {
    setDateRange(DEFAULT_RANGE)
    setPage(1)
  }

  const isFilterModified =
    dateRange.mode !== DEFAULT_RANGE.mode || dateRange.from !== DEFAULT_RANGE.from || dateRange.to !== DEFAULT_RANGE.to

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0

  // 매수 vs 매도 비율 계산
  const buyCount = data?.summary.buy ?? 0
  const sellCount = data?.summary.sell ?? 0
  const totalCount = buyCount + sellCount
  const buyRatio = totalCount > 0 ? (buyCount / totalCount) * 100 : 50

  return (
    <div className="space-y-4 pb-8">
      <PageHeader
        {...PAGE_META.trades}
        actions={
          <div className="flex items-center gap-2">
            <SyncIndicator lastUpdated={lastUpdated} loading={loading} error={error} />
            <button
              onClick={handleExportCsv}
              disabled={!data || data.trades.length === 0}
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors shadow-sm disabled:opacity-50"
            >
              <Download size={14} />
              <span>CSV</span>
            </button>
          </div>
        }
      />

      {error && <ErrorBanner message={error} />}

      {/* 4대 메트릭 요약 카드 & 매수/매도 비율 게이지 */}
      {loading && !data ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">조회기간 거래</span>
              <p className="mt-1.5 text-xl font-extrabold text-slate-900 dark:text-white font-mono">
                {data?.total.toLocaleString()}건
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">총 거래금액</span>
              <p className="mt-1.5 text-xl font-extrabold text-emerald-600 dark:text-emerald-400 font-mono">
                {krwFmt(data?.summary.volume_krw ?? 0)}
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">매수 체결</span>
              <p className="mt-1.5 text-xl font-extrabold text-red-500 dark:text-red-400 font-mono flex items-center gap-1">
                <ArrowUpRight size={18} />
                {buyCount.toLocaleString()}건
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">매도 체결</span>
              <p className="mt-1.5 text-xl font-extrabold text-blue-500 dark:text-blue-400 font-mono flex items-center gap-1">
                <ArrowDownRight size={18} />
                {sellCount.toLocaleString()}건
              </p>
            </div>
          </div>

          {/* 매수/매도 비율 게이지 바 */}
          {totalCount > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-600 dark:text-slate-300">
                <span className="text-red-500">매수 {buyRatio.toFixed(1)}%</span>
                <span className="text-slate-400">체결 거래량 비율</span>
                <span className="text-blue-500">매도 {(100 - buyRatio).toFixed(1)}%</span>
              </div>
              <div className="mt-2 flex h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <div style={{ width: `${buyRatio}%` }} className="bg-red-500 transition-all duration-300" />
                <div style={{ width: `${100 - buyRatio}%` }} className="bg-blue-500 transition-all duration-300" />
              </div>
            </div>
          )}
        </div>
      )}

      {/* 필터 조작 바 */}
      <div className="flex items-center justify-between gap-2">
        <DateRangePicker value={dateRange} onChange={handleRangeChange} />
        {isFilterModified && (
          <button
            onClick={handleResetFilters}
            className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
          >
            <RotateCcw size={12} />
            <span>초기화</span>
          </button>
        )}
      </div>

      {/* 거래 리스트 (데스크톱 테이블 / 모바일 타임라인) */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {loading && !data ? (
          <div className="p-4 space-y-3">
            <CardSkeleton />
            <CardSkeleton />
          </div>
        ) : (
          <>
            {/* 데스크톱 테이블 뷰 (md+) */}
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 font-semibold text-slate-500 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400">
                    <th className="px-4 py-3">체결시간</th>
                    <th className="px-4 py-3">거래소</th>
                    <th className="px-4 py-3">종목</th>
                    <th className="px-4 py-3">구분</th>
                    <th className="px-4 py-3 text-right">체결단가</th>
                    <th className="px-4 py-3 text-right">체결수량</th>
                    <th className="px-4 py-3 text-right">체결금액</th>
                    <th className="px-4 py-3 text-right">수수료</th>
                    <th className="px-4 py-3">전략</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-mono">
                  {!data || data.trades.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="py-12 text-center text-xs text-slate-400 font-sans">
                        조회 기간 내 체결 내역이 없습니다.
                      </td>
                    </tr>
                  ) : (
                    data.trades.map((trade, idx) => (
                      <tr key={trade.id || idx} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                        <td className="whitespace-nowrap px-4 py-2.5 text-slate-500 dark:text-slate-400">
                          {trade.executed_fmt}
                        </td>
                        <td className="px-4 py-2.5 font-sans">
                          <Badge value={trade.exchange} label={trade.exchange.toUpperCase()} />
                        </td>
                        <td className="whitespace-nowrap px-4 py-2.5 font-semibold text-slate-800 dark:text-slate-200 font-sans">
                          {trade.ticker}
                        </td>
                        <td className="px-4 py-2.5 font-sans">
                          <Badge value={trade.side} />
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-700 dark:text-slate-300">
                          {trade.price?.toLocaleString()}원
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-600 dark:text-slate-400">
                          {trade.volume?.toFixed(4)}
                        </td>
                        <td className="px-4 py-2.5 text-right font-semibold text-slate-900 dark:text-white">
                          {krwFmt(trade.krw ?? 0)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-400">
                          {trade.fee_amount ? `${krwFmt(trade.fee_amount)}` : '—'}
                        </td>
                        <td className="px-4 py-2.5 text-slate-500 font-sans">{trade.strategy || '—'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* 모바일 타임라인 카드 뷰 (<md) */}
            <div className="block divide-y divide-slate-100 p-3 md:hidden dark:divide-slate-800">
              {!data || data.trades.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-400">
                  조회 기간 내 체결 내역이 없습니다.
                </div>
              ) : (
                data.trades.map((trade, idx) => (
                  <div key={trade.id || idx} className="py-3 space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-1.5">
                        <Badge value={trade.exchange} label={trade.exchange.toUpperCase()} />
                        <span className="font-bold text-slate-900 dark:text-white">{trade.ticker}</span>
                        <Badge value={trade.side} />
                      </div>
                      <span className="font-mono text-[11px] text-slate-400">{trade.executed_fmt}</span>
                    </div>

                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="text-slate-400 font-sans text-[11px]">
                        {trade.price?.toLocaleString()}원 × {trade.volume?.toFixed(4)}
                      </span>
                      <span className="font-bold text-slate-900 dark:text-white">
                        {krwFmt(trade.krw ?? 0)}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        )}

        {/* 페이지네이션 */}
        {data && totalPages > 1 && (
          <Pagination
            currentPage={page}
            totalPages={totalPages}
            pageSize={pageSize}
            totalCount={data.total}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
          />
        )}
      </div>
    </div>
  )
}
