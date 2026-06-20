import { Suspense, lazy, type ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import Spinner from './components/ui/Spinner'
import { useAuthContext } from './contexts/AuthContext'
import { readDefaultPage } from './lib/navPreferences'

const Login = lazy(() => import('./pages/Login'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Orders = lazy(() => import('./pages/Orders'))
const Trades = lazy(() => import('./pages/Trades'))
const Templates = lazy(() => import('./pages/Templates'))
const Config = lazy(() => import('./pages/Config'))
const Reports = lazy(() => import('./pages/Reports'))
const Admin = lazy(() => import('./pages/Admin'))
const Analytics = lazy(() => import('./pages/Analytics'))

function RouteFallback() {
  return (
    <div className="font-app-ui flex min-h-[40vh] items-center justify-center">
      <div className="flex flex-col items-center gap-3 text-slate-500 dark:text-slate-400">
        <Spinner className="py-0" />
        <span className="text-app-body-sm">Loading…</span>
      </div>
    </div>
  )
}

function withRouteFallback(node: ReactNode) {
  return <Suspense fallback={<RouteFallback />}>{node}</Suspense>
}

function AdminRoute({ children }: { children: ReactNode }) {
  const { user } = useAuthContext()
  if (!user?.is_admin) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

function DefaultRedirect() {
  const target = readDefaultPage() || '/dashboard'
  return <Navigate to={target} replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={withRouteFallback(<Login />)} />
        <Route element={<AppLayout />}>
          <Route index element={<DefaultRedirect />} />
          <Route path="/dashboard" element={withRouteFallback(<Dashboard />)} />
          <Route path="/orders" element={withRouteFallback(<Orders />)} />
          <Route path="/trades" element={withRouteFallback(<Trades />)} />
          <Route path="/templates" element={withRouteFallback(<Templates />)} />
          <Route path="/reports" element={withRouteFallback(<Reports />)} />
          <Route path="/admin" element={withRouteFallback(<AdminRoute><Admin /></AdminRoute>)} />
          <Route path="/analytics" element={withRouteFallback(<AdminRoute><Analytics /></AdminRoute>)} />
          <Route path="/events" element={<Navigate to="/admin" replace />} />
          <Route path="/users" element={<Navigate to="/admin" replace />} />
          <Route path="/config" element={withRouteFallback(<Config />)} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
