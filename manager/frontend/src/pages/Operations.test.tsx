import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../contexts/ToastContext'
import Operations from './Operations'

const mockTemplates = [
  {
    id: 1,
    name: '업비트 비트코인 DCA',
    exchange: 'upbit',
    ticker: 'KRW-BTC',
    strategy_type: 'dca',
    budget: 1000000,
    interval_minutes: 60,
    params: {
      strategy_status: 'active',
      schedule_enabled: true,
      amount_type: 'amount',
    },
  },
  {
    id: 2,
    name: '업비트 이더리움 DCA (정지)',
    exchange: 'upbit',
    ticker: 'KRW-ETH',
    strategy_type: 'dca',
    budget: 500000,
    interval_minutes: 60,
    params: {
      strategy_status: 'paused',
      schedule_enabled: false,
      amount_type: 'amount',
    },
  },
  {
    id: 3,
    name: '한투 삼성전자 RSI',
    exchange: 'kis',
    ticker: '005930',
    strategy_type: 'rsi',
    budget: 2000000,
    interval_minutes: 30,
    params: {
      strategy_status: 'active',
      schedule_enabled: true,
    },
  },
  {
    id: 4,
    name: '보관된 빗썸 리플 전략',
    exchange: 'bithumb',
    ticker: 'KRW-XRP',
    strategy_type: 'grid',
    budget: 300000,
    interval_minutes: 10,
    params: {
      is_archived: true,
    },
  },
  {
    id: 5,
    name: '한투 코스피 TOP 10 순환매',
    exchange: 'kis',
    ticker: 'TOP10',
    strategy_type: 'dca',
    budget: 100000,
    interval_minutes: 1440,
    params: {
      strategy_status: 'active',
      schedule_enabled: true,
      universe_type: 'market_top_n',
      progression_mode: 'top_n_rotation',
      top_n: 10,
      current_rank_index: 2,
    },
  },
]

vi.mock('../api/templates', () => ({
  fetchTemplates: vi.fn().mockImplementation(() => Promise.resolve(mockTemplates)),
  toggleTemplateHolding: vi.fn().mockResolvedValue({ ok: true }),
  executeTemplate: vi.fn().mockResolvedValue({ ok: true, message: '실행 완료' }),
  stopTemplate: vi.fn().mockResolvedValue({ ok: true }),
  manualTopupTemplate: vi.fn().mockResolvedValue({ ok: true }),
  archiveTemplate: vi.fn().mockResolvedValue({ ok: true }),
  restoreTemplate: vi.fn().mockResolvedValue({ ok: true }),
  deleteTemplate: vi.fn().mockResolvedValue({ ok: true }),
  duplicateTemplate: vi.fn().mockResolvedValue({ ok: true }),
}))

vi.mock('../api/stockCache', () => ({
  fetchStockCache: vi.fn().mockResolvedValue([]),
}))

vi.mock('../api/reports', () => ({
  fetchTopRotationReport: vi.fn().mockResolvedValue({
    template: {
      id: 5,
      name: '한투 코스피 TOP 10 순환매',
      exchange: 'kis',
      budget: 100000,
      interval_minutes: 1440,
      params: {
        strategy_status: 'active',
        schedule_enabled: true,
        top_n: 10,
        current_rank_index: 2,
        carryover_budget: 15000,
      },
    },
    holdings_status: [],
    batch_budget_logs: [],
    orders: [],
    trades: [],
    master_top: [],
    cycle_pipeline: {
      cycle_no: 1,
      rank_start: 1,
      rank_end: 10,
      total_targets: 10,
      bought_count: 1,
      progress_pct: 10,
      pipeline: [
        {
          rank: 1,
          code: '005930',
          name: '삼성전자',
          price: 75000,
          target_qty: 1,
          cost: 75000,
          status: 'bought',
          is_affordable: true,
        },
        {
          rank: 2,
          code: '000660',
          name: 'SK하이닉스',
          price: 180000,
          target_qty: 1,
          cost: 180000,
          status: 'next',
          is_affordable: false,
        },
      ],
      next_target: null,
      affordable_targets: [],
    },
    daily_execution_flow: [],
    daily_snapshots: [
      {
        date: '2026-10-15',
        group_no: 101,
        cycle_no: 1,
        total_price: 255000,
        avg_price: 127500,
        spent_krw: 75000,
        carryover_budget: 25000,
        items: [
          { rank: 1, code: '005930', name: '삼성전자', price: 75000, is_bought: true },
          { rank: 2, code: '000660', name: 'SK하이닉스', price: 180000, is_bought: false },
        ],
      },
      {
        date: '2026-11-10',
        group_no: 102,
        cycle_no: 1,
        total_price: 262000,
        avg_price: 131000,
        spent_krw: 80000,
        carryover_budget: 20000,
        items: [
          { rank: 1, code: '005930', name: '삼성전자', price: 78000, is_bought: true },
          { rank: 2, code: '000660', name: 'SK하이닉스', price: 184000, is_bought: false },
        ],
      },
    ],
  }),
  fetchBudgetPlanSummary: vi.fn().mockResolvedValue(null),
  fetchBudgetAuditLedger: vi.fn().mockResolvedValue([]),
  fetchBatchTimeline: vi.fn().mockResolvedValue([]),
}))

