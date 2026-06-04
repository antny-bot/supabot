import { useState } from 'react'
import { User, Mail, Save, CheckCircle2 } from 'lucide-react'

interface Props {
  initialUsername: string
  email: string
}

export default function ProfileSettingsCard({ initialUsername, email }: Props) {
  const [username, setUsername] = useState(initialUsername)
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSave() {
    setLoading(true)
    setError(null)
    setSaved(false)
    try {
      const res = await fetch('/api/me/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username }),
      })
      if (res.ok) {
        setSaved(true)
        setTimeout(() => setSaved(false), 3000)
        // Optionally reload page to update sidebar, but ideally AuthContext would update
        // For simplicity, we can suggest a refresh or trigger a state update if possible.
        // window.location.reload() 
      } else {
        const body = await res.json().catch(() => ({}))
        setError(body.error || '저장에 실패했습니다.')
      }
    } catch {
      setError('서버와 통신할 수 없습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center gap-2">
        <User size={18} className="text-indigo-500" />
        <h3 className="font-semibold text-slate-800 dark:text-slate-100">프로필 설정</h3>
      </div>

      <div className="p-5 space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
            <User size={14} className="text-slate-400" />
            이름
          </label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:focus:ring-indigo-400 transition-shadow"
            placeholder="홍길동"
          />
          <p className="text-xs text-slate-500 mt-1.5">대시보드 하단에 표시될 이름입니다.</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5 flex items-center gap-1.5">
            <Mail size={14} className="text-slate-400" />
            이메일
          </label>
          <input
            type="email"
            value={email}
            readOnly
            className="w-full px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-500 dark:text-slate-400 text-sm cursor-not-allowed"
          />
          <p className="text-xs text-slate-500 mt-1.5">이메일은 변경할 수 없습니다.</p>
        </div>

        {error && (
          <p className="text-xs text-rose-600 dark:text-rose-400 font-medium bg-rose-50 dark:bg-rose-900/20 p-2.5 rounded-lg border border-rose-100 dark:border-rose-900/30">
            {error}
          </p>
        )}

        <div className="pt-2">
          <button
            onClick={handleSave}
            disabled={loading || (username === initialUsername && !error)}
            className={`flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-medium transition-all ${
              saved 
                ? 'bg-emerald-500 text-white' 
                : 'bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 disabled:grayscale'
            }`}
          >
            {loading ? (
              '저장 중...'
            ) : saved ? (
              <><CheckCircle2 size={16} /> 저장됨</>
            ) : (
              <><Save size={16} /> 변경사항 저장</>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
