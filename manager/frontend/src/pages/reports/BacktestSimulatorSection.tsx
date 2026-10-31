import { useState } from 'react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend
} from 'recharts'
import {
  Play, Copy, Trash2, Award, TrendingUp, Sliders
} from 'lucide-react'
import { compareBacktestScenarios } from '../../api/reports'
import Spinner from '../../components/ui/Spinner'
import ErrorBanner from '../../components/ui/ErrorBanner'
import { krwFmt, CARD, TH, TD } from './ReportsShared'

const LINE_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#06b6d4', '#94a3b8']

interface ScenarioConfig {
  name: string
  market: string
  rank_start: number
  rank_end: number
  cycle_alloc_mode: string
  cycle_target_krw: number
  sell_proceeds_mode: string
  sell_split_days: number
  exit_rank_buffer: number
  exit_confirm_days: number
  upper_exit_mode: string
  budget_mode: string
  monthly_budget: number
  daily_fixed_budget: number
  initial_carryover: number
}

const DEFAULT_SCENARIOS: ScenarioConfig[] = [
  {
    name: '시나리오 A (표준 TOP 1~10)',
    market: 'KOSPI',
    rank_start: 1,
    rank_end: 10,
    cycle_alloc_mode: 'one_share',
    cycle_target_krw: 300000,
    sell_proceeds_mode: 'keep_cash',
    sell_split_days: 5,
    exit_rank_buffer: 2,
    exit_confirm_days: 2,
    upper_exit_mode: 'sell_on_any_exit',
    budget_mode: 'monthly',
    monthly_budget: 3000000,
    daily_fixed_budget: 150000,
    initial_carryover: 0,
  },
  {
    name: '시나리오 B (초대형주 집중 TOP 1~5)',
    market: 'KOSPI',
    rank_start: 1,
    rank_end: 5,
    cycle_alloc_mode: 'one_share',
    cycle_target_krw: 300000,
    sell_proceeds_mode: 'keep_cash',
    sell_split_days: 5,
    exit_rank_buffer: 2,
    exit_confirm_days: 2,
    upper_exit_mode: 'sell_on_any_exit',
    budget_mode: 'monthly',
    monthly_budget: 3000000,
    daily_fixed_budget: 150000,
    initial_carryover: 0,
  },
  {
    name: '시나리오 C (매도대금 복리 재투자)',
    market: 'KOSPI',
    rank_start: 1,
    rank_end: 10,
    cycle_alloc_mode: 'one_share',
    cycle_target_krw: 300000,
    sell_proceeds_mode: 'recycle_to_budget',
    sell_split_days: 5,
    exit_rank_buffer: 2,
    exit_confirm_days: 2,
    upper_exit_mode: 'sell_on_any_exit',
    budget_mode: 'monthly',
    monthly_budget: 3000000,
    daily_fixed_budget: 150000,
    initial_carryover: 0,
  },
]

