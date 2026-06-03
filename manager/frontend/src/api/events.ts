import { api } from './client'
import type { Event } from '../types'

export const fetchEvents = (level?: string, state?: string) => {
  const params = new URLSearchParams()
  if (level) params.set('level', level)
  if (state) params.set('state', state)
  const query = params.toString()
  return api.get<Event[]>(`/api/events${query ? `?${query}` : ''}`)
}

export const markEventRead = (eventId: number) => api.patch<Event>(`/api/events/${eventId}/read`)
export const unreadEvent = (eventId: number) => api.patch<Event>(`/api/events/${eventId}/unread`)
export const archiveEvent = (eventId: number) => api.patch<Event>(`/api/events/${eventId}/archive`)
export const unarchiveEvent = (eventId: number) => api.patch<Event>(`/api/events/${eventId}/unarchive`)
