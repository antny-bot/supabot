import { useEffect, useRef, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { LogOut, Menu, Moon, Settings, ShieldCheck, Sun, Zap } from 'lucide-react'
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
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => { writeCollapsed(collapsed) }, [collapsed])

  // Close popup on outside click
  useEffect(() => {
    if (!menuOpen) return
    function handler(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

  // config and admin are only accessible via the bottom settings popup
  const NAV_POPUP_KEYS = new Set(['config', 'admin'])
  const visibleItems = APP_NAV_ITEMS.filter(
    (item) => !NAV_POPUP_KEYS.has(item.key) && (!item.adminOnly || user?.is_admin),
  )

  async function handleLogout() {
    setMenuOpen(false)
    await fetch('/api/logout', { method: 'POST', credentials: 'include' })
    navigate('/login', { replace: true })
  }

  const displayName = user?.username || user?.email || ''

  return (
    <aside
      className={`hidden md:flex flex-col shrink-0 h-screen sticky top-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-all duration-200 overflow-visible ${
        collapsed ? 'w-16' : 'w-56'
      }`}
    >
      {/* Header: logo + hamburger toggle */}
      <div className={`flex h-14 items-center border-b border-slate-200 dark:border-slate-800 shrink-0 px-3 gap-2 ${collapsed ? 'justify-center' : ''}`}>
        {!collapsed && (
          <NavLink
            to="/dashboard"
            className="flex items-center gap-2 font-bold text-slate-900 dark:text-white min-w-0 flex-1"
          >
            <div className="shrink-0 rounded-lg bg-indigo-600 p-1.5">
              <Zap size={14} className="text-white" />
            </div>
            <span className="text-app-body-sm whitespace-nowrap truncate">supabot</span>
          </NavLink>
        )}
        <button
          onClick={() => setCollapsed((v) => !v)}
          className="shrink-0 rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition-colors"
          title={collapsed ? '메뉴 펼치기' : '메뉴 접기'}
        >
          <Menu size={16} />
        </button>
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
            {!collapsed && (
              <span className="truncate flex items-center gap-1">
                {item.label}
                {item.key === 'analytics' && <ShieldCheck size={12} className="text-slate-400 dark:text-slate-500" />}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom: user + settings popup trigger */}
      <div className="shrink-0 border-t border-slate-200 dark:border-slate-800 px-2 py-3 relative" ref={menuRef}>
        {/* Settings popup — slides up above this area */}
        {menuOpen && (
          <div className="absolute bottom-full left-2 right-2 mb-1 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-lg overflow-hidden z-50">
            {/* Theme row */}
            <div className="flex items-center gap-1 px-3 py-2 border-b border-slate-100 dark:border-slate-800">
              <span className="text-xs text-slate-500 dark:text-slate-400 flex-1">
                {collapsed ? '' : '테마'}
              </span>
              <button
                onClick={() => { toggleTheme() }}
                title={isDark ? '라이트 모드' : '다크 모드'}
                className={`rounded-lg p-1.5 transition-colors ${
                  !isDark
                    ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400'
                    : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800'
                }`}
              >
                <Sun size={15} />
              </button>
              <button
                onClick={() => { toggleTheme() }}
                title={isDark ? '라이트 모드' : '다크 모드'}
                className={`rounded-lg p-1.5 transition-colors ${
                  isDark
                    ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400'
                    : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800'
                }`}
              >
                <Moon size={15} />
              </button>
            </div>

            {/* Settings link */}
            <NavLink
              to="/config"
              onClick={() => setMenuOpen(false)}
              className="flex items-center gap-2.5 px-3 py-2.5 text-app-body-sm text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              <Settings size={15} className="shrink-0 text-slate-500 dark:text-slate-400" />
              설정
            </NavLink>

            {/* Admin link — admin only */}
            {user?.is_admin && (
              <NavLink
                to="/admin"
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-2.5 px-3 py-2.5 text-app-body-sm text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
              >
                <ShieldCheck size={15} className="shrink-0 text-slate-500 dark:text-slate-400" />
                관리자 메뉴
              </NavLink>
            )}

            {/* Logout */}
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-2.5 px-3 py-2.5 text-app-body-sm text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-900/20 transition-colors border-t border-slate-100 dark:border-slate-800"
            >
              <LogOut size={15} className="shrink-0" />
              로그아웃
            </button>
          </div>
        )}

        {/* User row */}
        <button
          onClick={() => setMenuOpen((v) => !v)}
          className={`w-full flex items-center gap-2.5 rounded-xl px-2 py-2 transition-colors hover:bg-slate-100 dark:hover:bg-slate-800 ${
            collapsed ? 'justify-center' : ''
          } ${menuOpen ? 'bg-slate-100 dark:bg-slate-800' : ''}`}
          title={collapsed ? displayName : undefined}
        >
          <div className="shrink-0 h-7 w-7 rounded-full bg-indigo-100 dark:bg-indigo-900/40 flex items-center justify-center">
            <span className="text-xs font-bold text-indigo-600 dark:text-indigo-400">
              {displayName.slice(0, 1).toUpperCase() || '?'}
            </span>
          </div>
          {!collapsed && (
            <>
              <span className="flex-1 text-left text-app-body-sm font-medium text-slate-700 dark:text-slate-200 truncate min-w-0">
                {displayName}
              </span>
              <Settings size={14} className="shrink-0 text-slate-400 dark:text-slate-500" />
            </>
          )}
        </button>
      </div>
    </aside>
  )
}
