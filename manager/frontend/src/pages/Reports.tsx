import { useState, useEffect, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { Filter } from 'lucide-react'
import DateRangePicker, { type DateRangeValue } from '../components/ui/DateRangePicker'
import PageHeader from '../components/ui/PageHeader'
import ResponsiveTabs from '../components/ui/ResponsiveTabs'
import { PAGE_META } from '../config/pageMeta'

// Section components
import PnlSection from './reports/PnlSection'
import StrategySection from './reports/StrategySection'
import ExchangeSection from './reports/ExchangeSection'
import DailySection from './reports/DailySection'
import RoiRankingSection from './reports/RoiRankingSection'
import MonthlySection from './reports/MonthlySection'
import HoldingsSection from './reports/HoldingsSection'
import PairsSection from './reports/PairsSection'
import WinStatsSection from './reports/WinStatsSection'
import DrawdownSection from './reports/DrawdownSection'
import AllocationSection from './reports/AllocationSection'
import BacktestSimulatorSection from './reports/BacktestSimulatorSection'

// 메인 5개 핵심 카테고리 탭 (기존 12개에서 통합 정리)
export const REPORT_TABS = [
  { id: 'holdings', label: '현재 투자중' },
  { id: 'pnl', label: '실현 손익' },
  { id: 'performance', label: '다각도 분석' },
  { id: 'risk_stats', label: '승률 / 리스크' },
  { id: 'backtest_compare', label: '시뮬레이터' },
]

// 기간 선택기가 필요한 탭 목록
const PERIOD_SENSITIVE_TABS = new Set([
  'pnl',
  'performance',
  'risk_stats',
  'daily',
  'monthly',
  'strategy',
  'exchange',
  'ranking',
  'pairs',
  'winstats',
  'drawdown',
])

// 레거시 탭 ID 호환 매핑 테이블
const TAB_MAPPING: Record<string, { main: string; sub: string }> = {
  holdings: { main: 'holdings', sub: 'holdings' },
  allocation: { main: 'holdings', sub: 'allocation' },
  portfolio: { main: 'holdings', sub: 'holdings' },

  pnl: { main: 'pnl', sub: 'pnl' },
  daily: { main: 'pnl', sub: 'daily' },
  monthly: { main: 'pnl', sub: 'monthly' },

  performance: { main: 'performance', sub: 'strategy' },
  strategy: { main: 'performance', sub: 'strategy' },
  exchange: { main: 'performance', sub: 'exchange' },
  ranking: { main: 'performance', sub: 'ranking' },

  risk_stats: { main: 'risk_stats', sub: 'win_and_pairs' },
  winstats: { main: 'risk_stats', sub: 'win_and_pairs' },
  pairs: { main: 'risk_stats', sub: 'win_and_pairs' },
  drawdown: { main: 'risk_stats', sub: 'drawdown' },

  backtest_compare: { main: 'backtest_compare', sub: 'backtest_compare' },
}

const EXCHANGE_OPTIONS = [
  { value: 'all', label: '전체 거래소' },
  { value: 'upbit', label: 'Upbit' },
  { value: 'bithumb', label: 'Bithumb' },
  { value: 'kis', label: 'KIS' },
  { value: 'toss', label: 'TOSS' },
]

const DEFAULT_RANGE: DateRangeValue = { mode: '30d', from: '', to: '' }

export default function Reports() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabFromUrl = searchParams.get('tab')
  const subFromUrl = searchParams.get('sub')

  // 기존 운용성 탭 접근 시 전략 운용 페이지로 자동 안내/리다이렉트
  useEffect(() => {
    if (tabFromUrl === 'top_rotation') {
      navigate('/operations?tab=rotation', { replace: true })
    } else if (tabFromUrl === 'budget_plan') {
      navigate('/operations?tab=ledger', { replace: true })
    } else if (tabFromUrl === 'batches') {
      navigate('/orders?tab=batches', { replace: true })
    }
  }, [tabFromUrl, navigate])

  // URL 파라미터 기반 초기 탭 및 서브탭 결정
  const initialResolved = useMemo(() => {
    if (tabFromUrl && TAB_MAPPING[tabFromUrl]) {
      return {
        main: TAB_MAPPING[tabFromUrl].main,
        sub: subFromUrl || TAB_MAPPING[tabFromUrl].sub,
      }
    }
    return { main: 'holdings', sub: 'holdings' }
  }, [tabFromUrl, subFromUrl])

  const [activeTab, setActiveTab] = useState<string>(initialResolved.main)
  const [subTab, setSubTab] = useState<string>(initialResolved.sub)
  const [selectedExchange, setSelectedExchange] = useState<string>('all')
  const [dateRange, setDateRange] = useState<DateRangeValue>(DEFAULT_RANGE)
  const [dateFilterOpen, setDateFilterOpen] = useState(false)

  // URL 변경 시 동기화
  useEffect(() => {
    if (tabFromUrl && TAB_MAPPING[tabFromUrl]) {
      const target = TAB_MAPPING[tabFromUrl]
      if (activeTab !== target.main) {
        setActiveTab(target.main)
      }
      const targetSub = subFromUrl || target.sub
      if (subTab !== targetSub) {
        setSubTab(targetSub)
      }
    }
  }, [tabFromUrl, subFromUrl, activeTab, subTab])

  const handleMainTabChange = (newMainTab: string) => {
    setActiveTab(newMainTab)
    let defaultSub = 'holdings'
    if (newMainTab === 'pnl') defaultSub = 'pnl'
    else if (newMainTab === 'performance') defaultSub = 'strategy'
    else if (newMainTab === 'risk_stats') defaultSub = 'win_and_pairs'
    else if (newMainTab === 'backtest_compare') defaultSub = 'backtest_compare'

    setSubTab(defaultSub)
    setSearchParams({ tab: newMainTab, sub: defaultSub }, { replace: true })
  }

  const handleSubTabChange = (newSubTab: string) => {
    setSubTab(newSubTab)
    setSearchParams({ tab: activeTab, sub: newSubTab }, { replace: true })
  }

  // 거래소 필터 표시 여부 (백테스트 제외)
  const showExchangeFilter = activeTab !== 'backtest_compare'
  // 기간 선택기 표시 여부
  const showDatePicker = PERIOD_SENSITIVE_TABS.has(activeTab) || PERIOD_SENSITIVE_TABS.has(subTab)

  return (
    <div className="space-y-4 pb-8">
      <PageHeader {...PAGE_META.reports} />

      {/* 시트 형태 반응형 5개 핵심 카테고리 탭 */}
      <ResponsiveTabs tabs={REPORT_TABS} activeTab={activeTab} onChange={handleMainTabChange} />

      {/* 상단 툴바: 서브 세그먼트 전환 및 전역 필터 (거래소, 기간) */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-white dark:bg-slate-900/60 p-3 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
        {/* 서브 뷰 세그먼트 칩 */}
        <div className="flex flex-wrap items-center gap-1.5">
          {activeTab === 'holdings' && (
            <>
              {[
                { id: 'holdings', label: '보유 종목 상세' },
                { id: 'allocation', label: '자산 배분 비중' },
              ].map((chip) => (
                <button
                  key={chip.id}
                  onClick={() => handleSubTabChange(chip.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    subTab === chip.id
                      ? 'bg-primary-600 text-white shadow-sm font-semibold'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  {chip.label}
                </button>
              ))}
            </>
          )}

          {activeTab === 'pnl' && (
            <>
              {[
                { id: 'pnl', label: '종목별 실현손익' },
                { id: 'daily', label: '일별 손익 추이' },
                { id: 'monthly', label: '월별 손익 추이' },
              ].map((chip) => (
                <button
                  key={chip.id}
                  onClick={() => handleSubTabChange(chip.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    subTab === chip.id
                      ? 'bg-primary-600 text-white shadow-sm font-semibold'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  {chip.label}
                </button>
              ))}
            </>
          )}

          {activeTab === 'performance' && (
            <>
              {[
                { id: 'strategy', label: '전략별 성과' },
                { id: 'exchange', label: '거래소별 성과' },
                { id: 'ranking', label: '수익률 랭킹 TOP' },
              ].map((chip) => (
                <button
                  key={chip.id}
                  onClick={() => handleSubTabChange(chip.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    subTab === chip.id
                      ? 'bg-primary-600 text-white shadow-sm font-semibold'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  {chip.label}
                </button>
              ))}
            </>
          )}

          {activeTab === 'risk_stats' && (
            <>
              {[
                { id: 'win_and_pairs', label: '승률 & 거래 페어' },
                { id: 'drawdown', label: 'MDD / 리스크' },
              ].map((chip) => (
                <button
                  key={chip.id}
                  onClick={() => handleSubTabChange(chip.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    subTab === chip.id
                      ? 'bg-primary-600 text-white shadow-sm font-semibold'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
                  }`}
                >
                  {chip.label}
                </button>
              ))}
            </>
          )}

          {activeTab === 'backtest_compare' && (
            <span className="text-xs font-medium text-slate-500 dark:text-slate-400 break-keep">
              다중 시나리오 백테스트 비교 시뮬레이터
            </span>
          )}
        </div>

        {/* 우측 전역 필터: 거래소 선택기 + 기간 선택기 */}
        <div className="flex flex-wrap items-center gap-2 self-end md:self-auto">
          {showExchangeFilter && (
            <div className="flex items-center gap-1.5">
              <Filter size={13} className="text-slate-400 shrink-0" />
              <select
                aria-label="보고서 거래소 필터"
                value={selectedExchange}
                onChange={(e) => setSelectedExchange(e.target.value)}
                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
              >
                {EXCHANGE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          )}

          {showDatePicker && (
            <DateRangePicker
              collapsible
              isOpen={dateFilterOpen}
              onToggle={() => setDateFilterOpen((v) => !v)}
              value={dateRange}
              onChange={setDateRange}
            />
          )}
        </div>
      </div>

      {/* 메인 탭 콘텐츠 렌더링 */}
      <div key={`${activeTab}-${subTab}`} className="animate-fade-in space-y-4">
        {/* 1. 현재 투자중 (포트폴리오) */}
        {activeTab === 'holdings' && (
          <>
            {subTab === 'holdings' && <HoldingsSection exchange={selectedExchange} />}
            {subTab === 'allocation' && <AllocationSection />}
          </>
        )}

        {/* 2. 실현 손익 분석 */}
        {activeTab === 'pnl' && (
          <>
            {subTab === 'pnl' && <PnlSection dateRange={dateRange} exchange={selectedExchange} />}
            {subTab === 'daily' && <DailySection dateRange={dateRange} exchange={selectedExchange} />}
            {subTab === 'monthly' && <MonthlySection dateRange={dateRange} exchange={selectedExchange} />}
          </>
        )}

        {/* 3. 다각도 성과 분석 */}
        {activeTab === 'performance' && (
          <>
            {subTab === 'strategy' && <StrategySection dateRange={dateRange} exchange={selectedExchange} />}
            {subTab === 'exchange' && <ExchangeSection dateRange={dateRange} />}
            {subTab === 'ranking' && <RoiRankingSection dateRange={dateRange} exchange={selectedExchange} />}
          </>
        )}

        {/* 4. 승률 및 리스크 분석 */}
        {activeTab === 'risk_stats' && (
          <>
            {subTab === 'win_and_pairs' && (
              <div className="space-y-6">
                <WinStatsSection dateRange={dateRange} exchange={selectedExchange} />
                <PairsSection dateRange={dateRange} exchange={selectedExchange} />
              </div>
            )}
            {subTab === 'drawdown' && <DrawdownSection dateRange={dateRange} exchange={selectedExchange} />}
          </>
        )}

        {/* 5. 백테스트 시뮬레이터 */}
        {activeTab === 'backtest_compare' && <BacktestSimulatorSection />}
      </div>
    </div>
  )
}
