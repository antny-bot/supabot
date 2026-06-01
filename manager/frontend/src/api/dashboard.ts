import { api } from './client'
import type { DashboardData } from '../types'

export const fetchDashboard = () => api.get<DashboardData>('/api/dashboard')
