import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, DollarSign, Award } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, PieChart, Pie, Cell, LineChart, Line
} from 'recharts'
import {
  fetchReportPnl,
  fetchReportStrategy,
  fetchReportRoiRanking,
  fetchReportMonthly,
  fetchReportPairs,
  fetchReportWinStats,
} from '../api/reports'
import type {
  PnlReport,
  StrategyReport,
  RoiRankingReport,
  MonthlyReport,
  PairsReport,
  WinStatsReport,
} from '../types'
import Badge from '../components/ui/Badge'
import FilterBar from '../components/ui/FilterBar'
import ProgressBar from '../components/ui/ProgressBar'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'

const PERIOD_OPTIONS = [
  { value: '1d',  label: '1일' },
  { value: '7d',  label: '7일' },
  { value: '30d', label: '30일' },
  { value: 'all', label: '전체' },
]

const REPORT_TABS = [
  { id: 'pnl',      label: '실현 손익' },
  { id: 'strategy', label: '전략별 분석' },
  { id: 'ranking',  label: '수익률 랭킹' },
  { id: 'monthly',  label: '월별 손익' },
  { id: 'pairs',    label: '거래 페어' },
  { id: 'winstats', label: '승률/손익비' },
]

function krwFmt(n: number) {
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`
  if (n >= 10_000) return `${(n / 10_000).toFixed(0)}만`
  return n.toLocaleString()
}

function pctFmt(v: number) {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

function pctColor(v: number) {
  if (v > 0) return 'text-emerald-600 dark:text-emerald-400'
  if (v < 0) return 'text-rose-600 dark:text-rose-400'
  return 'text-slate-500 dark:text-slate-400'
}

const CARD = 'bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm'
const TH = 'px-4 py-2.5 font-medium'
const TD = 'px-4 py-2.5'
const MEDALS = ['🥇', '🥈', '🥉']

// ── PnlSection ────────────────────────────────────────────────────────────

function PnlSection({ period }: { period: string }) {
  const [data, setData] = useState<PnlReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportPnl(period)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [period])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  const { summary, rows } = data
  const summaryCards = [
    { label: '총 매수금액', value: krwFmt(summary.total_bid), Icon: TrendingUp, bg: 'bg-blue-500' },
    { label: '총 매도금액', value: krwFmt(summary.total_ask), Icon: TrendingDown, bg: 'bg-rose-500' },
    { label: '총 수수료', value: krwFmt(summary.total_fee), Icon: DollarSign, bg: 'bg-amber-500' },
    { label: '실현 손익', value: krwFmt(Math.abs(summary.total_pnl)), Icon: Award,
      bg: summary.total_pnl >= 0 ? 'bg-emerald-500' : 'bg-rose-500',
      extra: pctFmt(summary.total_bid ? summary.total_pnl / summary.total_bid * 100 : 0),
      extraColor: pctColor(summary.total_pnl),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {summaryCards.map(({ label, value, Icon, bg, extra, extraColor }) => (
          <div key={label} className={`${CARD} p-4 flex items-center gap-3`}>
            <div className={`${bg} rounded-lg p-2 text-white shrink-0`}><Icon size={16} /></div>
            <div>
              <p className="text-xl font-bold text-slate-900 dark:text-white leading-none">{value}</p>
              {extra && <p className={`text-xs font-medium mt-0.5 ${extraColor}`}>{extra}</p>}
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{label}</p>
            </div>
          </div>
        ))}
      </div>

      <div className={`${CARD} overflow-hidden`}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">종목별 손익</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left`}>거래소</th>
                <th className={`${TH} text-left`}>종목</th>
                <th className={`${TH} text-right`}>매수금액</th>
                <th className={`${TH} text-right`}>매도금액</th>
                <th className={`${TH} text-right`}>수수료</th>
                <th className={`${TH} text-right`}>손익</th>
                <th className={`${TH} text-right`}>수익률</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {rows.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-400 text-xs">데이터 없음</td></tr>
              ) : rows.map((r, i) => (
                <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                  <td className={TD}><Badge value={r.exchange} label={r.exchange.toUpperCase()} /></td>
                  <td className={`${TD} font-medium text-xs text-slate-800 dark:text-slate-200`}>{r.ticker}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.bid_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.ask_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-500 dark:text-slate-500`}>{krwFmt(r.fee_amount)}</td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.pnl)}`}>{krwFmt(Math.abs(r.pnl))}</td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.roi_pct)}`}>{pctFmt(r.roi_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ── StrategySection ───────────────────────────────────────────────────────

function StrategySection({ period }: { period: string }) {
  const [data, setData] = useState<StrategyReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportStrategy(period)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [period])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  const chartData = data.rows.map(r => ({
    name: r.strategy,
    value: Math.max(0, r.pnl),
    '손익': r.pnl,
    '거래수': r.trade_count
  }))

  const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#3b82f6', '#8b5cf6']

  return (
    <div className="space-y-4">
      {chartData.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className={`${CARD} p-4 h-64`}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">전략별 손익 비교</h4>
            <ResponsiveContainer width="100%" height="90%">
              <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 5, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
                <XAxis type="number" stroke="#64748b" fontSize={11} tickFormatter={(v) => krwFmt(v)} />
                <YAxis dataKey="name" type="category" stroke="#64748b" fontSize={11} width={80} tickLine={false} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  itemStyle={{ color: '#fff', fontSize: '12px' }}
                  formatter={(value: any) => [`${krwFmt(Number(value))}원`, '손익']}
                />
                <ReferenceLine x={0} stroke="#64748b" />
                <Bar dataKey="손익" radius={[0, 4, 4, 0]}>
                  {chartData.map((entry: any, index: number) => {
                    const color = entry['손익'] >= 0 ? '#10b981' : '#f43f5e';
                    return <Cell key={`cell-${index}`} fill={color} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className={`${CARD} p-4 h-64`}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">전략별 거래 비중 (거래건수)</h4>
            <ResponsiveContainer width="100%" height="90%">
              <PieChart>
                <Pie
                  data={chartData}
                  dataKey="거래수"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={65}
                  label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                  labelLine={false}
                >
                  {chartData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  itemStyle={{ color: '#fff', fontSize: '12px' }}
                  formatter={(value: any) => [`${value}건`, '거래수']}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className={`${CARD} overflow-hidden`}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">전략별 손익</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left`}>전략</th>
                <th className={`${TH} text-right`}>거래수</th>
                <th className={`${TH} text-right`}>매수금액</th>
                <th className={`${TH} text-right`}>매도금액</th>
                <th className={`${TH} text-right`}>수수료</th>
                <th className={`${TH} text-right`}>손익</th>
                <th className={`${TH} text-right`}>수익률</th>
                <th className={`${TH} text-left`} style={{ minWidth: 120 }}>승률</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.rows.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-400 text-xs">데이터 없음</td></tr>
              ) : data.rows.map((r, i) => (
                <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                  <td className={`${TD} text-xs font-medium text-slate-700 dark:text-slate-300`}>{r.strategy}</td>
                  <td className={`${TD} text-right text-xs text-slate-500`}>{r.trade_count.toLocaleString()}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.bid_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.ask_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-500`}>{krwFmt(r.fee_amount)}</td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.pnl)}`}>{krwFmt(Math.abs(r.pnl))}</td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.roi_pct)}`}>{pctFmt(r.roi_pct)}</td>
                  <td className={TD}><ProgressBar value={r.win_rate} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ── RoiRankingSection ─────────────────────────────────────────────────────

function RoiRankingSection({ period }: { period: string }) {
  const [data, setData] = useState<RoiRankingReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportRoiRanking(period)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [period])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  return (
    <div className={`${CARD} overflow-hidden`}>
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">수익률 랭킹</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
              <th className={`${TH} text-center`}>#</th>
              <th className={`${TH} text-left`}>거래소</th>
              <th className={`${TH} text-left`}>종목</th>
              <th className={`${TH} text-right`}>매수금액</th>
              <th className={`${TH} text-right`}>매도금액</th>
              <th className={`${TH} text-right`}>수수료</th>
              <th className={`${TH} text-right`}>손익</th>
              <th className={`${TH} text-right`}>수익률</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {data.rows.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-400 text-xs">데이터 없음</td></tr>
            ) : data.rows.map((r) => (
              <tr key={r.rank} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                <td className={`${TD} text-center text-xs font-bold text-slate-500`}>
                  {r.rank <= 3 ? MEDALS[r.rank - 1] : r.rank}
                </td>
                <td className={TD}><Badge value={r.exchange} label={r.exchange.toUpperCase()} /></td>
                <td className={`${TD} font-medium text-xs text-slate-800 dark:text-slate-200`}>{r.ticker}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.bid_krw)}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.ask_krw)}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-500`}>{krwFmt(r.fee_amount)}</td>
                <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.pnl)}`}>{krwFmt(Math.abs(r.pnl))}</td>
                <td className={`${TD} text-right font-mono text-xs font-bold ${pctColor(r.roi_pct)}`}>{pctFmt(r.roi_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── MonthlySection ────────────────────────────────────────────────────────

function MonthlySection() {
  const [data, setData] = useState<MonthlyReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportMonthly()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  let cumulative = 0;
  const chartData = data.rows.map(r => {
    cumulative += r.pnl;
    return {
      name: r.month,
      '손익': r.pnl,
      '누적손익': cumulative,
      '매수': r.bid_krw,
      '매도': r.ask_krw
    };
  })

  return (
    <div className="space-y-4">
      {chartData.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className={`${CARD} p-4 h-72`}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">월별 실현 손익 추이</h4>
            <ResponsiveContainer width="100%" height="90%">
              <BarChart data={chartData} margin={{ top: 5, right: 5, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
                <XAxis dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} tickFormatter={(v) => krwFmt(v)} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  labelStyle={{ color: '#94a3b8', fontSize: '12px', fontWeight: 'bold' }}
                  itemStyle={{ color: '#fff', fontSize: '12px' }}
                  formatter={(value: any) => [`${krwFmt(Number(value))}원`, '손익']}
                />
                <ReferenceLine y={0} stroke="#64748b" />
                <Bar dataKey="손익" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry: any, index: number) => {
                    const color = entry['손익'] >= 0 ? '#10b981' : '#f43f5e';
                    return <Cell key={`cell-${index}`} fill={color} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className={`${CARD} p-4 h-72`}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">누적 자산 성장 곡선 (Cumulative PnL)</h4>
            <ResponsiveContainer width="100%" height="90%">
              <LineChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
                <XAxis dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} tickFormatter={(v) => krwFmt(v)} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  labelStyle={{ color: '#94a3b8', fontSize: '12px', fontWeight: 'bold' }}
                  itemStyle={{ color: '#fff', fontSize: '12px' }}
                  formatter={(value: any) => [`${krwFmt(Number(value))}원`, '누적 손익']}
                />
                <ReferenceLine y={0} stroke="#64748b" />
                <Line type="monotone" dataKey="누적손익" stroke="#6366f1" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className={`${CARD} overflow-hidden`}>
        <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">월별 손익</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                <th className={`${TH} text-left`}>월</th>
                <th className={`${TH} text-right`}>매수금액</th>
                <th className={`${TH} text-right`}>매도금액</th>
                <th className={`${TH} text-right`}>수수료</th>
                <th className={`${TH} text-right`}>손익</th>
                <th className={`${TH} text-left`} style={{ minWidth: 160 }}>막대</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.rows.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400 text-xs">데이터 없음</td></tr>
              ) : [...data.rows].reverse().map((r) => (
                <tr key={r.month} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                  <td className={`${TD} font-mono text-xs font-medium text-slate-700 dark:text-slate-300`}>{r.month}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.bid_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{krwFmt(r.ask_krw)}</td>
                  <td className={`${TD} text-right font-mono text-xs text-slate-500`}>{krwFmt(r.fee_amount)}</td>
                  <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(r.pnl)}`}>
                    {r.pnl >= 0 ? '+' : '-'}{krwFmt(Math.abs(r.pnl))}
                  </td>
                  <td className={TD}>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-slate-200 dark:bg-slate-700 rounded h-2 overflow-hidden">
                        <div
                          className={`h-full rounded ${r.pnl >= 0 ? 'bg-emerald-500' : 'bg-rose-500'}`}
                          style={{ width: `${r.bar_pct}%` }}
                        />
                      </div>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ── PairsSection ──────────────────────────────────────────────────────────

