import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('./components/layout/AppLayout', async () => {
  const { Outlet } = await import('react-router-dom')
  const { AuthContext } = await import('./contexts/AuthContext')

  function MockAppLayout() {
    return (
      <AuthContext.Provider
        value={{
          user: {
            email: 'user@example.com',
            bot_user_id: 'user-1',
            username: 'user',
            is_admin: false,
            mfa_enabled: false,
          },
          loading: false,
        }}
      >
        <Outlet />
      </AuthContext.Provider>
    )
  }

  return { default: MockAppLayout }
})

vi.mock('./pages/Login', () => ({ default: () => <div>login page</div> }))
vi.mock('./pages/Orders', () => ({ default: () => <div>orders page</div> }))
vi.mock('./pages/Trades', () => ({ default: () => <div>trades page</div> }))
vi.mock('./pages/Templates', () => ({ default: () => <div>templates page</div> }))
vi.mock('./pages/Config', () => ({ default: () => <div>config page</div> }))
vi.mock('./pages/Reports', () => ({ default: () => <div>reports page</div> }))
vi.mock('./pages/Admin', () => ({ default: () => <div>admin page</div> }))
vi.mock('./pages/Analytics', () => ({ default: () => <div>analytics page</div> }))
vi.mock('./lib/navPreferences', () => ({ readDefaultPage: () => '/dashboard' }))
vi.mock('./pages/Dashboard', () => ({
  default: function SuspendedDashboard() {
    throw new Promise(() => {})
  },
}))

afterEach(() => {
  window.history.replaceState({}, '', '/')
})

describe('App routes', () => {
  it('shows a loading fallback while a route component is suspended', async () => {
    window.history.pushState({}, '', '/dashboard')

    const { default: App } = await import('./App')

    render(<App />)

    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })
})
