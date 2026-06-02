import { useEffect, useState, useCallback } from 'react'
import { BarChart2, TrendingUp, TrendingDown, DollarSign, ChevronLeft, ChevronRight } from 'lucide-react'
import { fetchTrades } from '../api/trades'
import type { TradesData } from '../types'
import Badge from '../components/ui/Badge'
import FilterBar from '../components/ui/FilterBar'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'
import { useRealtime } from '../hooks/useRealtime'
import { krwFmt } from '../utils/formatters'

const PERIOD_OPTIONS = [
  { value: '1d',  label: '1일' },
  { value: '7d',  label: '7일' },
  { value: '30d', label: '30일' },
  { value: 'all', label: '전체' },
]

export default function Trades() {
  const [data, setData] = useState<TradesData | null>(null)
  const [period, setPeriod] = useState('7d')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pageSize = 50

  const loadData = useCallback((showSpinner = false, targetPage = page) => {
    if (showSpinner) setLoading(true)
    fetchTrades(period, targetPage, pageSize)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => {
        if (showSpinner) setLoading(false)
      })
  }, [period, page])

  useEffect(() => {
    loadData(true, page)
  }, [loadData, page])

  useRealtime(useCallback(() => loadData(false, page), [loadData, page]))

  const handlePeriodChange = (p: string) => {
    setPeriod(p)
    setPage(1) // 기간 변경 시 첫 페이지로
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
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">거래 내역</h1>
        <FilterBar options={PERIOD_OPTIONS} value={period} onChange={handlePeriodChange} />
      </div>

      {error && <ErrorBanner message={error} />}

      {loading && !data && <Spinner />}

      {data && (
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
              { title: '거래소별 (현재 페이지)', rows: data.by_exchange },
              { title: '전략별 (현재 페이지)', rows: data.by_strategy },
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
            <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">상세 내역</h3>
              <span className="text-[10px] text-slate-400 font-mono">Total: {data.total.toLocaleString()}</span>
            </div>
            
            {/* 데스크톱 뷰 (테이블 형태) */}
            <div className="hidden md:block overflow-x-auto">
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

            {/* 모바일 뷰 (카드 형태) */}
            <div className="block md:hidden divide-y divide-slate-100 dark:divide-slate-800">
              {data.trades.length === 0 ? (
                <div className="px-4 py-10 text-center text-slate-400 text-xs">
                  거래 없음
                </div>
              ) : (
                data.trades.map((t, i) => (
                  <div key={i} className="p-4 space-y-3 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-slate-500 dark:text-slate-400 font-mono">{t.executed_fmt}</span>
                      <Badge value={t.side} />
                    </div>
                    <div className="flex justify-between items-baseline">
                      <div className="flex items-center gap-1.5">
                        <Badge value={t.exchange} label={t.exchange.toUpperCase()} />
                        <span className="font-semibold text-slate-800 dark:text-slate-200 text-xs">{t.ticker}</span>
                      </div>
                      <span className="font-mono text-xs font-bold text-slate-900 dark:text-white">
                        {t.price?.toLocaleString()}원
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                      <span>전략: {t.strategy}</span>
                      <span>수량: <span className="font-mono text-slate-800 dark:text-slate-200 font-medium">{t.volume?.toFixed(4)}</span></span>
                    </div>
                    <div className="flex justify-end text-xs font-semibold text-slate-700 dark:text-slate-300">
                      대금: {t.krw?.toLocaleString()}원
                    </div>
                  </div>
                ))
              )}
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
          </div>
        </>
      )}
    </div>
  )
}
