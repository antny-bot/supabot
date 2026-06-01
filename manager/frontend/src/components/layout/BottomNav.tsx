import { NavLink } from 'react-router-dom'
import { LayoutDashboard, ClipboardList, ArrowLeftRight, Activity, Users } from 'lucide-react'

const TABS = [
  { to: '/dashboard', label: '대시보드', Icon: LayoutDashboard },
  { to: '/orders',    label: '주문',     Icon: ClipboardList },
  { to: '/trades',    label: '거래',     Icon: ArrowLeftRight },
  { to: '/events',    label: '이벤트',   Icon: Activity },
  { to: '/users',     label: '유저',     Icon: Users },
]

export default function BottomNav() {
  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-white/90 dark:bg-slate-900/90 backdrop-blur border-t border-slate-200 dark:border-slate-800 safe-bottom">
      <div className="flex">
        {TABS.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center justify-center py-2 gap-0.5 text-[10px] font-medium transition-colors min-h-[56px] ${
                isActive
                  ? 'text-indigo-600 dark:text-indigo-400'
                  : 'text-slate-500 dark:text-slate-500'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <div className={`p-1.5 rounded-xl transition-colors ${isActive ? 'bg-indigo-50 dark:bg-indigo-900/30' : ''}`}>
                  <Icon size={20} />
                </div>
                {label}
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
