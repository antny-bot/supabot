import { useEffect, useState, useCallback } from 'react'
import { Users, UserCheck, Clock, ShoppingCart, TrendingUp, AlertTriangle, Shield } from 'lucide-react'
import { fetchDashboard } from '../api/dashboard'
import type { DashboardData, DashboardStats } from '../types'
import { useAuthContext } from '../contexts/AuthContext'
import { useRealtime } from '../hooks/useRealtime'
import StatCard from '../components/ui/StatCard'
import Badge from '../components/ui/Badge'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'

const STAT_CONFIG: {
  key: keyof DashboardStats
  label: string
  Icon: React.ElementType
  bg: string
  adminOnly: boolean
}[] = [
  { key: 'users_total',   label: '전체 유저',   Icon: Users,         bg: 'bg-indigo-500',  adminOnly: true },
  { key: 'users_active',  label: '활성 유저',   Icon: UserCheck,     bg: 'bg-emerald-500', adminOnly: true },
  { key: 'users_pending', label: '대기 유저',   Icon: Clock,         bg: 'bg-amber-500',   adminOnly: true },
  { key: 'orders_open',   label: '활성 주문',   Icon: ShoppingCart,  bg: 'bg-blue-500',    adminOnly: false },
  { key: 'trades_24h',    label: '24h 거래',    Icon: TrendingUp,    bg: 'bg-violet-500',  adminOnly: false },
  { key: 'errors_24h',    label: '24h 오류',    Icon: AlertTriangle, bg: 'bg-rose-500',    adminOnly: true },
]

function fmtTime(s: string) {
  return s ? s.slice(0, 19).replace('T', ' ') : '—'
}

