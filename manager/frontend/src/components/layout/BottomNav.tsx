import { NavLink } from 'react-router-dom'
import { useAuthContext } from '../../contexts/AuthContext'
import { APP_NAV_ITEMS } from '../../config/pageMeta'

export default function BottomNav() {
  const { user } = useAuthContext()
  const visibleTabs = APP_NAV_ITEMS.filter((tab) => !tab.adminOnly || user?.is_admin)

  return (
    <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90 md:hidden">
      <div className="flex">
        {visibleTabs.map(({ to, compactLabel, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `min-h-[56px] flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-medium transition-colors ${
                isActive
                  ? 'text-indigo-600 dark:text-indigo-400'
                  : 'text-slate-500 dark:text-slate-500'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <div className={`rounded-xl p-1.5 transition-colors ${isActive ? 'bg-indigo-50 dark:bg-indigo-900/30' : ''}`}>
                  <Icon size={20} />
                </div>
                {compactLabel}
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
