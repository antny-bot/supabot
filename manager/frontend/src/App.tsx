import type { ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import { useAuthContext } from './contexts/AuthContext'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Orders from './pages/Orders'
import Trades from './pages/Trades'
import Templates from './pages/Templates'
import Config from './pages/Config'
import Reports from './pages/Reports'
import Admin from './pages/Admin'
import { readDefaultPage } from './lib/navPreferences'

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
        <Route path="/login" element={<Login />} />
        <Route element={<AppLayout />}>
          <Route index element={<DefaultRedirect />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/templates" element={<Templates />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/admin" element={<AdminRoute><Admin /></AdminRoute>} />
          <Route path="/events" element={<Navigate to="/admin" replace />} />
          <Route path="/users" element={<Navigate to="/admin" replace />} />
          <Route path="/config" element={<Config />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
