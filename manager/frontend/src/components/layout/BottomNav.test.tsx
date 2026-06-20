import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../../contexts/AuthContext'
import BottomNav from './BottomNav'

vi.mock('./AllMenuDrawer', () => ({
  default: () => <div>drawer opened</div>,
}))

describe('BottomNav', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('renders pinned items from nav preferences and opens the drawer', async () => {
    const user = userEvent.setup()

    localStorage.setItem('sbm_nav_order', JSON.stringify(['dashboard', 'orders', 'reports', 'config']))

    render(
      <MemoryRouter>
        <AuthContext.Provider
          value={{
            user: {
              email: 'user@example.com',
              bot_user_id: 'user-1',
              is_admin: false,
            },
            loading: false,
          }}
        >
          <BottomNav />
        </AuthContext.Provider>
      </MemoryRouter>,
    )

    expect(screen.getByText('대시보드')).toBeInTheDocument()
    expect(screen.queryByText('설정')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /전체/i }))

    expect(screen.getByText('drawer opened')).toBeInTheDocument()
  })
})