vi.mock('../api/orders', () => ({
  fetchOrders: vi.fn().mockResolvedValue({ orders: [], total: 0 }),
}))

describe('Operations strategy filtering & localStorage persistence', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
    window.localStorage.clear()
  })

  it('renders exchange dropdown and All | On | Off filters, displaying all active strategies by default', async () => {
    render(
      <MemoryRouter>
        <ToastProvider>
          <Operations />
        </ToastProvider>
      </MemoryRouter>,
    )

    const exchangeSelect = await screen.findByLabelText('거래소 필터')
    expect(exchangeSelect).toBeInTheDocument()
    expect((exchangeSelect as HTMLSelectElement).value).toBe('all')

    expect(screen.getByRole('tab', { name: '모두' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'On' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Off' })).toBeInTheDocument()

    // 3 active strategies rendered
    expect(await screen.findByText('업비트 비트코인 DCA')).toBeInTheDocument()
    expect(screen.getByText('업비트 이더리움 DCA (정지)')).toBeInTheDocument()
    expect(screen.getByText('한투 삼성전자 RSI')).toBeInTheDocument()
    // archived strategy should not be in active tab
    expect(screen.queryByText('보관된 빗썸 리플 전략')).not.toBeInTheDocument()
  })

  it('filters strategies by exchange and persists to localStorage', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <ToastProvider>
          <Operations />
        </ToastProvider>
      </MemoryRouter>,
    )

    const exchangeSelect = await screen.findByLabelText('거래소 필터')
    await user.selectOptions(exchangeSelect, 'kis')

    // Only KIS strategy visible
    expect(screen.getByText('한투 삼성전자 RSI')).toBeInTheDocument()
    expect(screen.queryByText('업비트 비트코인 DCA')).not.toBeInTheDocument()
    expect(screen.queryByText('업비트 이더리움 DCA (정지)')).not.toBeInTheDocument()

    // Saved in localStorage
    expect(JSON.parse(window.localStorage.getItem('sbm_operations_exchange_filter') || '""')).toBe('kis')
  })

  it('filters strategies by On / Off status and persists to localStorage', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <ToastProvider>
          <Operations />
        </ToastProvider>
      </MemoryRouter>,
    )

    await screen.findByText('업비트 비트코인 DCA')

    // Click 'On' tab
    const onTab = screen.getByRole('tab', { name: 'On' })
    await user.click(onTab)

    // Only active strategies (ID 1, 3) should appear, paused (ID 2) hidden
    expect(screen.getByText('업비트 비트코인 DCA')).toBeInTheDocument()
    expect(screen.getByText('한투 삼성전자 RSI')).toBeInTheDocument()
    expect(screen.queryByText('업비트 이더리움 DCA (정지)')).not.toBeInTheDocument()
    expect(JSON.parse(window.localStorage.getItem('sbm_operations_status_filter') || '""')).toBe('on')

    // Click 'Off' tab
    const offTab = screen.getByRole('tab', { name: 'Off' })
    await user.click(offTab)

    // Only paused strategy (ID 2) should appear
    expect(screen.queryByText('업비트 비트코인 DCA')).not.toBeInTheDocument()
    expect(screen.queryByText('한투 삼성전자 RSI')).not.toBeInTheDocument()
    expect(screen.getByText('업비트 이더리움 DCA (정지)')).toBeInTheDocument()
    expect(JSON.parse(window.localStorage.getItem('sbm_operations_status_filter') || '""')).toBe('off')
  })

  it('restores filters from localStorage on page open', async () => {
    // Pre-populate localStorage
    window.localStorage.setItem('sbm_operations_exchange_filter', JSON.stringify('upbit'))
    window.localStorage.setItem('sbm_operations_status_filter', JSON.stringify('on'))

    render(
      <MemoryRouter>
        <ToastProvider>
          <Operations />
        </ToastProvider>
      </MemoryRouter>,
    )

    await screen.findByText('업비트 비트코인 DCA')

    const exchangeSelect = screen.getByLabelText('거래소 필터') as HTMLSelectElement
    expect(exchangeSelect.value).toBe('upbit')

    const onTab = screen.getByRole('tab', { name: 'On' })
    expect(onTab).toHaveAttribute('aria-selected', 'true')

    // Only upbit + ON strategy (ID 1) visible
    expect(screen.getByText('업비트 비트코인 DCA')).toBeInTheDocument()
    expect(screen.queryByText('업비트 이더리움 DCA (정지)')).not.toBeInTheDocument()
    expect(screen.queryByText('한투 삼성전자 RSI')).not.toBeInTheDocument()
  })

  it('resets filters when clicking the reset button', async () => {
    const user = userEvent.setup()
    window.localStorage.setItem('sbm_operations_exchange_filter', JSON.stringify('kis'))

    render(
      <MemoryRouter>
        <ToastProvider>
          <Operations />
        </ToastProvider>
      </MemoryRouter>,
    )

    await screen.findByText('한투 삼성전자 RSI')
    expect(screen.queryByText('업비트 비트코인 DCA')).not.toBeInTheDocument()

    // Click reset button
    const resetBtn = screen.getByRole('button', { name: '초기화' })
    await user.click(resetBtn)

    // Both exchange and status reset to all
    const exchangeSelect = screen.getByLabelText('거래소 필터') as HTMLSelectElement
    expect(exchangeSelect.value).toBe('all')
    expect(screen.getByText('업비트 비트코인 DCA')).toBeInTheDocument()
    expect(screen.getByText('업비트 이더리움 DCA (정지)')).toBeInTheDocument()
    expect(screen.getByText('한투 삼성전자 RSI')).toBeInTheDocument()

    expect(JSON.parse(window.localStorage.getItem('sbm_operations_exchange_filter') || '""')).toBe('all')
    expect(JSON.parse(window.localStorage.getItem('sbm_operations_status_filter') || '""')).toBe('all')
  })

  it('opens strategy detail view on card click without duplicate batches tab and shows daily snapshot bar charts', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <ToastProvider>
          <Operations />
        </ToastProvider>
      </MemoryRouter>,
    )

    const topCardTitle = await screen.findByText('한투 코스피 TOP 10 순환매')
    await user.click(topCardTitle)

    // Duplicate '전략 배치 주문 묶음' tab is removed; instead there is a quick link button to Orders batches
    expect(screen.queryByRole('tab', { name: '전략 배치 주문 묶음' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /배치 주문 묶음/ })).toBeInTheDocument()

    // Switch to '일단위 스냅샷 (차트)' tab (ResponsiveTabs renders mobile + desktop tabs)
    const snapshotTabs = await screen.findAllByRole('tab', { name: '일단위 스냅샷 (차트)' })
    await user.click(snapshotTabs[0])

    // Verify period buttons (30일, 3개월, 6개월, 1년) and recording start date
    expect(await screen.findByText(/기록 시작일:\s*2026-10-15/)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '30일' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '3개월' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '6개월' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '1년' })).toBeInTheDocument()

    // Verify 1~10 rank bar chart section renders
    expect(screen.getByText(/순위별 종목 금액 Bar 차트/)).toBeInTheDocument()
  })
})
