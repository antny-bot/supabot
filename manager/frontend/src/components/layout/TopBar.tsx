import { NavLink, useNavigate } from 'react-router-dom'
import { LogOut, Moon, Settings, Sun, Zap } from 'lucide-react'
import { APP_NAV_ITEMS } from '../../config/pageMeta'
import { useAuthContext } from '../../contexts/AuthContext'
import { useTheme } from '../../hooks/useTheme'

export default function TopBar() {
  const { isDark, toggle } = useTheme()
  const navigate = useNavigate()
  const { user } = useAuthContext()

  const visibleItems = APP_NAV_ITEMS.filter((item) => !item.adminOnly || user?.is_admin)

  async function handleLogout() {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' })
    navigate('/login', { replace: true })
  }

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-900/80">
      <div className="mx-auto flex h-14 max-w-screen-xl items-center gap-6 px-4">
        <NavLink to="/dashboard" className="flex shrink-0 items-center gap-2 font-bold text-slate-900 dark:text-white">
          <div className="rounded-lg bg-indigo-600 p-1.5">
            <Zap size={14} className="text-white" />
          </div>
          <span className="text-sm">supabot</span>
        </NavLink>

        <nav className="hidden flex-1 items-center gap-0.5 md:flex">
          {visibleItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `rounded-lg px-3 py-1.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-indigo-50 font-medium text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1">
          <NavLink
            to="/config"
            className={({ isActive }) =>
              `rounded-lg p-2 transition-colors ${
                isActive
                  ? 'text-indigo-600 dark:text-indigo-400'
                  : 'text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
              }`
            }
            title="설정"
          >
            <Settings size={16} />
          </NavLink>

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
