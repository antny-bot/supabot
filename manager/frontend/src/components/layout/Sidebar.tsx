import { useEffect, useRef, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { LogOut, Menu, Moon, Settings, ShieldCheck, Sun, Zap, MessageSquarePlus } from 'lucide-react'
import { APP_NAV_ITEMS } from '../../config/pageMeta'
import { useAuthContext } from '../../contexts/AuthContext'
import FeedbackModal from '../feedback/FeedbackModal'
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
  const [feedbackOpen, setFeedbackOpen] = useState(false)
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

  // config is only accessible via the bottom settings popup
  const NAV_POPUP_KEYS = new Set(['config'])
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
      className={`hidden md:flex flex-col shrink-0 h-screen sticky top-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 transition-all duration-200 overflow-visible z-30 ${
        collapsed ? 'w-14' : 'w-[150px]'
      }`}
    >
      {/* Header: logo + hamburger toggle */}
      <div className={`flex h-14 items-center border-b border-slate-200 dark:border-slate-800 shrink-0 px-2.5 gap-1.5 ${collapsed ? 'justify-center' : ''}`}>
        {!collapsed && (
          <NavLink
            to="/dashboard"
            className="flex items-center gap-1.5 font-bold text-slate-900 dark:text-white min-w-0 flex-1"
          >
            <div className="shrink-0 rounded-lg bg-primary-600 p-1">
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
      <nav className="flex-1 overflow-y-auto py-3 space-y-0.5 px-1.5">
        {visibleItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-2 rounded-xl px-2 py-2 text-app-body-sm font-medium whitespace-nowrap break-keep transition-colors ${
                isActive
                  ? 'bg-primary-50 text-primary-600 dark:bg-primary-900/30 dark:text-primary-400'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200'
              } ${collapsed ? 'justify-center' : ''}`
            }
          >
            <item.Icon size={17} className="shrink-0" />
            {!collapsed && (
              <>
                <span className="truncate">{item.label}</span>
                {item.key === 'analytics' && (
                  <ShieldCheck size={12} className="ml-auto shrink-0 text-slate-400 dark:text-slate-500" />
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom Profile / Settings Area */}
      <div className="relative border-t border-slate-200 dark:border-slate-800 p-2 shrink-0" ref={menuRef}>
        {/* Popover Menu */}
        {menuOpen && (
          <div
            className="absolute bottom-full left-2 mb-2 w-52 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl p-1.5 z-50 text-app-body-sm animate-fade-in-up"
          >
            {/* 설정 링크 */}
            <NavLink
              to="/config"
              onClick={() => setMenuOpen(false)}
              className="w-full flex items-center gap-2.5 rounded-xl px-3 py-2 text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors whitespace-nowrap"
            >
              <Settings size={15} />
              <span>설정</span>
            </NavLink>

            <div className="my-1 border-t border-slate-100 dark:border-slate-800" />

            {/* 테마 셀렉터 */}
            <div className="flex items-center justify-between px-3 py-1.5">
              <span className="text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">테마</span>
              <div className="flex items-center gap-0.5 rounded-lg bg-slate-100 dark:bg-slate-800 p-0.5">
                <button
                  type="button"
                  onClick={() => toggleTheme()}
                  className={`rounded-md p-1 transition-colors ${
                    !isDark
                      ? 'bg-white text-primary-600 shadow-sm dark:bg-slate-700 font-semibold'
                      : 'text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                  }`}
                  title="라이트 모드"
                >
                  <Sun size={13} />
                </button>
                <button
                  type="button"
                  onClick={() => toggleTheme()}
                  className={`rounded-md p-1 transition-colors ${
                    isDark
                      ? 'bg-white text-primary-600 shadow-sm dark:bg-slate-700 font-semibold'
                      : 'text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
                  }`}
                  title="다크 모드"
                >
                  <Moon size={13} />
                </button>
              </div>
            </div>

            <div className="my-1 border-t border-slate-100 dark:border-slate-800" />

            {/* 피드백 보내기 버튼 */}
            <div
              onClick={() => {
                setMenuOpen(false)
                setFeedbackOpen(true)
              }}
              className="flex items-center justify-between px-3 py-1.5 rounded-xl cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors group"
            >
              <span className="text-xs text-slate-500 dark:text-slate-400 group-hover:text-slate-700 dark:group-hover:text-slate-200 whitespace-nowrap">피드백</span>
              <div className="flex items-center rounded-lg bg-slate-100 dark:bg-slate-800 p-0.5">
                <button
                  type="button"
                  tabIndex={-1}
                  className="rounded-md p-1 text-slate-400 group-hover:text-primary-600 dark:text-slate-400 dark:group-hover:text-primary-400 group-hover:bg-white dark:group-hover:bg-slate-700 group-hover:shadow-sm transition-colors"
                  title="피드백 보내기"
                >
                  <MessageSquarePlus size={13} />
                </button>
              </div>
            </div>

            <div className="my-1 border-t border-slate-100 dark:border-slate-800" />

            {/* 로그아웃 버튼 */}
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-2.5 rounded-xl px-3 py-2 text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors whitespace-nowrap"
            >
              <LogOut size={15} />
              <span>로그아웃</span>
            </button>
          </div>
        )}

        {/* Profile Bar */}
        <button
          onClick={() => setMenuOpen((v) => !v)}
          className={`w-full flex items-center gap-2.5 rounded-xl px-2 py-2 transition-colors hover:bg-slate-100 dark:hover:bg-slate-800 ${
            collapsed ? 'justify-center px-0' : ''
          } ${menuOpen ? 'bg-slate-100 dark:bg-slate-800' : ''}`}
          title={collapsed ? displayName : undefined}
        >
          <div className="shrink-0 h-7 w-7 rounded-full bg-primary-100 dark:bg-primary-900/40 flex items-center justify-center">
            <span className="text-xs font-bold text-primary-600 dark:text-primary-400">
              {displayName.slice(0, 1).toUpperCase() || '?'}
            </span>
          </div>
          {!collapsed && (
            <>
              <span className="flex-1 text-left text-xs font-normal text-slate-700 dark:text-slate-200 truncate min-w-0">
                {displayName}
              </span>
              <Settings size={14} className="shrink-0 text-slate-400 dark:text-slate-500" />
            </>
          )}
        </button>
      </div>
      {/* 피드백 모달 */}
      <FeedbackModal isOpen={feedbackOpen} onClose={() => setFeedbackOpen(false)} />
    </aside>
  )
}
