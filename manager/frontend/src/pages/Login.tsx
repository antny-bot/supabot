import { useState, FormEvent, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap, AlertCircle } from 'lucide-react'
import { useTheme } from '../hooks/useTheme'
import { Sun, Moon } from 'lucide-react'

const SAVE_EMAIL_KEY = 'sbm_saved_email'
const REMEMBER_KEY = 'sbm_remember_email'

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
    const errSlug = params.get('error')
    if (errSlug === 'no_access') setError('대시보드 접근 권한이 없습니다.')
    else if (errSlug === 'oauth_failed') setError('Google 로그인에 실패했습니다. 다시 시도해주세요.')
    if (params.get('oauth_mfa') === '1') setIsMfaRequired(true)
    if (errSlug || params.get('oauth_mfa')) {
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
      const res = await fetch('/api/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (res.ok) {
        const body = await res.json().catch(() => ({})) as { mfa_required?: boolean }
        if (body.mfa_required) {
          setIsMfaRequired(true)
        } else {
          handlePostLogin()
        }
      } else if (res.status === 403) {
        const body = await res.json().catch(() => ({})) as { error?: string }
        setError(body.error ?? '대시보드 접근 권한이 없습니다.')
      } else {
        setError('이메일 또는 비밀번호가 올바르지 않습니다.')
      }
    } catch {
      setError('서버에 연결할 수 없습니다.')
    } finally {
      setLoading(false)
    }
  }

  async function handleMfaSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/login/mfa', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: otpCode, trust_device: trustDevice }),
      })
      if (res.ok) {
        handlePostLogin()
      } else {
        const body = await res.json().catch(() => ({})) as { error?: string }
        setError(body.error ?? '인증 코드가 올바르지 않습니다.')
      }
    } catch {
      setError('서버에 연결할 수 없습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="font-app-ui min-h-screen bg-slate-50 dark:bg-slate-950 flex flex-col items-center justify-center p-4">
      <button
        onClick={toggle}
        className="absolute top-4 right-4 p-2 rounded-lg text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors"
      >
        {isDark ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <div className="bg-indigo-600 rounded-xl p-3 mb-4">
            <Zap size={28} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">supabot manager</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">통합 웹 대시보드</p>
        </div>

        <div className="bg-white dark:bg-slate-900 rounded-2xl shadow-sm border border-slate-200 dark:border-slate-800 p-6">
          {error && (
            <div className="flex items-center gap-2 p-3 bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 rounded-xl text-rose-700 dark:text-rose-400 text-sm mb-5">
              <AlertCircle size={14} className="shrink-0" />
              {error}
            </div>
          )}

          {isMfaRequired ? (
            <form onSubmit={handleMfaSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
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
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400 text-sm transition-shadow text-center text-lg tracking-widest font-bold"
                  placeholder="000000"
                  autoComplete="one-time-code"
                  autoFocus
                />
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 text-center">
                  구글 OTP 등 인증 앱에 표시된 6자리 번호를 입력하세요.
                </p>
              </div>

              <div className="flex items-center gap-2 px-1">
                <input
                  type="checkbox"
                  id="trustDevice"
                  checked={trustDevice}
                  onChange={(e) => setTrustDevice(e.target.checked)}
                  className="w-4 h-4 rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-indigo-500 dark:bg-slate-800 transition-colors cursor-pointer"
                />
                <label htmlFor="trustDevice" className="text-xs text-slate-600 dark:text-slate-400 cursor-pointer select-none">
                  이 기기를 30일 동안 신뢰함 (2차 인증 생략)
                </label>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white rounded-xl font-medium text-sm transition-colors mt-2"
              >
                {loading ? '인증 중…' : '인증 및 로그인'}
              </button>

              <button
                type="button"
                onClick={() => {
                  setIsMfaRequired(false)
                  setOtpCode('')
                  setError(null)
                }}
                className="w-full py-2 text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 text-xs text-center transition-colors block mt-2"
              >
                이전 화면으로 돌아가기
              </button>
            </form>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  이메일
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400 text-sm transition-shadow"
                  placeholder="admin@example.com"
                  autoComplete="email"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                  비밀번호
                </label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400 text-sm transition-shadow"
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
                  className="w-4 h-4 rounded border-slate-300 dark:border-slate-700 text-indigo-600 focus:ring-indigo-500 dark:bg-slate-800 transition-colors cursor-pointer"
                />
                <label htmlFor="rememberEmail" className="text-xs text-slate-600 dark:text-slate-400 cursor-pointer select-none">
                  이메일 저장
                </label>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white rounded-xl font-medium text-sm transition-colors mt-2"
              >
                {loading ? '로그인 중…' : '로그인'}
              </button>

              <div className="relative my-2">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-200 dark:border-slate-700" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="px-2 bg-white dark:bg-slate-900 text-slate-400 dark:text-slate-500">또는</span>
                </div>
              </div>

              <button
                type="button"
                onClick={() => { window.location.href = '/api/auth/google' }}
                className="w-full py-2.5 flex items-center justify-center gap-2.5 border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-xl text-sm font-medium transition-colors"
              >
                <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
                  <path fill="#4285F4" d="M44.5 20H24v8.5h11.9C34.2 33.5 29.6 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.1 8 2.9l6.4-6.4C34.5 6.1 29.5 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20c11 0 19.6-7.7 19.6-20 0-1.3-.1-2.7-.1-4z"/>
                  <path fill="#34A853" d="M6.3 14.7l7 5.1C15 16.5 19.2 14 24 14c3.1 0 5.8 1.1 8 2.9l6.4-6.4C34.5 6.1 29.5 4 24 4c-7.8 0-14.4 4.6-17.7 10.7z"/>
                  <path fill="#FBBC05" d="M24 44c5.4 0 10.3-1.8 14.1-4.9l-6.5-5.4C29.6 35.4 27 36 24 36c-5.5 0-10.1-2.5-12-6.5l-7 5.4C8.6 41.3 15.8 44 24 44z"/>
                  <path fill="#EA4335" d="M44.5 20H24v8.5h11.9c-1 2.7-2.9 4.9-5.4 6.5l6.5 5.4C41.4 36.4 44 30.9 44 24c0-1.3-.1-2.7-.5-4z"/>
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
