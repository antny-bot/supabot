import { useState } from 'react'
import DateRangePicker, { type DateRangeValue } from '../components/ui/DateRangePicker'
import ResponsiveTabs from '../components/ui/ResponsiveTabs'
import PageHeader from '../components/ui/PageHeader'
import { PAGE_META } from '../config/pageMeta'

// Lazy loaded section components
import PnlSection from './reports/PnlSection'
import StrategySection from './reports/StrategySection'
import RoiRankingSection from './reports/RoiRankingSection'
import MonthlySection from './reports/MonthlySection'
import HoldingsSection from './reports/HoldingsSection'
import PairsSection from './reports/PairsSection'
import WinStatsSection from './reports/WinStatsSection'

const REPORT_TABS = [
  { id: 'holdings', label: '현재 투자중' },
  { id: 'pnl',      label: '실현 손익' },
  { id: 'monthly',  label: '월별 손익' },
  { id: 'strategy', label: '전략별 분석' },
  { id: 'ranking',  label: '수익률 랭킹' },
  { id: 'pairs',    label: '거래 페어' },
  { id: 'winstats', label: '승률/손익비' },
]

const PERIOD_SENSITIVE_TABS = new Set(['pnl', 'strategy', 'ranking', 'pairs', 'winstats'])
const DEFAULT_RANGE: DateRangeValue = { mode: '30d', from: '', to: '' }

export default function Reports() {
  const [activeTab, setActiveTab] = useState('holdings')
  const [dateRange, setDateRange] = useState<DateRangeValue>(DEFAULT_RANGE)
  const [dateFilterOpen, setDateFilterOpen] = useState(false)

  return (
    <div className="space-y-5">
      <PageHeader {...PAGE_META.reports} />

      <ResponsiveTabs tabs={REPORT_TABS} activeTab={activeTab} onChange={setActiveTab} />

      {/* 기간 선택기 — 탭 아래, 기간 민감 탭에만 표시 */}
      {PERIOD_SENSITIVE_TABS.has(activeTab) && (
        <DateRangePicker collapsible isOpen={dateFilterOpen} onToggle={() => setDateFilterOpen((v) => !v)}
          value={dateRange} onChange={setDateRange} />
      )}

      {/* Tab content — lazy mount */}
      <div key={activeTab} className="animate-fade-in-up">
        {activeTab === 'pnl'      && <PnlSection dateRange={dateRange} />}
        {activeTab === 'strategy' && <StrategySection dateRange={dateRange} />}
        {activeTab === 'ranking'  && <RoiRankingSection dateRange={dateRange} />}
        {activeTab === 'monthly'  && <MonthlySection />}
        {activeTab === 'holdings' && <HoldingsSection />}
        {activeTab === 'pairs'    && <PairsSection dateRange={dateRange} />}
        {activeTab === 'winstats' && <WinStatsSection dateRange={dateRange} />}
      </div>
    </div>
  )
}
