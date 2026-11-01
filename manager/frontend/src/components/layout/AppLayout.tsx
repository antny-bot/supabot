import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import BottomNav from './BottomNav'
import { useAuth } from '../../hooks/useAuth'
import { AuthContext } from '../../contexts/AuthContext'
import { PageSkeleton, Skeleton } from '../ui/Skeleton'

export default function AppLayout() {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="font-app-ui min-h-screen bg-slate-50 dark:bg-slate-950 flex">
        {/* Desktop sidebar skeleton */}
        <aside className="hidden md:flex flex-col w-[150px] shrink-0 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3 space-y-4">
          <div className="flex items-center gap-2 px-1 py-2">
            <Skeleton className="h-6 w-6 rounded-lg" />
            <Skeleton className="h-5 w-20" />
          </div>
          <div className="space-y-2 pt-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex items-center gap-2.5 px-2 py-2">
                <Skeleton className="h-4 w-4 rounded" />
                <Skeleton className="h-3.5 w-16" />
              </div>
            ))}
          </div>
        </aside>

        {/* Main column */}
        <div className="flex flex-col flex-1 min-w-0">
          {/* Mobile top bar skeleton */}
          <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
            <div className="flex items-center gap-2">
              <Skeleton className="h-6 w-6 rounded-lg" />
              <Skeleton className="h-5 w-20" />
            </div>
            <Skeleton className="h-7 w-7 rounded-full" />
          </div>

          <main className="flex-1 px-4 py-5 pb-24 md:pb-8 md:px-6 max-w-screen-xl w-full">
            <PageSkeleton />
          </main>
        </div>
      </div>
    )
  }

  return (
    <AuthContext.Provider value={{ user, loading }}>
      <div className="font-app-ui min-h-screen bg-slate-50 dark:bg-slate-950 flex">
        {/* Desktop sidebar */}
        <Sidebar />

        {/* Main column */}
        <div className="flex flex-col flex-1 min-w-0">
          {/* Mobile top bar */}
          <TopBar />

          <main className="flex-1 px-4 py-5 pb-24 md:pb-8 md:px-6 max-w-screen-xl w-full">
            <div key={location.pathname} className="animate-fade-in-up">
              <Outlet />
            </div>
          </main>
        </div>

        {/* Mobile bottom nav */}
        <BottomNav />
      </div>
    </AuthContext.Provider>
  )
}
