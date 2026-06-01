import { Outlet } from 'react-router-dom'
import TopBar from './TopBar'
import BottomNav from './BottomNav'
import { useAuth } from '../../hooks/useAuth'
import Spinner from '../ui/Spinner'

export default function AppLayout() {
  const { loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col">
      <TopBar />
      <main className="flex-1 max-w-screen-xl mx-auto w-full px-4 py-5 pb-24 md:pb-6">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  )
}
