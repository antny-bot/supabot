import { api } from './client'
import type { Event } from '../types'

export interface PaginatedEvents {
  events: Event[]
  total: number
  page: number
  limit: number
}

export const fetchEvents = (level?: string, state?: string, page: number = 1, limit: number = 50) => {
  const params = new URLSearchParams()
  if (level) params.set('level', level)
  if (state) params.set('state', state)
  params.set('page', String(page))
  params.set('limit', String(limit))
  const query = params.toString()
  return api.get<PaginatedEvents>(`/api/events?${query}`)
}

export const markEventRead = (eventId: number) => api.patch<Event>(`/api/events/${eventId}/read`)
export const unreadEvent = (eventId: number) => api.patch<Event>(`/api/events/${eventId}/unread`)
export const archiveEvent = (eventId: number) => api.patch<Event>(`/api/events/${eventId}/archive`)
export const unarchiveEvent = (eventId: number) => api.patch<Event>(`/api/events/${eventId}/unarchive`)

export const bulkMarkEventsRead = (ids: number[]) => api.patch<{ success: boolean }>('/api/events/bulk/read', { ids })
export const bulkArchiveEvents = (ids: number[]) => api.patch<{ success: boolean }>('/api/events/bulk/archive', { ids })
export const bulkDeleteEvents = (ids: number[]) => api.post<{ success: boolean }>('/api/events/bulk/delete', { ids })
