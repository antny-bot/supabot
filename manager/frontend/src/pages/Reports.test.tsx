import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../contexts/AuthContext'
import Reports from './Reports'

vi.mock('./reports/HoldingsSection', () => ({ default: () => <div>holdings section</div> }))
vi.mock('./reports/PnlSection', () => ({ default: () => <div>pnl section</div> }))
vi.mock('./reports/MonthlySection', () => ({ default: () => <div>monthly section</div> }))
vi.mock('./reports/StrategySection', () => ({ default: () => <div>strategy section</div> }))
vi.mock('./reports/RoiRankingSection', () => ({ default: () => <div>ranking section</div> }))
vi.mock('./reports/PairsSection', () => ({ default: () => <div>pairs section</div> }))
vi.mock('./reports/WinStatsSection', () => ({ default: () => <div>winstats section</div> }))
vi.mock('./reports/NlLogsSection', () => ({ default: () => <div>nllogs section</div> }))

vi.mock('../components/ui/DateRangePicker', () => ({
  default: () => <div data-testid="date-range-picker">date range picker</div>
}))

describe('Reports', () => {
  it('renders correctly and handles tab switching and visibility for admin', async () => {
    const user = userEvent.setup()

    const { rerender } = render(
      <AuthContext.Provider
        value={{
          user: {
            email: 'user@example.com',
            bot_user_id: 'user-1',
            is_admin: false,
            mfa_enabled: false,
            username: 'user',
          },
          loading: false,
        }}
      >
        <Reports />
      </AuthContext.Provider>
    )

    // 1. holdings tab is default and active
    expect(screen.getByText('holdings section')).toBeInTheDocument()
    // Holdings is not period sensitive, so picker should not exist
    expect(screen.queryByTestId('date-range-picker')).not.toBeInTheDocument()

    // 2. Non-admin should not see NL logs tab
    expect(screen.queryAllByRole('tab', { name: 'NL 로그' })).toHaveLength(0)

    // 3. Switch to Pnl (which is period sensitive)
    await user.click(screen.getAllByRole('tab', { name: '실현 손익' })[0])
    expect(screen.getByText('pnl section')).toBeInTheDocument()
    expect(screen.getByTestId('date-range-picker')).toBeInTheDocument()

    // 4. Rerender as Admin to test NL logs tab visibility
    rerender(
      <AuthContext.Provider
        value={{
          user: {
            email: 'admin@example.com',
            bot_user_id: 'user-1',
            is_admin: true,
            mfa_enabled: false,
            username: 'admin',
          },
          loading: false,
        }}
      >
        <Reports />
      </AuthContext.Provider>
    )

    // Admin should see NL logs tab
    const nlTabs = screen.getAllByRole('tab', { name: 'NL 로그' })
    expect(nlTabs.length).toBeGreaterThan(0)

    await user.click(nlTabs[0])
    expect(screen.getByText('nllogs section')).toBeInTheDocument()
  })
})
