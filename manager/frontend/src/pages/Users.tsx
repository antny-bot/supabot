import { useCallback, useEffect, useState } from 'react'
import { usePersistedState } from '../hooks/usePersistedState'
import { KeyRound, Mail, Pencil, ShieldCheck } from 'lucide-react'
import { activateUser, approveUser, blockUser, deactivateUser, deleteUser, fetchUsers, inviteAuthAccount, resetAuthPassword, setUserEmail } from '../api/users'
import type { User } from '../types'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import ErrorBanner from '../components/ui/ErrorBanner'
import FilterBar from '../components/ui/FilterBar'
import Spinner from '../components/ui/Spinner'
import { staggerDelay } from '../utils/animation'

const STATUS_OPTIONS = [
  { value: '', label: '전체' },
  { value: 'pending', label: '대기' },
  { value: 'active', label: '활성' },
  { value: 'inactive', label: '비활성' },
  { value: 'blocked', label: '차단' },
  { value: 'deleted', label: '삭제' },
]

function fmtDate(value: string) {
  return value ? value.slice(0, 10) : '--'
}

interface ActionButtonsProps {
  user: User
  onUpdate: (updated: User) => void
}

function ActionButtons({ user, onUpdate }: ActionButtonsProps) {
  const [busy, setBusy] = useState(false)
  const [authActionResult, setAuthActionResult] = useState<{ ok: boolean; message: string } | null>(null)

  async function run(action: () => Promise<User>) {
    setBusy(true)
    try {
      const updated = await action()
      onUpdate(updated)
    } finally {
      setBusy(false)
    }
  }

  async function handleInvite() {
    const email = user.manager_email
    if (!email || !window.confirm(`${email} 으로 초대 메일을 발송할까요?\n사용자가 메일의 링크로 접속해 직접 비밀번호를 설정하게 됩니다.`)) {
      return
    }
    setBusy(true)
    setAuthActionResult(null)
    try {
      const updated = await inviteAuthAccount(user.user_id)
      onUpdate(updated)
      setAuthActionResult({ ok: true, message: `${email}로 초대 메일을 발송했습니다.` })
    } catch (e: unknown) {
      setAuthActionResult({ ok: false, message: e instanceof Error ? e.message : '초대 메일 발송에 실패했습니다.' })
    } finally {
      setBusy(false)
    }
  }

  async function handleResetPassword() {
    const email = user.manager_email
    if (!email || !window.confirm(`${email} 으로 비밀번호 재설정 메일을 발송할까요?`)) {
      return
    }
    setBusy(true)
    setAuthActionResult(null)
    try {
      const res = await resetAuthPassword(user.user_id)
      setAuthActionResult({ ok: true, message: `${res.email}로 비밀번호 재설정 메일을 발송했습니다.` })
    } catch (e: unknown) {
      setAuthActionResult({ ok: false, message: e instanceof Error ? e.message : '비밀번호 재설정 메일 발송에 실패했습니다.' })
    } finally {
      setBusy(false)
    }
  }

  const status = user.status

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap gap-1">
        {status === 'pending' && (
          <Button variant="success" disabled={busy} onClick={() => run(() => approveUser(user.user_id))}>승인</Button>
        )}
        {status === 'inactive' && (
          <Button variant="success" disabled={busy} onClick={() => run(() => activateUser(user.user_id))}>활성화</Button>
        )}
        {status === 'active' && (
          <Button variant="ghost" disabled={busy} onClick={() => run(() => deactivateUser(user.user_id))}>비활성화</Button>
        )}
        {(status === 'pending' || status === 'active' || status === 'inactive') && (
          <Button variant="warning" disabled={busy} onClick={() => run(() => blockUser(user.user_id))}>차단</Button>
        )}
        {status === 'blocked' && (
          <Button variant="ghost" disabled={busy} onClick={() => run(() => activateUser(user.user_id))}>차단 해제</Button>
        )}
        {user.manager_email && status !== 'deleted' && (
          user.manager_invited_at ? (
            <Button variant="ghost" disabled={busy} onClick={() => void handleResetPassword()} title="Supabase 로그인 계정 비밀번호 재설정 메일 발송">
              <KeyRound size={11} /> 비밀번호 재설정
            </Button>
          ) : (
            <Button variant="ghost" disabled={busy} onClick={() => void handleInvite()} title="Supabase 로그인 계정 초대 메일 발송">
              <Mail size={11} /> 초대 메일 발송
            </Button>
          )
        )}
        {status !== 'deleted' && !user.is_admin && (
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => {
              if (window.confirm(`${user.username || user.user_id} 사용자를 삭제하시겠습니까?`)) {
                void run(() => deleteUser(user.user_id))
              }
            }}
          >
            삭제
          </Button>
        )}
      </div>
      {authActionResult && (
        <span className={`text-[11px] ${authActionResult.ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-500'}`}>
          {authActionResult.message}
        </span>
      )}
    </div>
  )
}

interface EmailCellProps {
  user: User
  onUpdate: (updated: User) => void
}

