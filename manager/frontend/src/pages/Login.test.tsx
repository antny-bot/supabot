import { fireEvent, render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Login from './Login'

const { navigateMock, loginWithPasswordMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  loginWithPasswordMock: vi.fn(),
}))

vi.mock('../api/auth', () => ({
  loginWithPassword: loginWithPasswordMock,
  loginWithMfa: vi.fn(),
}))

vi.mock('../hooks/useTheme', () => ({
  useTheme: () => ({ isDark: false, toggle: vi.fn() }),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

describe('Login', () => {
  beforeEach(() => {
    loginWithPasswordMock.mockReset()
    navigateMock.mockReset()
    localStorage.clear()
    window.history.replaceState({}, '', '/login')
  })

  it('submits credentials through the auth API module', async () => {
    loginWithPasswordMock.mockResolvedValue({ mfa_required: false })

    const { container } = render(<Login />)
    const emailInput = container.querySelector('input[type="email"]') as HTMLInputElement
    const passwordInput = container.querySelector('input[type="password"]') as HTMLInputElement
    const form = container.querySelector('form') as HTMLFormElement

    fireEvent.change(emailInput, { target: { value: 'admin@example.com' } })
    fireEvent.change(passwordInput, { target: { value: 'secret' } })
    fireEvent.submit(form)

    expect(loginWithPasswordMock).toHaveBeenCalledWith('admin@example.com', 'secret')
  })
})
