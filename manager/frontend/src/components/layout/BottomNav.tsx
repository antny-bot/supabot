import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { useAuthContext } from '../../contexts/AuthContext'
import { APP_NAV_ITEMS } from '../../config/pageMeta'
import {
  MAX_PINNED,
  readDefaultPage,
  readNavOrder,
  type NavKey,
} from '../../lib/navPreferences'
import AllMenuDrawer from './AllMenuDrawer'

export default function BottomNav() {
  const { user } = useAuthContext()
  const isAdmin = user?.is_admin ?? false

  const [order, setOrder] = useState<NavKey[]>(() => readNavOrder())
  const [defaultPage, setDefaultPage] = useState<string | null>(() => readDefaultPage())
  const [showDrawer, setShowDrawer] = useState(false)

  useEffect(() => {
    function sync() {
      setOrder(readNavOrder())
      setDefaultPage(readDefaultPage())
    }
    window.addEventListener('sbm-navprefs-change', sync)
    return () => window.removeEventListener('sbm-navprefs-change', sync)
  }, [])

  // Top MAX_PINNED visible items from ordered list
  const pinnedItems = order
    .filter((key) => key !== 'config') // Hide Settings from mobile bottom nav
    .map((key) => APP_NAV_ITEMS.find((n) => n.key === key))
    .filter((item): item is NonNullable<typeof item> =>
      !!item && (!item.adminOnly || isAdmin),
    )
    .slice(0, MAX_PINNED)

  return (
    <>
      <nav className="safe-bottom fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90 md:hidden">
        <div className="flex">
          {pinnedItems.map(({ to, compactLabel, Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `min-h-[56px] flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-app-caption font-medium transition-colors ${
                  isActive
                    ? 'text-primary-600 dark:text-primary-400'
                    : 'text-slate-500 dark:text-slate-500'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <div className={`rounded-xl p-1.5 transition-colors ${isActive ? 'bg-primary-50 dark:bg-primary-900/30' : ''}`}>
                    <Icon size={20} />
                  </div>
                  {compactLabel}
                </>
              )}
            </NavLink>
          ))}

          {/* 전체 button */}
          <button
            onClick={() => setShowDrawer(true)}
            className="min-h-[56px] flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-app-caption font-medium transition-colors text-slate-500 dark:text-slate-500"
          >
            <div className="rounded-xl p-1.5">
              <Menu size={20} />
            </div>
            전체
          </button>
        </div>
      </nav>

      {showDrawer && (
        <AllMenuDrawer
          order={order}
          defaultPage={defaultPage}
          isAdmin={isAdmin}
          onOrderChange={setOrder}
          onDefaultChange={setDefaultPage}
          onClose={() => setShowDrawer(false)}
        />
      )}
    </>
  )
}
