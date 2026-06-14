import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import BottomNav from './BottomNav'
import { useAuth } from '../../hooks/useAuth'
import { AuthContext } from '../../contexts/AuthContext'
import Spinner from '../ui/Spinner'

export default function AppLayout() {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="font-app-ui min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center">
        <Spinner />
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
