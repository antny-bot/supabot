import { useState } from 'react'
import { PieChart, TrendingUp, BarChart3, Layers } from 'lucide-react'
import DateRangePicker, { type DateRangeValue } from '../components/ui/DateRangePicker'
import PageHeader from '../components/ui/PageHeader'
import SegmentedControl from '../components/ui/SegmentedControl'
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

// 전체 12개 탭 명세 및 카테고리 매핑
export type ReportCategory = 'all' | 'portfolio' | 'performance' | 'strategy'

interface ReportTabItem {
  id: string
  label: string
  category: 'portfolio' | 'performance' | 'strategy'
}

const ALL_REPORT_TABS: ReportTabItem[] = [
  // 포트폴리오
  { id: 'holdings', label: '현재 투자중', category: 'portfolio' },
  { id: 'allocation', label: '자산 배분', category: 'portfolio' },
  // 수익 & 리스크
  { id: 'pnl', label: '실현 손익', category: 'performance' },
  { id: 'daily', label: '일별 손익', category: 'performance' },
  { id: 'monthly', label: '월별 손익', category: 'performance' },
  { id: 'drawdown', label: 'MDD / 리스크', category: 'performance' },
  // 트레이딩 분석
  { id: 'batches', label: '배치·시계열 추적', category: 'strategy' },
  { id: 'strategy', label: '전략별 분석', category: 'strategy' },
  { id: 'exchange', label: '거래소별 분석', category: 'strategy' },
  { id: 'ranking', label: '수익률 랭킹', category: 'strategy' },
  { id: 'pairs', label: '거래 페어', category: 'strategy' },
  { id: 'winstats', label: '승률/손익비', category: 'strategy' },
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
  const [selectedCategory, setSelectedCategory] = useState<ReportCategory>('all')
  const [activeTab, setActiveTab] = useState('holdings')
  const [dateRange, setDateRange] = useState<DateRangeValue>(DEFAULT_RANGE)
  const [dateFilterOpen, setDateFilterOpen] = useState(false)

  const handleTabClick = (tabId: string) => {
    setActiveTab(tabId)
  }

  const handleCategoryChange = (cat: ReportCategory) => {
    setSelectedCategory(cat)
    if (cat !== 'all') {
      const match = ALL_REPORT_TABS.find((t) => t.category === cat)
      if (match) setActiveTab(match.id)
    }
  }

  return (
    <div className="space-y-4 pb-8">
      <PageHeader {...PAGE_META.reports} />

      {/* 상단: 3대 핵심 허브 빠른 필터 & 기간 선택기 */}
      <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
        <SegmentedControl<ReportCategory>
          options={[
            { id: 'all', label: '전체 리포트', icon: <Layers size={14} /> },
            { id: 'portfolio', label: '포트폴리오', icon: <PieChart size={14} /> },
            { id: 'performance', label: '수익&리스크', icon: <TrendingUp size={14} /> },
            { id: 'strategy', label: '전략분석', icon: <BarChart3 size={14} /> },
          ]}
          value={selectedCategory}
          onChange={handleCategoryChange}
          size="sm"
        />

        {/* 기간 선택기 — 기간 민감 탭에만 표시 */}
        {PERIOD_SENSITIVE_TABS.has(activeTab) && (
          <DateRangePicker
            collapsible
            isOpen={dateFilterOpen}
            onToggle={() => setDateFilterOpen((v) => !v)}
            value={dateRange}
            onChange={setDateRange}
          />
        )}
      </div>

      {/* 탭 칩 스크롤 스트립 (모든 탭이 항상 DOM에 존재하여 테스트 및 접근성 100% 충족) */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none" role="tablist">
        {ALL_REPORT_TABS.map((tab) => {
          const isActive = tab.id === activeTab
          const isDimmed = selectedCategory !== 'all' && tab.category !== selectedCategory

          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              onClick={() => handleTabClick(tab.id)}
              className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
                isActive
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : isDimmed
                  ? 'bg-slate-50 text-slate-400 dark:bg-slate-900 dark:text-slate-600'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
              }`}
            >
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      <div key={activeTab} className="animate-fade-in">
        {activeTab === 'holdings' && <HoldingsSection />}
        {activeTab === 'allocation' && <AllocationSection />}
        {activeTab === 'drawdown' && <DrawdownSection dateRange={dateRange} />}
        {activeTab === 'pnl' && <PnlSection dateRange={dateRange} />}
        {activeTab === 'daily' && <DailySection dateRange={dateRange} />}
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
