import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import HoldingsSection from './HoldingsSection'

const mockHoldingsData = {
  summary: {
    total_cost: 3500000,
    total_value: 3800000,
    total_pnl: 300000,
    total_roi_pct: 8.57,
    asset_count: 3,
    oversold_count: 0,
  },
  rows: [
    {
      exchange: 'upbit',
      ticker: 'KRW-BTC',
      quantity: 0.05,
      avg_price: 40000000,
      cost_krw: 2000000,
      current_price: 44000000,
      value_krw: 2200000,
      pnl: 200000,
      roi_pct: 10.0,
      oversold: false,
    },
    {
      exchange: 'kis',
      ticker: '005930',
      quantity: 15,
      avg_price: 66666.67,
      cost_krw: 1000000,
      current_price: 700000,
      value_krw: 1050000,
      pnl: 50000,
      roi_pct: 5.0,
      oversold: false,
    },
    {
      exchange: 'bithumb',
      ticker: 'KRW-XRP',
      quantity: 1000,
      avg_price: 500,
      cost_krw: 500000,
      current_price: 550,
      value_krw: 550000,
      pnl: 50000,
      roi_pct: 10.0,
      oversold: false,
    },
  ],
}

vi.mock('../../api/reports', () => ({
  fetchReportHoldings: vi.fn().mockImplementation(() => Promise.resolve(mockHoldingsData)),
}))

describe('HoldingsSection exchange filtering & localStorage persistence', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
    window.localStorage.clear()
  })

  it('renders exchange dropdown and displays all holdings by default', async () => {
    render(<HoldingsSection />)

    const exchangeSelect = await screen.findByLabelText('거래소 필터')
    expect(exchangeSelect).toBeInTheDocument()
    expect((exchangeSelect as HTMLSelectElement).value).toBe('all')

    expect(await screen.findByText('KRW-BTC')).toBeInTheDocument()
    expect(screen.getByText('005930')).toBeInTheDocument()
    expect(screen.getByText('KRW-XRP')).toBeInTheDocument()
    expect(screen.getByText(/전체 거래소 기준 \(3개 종목\)/)).toBeInTheDocument()
  })

  it('filters holdings by selected exchange and persists to localStorage', async () => {
    const user = userEvent.setup()
    render(<HoldingsSection />)

    const exchangeSelect = await screen.findByLabelText('거래소 필터')
    await user.selectOptions(exchangeSelect, 'upbit')

    // Only Upbit row visible
    expect(screen.getByText('KRW-BTC')).toBeInTheDocument()
    expect(screen.queryByText('005930')).not.toBeInTheDocument()
    expect(screen.queryByText('KRW-XRP')).not.toBeInTheDocument()

    // Saved to localStorage
    expect(JSON.parse(window.localStorage.getItem('sbm_reports_holdings_exchange_filter') || '""')).toBe('upbit')
  })

  it('re-calculates summary cards based on the selected exchange', async () => {
    const user = userEvent.setup()
    render(<HoldingsSection />)

    await screen.findByText('KRW-BTC')

    // Select KIS
    const exchangeSelect = screen.getByLabelText('거래소 필터')
    await user.selectOptions(exchangeSelect, 'kis')

    // 005930 only (cost: 1,000,000, value: 1,050,000, asset_count: 1)
    expect(screen.getByText('005930')).toBeInTheDocument()
    expect(screen.queryByText('KRW-BTC')).not.toBeInTheDocument()

    // 1개 종목 표시중 뱃지
    expect(screen.getByText('1개 종목 표시중')).toBeInTheDocument()
  })

  it('restores exchange filter from localStorage on initial render', async () => {
    window.localStorage.setItem('sbm_reports_holdings_exchange_filter', JSON.stringify('bithumb'))

    render(<HoldingsSection />)

    await screen.findByText('KRW-XRP')

    const exchangeSelect = screen.getByLabelText('거래소 필터') as HTMLSelectElement
    expect(exchangeSelect.value).toBe('bithumb')

    expect(screen.getByText('KRW-XRP')).toBeInTheDocument()
    expect(screen.queryByText('KRW-BTC')).not.toBeInTheDocument()
    expect(screen.queryByText('005930')).not.toBeInTheDocument()
  })

  it('resets filter when clicking the reset button', async () => {
    const user = userEvent.setup()
    window.localStorage.setItem('sbm_reports_holdings_exchange_filter', JSON.stringify('upbit'))

    render(<HoldingsSection />)

    await screen.findByText('KRW-BTC')
    expect(screen.queryByText('005930')).not.toBeInTheDocument()

    // Click reset button
    const resetBtn = screen.getByRole('button', { name: '초기화' })
    await user.click(resetBtn)

    const exchangeSelect = screen.getByLabelText('거래소 필터') as HTMLSelectElement
    expect(exchangeSelect.value).toBe('all')

    expect(screen.getByText('KRW-BTC')).toBeInTheDocument()
    expect(screen.getByText('005930')).toBeInTheDocument()
    expect(screen.getByText('KRW-XRP')).toBeInTheDocument()
    expect(JSON.parse(window.localStorage.getItem('sbm_reports_holdings_exchange_filter') || '""')).toBe('all')
  })
})
