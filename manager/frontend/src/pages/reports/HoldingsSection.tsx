import { useEffect, useState, useMemo } from 'react'
import { TrendingUp, TrendingDown, DollarSign, Award } from 'lucide-react'
import { fetchReportHoldings } from '../../api/reports'
import type { HoldingsReport } from '../../types'
import Badge from '../../components/ui/Badge'
import { StatCardSkeleton, TableRowSkeleton } from '../../components/ui/Skeleton'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay } from '../../utils/animation'
import { krwFmt, pctFmt, pctColor, CARD, TH, TD } from './ReportsShared'
import { usePersistedState } from '../../hooks/usePersistedState'

const HOLDINGS_EXCHANGE_FILTER_KEY = 'sbm_reports_holdings_exchange_filter'

export default function HoldingsSection() {
  const [data, setData] = useState<HoldingsReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 거래소 필터링 상태 (localStorage 영속화)
  const [exchangeFilter, setExchangeFilter] = usePersistedState<string>(
    HOLDINGS_EXCHANGE_FILTER_KEY,
    'all',
  )

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportHoldings()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [])

  // 거래소 드롭다운 옵션
  const exchangeOptions = useMemo(() => {
    const baseExchanges = [
      { value: 'all', label: '전체 거래소' },
      { value: 'upbit', label: 'Upbit' },
      { value: 'bithumb', label: 'Bithumb' },
      { value: 'kis', label: 'KIS' },
      { value: 'toss', label: 'TOSS' },
    ]
    if (!data?.rows) return baseExchanges

    const known = new Set(baseExchanges.map((o) => o.value.toLowerCase()))
    const extraExchanges: { value: string; label: string }[] = []
    data.rows.forEach((r) => {
      const ex = (r.exchange || '').toLowerCase().trim()
      if (ex && !known.has(ex)) {
        known.add(ex)
        extraExchanges.push({ value: ex, label: ex.toUpperCase() })
      }
    })
    return [...baseExchanges, ...extraExchanges]
  }, [data?.rows])

  // 필터링된 rows
  const filteredRows = useMemo(() => {
    if (!data?.rows) return []
    if (!exchangeFilter || exchangeFilter === 'all') return data.rows
    return data.rows.filter(
      (row) => (row.exchange || '').toLowerCase() === exchangeFilter.toLowerCase(),
    )
  }, [data?.rows, exchangeFilter])

  // 필터링된 요약 지표 (선택된 거래소 기준 계산, 전체일 경우 백엔드 summary 사용)
  const currentSummary = useMemo(() => {
    if (!data) return null
    if (!exchangeFilter || exchangeFilter === 'all') return data.summary

    const totalCost = filteredRows.reduce((sum, r) => sum + (r.cost_krw || 0), 0)
    const totalValue = filteredRows.reduce((sum, r) => sum + (r.value_krw || 0), 0)
    const totalPnl = filteredRows.reduce((sum, r) => sum + (r.pnl || 0), 0)
    const totalRoiPct = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0
    const oversoldCount = filteredRows.filter((r) => r.oversold).length

    return {
      total_cost: totalCost,
      total_value: totalValue,
      total_pnl: totalPnl,
      total_roi_pct: totalRoiPct,
      asset_count: filteredRows.length,
      oversold_count: oversoldCount,
    }
  }, [data, exchangeFilter, filteredRows])

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <StatCardSkeleton key={i} />
          ))}
        </div>
        <div className={`${CARD} overflow-hidden`}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                <th className={TH}>거래소</th>
                <th className={TH}>종목</th>
                <th className={`${TH} text-right`}>보유수량</th>
                <th className={`${TH} text-right`}>평균매수가</th>
                <th className={`${TH} text-right`}>현재가</th>
                <th className={`${TH} text-right`}>평가금액</th>
                <th className={`${TH} text-right`}>평가손익</th>
                <th className={`${TH} text-right`}>수익률</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {Array.from({ length: 5 }).map((_, i) => (
                <TableRowSkeleton key={i} cols={8} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }
  if (error) return <ErrorBanner message={error} />
  if (!data || !currentSummary) return null

  const summaryCards = [
    { label: '보유원가', value: krwFmt(currentSummary.total_cost), Icon: TrendingUp, bg: 'bg-blue-500' },
    { label: '평가금액', value: krwFmt(currentSummary.total_value), Icon: DollarSign, bg: 'bg-slate-700' },
    {
      label: '평가손익',
      value: `${currentSummary.total_pnl >= 0 ? '+' : '-'}${krwFmt(Math.abs(currentSummary.total_pnl))}`,
      Icon: Award,
      bg: currentSummary.total_pnl >= 0 ? 'bg-up-500' : 'bg-down-500',
      extra: pctFmt(currentSummary.total_roi_pct),
      extraColor: pctColor(currentSummary.total_pnl),
    },
    {
      label: '투자 종목',
      value: currentSummary.asset_count.toLocaleString(),
      Icon: TrendingDown,
      bg: 'bg-primary-500',
      extra: currentSummary.oversold_count > 0 ? `oversell ${currentSummary.oversold_count}건` : undefined,
      extraColor: currentSummary.oversold_count > 0 ? 'text-amber-600 dark:text-amber-400' : undefined,
    },
  ]

  const isFiltered = exchangeFilter !== 'all'

  return (
    <div className="flex flex-col gap-4">
      {/* 상단 툴바: 거래소 필터링 컨트롤 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        <div className="text-xs text-slate-500 dark:text-slate-400">
          {isFiltered ? (
            <span>
              선택된 거래소:{' '}
              <span className="font-bold text-indigo-600 dark:text-indigo-400 uppercase">
                {exchangeFilter}
              </span>
              {' '}({filteredRows.length}개 종목 / 전체 {data.rows.length}개)
            </span>
          ) : (
            <span>전체 거래소 기준 ({data.rows.length}개 종목)</span>
          )}
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <label htmlFor="holdings-exchange-select" className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            거래소
          </label>
          <select
            id="holdings-exchange-select"
            value={exchangeFilter}
            onChange={(e) => setExchangeFilter(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 outline-none transition-colors hover:border-slate-300 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
            aria-label="거래소 필터"
          >
            {exchangeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          {isFiltered && (
            <button
              type="button"
              onClick={() => setExchangeFilter('all')}
              className="text-[11px] font-medium text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 underline underline-offset-2 ml-0.5 whitespace-nowrap break-keep"
              title="필터 조건 초기화"
            >
              초기화
            </button>
          )}
        </div>
      </div>

      {/* 요약 KPI 카드 (선택된 거래소 기준 계산) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {summaryCards.map(({ label, value, Icon, bg, extra, extraColor }, index) => (
          <div key={label} className={`${CARD} animate-fade-in-up p-4 flex items-center gap-3`} style={staggerDelay(index)}>
            <div className={`${bg} rounded-lg p-2 text-white shrink-0`}><Icon size={16} /></div>
            <div>
              <p className="text-xl font-bold text-slate-900 dark:text-white leading-none">{value}</p>
              {extra && <p className={`text-xs font-medium mt-0.5 ${extraColor}`}>{extra}</p>}
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* 상세 보유 종목 테이블 */}
      <div className={`${CARD} animate-fade-in-up overflow-hidden`} style={staggerDelay(4)}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">현재 투자중인 자산</h3>
            <p className="text-xs text-slate-400 mt-0.5">supabot 트랜잭션 이력 기준 포지션</p>
          </div>
          {isFiltered && (
            <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-bold text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
              {filteredRows.length}개 종목 표시중
            </span>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left`}>거래소</th>
                <th className={`${TH} text-left`}>종목</th>
                <th className={`${TH} text-right`}>보유수량</th>
                <th className={`${TH} text-right`}>평단가</th>
                <th className={`${TH} text-right`}>보유원가</th>
                <th className={`${TH} text-right`}>현재가</th>
                <th className={`${TH} text-right`}>평가금액</th>
                <th className={`${TH} text-right`}>평가손익</th>
                <th className={`${TH} text-right`}>평가수익률</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {filteredRows.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-slate-400 text-xs">
                    {isFiltered
                      ? `선택한 거래소(${exchangeFilter.toUpperCase()})에 현재 투자중인 자산이 없습니다.`
                      : '현재 투자중인 자산 없음'}
                    {isFiltered && (
                      <div className="mt-2">
                        <button
                          type="button"
                          onClick={() => setExchangeFilter('all')}
                          className="font-semibold text-indigo-600 dark:text-indigo-400 hover:underline"
                        >
                          전체 거래소 보기
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ) : (
                filteredRows.map((row, index) => (
                  <tr
                    key={`${row.exchange}-${row.ticker}-${index}`}
                    className="animate-fade-in hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                    style={staggerDelay(index)}
                  >
                    <td className={TD}><Badge value={row.exchange} label={row.exchange.toUpperCase()} /></td>
                    <td className={`${TD} font-medium text-xs text-slate-800 dark:text-slate-200`}>
                      <div className="flex items-center gap-2">
                        <span>{row.ticker}</span>
                        {row.oversold && <Badge value="warning" label="oversell" />}
                      </div>
                    </td>
                    <td className={`${TD} text-right text-xs text-slate-600 dark:text-slate-400`}>{row.quantity.toFixed(4)}</td>
                    <td className={`${TD} text-right text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(row.avg_price)}</td>
                    <td className={`${TD} text-right text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(row.cost_krw)}</td>
                    <td className={`${TD} text-right text-xs text-slate-600 dark:text-slate-400`}>
                      {row.current_price > 0 ? krwFmt(row.current_price) : '—'}
                    </td>
                    <td className={`${TD} text-right text-xs text-slate-600 dark:text-slate-400`}>
                      {row.current_price > 0 ? krwFmt(row.value_krw) : '—'}
                    </td>
                    <td className={`${TD} text-right text-xs font-medium ${pctColor(row.pnl)}`}>
                      {row.current_price > 0 ? `${row.pnl >= 0 ? '+' : '-'}${krwFmt(Math.abs(row.pnl))}` : '—'}
                    </td>
                    <td className={`${TD} text-right text-xs font-medium ${pctColor(row.roi_pct)}`}>
                      {row.current_price > 0 ? pctFmt(row.roi_pct) : '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
