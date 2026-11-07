import { Suspense, lazy, type ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import { PageSkeleton } from './components/ui/Skeleton'
import { useAuthContext } from './contexts/AuthContext'
import { ToastProvider } from './contexts/ToastContext'
import { readDefaultPage } from './lib/navPreferences'

const Login = lazy(() => import('./pages/Login'))
const Home = lazy(() => import('./pages/Home'))
const Privacy = lazy(() => import('./pages/Privacy'))
const Terms = lazy(() => import('./pages/Terms'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Operations = lazy(() => import('./pages/Operations'))
const Orders = lazy(() => import('./pages/Orders'))
const Trades = lazy(() => import('./pages/Trades'))
const Templates = lazy(() => import('./pages/Templates'))
const Config = lazy(() => import('./pages/Config'))
const Reports = lazy(() => import('./pages/Reports'))
const Admin = lazy(() => import('./pages/Admin'))

function RouteFallback() {
  return (
    <div className="font-app-ui space-y-4">
      <span className="sr-only">Loading…</span>
      <PageSkeleton />
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
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/home" element={withRouteFallback(<Home />)} />
          <Route path="/privacy" element={withRouteFallback(<Privacy />)} />
          <Route path="/privacy-policy" element={<Navigate to="/privacy" replace />} />
          <Route path="/terms" element={withRouteFallback(<Terms />)} />
          <Route path="/terms-of-service" element={<Navigate to="/terms" replace />} />
          <Route path="/login" element={withRouteFallback(<Login />)} />
          <Route element={<AppLayout />}>
            <Route index element={<DefaultRedirect />} />
            <Route path="/dashboard" element={withRouteFallback(<Dashboard />)} />
            <Route path="/operations" element={withRouteFallback(<Operations />)} />
            <Route path="/strategy-monitor" element={<Navigate to="/operations" replace />} />
            <Route path="/orders" element={withRouteFallback(<Orders />)} />
            <Route path="/trades" element={withRouteFallback(<Trades />)} />
            <Route path="/templates" element={withRouteFallback(<Templates />)} />
            <Route path="/reports" element={withRouteFallback(<Reports />)} />
            <Route path="/admin" element={withRouteFallback(<AdminRoute><Admin /></AdminRoute>)} />
            <Route path="/analytics" element={<Navigate to="/admin" replace />} />
            <Route path="/events" element={<Navigate to="/admin" replace />} />
            <Route path="/users" element={<Navigate to="/admin" replace />} />
            <Route path="/config" element={withRouteFallback(<Config />)} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  )
}
