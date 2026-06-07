import { api } from './client'
import type { User } from '../types'

export const fetchUsers = (status?: string) =>
  api.get<User[]>(`/api/users${status ? `?status=${status}` : ''}`)

export const approveUser = (id: string) => api.post<User>(`/api/users/${id}/approve`)
export const deactivateUser = (id: string) => api.post<User>(`/api/users/${id}/deactivate`)
export const activateUser = (id: string) => api.post<User>(`/api/users/${id}/activate`)
export const blockUser = (id: string) => api.post<User>(`/api/users/${id}/block`)
export const deleteUser = (id: string) => api.delete<User>(`/api/users/${id}`)
export const setUserEmail = (id: string, email: string) =>
  api.patch<User>(`/api/users/${id}/email`, { email })
export const inviteAuthAccount = (id: string) =>
  api.post<{ email: string; ok: boolean }>(`/api/users/${id}/invite-auth-account`)
