import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Moon, Sun, Zap } from 'lucide-react'
import { loginWithMfa, loginWithPassword } from '../api/auth'
import { ApiError } from '../api/client'
import { useTheme } from '../hooks/useTheme'
import ShaderBackground from '@/components/ui/shader-background'

const SAVE_EMAIL_KEY = 'sbm_saved_email'
const REMEMBER_KEY = 'sbm_remember_email'

function readQueryErrorMessage(search: string) {
  const params = new URLSearchParams(search)
  const errSlug = params.get('error')

  if (errSlug === 'no_access') {
    return '대시보드 접근 권한이 없습니다.'
  }
  if (errSlug === 'oauth_failed') {
    return 'Google 로그인에 실패했습니다. 다시 시도해 주세요.'
  }

  return null
}

export default function Login() {
  const [email, setEmail] = useState(() => localStorage.getItem(SAVE_EMAIL_KEY) || '')
  const [password, setPassword] = useState('')
  const [rememberEmail, setRememberEmail] = useState(() => localStorage.getItem(REMEMBER_KEY) === 'true')
  const [otpCode, setOtpCode] = useState('')
  const [trustDevice, setTrustDevice] = useState(false)
  const [isMfaRequired, setIsMfaRequired] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { isDark, toggle } = useTheme()

  useEffect(() => {
    localStorage.setItem(REMEMBER_KEY, String(rememberEmail))
    if (!rememberEmail) {
      localStorage.removeItem(SAVE_EMAIL_KEY)
    }
  }, [rememberEmail])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const queryError = readQueryErrorMessage(window.location.search)

    if (queryError) {
      setError(queryError)
    }
    if (params.get('oauth_mfa') === '1') {
      setIsMfaRequired(true)
    }
    if (queryError || params.get('oauth_mfa')) {
      window.history.replaceState({}, '', '/login')
    }
  }, [])

  function handlePostLogin() {
    if (rememberEmail) {
      localStorage.setItem(SAVE_EMAIL_KEY, email)
    } else {
      localStorage.removeItem(SAVE_EMAIL_KEY)
    }
    navigate('/dashboard', { replace: true })
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      const body = await loginWithPassword(email, password)
      if (body.mfa_required) {
        setIsMfaRequired(true)
      } else {
        handlePostLogin()
      }
    } catch (caughtError) {
      if (caughtError instanceof ApiError && caughtError.status === 403) {
        const body = caughtError.body as { error?: string }
        setError(body.error ?? '대시보드 접근 권한이 없습니다.')
      } else if (caughtError instanceof ApiError) {
        setError('이메일 또는 비밀번호가 올바르지 않습니다.')
      } else {
        setError('서버에 연결할 수 없습니다.')
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleMfaSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)

    try {
      await loginWithMfa(otpCode, trustDevice)
      handlePostLogin()
    } catch (caughtError) {
      if (caughtError instanceof ApiError) {
        const body = caughtError.body as { error?: string }
        setError(body.error ?? '인증 코드가 올바르지 않습니다.')
      } else {
        setError('서버에 연결할 수 없습니다.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative font-app-ui flex min-h-screen flex-col items-center justify-center p-4 overflow-hidden">
      <ShaderBackground />
      <div className="absolute inset-0 bg-white/40 dark:bg-slate-950/60 pointer-events-none -z-10" />

      <button
        type="button"
        onClick={toggle}
        className="absolute right-4 top-4 rounded-xl border border-slate-200/50 bg-white/50 p-2 text-slate-600 shadow-md backdrop-blur-md transition-all hover:bg-white/80 dark:border-slate-800/50 dark:bg-slate-900/50 dark:text-slate-400 dark:hover:bg-slate-800/80"
      >
        {isDark ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      <div className="w-full max-w-sm relative z-10">
        <div className="mb-8 flex animate-fade-in-up flex-col items-center">
          <div className="mb-4 rounded-2xl bg-primary-600 p-3 shadow-lg shadow-primary-500/20">
            <Zap size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white drop-shadow-sm">supabot manager</h1>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">통합 관리자 대시보드</p>
        </div>

        <div
          className="animate-fade-in-up rounded-2xl border border-white/40 bg-white/80 p-6 shadow-2xl backdrop-blur-xl dark:border-slate-800/40 dark:bg-slate-900/80"
          style={{ animationDelay: '80ms' }}
        >
          {error ? (
            <div className="mb-5 flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-400">
              <AlertCircle size={14} className="shrink-0" />
              {error}
            </div>
          ) : null}

          {isMfaRequired ? (
            <form onSubmit={handleMfaSubmit} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
                  2차 인증 번호 (OTP)
                </label>
                <input
                  type="text"
                  required
                  pattern="[0-9]*"
                  inputMode="numeric"
                  maxLength={6}
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-center text-lg font-bold tracking-widest text-slate-900 transition-shadow focus:outline-none focus:ring-2 focus:ring-primary-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-primary-400"
                  placeholder="000000"
                  autoComplete="one-time-code"
                  autoFocus
                />
                <p className="mt-2 text-center text-xs text-slate-500 dark:text-slate-400">
                  Google OTP 앱에 표시된 6자리 번호를 입력해 주세요.
                </p>
              </div>

              <div className="flex items-center gap-2 px-1">
                <input
                  type="checkbox"
                  id="trustDevice"
                  checked={trustDevice}
                  onChange={(e) => setTrustDevice(e.target.checked)}
                  className="h-4 w-4 cursor-pointer rounded border-slate-300 text-primary-600 transition-colors focus:ring-primary-500 dark:border-slate-700 dark:bg-slate-800"
                />
                <label htmlFor="trustDevice" className="cursor-pointer select-none text-xs text-slate-600 dark:text-slate-400">
                  이 기기를 30일 동안 신뢰함 (2차 인증 생략)
                </label>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="mt-2 w-full rounded-xl bg-primary-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-700 disabled:opacity-60"
              >
                {loading ? '인증 중...' : '인증 및 로그인'}
              </button>

              <button
                type="button"
                onClick={() => {
                  setIsMfaRequired(false)
                  setOtpCode('')
                  setError(null)
                }}
                className="mt-2 block w-full py-2 text-center text-xs text-slate-500 transition-colors hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              >
                이전 화면으로 돌아가기
              </button>
            </form>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
                  이메일
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 transition-shadow focus:outline-none focus:ring-2 focus:ring-primary-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-primary-400"
                  placeholder="admin@example.com"
                  autoComplete="email"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">
                  비밀번호
                </label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 transition-shadow focus:outline-none focus:ring-2 focus:ring-primary-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:focus:ring-primary-400"
                  placeholder="••••••••"
                  autoComplete="current-password"
                />
              </div>

              <div className="flex items-center gap-2 px-1">
                <input
                  type="checkbox"
                  id="rememberEmail"
                  checked={rememberEmail}
                  onChange={(e) => setRememberEmail(e.target.checked)}
                  className="h-4 w-4 cursor-pointer rounded border-slate-300 text-primary-600 transition-colors focus:ring-primary-500 dark:border-slate-700 dark:bg-slate-800"
                />
                <label htmlFor="rememberEmail" className="cursor-pointer select-none text-xs text-slate-600 dark:text-slate-400">
                  이메일 저장
                </label>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="mt-2 w-full rounded-xl bg-primary-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-700 disabled:opacity-60"
              >
                {loading ? '로그인 중...' : '로그인'}
              </button>

              <div className="relative my-2">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-200 dark:border-slate-700" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-white px-2 text-slate-400 dark:bg-slate-900 dark:text-slate-500">또는</span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => {
                  window.location.href = '/api/auth/google'
                }}
                className="flex w-full items-center justify-center gap-2.5 rounded-xl border border-slate-200 bg-white py-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
              >
                <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
                  <path fill="#4285F4" d="M44.5 20H24v8.5h11.9C34.2 33.5 29.6 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.1 8 2.9l6.4-6.4C34.5 6.1 29.5 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20c11 0 19.6-7.7 19.6-20 0-1.3-.1-2.7-.1-4z" />
                  <path fill="#34A853" d="M6.3 14.7l7 5.1C15 16.5 19.2 14 24 14c3.1 0 5.8 1.1 8 2.9l6.4-6.4C34.5 6.1 29.5 4 24 4c-7.8 0-14.4 4.6-17.7 10.7z" />
                  <path fill="#FBBC05" d="M24 44c5.4 0 10.3-1.8 14.1-4.9l-6.5-5.4C29.6 35.4 27 36 24 36c-5.5 0-10.1-2.5-12-6.5l-7 5.4C8.6 41.3 15.8 44 24 44z" />
                  <path fill="#EA4335" d="M44.5 20H24v8.5h11.9c-1 2.7-2.9 4.9-5.4 6.5l6.5 5.4C41.4 36.4 44 30.9 44 24c0-1.3-.1-2.7-.5-4z" />
                </svg>
                Google로 로그인
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