export default function Dashboard() {
  const { user } = useAuthContext()
  const [data, setData] = useState<DashboardData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [mfaEnabled, setMfaEnabled] = useState(user?.mfa_enabled ?? false)
  const [mfaSetupData, setMfaSetupData] = useState<{ secret: string; qr_url: string } | null>(null)
  const [otpConfirmCode, setOtpConfirmCode] = useState('')
  const [mfaLoading, setMfaLoading] = useState(false)
  const [mfaError, setMfaError] = useState<string | null>(null)
  const [showDisableForm, setShowDisableForm] = useState(false)

  useEffect(() => {
    if (user) {
      setMfaEnabled(user.mfa_enabled ?? false)
    }
  }, [user])

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
        setMfaEnabled(true)
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
        setMfaEnabled(false)
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

  const loadData = useCallback(() => {
    fetchDashboard()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  useRealtime(loadData)

  if (!data && !error) return <Spinner />

  const visibleStats = STAT_CONFIG.filter((c) => !c.adminOnly || user?.is_admin)

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-slate-900 dark:text-white">대시보드</h1>

      {error && <ErrorBanner message={error} />}

      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-3">
            {visibleStats.map(({ key, label, Icon, bg }) => (
              <StatCard
                key={key}
                label={label}
                value={data.stats[key] ?? 0}
                icon={<Icon size={16} />}
                iconBg={bg}
              />
            ))}
          </div>

          {user?.is_admin && (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800">
                <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">최근 이벤트</h2>
              </div>
              {/* 데스크톱 뷰 (테이블 형태) */}
              <div className="hidden md:block overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-slate-500 dark:text-slate-400 border-b border-slate-100 dark:border-slate-800">
                      <th className="px-4 py-2.5 text-left font-medium">시간</th>
                      <th className="px-4 py-2.5 text-left font-medium">레벨</th>
                      <th className="px-4 py-2.5 text-left font-medium">소스</th>
                      <th className="px-4 py-2.5 text-left font-medium">메시지</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {data.recent_events.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-4 py-8 text-center text-slate-400 dark:text-slate-500 text-xs">
                          이벤트 없음
                        </td>
                      </tr>
                    ) : data.recent_events.map((ev, i) => (
                      <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                        <td className="px-4 py-2.5 text-slate-500 dark:text-slate-400 font-mono text-xs whitespace-nowrap">
                          {fmtTime(String(ev.created_at))}
                        </td>
                        <td className="px-4 py-2.5">
                          <Badge value={ev.level} />
                        </td>
                        <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300 text-xs">{ev.source}</td>
                        <td className="px-4 py-2.5 text-slate-700 dark:text-slate-200 text-xs max-w-xs truncate">
                          {ev.message}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* 모바일 뷰 (리스트 형태) */}
              <div className="block md:hidden divide-y divide-slate-100 dark:divide-slate-800">
                {data.recent_events.length === 0 ? (
                  <div className="px-4 py-8 text-center text-slate-400 dark:text-slate-500 text-xs">
                    이벤트 없음
                  </div>
                ) : data.recent_events.map((ev, i) => (
                  <div key={i} className="p-3 space-y-1.5 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-slate-500 dark:text-slate-400 font-mono">{fmtTime(String(ev.created_at))}</span>
                      <Badge value={ev.level} />
                    </div>
                    <div className="text-xs font-semibold text-slate-600 dark:text-slate-300">[{ev.source || 'system'}]</div>
                    <div className="text-xs text-slate-700 dark:text-slate-200 text-break">{ev.message}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 내 계정 보안 설정 (MFA/OTP) */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm p-6 mt-6">
            <div className="flex items-center gap-3 mb-4">
              <div className={`p-2 rounded-lg ${mfaEnabled ? 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400' : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'}`}>
                <Shield size={20} />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">2차 인증 (MFA / OTP)</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">계정 로그인의 보안을 강화합니다.</p>
              </div>
              <div className="ml-auto">
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${mfaEnabled ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-800 dark:text-emerald-400' : 'bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-400'}`}>
                  {mfaEnabled ? '활성화됨' : '비활성화됨'}
                </span>
              </div>
            </div>

            {/* MFA 비활성화 상태이며 셋업 중이 아닐 때 */}
            {!mfaEnabled && !mfaSetupData && (
              <div className="space-y-3">
                <p className="text-xs text-slate-600 dark:text-slate-400">
                  비밀번호가 유출되더라도 계정을 안전하게 보호하기 위해 Google Authenticator 등의 모바일 OTP 앱을 이용한 2차 인증을 설정할 수 있습니다.
                </p>
                <button
                  onClick={handleMfaSetup}
                  disabled={mfaLoading}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white rounded-lg text-xs font-medium transition-colors"
                >
                  {mfaLoading ? '준비 중…' : '2차 인증 활성화 설정'}
                </button>
              </div>
            )}

            {/* MFA 활성화를 위한 QR 코드 및 검증 단계 */}
            {!mfaEnabled && mfaSetupData && (
              <div className="space-y-4 border-t border-slate-100 dark:border-slate-800 pt-4">
                <div className="flex flex-col sm:flex-row gap-4 items-center">
                  <div className="bg-white p-2 rounded-lg border border-slate-200 shrink-0">
                    <img src={mfaSetupData.qr_url} alt="OTP QR Code" className="w-40 h-40" />
                  </div>
                  <div className="flex-1 space-y-2">
                    <h3 className="text-xs font-bold text-slate-800 dark:text-slate-200">1단계: OTP 앱에 등록</h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                      Google Authenticator, Microsoft Authenticator 또는 Duo 앱을 켜고 왼쪽의 QR 코드를 스캔하세요.
                    </p>
                    <p className="text-xs text-slate-400 dark:text-slate-500 leading-relaxed">
                      스캔이 안 되나요? 다음 키를 직접 입력하세요:<br />
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
                        className="w-32 px-3 py-2 text-center font-bold tracking-widest border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      />
                      <button
                        type="submit"
                        disabled={mfaLoading}
                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white rounded-lg text-xs font-medium transition-colors"
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

            {/* MFA 활성화된 상태이며 비활성화를 누르지 않았을 때 */}
            {mfaEnabled && !showDisableForm && (
              <div className="space-y-3">
                <p className="text-xs text-slate-600 dark:text-slate-400">
                  현재 2차 인증(MFA)이 설정되어 계정이 더욱 안전하게 보호되고 있습니다. 로그인 시 OTP 앱의 번호를 추가 입력해야 합니다.
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

            {/* MFA 비활성화를 위한 인증 검증 단계 */}
            {mfaEnabled && showDisableForm && (
              <form onSubmit={handleMfaDisable} className="space-y-3 border-t border-slate-100 dark:border-slate-800 pt-4">
                <div>
                  <h3 className="text-xs font-bold text-slate-800 dark:text-slate-200 mb-1.5">2차 인증 비활성화</h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">
                    MFA를 비활성화하려면 OTP 앱에 표시된 6자리 코드를 입력하여 본인 인증을 완료하세요.
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
                      className="w-32 px-3 py-2 text-center font-bold tracking-widest border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
        </>
      )}
    </div>
  )
}
