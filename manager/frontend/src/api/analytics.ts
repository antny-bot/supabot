import { api } from './client'
import type {
  AnalyticsOverview,
  AnalyticsActivity,
  AnalyticsCommands,
  AnalyticsUsers,
  AnalyticsHeatmap,
} from '../types'

export const fetchAnalyticsOverview  = ()                    => api.get<AnalyticsOverview>('/api/analytics/overview')
export const fetchAnalyticsActivity  = (days = 30)           => api.get<AnalyticsActivity>(`/api/analytics/activity?days=${days}`)
export const fetchAnalyticsCommands  = (period = '7d')       => api.get<AnalyticsCommands>(`/api/analytics/commands?period=${period}`)
export const fetchAnalyticsUsers     = (period = '7d')       => api.get<AnalyticsUsers>(`/api/analytics/users?period=${period}`)
export const fetchAnalyticsHeatmap   = ()                    => api.get<AnalyticsHeatmap>('/api/analytics/heatmap')
