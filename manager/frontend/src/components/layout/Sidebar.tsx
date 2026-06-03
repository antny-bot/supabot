import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, LogOut, Moon, Settings, Sun, Zap } from 'lucide-react'
import { APP_NAV_ITEMS } from '../../config/pageMeta'
import { useAuthContext } from '../../contexts/AuthContext'
import { useTheme } from '../../hooks/useTheme'

const COLLAPSED_KEY = 'sbm_sidebar_collapsed'

function readCollapsed(): boolean {
  try { return localStorage.getItem(COLLAPSED_KEY) === '1' } catch { return false }
}
function writeCollapsed(v: boolean) {
  try { localStorage.setItem(COLLAPSED_KEY, v ? '1' : '0') } catch {}
}

export default function Sidebar() {
  const { user } = useAuthContext()
  const { isDark, toggle: toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(readCollapsed)

  useEffect(() => { writeCollapsed(collapsed) }, [collapsed])

  const visibleItems = APP_NAV_ITEMS.filter((item) => !item.adminOnly || user?.is_admin)

  async function handleLogout() {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' })
    navigate('/login', { replace: true })
  }

  return (
    <aside
      className={`hidden md:flex flex-col shrink-0 h-screen sticky top-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-all duration-200 ${
        collapsed ? 'w-16' : 'w-56'
      }`}
    >
      {/* Logo */}
      <div className={`flex h-14 items-center border-b border-slate-200 dark:border-slate-800 shrink-0 ${collapsed ? 'justify-center px-0' : 'gap-2 px-4'}`}>
        <NavLink to="/dashboard" className="flex items-center gap-2 font-bold text-slate-900 dark:text-white">
          <div className="shrink-0 rounded-lg bg-indigo-600 p-1.5">
            <Zap size={14} className="text-white" />
          </div>
          {!collapsed && <span className="text-app-body-sm whitespace-nowrap">supabot</span>}
        </NavLink>
      </div>

      {/* Nav items */}
      <nav className="flex-1 overflow-y-auto py-3 space-y-0.5 px-2">
        {visibleItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-2.5 py-2 text-app-body-sm font-medium transition-colors ${
                isActive
                  ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
              } ${collapsed ? 'justify-center' : ''}`
            }
          >
            <item.Icon size={18} className="shrink-0" />
            {!collapsed && <span className="truncate">{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Bottom actions */}
      <div className={`shrink-0 border-t border-slate-200 dark:border-slate-800 py-3 px-2 space-y-0.5`}>
        <NavLink
          to="/config"
          title={collapsed ? '설정' : undefined}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-xl px-2.5 py-2 text-app-body-sm font-medium transition-colors ${
              isActive
                ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
            } ${collapsed ? 'justify-center' : ''}`
          }
        >
          <Settings size={18} className="shrink-0" />
          {!collapsed && <span>설정</span>}
        </NavLink>

        <button
          onClick={toggleTheme}
          title={collapsed ? (isDark ? '라이트 모드' : '다크 모드') : undefined}
          className={`w-full flex items-center gap-3 rounded-xl px-2.5 py-2 text-app-body-sm font-medium transition-colors text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200 ${collapsed ? 'justify-center' : ''}`}
        >
          {isDark ? <Sun size={18} className="shrink-0" /> : <Moon size={18} className="shrink-0" />}
          {!collapsed && <span>{isDark ? '라이트 모드' : '다크 모드'}</span>}
        </button>

        <button
          onClick={handleLogout}
          title={collapsed ? '로그아웃' : undefined}
          className={`w-full flex items-center gap-3 rounded-xl px-2.5 py-2 text-app-body-sm font-medium transition-colors text-slate-600 hover:bg-rose-50 hover:text-rose-600 dark:text-slate-400 dark:hover:bg-rose-900/20 dark:hover:text-rose-400 ${collapsed ? 'justify-center' : ''}`}
        >
          <LogOut size={18} className="shrink-0" />
          {!collapsed && <span>로그아웃</span>}
        </button>
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed((v) => !v)}
        className="absolute -right-3 top-16 hidden md:flex h-6 w-6 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 shadow-sm transition-colors hover:bg-slate-50 hover:text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800"
        title={collapsed ? '메뉴 펼치기' : '메뉴 접기'}
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>
    </aside>
  )
}
