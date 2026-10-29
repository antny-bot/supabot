import { useEffect, useState } from 'react'
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell
} from 'recharts'
import { AlertTriangle, CalendarClock, Filter, RotateCcw } from 'lucide-react'
import { fetchReportBatches, type BatchesReport } from '../../api/reports'
import type { DateRangeValue } from '../../components/ui/DateRangePicker'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { staggerDelay } from '../../utils/animation'
import { krwFmt, pctColor, PNL_UP_HEX, PNL_DOWN_HEX, CARD, TH, TD } from './ReportsShared'

export default function BatchTimelineSection({ dateRange }: { dateRange: DateRangeValue }) {
  const [data, setData] = useState<BatchesReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedBatch, setSelectedBatch] = useState<number | null>(null)
  const [selectedTicker, setSelectedTicker] = useState<string>('')

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportBatches(dateRange, selectedBatch, selectedTicker)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [dateRange, selectedBatch, selectedTicker])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  const chartData = data.timeline.map((ev) => ({
    name: `#${ev.seq} (${ev.date_fmt.slice(5)})`,
    매매금액: ev.side === 'bid' ? -ev.amount : ev.amount,
    누적실현손익: ev.cum_realized_pnl,
    평균단가: ev.avg_buy_price,
    체결단가: ev.price,
    side: ev.side,
  }))

  return (
    <div className="space-y-4">
      {/* 1. 예수금 부족 알림 배너 */}
      {data.cash_alerts && data.cash_alerts.length > 0 && (
        <div
          className="rounded-xl border border-amber-300 bg-amber-50/90 p-4 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200 animate-fade-in"
          style={staggerDelay(0)}
        >
          <div className="flex items-center gap-2 font-semibold text-sm mb-2">
            <AlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0" />
            <span>계좌 예수금 부족 알림 & 충전 가이드</span>
          </div>
          <ul className="space-y-1 text-xs">
            {data.cash_alerts.map((alert, idx) => (
              <li key={idx} className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                <span>• {alert.details || alert.message}</span>
                <span className="text-[11px] opacity-70 shrink-0">{alert.created_at.slice(0, 16)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 2. 활성 정기 매매(DCA) 스케줄 요약 */}
      {data.dca_schedules && data.dca_schedules.length > 0 && (
        <div className={`${CARD} p-4 animate-fade-in-up`} style={staggerDelay(1)}>
          <div className="flex items-center gap-2 mb-3">
            <CalendarClock size={15} className="text-indigo-500" />
            <h3 className="text-xs font-semibold text-slate-700 dark:text-slate-300">
              가동 중인 정기 매수/매도(DCA) 전략 ({data.dca_schedules.length}건)
            </h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {data.dca_schedules.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => s.group_no && setSelectedBatch(selectedBatch === s.group_no ? null : s.group_no)}
                className={`text-left rounded-lg border p-3 transition-all ${
                  s.group_no && selectedBatch === s.group_no
                    ? 'border-indigo-500 bg-indigo-50/60 dark:bg-indigo-950/40'
                    : 'border-slate-200 dark:border-slate-800 hover:border-indigo-300'
                }`}
              >
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className="text-slate-800 dark:text-slate-200">
                    [{s.exchange.toUpperCase()}] {s.ticker} ({s.side === 'bid' ? '매수' : '매도'})
                  </span>
                  {s.group_no && (
                    <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[11px] font-mono text-indigo-700 dark:bg-indigo-900/60 dark:text-indigo-300">
                      #{s.group_no}
                    </span>
                  )}
                </div>
                <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                  주기: {s.frequency} ({s.exec_time}) · 진행: {s.run_count}{s.max_runs ? `/${s.max_runs}` : ''}회
                </div>
                <div className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                  다음 실행: {s.next_run_fmt}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 3. 배치(#N) 및 종목 필터 바 */}
      <div className={`${CARD} p-3.5 flex flex-wrap items-center gap-3`} style={staggerDelay(2)}>
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300">
          <Filter size={14} />
          <span>시계열 필터:</span>
        </div>

        <select
          aria-label="배치 번호 필터"
          value={selectedBatch ?? ''}
          onChange={(e) => setSelectedBatch(e.target.value ? Number(e.target.value) : null)}
          className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
        >
          <option value="">전체 배치 (#N)</option>
          {data.batches.map((b) => (
            <option key={b.group_no} value={b.group_no}>
              #{b.group_no} — [{b.exchange.toUpperCase()}] {b.ticker} ({b.strategy})
            </option>
          ))}
        </select>

        <select
          aria-label="종목 필터"
          value={selectedTicker}
          onChange={(e) => setSelectedTicker(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
        >
          <option value="">전체 종목</option>
          {data.tickers.map((tk) => (
            <option key={tk} value={tk}>
              {tk}
            </option>
          ))}
        </select>

        {(selectedBatch !== null || selectedTicker !== '') && (
          <button
            type="button"
            onClick={() => {
              setSelectedBatch(null)
              setSelectedTicker('')
            }}
            className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
          >
            <RotateCcw size={12} />
            필터 초기화
          </button>
        )}
      </div>

      {/* 4. 시계열 차트 */}
      {chartData.length > 0 && (
        <div className={`${CARD} p-4 h-72 animate-fade-in-up`} style={staggerDelay(3)}>
          <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">
            시계열 매수·매도 체결 흐름 및 누적 실현손익
          </h4>
          <ResponsiveContainer width="100%" height="88%">
            <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
              <XAxis dataKey="name" stroke="#64748b" fontSize={10} />
              <YAxis stroke="#64748b" fontSize={10} tickFormatter={(v) => krwFmt(v)} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                itemStyle={{ color: '#fff', fontSize: '12px' }}
                formatter={(value: any, name: any) => [`${krwFmt(Number(value))}원`, name]}
              />
              <ReferenceLine y={0} stroke="#64748b" />
              <Bar dataKey="매매금액" radius={[3, 3, 0, 0]}>
                {chartData.map((entry, idx) => (
                  <Cell key={`c-${idx}`} fill={entry.side === 'bid' ? PNL_UP_HEX : PNL_DOWN_HEX} opacity={0.65} />
                ))}
              </Bar>
              <Line type="monotone" dataKey="누적실현손익" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 5. 배치(#N) 요약 테이블 */}
      <div className={`${CARD} overflow-hidden animate-fade-in-up`} style={staggerDelay(4)}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            배치(#N)별 누적 성과 요약 (클릭 시 해당 배치 시계열 필터링)
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left`}>배치</th>
                <th className={`${TH} text-left`}>거래소/종목</th>
                <th className={`${TH} text-left`}>전략</th>
                <th className={`${TH} text-right`}>매수(건/금액)</th>
                <th className={`${TH} text-right`}>매도(건/금액)</th>
                <th className={`${TH} text-right`}>잔여수량 / 평단가</th>
                <th className={`${TH} text-right`}>누적 실현손익</th>
                <th className={`${TH} text-right`}>기간</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.batches.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-400 text-xs">
                    배치 번호(#N)가 기록된 거래 내역이 없습니다.
                  </td>
                </tr>
              ) : (
                data.batches.map((b) => {
                  const active = selectedBatch === b.group_no
                  return (
                    <tr
                      key={b.group_no}
                      onClick={() => setSelectedBatch(active ? null : b.group_no)}
                      className={`cursor-pointer transition-colors ${
                        active
                          ? 'bg-indigo-50/70 dark:bg-indigo-950/40'
                          : 'hover:bg-slate-50 dark:hover:bg-slate-800/40'
                      }`}
                    >
                      <td className={`${TD} font-mono text-xs font-bold text-indigo-600 dark:text-indigo-400`}>
                        #{b.group_no}
                      </td>
                      <td className={`${TD} text-xs font-medium text-slate-700 dark:text-slate-300`}>
                        [{b.exchange.toUpperCase()}] {b.ticker}
                      </td>
                      <td className={`${TD} text-xs text-slate-500`}>{b.strategy}</td>
                      <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>
                        {b.bid_count}건 / {krwFmt(b.bid_krw)}
                      </td>
                      <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>
                        {b.ask_count}건 / {krwFmt(b.ask_krw)}
                      </td>
                      <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>
                        {b.holding_vol} / {krwFmt(Math.round(b.avg_buy_price))}
                      </td>
                      <td className={`${TD} text-right font-mono text-xs font-semibold ${pctColor(b.realized_pnl)}`}>
                        {b.realized_pnl >= 0 ? '+' : ''}{krwFmt(b.realized_pnl)}
                      </td>
                      <td className={`${TD} text-right text-[11px] text-slate-400`}>
                        {b.first_at_fmt} ~ {b.last_at_fmt}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 6. 시간순 체결 타임라인 테이블 */}
      <div className={`${CARD} overflow-hidden animate-fade-in-up`} style={staggerDelay(5)}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            시계열(Time-Series) 매수·매도 체결 내역 ({data.timeline.length}건)
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left`}>순번 / 시각</th>
                <th className={`${TH} text-left`}>배치</th>
                <th className={`${TH} text-left`}>종목 / 전략</th>
                <th className={`${TH} text-left`}>구분</th>
                <th className={`${TH} text-right`}>체결단가 × 수량</th>
                <th className={`${TH} text-right`}>체결금액</th>
                <th className={`${TH} text-right`}>누적보유 / 평단가</th>
                <th className={`${TH} text-right`}>건별 / 누적 실현손익</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.timeline.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-slate-400 text-xs">
                    조건에 해당하는 체결 내역이 없습니다.
                  </td>
                </tr>
              ) : (
                data.timeline.map((ev) => (
                  <tr key={ev.seq} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                    <td className={`${TD} font-mono text-xs text-slate-500`}>
                      #{ev.seq} · {ev.date_fmt}
                    </td>
                    <td className={`${TD} font-mono text-xs text-indigo-600 dark:text-indigo-400`}>
                      {ev.group_no ? `#${ev.group_no}` : '-'}
                    </td>
                    <td className={`${TD} text-xs text-slate-700 dark:text-slate-300`}>
                      [{ev.exchange.toUpperCase()}] {ev.ticker} <span className="text-slate-400">({ev.strategy})</span>
                    </td>
                    <td className={`${TD} text-xs font-semibold ${ev.side === 'bid' ? 'text-rose-500' : 'text-blue-500'}`}>
                      {ev.side === 'bid' ? '매수' : '매도'}
                    </td>
                    <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>
                      {krwFmt(ev.price)} × {ev.volume}
                    </td>
                    <td className={`${TD} text-right font-mono text-xs font-medium text-slate-700 dark:text-slate-300`}>
                      {krwFmt(ev.amount)}
                    </td>
                    <td className={`${TD} text-right font-mono text-xs text-slate-500`}>
                      {ev.holding_vol} / {krwFmt(Math.round(ev.avg_buy_price))}
                    </td>
                    <td className={`${TD} text-right font-mono text-xs`}>
                      {ev.trade_pnl !== null ? (
                        <span className={pctColor(ev.trade_pnl)}>
                          {ev.trade_pnl >= 0 ? '+' : ''}{krwFmt(ev.trade_pnl)}
                        </span>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}{' '}
                      <span className="text-slate-400">
                        (누적 {ev.cum_realized_pnl >= 0 ? '+' : ''}{krwFmt(ev.cum_realized_pnl)})
                      </span>
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
