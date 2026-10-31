import { useState } from 'react'
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
import BatchTimelineSection from './reports/BatchTimelineSection'
import TopRotationSection from './reports/TopRotationSection'
import BudgetPlanSection from './reports/BudgetPlanSection'
import BacktestSimulatorSection from './reports/BacktestSimulatorSection'

export const REPORT_TABS = [
  { id: 'holdings', label: '현재 투자중' },
  { id: 'allocation', label: '자산 배분' },
  { id: 'pnl', label: '실현 손익' },
  { id: 'daily', label: '일별 손익' },
  { id: 'monthly', label: '월별 손익' },
  { id: 'drawdown', label: 'MDD / 리스크' },
  { id: 'top_rotation', label: 'TOP 10 포지션·순위' },
  { id: 'budget_plan', label: 'Budget Plan & 감사 원장' },
  { id: 'backtest_compare', label: '다중 시나리오 백테스트' },
  { id: 'batches', label: '배치·시계열 추적' },
  { id: 'strategy', label: '전략별 분석' },
  { id: 'exchange', label: '거래소별 분석' },
  { id: 'ranking', label: '수익률 랭킹' },
  { id: 'pairs', label: '거래 페어' },
  { id: 'winstats', label: '승률/손익비' },
]

const PERIOD_SENSITIVE_TABS = new Set([
  'pnl',
  'daily',
  'batches',
  'strategy',
  'exchange',
  'ranking',
  'pairs',
  'winstats',
  'drawdown',
])

const DEFAULT_RANGE: DateRangeValue = { mode: '30d', from: '', to: '' }

export default function Reports() {
  const [activeTab, setActiveTab] = useState('holdings')
  const [dateRange, setDateRange] = useState<DateRangeValue>(DEFAULT_RANGE)
  const [dateFilterOpen, setDateFilterOpen] = useState(false)

  return (
    <div className="space-y-4 pb-8">
      <PageHeader {...PAGE_META.reports} />

      {/* 시트 형태 반응형 서브메뉴 탭 */}
      <ResponsiveTabs tabs={REPORT_TABS} activeTab={activeTab} onChange={setActiveTab} />

      {/* 기간 선택기 — 기간 민감 탭에만 표시 */}
      {PERIOD_SENSITIVE_TABS.has(activeTab) && (
        <div className="flex justify-end">
          <DateRangePicker
            collapsible
            isOpen={dateFilterOpen}
            onToggle={() => setDateFilterOpen((v) => !v)}
            value={dateRange}
            onChange={setDateRange}
          />
        </div>
      )}

      {/* Tab content */}
      <div key={activeTab} className="animate-fade-in">
        {activeTab === 'holdings' && <HoldingsSection />}
        {activeTab === 'allocation' && <AllocationSection />}
        {activeTab === 'drawdown' && <DrawdownSection dateRange={dateRange} />}
        {activeTab === 'pnl' && <PnlSection dateRange={dateRange} />}
        {activeTab === 'daily' && <DailySection dateRange={dateRange} />}
        {activeTab === 'top_rotation' && <TopRotationSection />}
        {activeTab === 'budget_plan' && <BudgetPlanSection />}
        {activeTab === 'backtest_compare' && <BacktestSimulatorSection />}
        {activeTab === 'batches' && <BatchTimelineSection dateRange={dateRange} />}
        {activeTab === 'strategy' && <StrategySection dateRange={dateRange} />}
        {activeTab === 'exchange' && <ExchangeSection dateRange={dateRange} />}
        {activeTab === 'ranking' && <RoiRankingSection dateRange={dateRange} />}
        {activeTab === 'monthly' && <MonthlySection />}
        {activeTab === 'pairs' && <PairsSection dateRange={dateRange} />}
        {activeTab === 'winstats' && <WinStatsSection dateRange={dateRange} />}
      </div>
    </div>
  )
}