function PairsSection({ period }: { period: string }) {
  const [data, setData] = useState<PairsReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportPairs(period)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [period])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  return (
    <div className={`${CARD} overflow-hidden`}>
      <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">거래 페어</h3>
        <p className="text-xs text-slate-400 mt-0.5">매수-매도 연결 주문 기준</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
              <th className={`${TH} text-left`}>종목</th>
              <th className={`${TH} text-left`}>거래소</th>
              <th className={`${TH} text-left`}>전략</th>
              <th className={`${TH} text-right`}>매수가</th>
              <th className={`${TH} text-right`}>매도가</th>
              <th className={`${TH} text-right`}>수량</th>
              <th className={`${TH} text-right`}>보유기간</th>
              <th className={`${TH} text-right`}>손익</th>
              <th className={`${TH} text-right`}>수익률</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {data.pairs.length === 0 ? (
              <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-400 text-xs">연결된 거래 페어 없음</td></tr>
            ) : data.pairs.map((p, i) => (
              <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                <td className={`${TD} font-medium text-xs text-slate-800 dark:text-slate-200`}>{p.ticker}</td>
                <td className={TD}><Badge value={p.exchange} label={p.exchange.toUpperCase()} /></td>
                <td className={`${TD} text-xs text-slate-500 dark:text-slate-400`}>{p.strategy}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{p.buy_price.toLocaleString()}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-600 dark:text-slate-400`}>{p.sell_price.toLocaleString()}</td>
                <td className={`${TD} text-right font-mono text-xs text-slate-500`}>{p.volume.toFixed(4)}</td>
                <td className={`${TD} text-right text-xs text-slate-500 dark:text-slate-400`}>{p.hold_time_fmt}</td>
                <td className={`${TD} text-right font-mono text-xs font-medium ${pctColor(p.pnl)}`}>
                  {p.pnl >= 0 ? '+' : '-'}{krwFmt(Math.abs(p.pnl))}
                </td>
                <td className={`${TD} text-right font-mono text-xs font-bold ${pctColor(p.roi_pct)}`}>{pctFmt(p.roi_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── WinStatsSection ───────────────────────────────────────────────────────

function WinStatsSection({ period }: { period: string }) {
  const [data, setData] = useState<WinStatsReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchReportWinStats(period)
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [period])

  if (loading) return <Spinner />
  if (error) return <ErrorBanner message={error} />
  if (!data) return null

  const { stats } = data

  const countCards = [
    { label: '총 페어', value: stats.total_pairs.toLocaleString(), bg: 'bg-indigo-500' },
    { label: '수익 거래', value: stats.win_count.toLocaleString(), bg: 'bg-emerald-500' },
    { label: '손실 거래', value: stats.loss_count.toLocaleString(), bg: 'bg-rose-500' },
    { label: '승률', value: `${stats.win_rate}%`, bg: stats.win_rate >= 50 ? 'bg-emerald-500' : 'bg-amber-500' },
  ]

  const pieData = [
    { name: '수익 거래', value: stats.win_count },
    { name: '손실 거래', value: stats.loss_count },
  ]

  const barData = [
    { name: '평균수익', '수익률': stats.avg_win_pct },
    { name: '평균손실', '수익률': stats.avg_loss_pct },
  ]

  const COLORS = ['#10b981', '#f43f5e']

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {countCards.map(({ label, value, bg }) => (
          <div key={label} className={`${CARD} p-4`}>
            <p className={`text-xs font-medium text-white ${bg} w-fit px-2 py-0.5 rounded-md mb-2`}>{label}</p>
            <p className="text-2xl font-bold text-slate-900 dark:text-white">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-3 gap-3">
        {[
          { label: '평균 수익률 (win)', value: pctFmt(stats.avg_win_pct), color: pctColor(stats.avg_win_pct), desc: '수익 거래 평균' },
          { label: '평균 손실률 (loss)', value: pctFmt(stats.avg_loss_pct), color: pctColor(stats.avg_loss_pct), desc: '손실 거래 평균' },
          { label: 'RR 비율', value: `${stats.rr_ratio}`, color: stats.rr_ratio >= 1 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400', desc: '평균수익 / 평균손실' },
        ].map(({ label, value, color, desc }) => (
          <div key={label} className={`${CARD} p-4`}>
            <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
            <p className={`text-3xl font-bold mt-1 ${color}`}>{value}</p>
            <p className="text-xs text-slate-400 mt-1">{desc}</p>
          </div>
        ))}
      </div>

      {stats.total_pairs > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className={`${CARD} p-4 h-72`}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">거래 승률 비중</h4>
            <ResponsiveContainer width="100%" height="90%">
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={65}
                  label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                  labelLine={false}
                >
                  {pieData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  itemStyle={{ color: '#fff', fontSize: '12px' }}
                  formatter={(value: any) => [`${value}건`, '거래수']}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className={`${CARD} p-4 h-72`}>
            <h4 className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-3">평균 수익/손실 비교</h4>
            <ResponsiveContainer width="100%" height="90%">
              <BarChart data={barData} margin={{ top: 5, right: 5, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.1} />
                <XAxis dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} tickFormatter={(v) => `${v}%`} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px' }}
                  itemStyle={{ color: '#fff', fontSize: '12px' }}
                  formatter={(value: any) => [`${value >= 0 ? '+' : ''}${Number(value).toFixed(2)}%`, '수익률']}
                />
                <ReferenceLine y={0} stroke="#64748b" />
                <Bar dataKey="수익률" radius={4}>
                  {barData.map((entry: any, index: number) => {
                    const color = entry['수익률'] >= 0 ? '#10b981' : '#f43f5e';
                    return <Cell key={`cell-${index}`} fill={color} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Reports (main page) ───────────────────────────────────────────────────

export default function Reports() {
  const [activeTab, setActiveTab] = useState('pnl')
  const [period, setPeriod] = useState('30d')

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">리포트</h1>
        {activeTab !== 'monthly' && (
          <FilterBar options={PERIOD_OPTIONS} value={period} onChange={setPeriod} />
        )}
      </div>

      {/* Tab strip */}
      <div className="flex gap-1.5 flex-wrap border-b border-slate-200 dark:border-slate-800 pb-0">
        {REPORT_TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3.5 py-2 text-sm font-medium rounded-t-lg transition-colors border-b-2 -mb-px ${
              activeTab === tab.id
                ? 'border-indigo-600 text-indigo-600 dark:text-indigo-400 dark:border-indigo-400'
                : 'border-transparent text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content — lazy mount */}
      <div>
        {activeTab === 'pnl'      && <PnlSection period={period} />}
        {activeTab === 'strategy' && <StrategySection period={period} />}
        {activeTab === 'ranking'  && <RoiRankingSection period={period} />}
        {activeTab === 'monthly'  && <MonthlySection />}
        {activeTab === 'pairs'    && <PairsSection period={period} />}
        {activeTab === 'winstats' && <WinStatsSection period={period} />}
      </div>
    </div>
  )
}
