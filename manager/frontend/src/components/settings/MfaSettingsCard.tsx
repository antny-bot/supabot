import { useEffect, useState } from 'react'
import { Shield } from 'lucide-react'

interface MfaSettingsCardProps {
  initialEnabled: boolean
  onStatusChange?: (enabled: boolean) => void
}

export default function MfaSettingsCard({ initialEnabled, onStatusChange }: MfaSettingsCardProps) {
  const [mfaEnabled, setMfaEnabled] = useState(initialEnabled)
  const [mfaSetupData, setMfaSetupData] = useState<{ secret: string; qr_url: string } | null>(null)
  const [otpConfirmCode, setOtpConfirmCode] = useState('')
  const [mfaLoading, setMfaLoading] = useState(false)
  const [mfaError, setMfaError] = useState<string | null>(null)
  const [showDisableForm, setShowDisableForm] = useState(false)

  useEffect(() => {
    setMfaEnabled(initialEnabled)
  }, [initialEnabled])

  function syncEnabled(enabled: boolean) {
    setMfaEnabled(enabled)
    onStatusChange?.(enabled)
  }

  async function handleMfaSetup() {
    setMfaLoading(true)
    setMfaError(null)
    try {
      const res = await fetch('/api/mfa/setup', { method: 'POST', credentials: 'include' })
      if (res.ok) {
        const data = await res.json() as { secret: string; qr_url: string }
        setMfaSetupData(data)
      } else {
        const body = await res.json().catch(() => ({})) as { error?: string }
        setMfaError(body.error ?? 'MFA 설정 초기화에 실패했습니다.')
      }
    } catch {
      setMfaError('서버와 통신할 수 없습니다.')
    } finally {
      setMfaLoading(false)
    }
  }

  async function handleMfaEnable(e: React.FormEvent) {
    e.preventDefault()
    setMfaLoading(true)
    setMfaError(null)
    try {
      const res = await fetch('/api/mfa/enable', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: otpConfirmCode }),
      })
      if (res.ok) {
        syncEnabled(true)
        setMfaSetupData(null)
        setOtpConfirmCode('')
      } else {
        const body = await res.json().catch(() => ({})) as { error?: string }
        setMfaError(body.error ?? '인증 코드가 올바르지 않습니다.')
      }
    } catch {
      setMfaError('서버와 통신할 수 없습니다.')
    } finally {
      setMfaLoading(false)
    }
  }

  async function handleMfaDisable(e: React.FormEvent) {
    e.preventDefault()
    setMfaLoading(true)
    setMfaError(null)
    try {
      const res = await fetch('/api/mfa/disable', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: otpConfirmCode }),
      })
      if (res.ok) {
        syncEnabled(false)
        setShowDisableForm(false)
        setOtpConfirmCode('')
      } else {
        const body = await res.json().catch(() => ({})) as { error?: string }
        setMfaError(body.error ?? '인증 코드가 올바르지 않습니다.')
      }
    } catch {
      setMfaError('서버와 통신할 수 없습니다.')
    } finally {
      setMfaLoading(false)
    }
  }

  return (
    <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-5">
      <div className="flex items-center gap-3 mb-4">
        <div className={`p-2 rounded-lg ${mfaEnabled ? 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400' : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'}`}>
          <Shield size={20} />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">보안</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">2차 인증(MFA/OTP) 설정</p>
        </div>
        <div className="ml-auto">
          <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${mfaEnabled ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-800 dark:text-emerald-400' : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-400'}`}>
            {mfaEnabled ? '활성화됨' : '비활성화됨'}
          </span>
        </div>
      </div>

      {!mfaEnabled && !mfaSetupData && (
        <div className="space-y-3">
          <p className="text-xs text-slate-600 dark:text-slate-400">
            로그인 보안을 강화하려면 OTP 앱을 사용한 2차 인증을 켜세요.
          </p>
          <button
            onClick={handleMfaSetup}
            disabled={mfaLoading}
            className="px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-60 text-white rounded-lg text-xs font-medium transition-colors"
          >
            {mfaLoading ? '준비 중…' : '2차 인증 활성화 설정'}
          </button>
        </div>
      )}

      {!mfaEnabled && mfaSetupData && (
        <div className="space-y-4 border-t border-slate-100 dark:border-slate-800 pt-4">
          <div className="flex flex-col sm:flex-row gap-4 items-center">
            <div className="bg-white p-2 rounded-lg border border-slate-200 shrink-0">
              <img src={mfaSetupData.qr_url} alt="OTP QR Code" className="w-40 h-40" />
            </div>
            <div className="flex-1 space-y-2">
              <h3 className="text-xs font-bold text-slate-800 dark:text-slate-200">1단계: OTP 앱 등록</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                Google Authenticator, Microsoft Authenticator, Duo 중 하나로 QR 코드를 스캔하세요.
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500 leading-relaxed">
                스캔이 어렵다면 아래 비밀키를 직접 입력할 수 있습니다.<br />
                <code className="bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono text-xs text-slate-700 dark:text-slate-300 font-semibold break-all select-all">{mfaSetupData.secret}</code>
              </p>
            </div>
          </div>

          <form onSubmit={handleMfaEnable} className="space-y-3 border-t border-slate-100 dark:border-slate-800 pt-4">
            <div>
              <h3 className="text-xs font-bold text-slate-800 dark:text-slate-200 mb-1.5">2단계: 인증 코드 확인</h3>
              <div className="flex flex-wrap gap-2">
                <input
                  type="text"
                  required
                  pattern="[0-9]*"
                  inputMode="numeric"
                  maxLength={6}
                  value={otpConfirmCode}
                  onChange={(e) => setOtpConfirmCode(e.target.value)}
                  placeholder="000000"
                  className="w-32 px-3 py-2 text-center font-bold tracking-widest border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <button
                  type="submit"
                  disabled={mfaLoading}
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-60 text-white rounded-lg text-xs font-medium transition-colors"
                >
                  {mfaLoading ? '확인 중…' : '인증 및 활성화'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMfaSetupData(null)
                    setOtpConfirmCode('')
                    setMfaError(null)
                  }}
                  className="px-3 py-2 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 text-xs transition-colors"
                >
                  취소
                </button>
              </div>
              {mfaError && <p className="text-xs text-rose-600 mt-1">{mfaError}</p>}
            </div>
          </form>
        </div>
      )}

      {mfaEnabled && !showDisableForm && (
        <div className="space-y-3">
          <p className="text-xs text-slate-600 dark:text-slate-400">
            현재 2차 인증이 켜져 있습니다. 로그인 시 OTP 앱의 6자리 코드를 추가로 입력해야 합니다.
          </p>
          <button
            onClick={() => {
              setShowDisableForm(true)
              setOtpConfirmCode('')
              setMfaError(null)
            }}
            className="px-4 py-2 bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/20 dark:hover:bg-rose-950/40 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-900 rounded-lg text-xs font-medium transition-colors"
          >
            2차 인증 비활성화
          </button>
        </div>
      )}

      {mfaEnabled && showDisableForm && (
        <form onSubmit={handleMfaDisable} className="space-y-3 border-t border-slate-100 dark:border-slate-800 pt-4">
          <div>
            <h3 className="text-xs font-bold text-slate-800 dark:text-slate-200 mb-1.5">2차 인증 비활성화</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">
              비활성화하려면 OTP 앱에 표시된 6자리 코드를 입력하세요.
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                required
                pattern="[0-9]*"
                inputMode="numeric"
                maxLength={6}
                value={otpConfirmCode}
                onChange={(e) => setOtpConfirmCode(e.target.value)}
                placeholder="000000"
                className="w-32 px-3 py-2 text-center font-bold tracking-widest border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
              <button
                type="submit"
                disabled={mfaLoading}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-700 disabled:opacity-60 text-white rounded-lg text-xs font-medium transition-colors"
              >
                {mfaLoading ? '확인 중…' : '인증 및 비활성화'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowDisableForm(false)
                  setOtpConfirmCode('')
                  setMfaError(null)
                }}
                className="px-3 py-2 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 text-xs transition-colors"
              >
                취소
              </button>
            </div>
            {mfaError && <p className="text-xs text-rose-600 mt-1">{mfaError}</p>}
          </div>
        </form>
      )}
    </div>
  )
}
