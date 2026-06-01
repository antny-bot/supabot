import { api } from './client'
import type { Event } from '../types'

export const fetchEvents = (level?: string) =>
  api.get<Event[]>(`/api/events${level ? `?level=${level}` : ''}`)
