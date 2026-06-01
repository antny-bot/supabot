import { useEffect, useState, useCallback } from 'react'
import { ShieldCheck } from 'lucide-react'
import { fetchUsers, approveUser, deactivateUser, activateUser, blockUser, deleteUser } from '../api/users'
import type { User } from '../types'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import FilterBar from '../components/ui/FilterBar'
import Spinner from '../components/ui/Spinner'
import ErrorBanner from '../components/ui/ErrorBanner'

const STATUS_OPTIONS = [
  { value: '',         label: '전체' },
  { value: 'pending',  label: '대기' },
  { value: 'active',   label: '활성' },
  { value: 'inactive', label: '비활성' },
  { value: 'blocked',  label: '차단' },
  { value: 'deleted',  label: '삭제' },
]

function fmtDate(s: string) {
  return s ? s.slice(0, 10) : '—'
}

interface ActionButtonsProps {
  user: User
  onUpdate: (updated: User) => void
}

function ActionButtons({ user, onUpdate }: ActionButtonsProps) {
  const [busy, setBusy] = useState(false)

  async function run(action: () => Promise<User>) {
    setBusy(true)
    try {
      const updated = await action()
      onUpdate(updated)
    } finally {
      setBusy(false)
    }
  }

  const s = user.status
  return (
    <div className="flex flex-wrap gap-1">
      {s === 'pending' && (
        <Button variant="success" disabled={busy} onClick={() => run(() => approveUser(user.user_id))}>승인</Button>
      )}
      {s === 'inactive' && (
        <Button variant="success" disabled={busy} onClick={() => run(() => activateUser(user.user_id))}>활성화</Button>
      )}
      {s === 'active' && (
        <Button variant="ghost" disabled={busy} onClick={() => run(() => deactivateUser(user.user_id))}>비활성</Button>
      )}
      {(s === 'pending' || s === 'active' || s === 'inactive') && (
        <Button variant="warning" disabled={busy} onClick={() => run(() => blockUser(user.user_id))}>차단</Button>
      )}
      {s === 'blocked' && (
        <Button variant="ghost" disabled={busy} onClick={() => run(() => activateUser(user.user_id))}>차단해제</Button>
      )}
      {s !== 'deleted' && !user.is_admin && (
        <Button
          variant="danger"
          disabled={busy}
          onClick={() => {
            if (window.confirm(`${user.username || user.user_id} 를 삭제하시겠습니까?`)) {
              void run(() => deleteUser(user.user_id))
            }
          }}
        >
          삭제
        </Button>
      )}
    </div>
  )
}

export default function Users() {
  const [users, setUsers] = useState<User[]>([])
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchUsers(statusFilter)
      .then(setUsers)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '오류 발생'))
      .finally(() => setLoading(false))
  }, [statusFilter])

  const handleUpdate = useCallback((updated: User) => {
    setUsers((prev) => prev.map((u) => (u.user_id === updated.user_id ? updated : u)))
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">유저 관리</h1>
      </div>

      <FilterBar options={STATUS_OPTIONS} value={statusFilter} onChange={setStatusFilter} />

      {error && <ErrorBanner message={error} />}

      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        {loading ? (
          <Spinner />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800">
                  <th className="px-4 py-3 text-left font-medium">유저 ID</th>
                  <th className="px-4 py-3 text-left font-medium">이름</th>
                  <th className="px-4 py-3 text-left font-medium">상태</th>
                  <th className="px-4 py-3 text-left font-medium">관리자</th>
                  <th className="px-4 py-3 text-left font-medium whitespace-nowrap">가입일</th>
                  <th className="px-4 py-3 text-left font-medium">액션</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-slate-400 dark:text-slate-500 text-xs">
                      유저 없음
                    </td>
                  </tr>
                ) : users.map((u) => (
                  <tr key={u.user_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-2.5 font-mono text-xs text-slate-500 dark:text-slate-400">
                      {u.user_id}
                    </td>
                    <td className="px-4 py-2.5 text-slate-800 dark:text-slate-200 font-medium text-xs">
                      {u.username || '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge value={u.status} label={u.status_label} />
                    </td>
                    <td className="px-4 py-2.5">
                      {u.is_admin && (
                        <ShieldCheck size={14} className="text-indigo-500" />
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-slate-500 dark:text-slate-400 text-xs whitespace-nowrap">
                      {fmtDate(String(u.created_at))}
                    </td>
                    <td className="px-4 py-2.5">
                      <ActionButtons user={u} onUpdate={handleUpdate} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="text-xs text-slate-400 dark:text-slate-600 text-right">총 {users.length}명</p>
    </div>
  )
}
