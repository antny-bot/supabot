import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
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

export const REPORT_TABS = [
  { id: 'holdings', label: '현재 투자중' },
  { id: 'allocation', label: '자산 배분' },
  { id: 'pnl', label: '실현 손익' },
  { id: 'daily', label: '일별 손익' },
  { id: 'monthly', label: '월별 손익' },
  { id: 'drawdown', label: 'MDD / 리스크' },
  { id: 'strategy', label: '전략별 분석' },
  { id: 'exchange', label: '거래소별 분석' },
  { id: 'ranking', label: '수익률 랭킹' },
  { id: 'pairs', label: '거래 페어' },
  { id: 'winstats', label: '승률/손익비' },
  { id: 'backtest_compare', label: '다중 시나리오 백테스트' },
]

const PERIOD_SENSITIVE_TABS = new Set([
  'pnl',
  'daily',
  'strategy',
  'exchange',
  'ranking',
  'pairs',
  'winstats',
  'drawdown',
])

const DEFAULT_RANGE: DateRangeValue = { mode: '30d', from: '', to: '' }

export default function Reports() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabFromUrl = searchParams.get('tab')

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

  const [activeTab, setActiveTab] = useState(() => {
    if (tabFromUrl && REPORT_TABS.some((t) => t.id === tabFromUrl)) {
      return tabFromUrl
    }
    return 'holdings'
  })
  const [dateRange, setDateRange] = useState<DateRangeValue>(DEFAULT_RANGE)
  const [dateFilterOpen, setDateFilterOpen] = useState(false)

  useEffect(() => {
    if (tabFromUrl && REPORT_TABS.some((t) => t.id === tabFromUrl) && tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl)
    }
  }, [tabFromUrl, activeTab])

  const handleTabChange = (newTab: string) => {
    setActiveTab(newTab)
    setSearchParams({ tab: newTab }, { replace: true })
  }

  return (
    <div className="space-y-4 pb-8">
      <PageHeader {...PAGE_META.reports} />

      {/* 시트 형태 반응형 서브메뉴 탭 */}
      <ResponsiveTabs tabs={REPORT_TABS} activeTab={activeTab} onChange={handleTabChange} />

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
        {activeTab === 'backtest_compare' && <BacktestSimulatorSection />}
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