function EmailCell({ user, onUpdate }: EmailCellProps) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(user.manager_email ?? '')
  const [busy, setBusy] = useState(false)
  const [cellError, setCellError] = useState<string | null>(null)

  async function handleSave() {
    setBusy(true)
    setCellError(null)
    try {
      const updated = await setUserEmail(user.user_id, value)
      onUpdate(updated)
      setEditing(false)
    } catch (e: unknown) {
      setCellError(e instanceof Error ? e.message : '저장에 실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  function handleCancel() {
    setValue(user.manager_email ?? '')
    setCellError(null)
    setEditing(false)
  }

  if (editing) {
    return (
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-1">
          <input
            type="email"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="w-44 rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-900 focus:outline-none focus:ring-1 focus:ring-primary-500 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            placeholder="email@example.com"
            autoFocus
            disabled={busy}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void handleSave()
              if (e.key === 'Escape') handleCancel()
            }}
          />
          <Button variant="success" disabled={busy} onClick={() => void handleSave()}>저장</Button>
          <Button variant="ghost" disabled={busy} onClick={handleCancel}>취소</Button>
        </div>
        {cellError && <span className="text-xs text-rose-500">{cellError}</span>}
      </div>
    )
  }

  return (
    <div className="group flex items-center gap-1">
      <span className="text-xs text-slate-500 dark:text-slate-400">
        {user.manager_email ?? <span className="italic text-slate-300 dark:text-slate-600">미설정</span>}
      </span>
      <button
        onClick={() => setEditing(true)}
        className="rounded p-0.5 text-slate-400 opacity-0 transition-all group-hover:opacity-100 hover:text-primary-500"
        title="이메일 수정"
      >
        <Pencil size={11} />
      </button>
    </div>
  )
}

export function UsersContent() {
  const [users, setUsers] = useState<User[]>([])
  const [statusFilter, setStatusFilter] = usePersistedState('filter:users:status', '')
  const [expandedFilter, setExpandedFilter] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const toggleFilter = (name: string) => {
    setExpandedFilter((prev) => (prev === name ? null : name))
  }

  useEffect(() => {
    setLoading(true)
    fetchUsers(statusFilter)
      .then(setUsers)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류가 발생했습니다.'))
      .finally(() => setLoading(false))
  }, [statusFilter])

  const handleUpdate = useCallback((updated: User) => {
    setUsers((prev) => prev.map((user) => (user.user_id === updated.user_id ? updated : user)))
  }, [])

  return (
    <div className="space-y-4">

      <FilterBar collapsible isOpen={expandedFilter === 'status'} onToggle={() => toggleFilter('status')}
        options={STATUS_OPTIONS} value={statusFilter} onChange={setStatusFilter} />


      {error && <ErrorBanner message={error} />}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        {loading ? (
          <Spinner />
        ) : (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                    <th className="px-4 py-3 text-left font-medium">유저 ID</th>
                    <th className="px-4 py-3 text-left font-medium">이름</th>
                    <th className="px-4 py-3 text-left font-medium">상태</th>
                    <th className="px-4 py-3 text-left font-medium">관리자</th>
                    <th className="px-4 py-3 text-left font-medium">매니저 이메일</th>
                    <th className="whitespace-nowrap px-4 py-3 text-left font-medium">가입일</th>
                    <th className="px-4 py-3 text-left font-medium">액션</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {users.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-10 text-center text-xs text-slate-400 dark:text-slate-500">
                        유저가 없습니다.
                      </td>
                    </tr>
                  ) : users.map((user, index) => (
                    <tr key={user.user_id} className="animate-fade-in transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40" style={staggerDelay(index)}>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-500 dark:text-slate-400">{user.user_id}</td>
                      <td className="px-4 py-2.5 text-xs font-medium text-slate-800 dark:text-slate-200">{user.username || '--'}</td>
                      <td className="px-4 py-2.5">
                        <Badge value={user.status} label={user.status_label} />
                      </td>
                      <td className="px-4 py-2.5">
                        {user.is_admin && <ShieldCheck size={14} className="text-primary-500" />}
                      </td>
                      <td className="px-4 py-2.5">
                        <EmailCell user={user} onUpdate={handleUpdate} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-xs text-slate-500 dark:text-slate-400">
                        {fmtDate(String(user.created_at))}
                      </td>
                      <td className="px-4 py-2.5">
                        <ActionButtons user={user} onUpdate={handleUpdate} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="block md:hidden">
              {users.length === 0 ? (
                <div className="px-4 py-10 text-center text-xs text-slate-400 dark:text-slate-500">
                  유저가 없습니다.
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3 p-3 min-[600px]:grid-cols-2">
                  {users.map((user, index) => (
                    <div key={user.user_id} className="animate-fade-in-up space-y-3 rounded-xl border border-slate-100 p-4 transition-colors hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/40" style={staggerDelay(index)}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-mono text-slate-500 dark:text-slate-400">{user.user_id}</span>
                        <div className="flex items-center gap-1">
                          {user.is_admin && <ShieldCheck size={12} className="text-primary-500" />}
                          <Badge value={user.status} label={user.status_label} />
                        </div>
                      </div>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{user.username || '--'}</span>
                        <span className="text-slate-400 dark:text-slate-500">{fmtDate(String(user.created_at))}</span>
                      </div>
                      <div className="flex flex-col gap-1 text-xs">
                        <span className="text-slate-400 dark:text-slate-500">매니저 이메일</span>
                        <EmailCell user={user} onUpdate={handleUpdate} />
                      </div>
                      <div className="border-t border-slate-100 pt-2 dark:border-slate-800/60">
                        <ActionButtons user={user} onUpdate={handleUpdate} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <p className="text-right text-xs text-slate-400 dark:text-slate-600">총 {users.length}명</p>
    </div>
  )
}

export default function Users() {
  return <UsersContent />
}
