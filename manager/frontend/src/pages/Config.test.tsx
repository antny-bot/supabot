import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext } from '../contexts/AuthContext'
import Config from './Config'

vi.mock('../components/settings/DisplaySettingsCard', () => ({
  default: () => <div>display settings</div>,
}))

vi.mock('../components/settings/ProfileSettingsCard', () => ({
  default: () => <div>profile settings</div>,
}))

vi.mock('../components/settings/MfaSettingsCard', () => ({
  default: () => <div>security settings</div>,
}))

describe('Config', () => {
  it('switches between tab panels', async () => {
    const user = userEvent.setup()

    render(
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
        <Config />
      </AuthContext.Provider>,
    )

    expect(screen.getByText('display settings')).toBeInTheDocument()

    await user.click(screen.getAllByRole('tab')[1])
    expect(screen.getByText('profile settings')).toBeInTheDocument()

    await user.click(screen.getAllByRole('tab')[2])
    expect(screen.getByText('security settings')).toBeInTheDocument()
  })
})
