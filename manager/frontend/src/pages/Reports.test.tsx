import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import Reports from './Reports'

vi.mock('./reports/HoldingsSection', () => ({ default: () => <div>holdings section</div> }))
vi.mock('./reports/PnlSection', () => ({ default: () => <div>pnl section</div> }))
vi.mock('./reports/MonthlySection', () => ({ default: () => <div>monthly section</div> }))
vi.mock('./reports/StrategySection', () => ({ default: () => <div>strategy section</div> }))
vi.mock('./reports/ExchangeSection', () => ({ default: () => <div>exchange section</div> }))
vi.mock('./reports/DailySection', () => ({ default: () => <div>daily section</div> }))
vi.mock('./reports/RoiRankingSection', () => ({ default: () => <div>ranking section</div> }))
vi.mock('./reports/PairsSection', () => ({ default: () => <div>pairs section</div> }))
vi.mock('./reports/WinStatsSection', () => ({ default: () => <div>winstats section</div> }))

vi.mock('../components/ui/DateRangePicker', () => ({
  default: () => <div data-testid="date-range-picker">date range picker</div>
}))

describe('Reports', () => {
  it('renders correctly and handles tab switching', async () => {
    const user = userEvent.setup()

    render(<Reports />)

    // 1. holdings tab is default and active
    expect(screen.getByText('holdings section')).toBeInTheDocument()
    // Holdings is not period sensitive, so picker should not exist
    expect(screen.queryByTestId('date-range-picker')).not.toBeInTheDocument()

    // 2. NL logs tab moved to Admin screen — should not be present here
    expect(screen.queryAllByRole('tab', { name: 'NL 로그' })).toHaveLength(0)

    // 3. Switch to Pnl (which is period sensitive)
    await user.click(screen.getAllByRole('tab', { name: '실현 손익' })[0])
    expect(screen.getByText('pnl section')).toBeInTheDocument()
    expect(screen.getByTestId('date-range-picker')).toBeInTheDocument()
  })
})
