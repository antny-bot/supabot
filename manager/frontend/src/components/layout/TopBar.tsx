import { NavLink, useNavigate } from 'react-router-dom'
import { Zap, Sun, Moon, LogOut, Settings } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import { useAuthContext } from '../../contexts/AuthContext'

const NAV_ITEMS = [
  { to: '/dashboard', label: '대시보드', adminOnly: false },
  { to: '/orders',    label: '주문 현황', adminOnly: false },
  { to: '/trades',    label: '거래 내역', adminOnly: false },
  { to: '/reports',   label: '리포트',   adminOnly: false },
  { to: '/events',    label: '이벤트',   adminOnly: true },
  { to: '/users',     label: '유저 관리', adminOnly: true },
]

export default function TopBar() {
  const { isDark, toggle } = useTheme()
  const navigate = useNavigate()
  const { user } = useAuthContext()

  const visibleItems = NAV_ITEMS.filter((item) => !item.adminOnly || user?.is_admin)

  async function handleLogout() {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' })
    navigate('/login', { replace: true })
  }

  return (
    <header className="sticky top-0 z-40 bg-white/80 dark:bg-slate-900/80 backdrop-blur border-b border-slate-200 dark:border-slate-800">
      <div className="max-w-screen-xl mx-auto px-4 h-14 flex items-center gap-6">
        {/* Logo */}
        <NavLink to="/dashboard" className="flex items-center gap-2 font-bold text-slate-900 dark:text-white shrink-0">
          <div className="bg-indigo-600 rounded-lg p-1.5">
            <Zap size={14} className="text-white" />
          </div>
          <span className="text-sm">supabot</span>
        </NavLink>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-0.5 flex-1">
          {visibleItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 font-medium'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Actions */}
        <div className="ml-auto flex items-center gap-1">
          {user?.is_admin && (
            <NavLink
              to="/config"
              className={({ isActive }) =>
                `p-2 rounded-lg transition-colors ${
                  isActive
                    ? 'text-indigo-600 dark:text-indigo-400'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800'
                }`
              }
              title="시스템 설정"
            >
              <Settings size={16} />
            </NavLink>
          )}

          <button
            onClick={toggle}
            className="p-2 rounded-lg text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title={isDark ? '라이트 모드' : '다크 모드'}
          >
            {isDark ? <Sun size={16} /> : <Moon size={16} />}
          </button>

          <button
            onClick={handleLogout}
            className="p-2 rounded-lg text-slate-500 dark:text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-900/20 transition-colors"
            title="로그아웃"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </header>
  )
}