export default function BacktestSimulatorSection() {
  const [startDate, setStartDate] = useState('2026-06-01')
  const [endDate, setEndDate] = useState('2026-10-30')
  const [scenarios, setScenarios] = useState<ScenarioConfig[]>(DEFAULT_SCENARIOS)
  const [results, setResults] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedScenarioIdx, setSelectedScenarioIdx] = useState<number>(0)
  const [chartMode, setChartMode] = useState<'return' | 'equity'>('return')

  const handleRunBacktest = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await compareBacktestScenarios({
        start_date: startDate,
        end_date: endDate,
        scenarios: scenarios,
        include_benchmark: true,
      })
      setResults(res?.data || res)
    } catch (e) {
      setError(e instanceof Error ? e.message : '백테스트 실행 실패')
    } finally {
      setLoading(false)
    }
  }

  const handleDuplicateScenario = (idx: number) => {
    if (scenarios.length >= 6) {
      alert('최대 6개 시나리오까지 비교 가능합니다.')
      return
    }
    const target = scenarios[idx]
    const copy = { ...target, name: `${target.name} (복제)` }
    setScenarios([...scenarios, copy])
  }

  const handleRemoveScenario = (idx: number) => {
    if (scenarios.length <= 1) {
      alert('최소 1개 이상의 시나리오가 필요합니다.')
      return
    }
    setScenarios(scenarios.filter((_, i) => i !== idx))
  }

  // 프리셋 로더
  const applyPreset = (presetName: string) => {
    if (presetName === 'ranks') {
      setScenarios([
        { ...DEFAULT_SCENARIOS[0], name: 'TOP 1~5 (초대형주)', rank_start: 1, rank_end: 5 },
        { ...DEFAULT_SCENARIOS[0], name: 'TOP 1~10 (표준)', rank_start: 1, rank_end: 10 },
        { ...DEFAULT_SCENARIOS[0], name: 'TOP 5~10 (차상위 추격)', rank_start: 5, rank_end: 10 },
        { ...DEFAULT_SCENARIOS[0], name: 'TOP 11~20 (중대형 성장주)', rank_start: 11, rank_end: 20 },
      ])
    } else if (presetName === 'alloc') {
      setScenarios([
        { ...DEFAULT_SCENARIOS[0], name: '1주 균등 모으기', cycle_alloc_mode: 'one_share' },
        { ...DEFAULT_SCENARIOS[0], name: '목표금액(30만) 균등', cycle_alloc_mode: 'target_amount', cycle_target_krw: 300000 },
        { ...DEFAULT_SCENARIOS[0], name: '매도대금 복리 재투자', sell_proceeds_mode: 'recycle_to_budget' },
      ])
    } else if (presetName === 'exit') {
      setScenarios([
        { ...DEFAULT_SCENARIOS[0], name: '즉시 매도 (버퍼 0위·1일)', exit_rank_buffer: 0, exit_confirm_days: 1, sell_split_days: 1 },
        { ...DEFAULT_SCENARIOS[0], name: '표준 분할 (버퍼 0위·5일)', exit_rank_buffer: 0, exit_confirm_days: 1, sell_split_days: 5 },
        { ...DEFAULT_SCENARIOS[0], name: '휩쏘 방어 (버퍼 2위·2일확인·5일)', exit_rank_buffer: 2, exit_confirm_days: 2, sell_split_days: 5 },
      ])
    }
  }

  return (
    <div className="space-y-4">
      {/* 1. 기간 설정 및 추천 비교 프리셋 바 */}
      <div className="bg-white dark:bg-slate-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-2">
            <Sliders size={18} className="text-indigo-600 dark:text-indigo-400" />
            <span className="text-sm font-bold text-slate-800 dark:text-slate-100">
              시뮬레이션 기간 및 프리셋:
            </span>
            <div className="flex items-center gap-1.5 text-xs font-mono">
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="rounded border border-slate-300 dark:border-slate-600 p-1 bg-white dark:bg-slate-700"
              />
              <span>~</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="rounded border border-slate-300 dark:border-slate-600 p-1 bg-white dark:bg-slate-700"
              />
            </div>
          </div>

          <button
            onClick={handleRunBacktest}
            disabled={loading}
            className="flex items-center justify-center gap-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-4 py-2 text-xs font-bold shadow-md transition-all"
          >
            {loading ? <Spinner className="py-0" /> : <Play size={14} fill="currentColor" />}
            다중 시나리오 백테스트 실행 (0.5초 고속 엔진)
          </button>
        </div>

        {/* 프리셋 버튼 */}
        <div className="flex items-center gap-2 overflow-x-auto pt-1 text-xs">
          <span className="text-slate-400 shrink-0">추천 프리셋:</span>
          <button
            onClick={() => applyPreset('ranks')}
            className="shrink-0 px-2.5 py-1 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 font-medium"
          >
            🔥 순위 구간 대결 (TOP 1~5 vs 1~10 vs 5~10 vs 11~20)
          </button>
          <button
            onClick={() => applyPreset('alloc')}
            className="shrink-0 px-2.5 py-1 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 font-medium"
          >
            💰 매수 배분 대결 (1주균등 vs 금액균등 vs 매도재투자)
          </button>
          <button
            onClick={() => applyPreset('exit')}
            className="shrink-0 px-2.5 py-1 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-700 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 font-medium"
          >
            🛡️ 이탈 휩쏘 방어 대결 (즉시매도 vs 5일분할 vs 버퍼2위)
          </button>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      {/* 2. 멀티 시나리오 카드 빌더 (최대 6개) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {scenarios.map((sc, idx) => (
          <div
            key={idx}
            className={`rounded-xl border p-3 bg-white dark:bg-slate-800 shadow-sm relative ${
              selectedScenarioIdx === idx ? 'ring-2 ring-indigo-500' : 'border-slate-200 dark:border-slate-700'
            }`}
          >
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-700">
              <div className="flex items-center gap-1.5 font-bold text-xs text-slate-800 dark:text-slate-100">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: LINE_COLORS[idx % LINE_COLORS.length] }} />
                <span>시나리오 #{chr(65 + idx)}</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleDuplicateScenario(idx)}
                  className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                  title="시나리오 복제"
                >
                  <Copy size={13} />
                </button>
                <button
                  onClick={() => handleRemoveScenario(idx)}
                  className="p-1 text-slate-400 hover:text-red-500"
                  title="삭제"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>

            <div className="mt-2 space-y-2 text-xs">
              <div>
                <label className="text-[11px] text-slate-400 block">시나리오 이름</label>
                <input
                  type="text"
                  value={sc.name}
                  onChange={(e) => {
                    const next = [...scenarios]
                    next[idx].name = e.target.value
                    setScenarios(next)
                  }}
                  className="w-full rounded border border-slate-200 dark:border-slate-700 p-1 font-semibold text-slate-800 dark:text-slate-100 bg-slate-50/50 dark:bg-slate-700/50"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[11px] text-slate-400 block">순위 구간</label>
                  <div className="flex items-center gap-1 font-mono">
                    <input
                      type="number"
                      value={sc.rank_start}
                      onChange={(e) => {
                        const next = [...scenarios]
                        next[idx].rank_start = Number(e.target.value)
                        setScenarios(next)
                      }}
                      className="w-12 rounded border border-slate-200 dark:border-slate-700 p-1 text-center bg-slate-50 dark:bg-slate-700"
                    />
                    <span>~</span>
                    <input
                      type="number"
                      value={sc.rank_end}
                      onChange={(e) => {
                        const next = [...scenarios]
                        next[idx].rank_end = Number(e.target.value)
                        setScenarios(next)
                      }}
                      className="w-12 rounded border border-slate-200 dark:border-slate-700 p-1 text-center bg-slate-50 dark:bg-slate-700"
                    />
                    <span className="text-[11px]">위</span>
                  </div>
                </div>

                <div>
                  <label className="text-[11px] text-slate-400 block">매수 배분</label>
                  <select
                    value={sc.cycle_alloc_mode}
                    onChange={(e) => {
                      const next = [...scenarios]
                      next[idx].cycle_alloc_mode = e.target.value
                      setScenarios(next)
                    }}
                    className="w-full rounded border border-slate-200 dark:border-slate-700 p-1 bg-slate-50 dark:bg-slate-700 text-xs"
                  >
                    <option value="one_share">1주 균등</option>
                    <option value="target_amount">금액 균등 (30만)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[11px] text-slate-400 block">매도 대금</label>
                  <select
                    value={sc.sell_proceeds_mode}
                    onChange={(e) => {
                      const next = [...scenarios]
                      next[idx].sell_proceeds_mode = e.target.value
                      setScenarios(next)
                    }}
                    className="w-full rounded border border-slate-200 dark:border-slate-700 p-1 bg-slate-50 dark:bg-slate-700 text-xs"
                  >
                    <option value="keep_cash">예수금 보관</option>
                    <option value="recycle_to_budget">예산 재투입</option>
                  </select>
                </div>

                <div>
                  <label className="text-[11px] text-slate-400 block">분할매도 일수</label>
                  <input
                    type="number"
                    value={sc.sell_split_days}
                    onChange={(e) => {
                      const next = [...scenarios]
                      next[idx].sell_split_days = Number(e.target.value)
                      setScenarios(next)
                    }}
                    className="w-full rounded border border-slate-200 dark:border-slate-700 p-1 bg-slate-50 dark:bg-slate-700 text-xs font-mono"
                  />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 3. 백테스트 결과 리더보드 & 비교 차트 */}
      {results && (
        <div className="space-y-4 animate-fade-in">
          {/* 리더보드 성적표 매트릭스 */}
          <div className={`${CARD} overflow-hidden`}>
            <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Award size={18} className="text-amber-500" />
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">
                  시나리오 성적표 리더보드 (Scenario Leaderboard)
                </h3>
              </div>
              <span className="text-xs text-slate-400">
                벤치마크 ROI: {results.benchmark?.roi}%
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/60">
                    <th className={TH}>순위</th>
                    <th className={TH}>시나리오</th>
                    <th className={TH}>배지</th>
                    <th className={`${TH} text-right`}>누적수익률 (ROI)</th>
                    <th className={`${TH} text-right`}>연환산 (CAGR)</th>
                    <th className={`${TH} text-right`}>최대낙폭 (MDD)</th>
                    <th className={`${TH} text-right`}>칼마 비율</th>
                    <th className={`${TH} text-right`}>벤치마크 대비 (Alpha)</th>
                    <th className={`${TH} text-right`}>총 투입원금</th>
                    <th className={`${TH} text-right`}>최종 평가액</th>
                    <th className={`${TH} text-center`}>상세</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {results.leaderboard.map((lb: any) => {
                    const isUp = lb.roi >= 0
                    const isSelected = selectedScenarioIdx === lb.scenario_index
                    return (
                      <tr
                        key={lb.scenario_index}
                        onClick={() => setSelectedScenarioIdx(lb.scenario_index)}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-indigo-50/70 dark:bg-indigo-950/40 font-semibold' : 'hover:bg-slate-50/50 dark:hover:bg-slate-800/50'
                        }`}
                      >
                        <td className={`${TD} font-bold`}>#{lb.rank}</td>
                        <td className={`${TD} text-slate-800 dark:text-slate-200`}>
                          <div className="flex items-center gap-1.5">
                            <span
                              className="w-2.5 h-2.5 rounded-full shrink-0"
                              style={{ backgroundColor: LINE_COLORS[lb.scenario_index % LINE_COLORS.length] }}
                            />
                            <span>{lb.name}</span>
                          </div>
                        </td>
                        <td className={TD}>
                          <div className="flex gap-1">
                            {lb.badges.map((b: string, bi: number) => (
                              <span key={bi} className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                                {b}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className={`${TD} text-right font-mono font-bold ${isUp ? 'text-red-500' : 'text-blue-500'}`}>
                          {lb.roi > 0 ? `+${lb.roi}` : lb.roi}%
                        </td>
                        <td className={`${TD} text-right font-mono`}>{lb.cagr}%</td>
                        <td className={`${TD} text-right font-mono text-slate-500`}>-{lb.mdd}%</td>
                        <td className={`${TD} text-right font-mono font-semibold`}>{lb.calmar}</td>
                        <td className={`${TD} text-right font-mono font-bold ${lb.alpha >= 0 ? 'text-emerald-600' : 'text-slate-400'}`}>
                          {lb.alpha > 0 ? `+${lb.alpha}` : lb.alpha}%p
                        </td>
                        <td className={`${TD} text-right font-mono text-slate-500`}>{krwFmt(lb.total_invested)}</td>
                        <td className={`${TD} text-right font-mono font-bold`}>{krwFmt(lb.final_equity)}</td>
                        <td className={`${TD} text-center`}>
                          <button className="text-indigo-600 dark:text-indigo-400 hover:underline">
                            보기
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* 다중 시나리오 오버레이 비교 차트 */}
          <div className={`${CARD} p-4`}>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <TrendingUp size={18} className="text-indigo-600 dark:text-indigo-400" />
                <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">
                  다중 시나리오 수익률 & 자산 성장 오버레이 차트
                </h3>
              </div>
              <div className="flex gap-1 text-xs">
                <button
                  onClick={() => setChartMode('return')}
                  className={`px-2.5 py-1 rounded font-semibold ${
                    chartMode === 'return' ? 'bg-indigo-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
                  }`}
                >
                  누적 수익률 (%)
                </button>
                <button
                  onClick={() => setChartMode('equity')}
                  className={`px-2.5 py-1 rounded font-semibold ${
                    chartMode === 'equity' ? 'bg-indigo-600 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
                  }`}
                >
                  총 평가자산 (원)
                </button>
              </div>
            </div>

            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={results.comparison_series}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis
                    tick={{ fontSize: 11 }}
                    domain={chartMode === 'return' ? ['auto', 'auto'] : ['auto', 'auto']}
                    tickFormatter={(v) => (chartMode === 'return' ? `${v}%` : `${Math.round(v / 10000)}만`)}
                  />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px', color: '#fff', fontSize: '12px' }}
                    formatter={(val: any) => (chartMode === 'return' ? `${val}%` : krwFmt(Number(val)))}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px' }} />

                  {scenarios.map((sc, i) => (
                    <Line
                      key={i}
                      type="monotone"
                      dataKey={chartMode === 'return' ? `sc_${i}_return` : `sc_${i}_equity`}
                      name={sc.name}
                      stroke={LINE_COLORS[i % LINE_COLORS.length]}
                      dot={false}
                      strokeWidth={selectedScenarioIdx === i ? 2.5 : 1.5}
                    />
                  ))}
                  <Line
                    type="monotone"
                    dataKey={chartMode === 'return' ? 'benchmark_return' : 'benchmark_equity'}
                    name="벤치마크 (적립식)"
                    stroke="#94a3b8"
                    strokeDasharray="4 4"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* 선택 시나리오 상세 드릴다운 리플레이 */}
          {results.scenario_details && results.scenario_details[selectedScenarioIdx] && (
            <div className={`${CARD} overflow-hidden`}>
              <div className="p-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: LINE_COLORS[selectedScenarioIdx % LINE_COLORS.length] }}
                  />
                  <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">
                    선택 상세: {results.scenario_details[selectedScenarioIdx].name} 종목별 손익 기여도
                  </h3>
                </div>
                <span className="text-xs text-slate-400">
                  완주 회차: {results.scenario_details[selectedScenarioIdx].cycles_completed}회 | 평균 사이클 소요일: {results.scenario_details[selectedScenarioIdx].avg_cycle_days}일
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-800/60">
                      <th className={TH}>종목코드</th>
                      <th className={`${TH} text-right`}>최종보유</th>
                      <th className={`${TH} text-right`}>총 매수원금</th>
                      <th className={`${TH} text-right`}>현재 평가액</th>
                      <th className={`${TH} text-right`}>손익 (P&L)</th>
                      <th className={`${TH} text-right`}>수익률</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {(results.scenario_details[selectedScenarioIdx].stock_contributions || []).map((sc: any, idx: number) => {
                      const isUp = sc.pnl >= 0
                      return (
                        <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                          <td className={`${TD} font-semibold font-mono`}>{sc.code}</td>
                          <td className={`${TD} text-right font-mono`}>{sc.qty}주</td>
                          <td className={`${TD} text-right font-mono text-slate-500`}>{krwFmt(sc.cost)}</td>
                          <td className={`${TD} text-right font-mono font-semibold`}>{krwFmt(sc.value)}</td>
                          <td className={`${TD} text-right font-mono font-bold ${isUp ? 'text-red-500' : 'text-blue-500'}`}>
                            {isUp ? `+${krwFmt(sc.pnl)}` : krwFmt(sc.pnl)}
                          </td>
                          <td className={`${TD} text-right font-mono font-bold ${isUp ? 'text-red-500' : 'text-blue-500'}`}>
                            {sc.return_pct > 0 ? `+${sc.return_pct}` : sc.return_pct}%
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function chr(code: number): string {
  return String.fromCharCode(code)
}
