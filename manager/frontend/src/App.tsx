import type { ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import { useAuthContext } from './contexts/AuthContext'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Orders from './pages/Orders'
import Trades from './pages/Trades'
import Templates from './pages/Templates'
import Events from './pages/Events'
import Users from './pages/Users'
import Config from './pages/Config'
import Reports from './pages/Reports'

function AdminRoute({ children }: { children: ReactNode }) {
  const { user } = useAuthContext()
  if (!user?.is_admin) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/templates" element={<Templates />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/events" element={<AdminRoute><Events /></AdminRoute>} />
          <Route path="/users" element={<AdminRoute><Users /></AdminRoute>} />
          <Route path="/config" element={<AdminRoute><Config /></AdminRoute>} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
