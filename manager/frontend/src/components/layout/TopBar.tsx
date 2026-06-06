import { useNavigate } from 'react-router-dom'
import { LogOut, Moon, Sun, Zap } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useTheme } from '../../hooks/useTheme'
import { useAuthContext } from '../../contexts/AuthContext'

export default function TopBar() {
  const { isDark, toggle } = useTheme()
  const navigate = useNavigate()
  const { user: _user } = useAuthContext()

  async function handleLogout() {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' })
    navigate('/login', { replace: true })
  }

  return (
    <header className="md:hidden sticky top-0 z-40 border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
      <div className="flex h-14 items-center gap-3 px-4">
        <NavLink to="/dashboard" className="flex items-center gap-2 font-bold text-slate-900 dark:text-white">
          <div className="rounded-lg bg-indigo-600 p-1.5">
            <Zap size={14} className="text-white" />
          </div>
          <span className="text-app-body-sm">supabot</span>
        </NavLink>

        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={toggle}
            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            title={isDark ? '라이트 모드' : '다크 모드'}
          >
            {isDark ? <Sun size={16} /> : <Moon size={16} />}
          </button>

          <button
            onClick={handleLogout}
            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-rose-50 hover:text-rose-600 dark:text-slate-400 dark:hover:bg-rose-900/20 dark:hover:text-rose-400"
            title="로그아웃"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </header>
  )
}
