import { api } from './client'
import type {
  AdminFeedbackListResponse,
  FeedbackCategory,
  FeedbackItem,
  FeedbackStatus,
} from '../types'

export interface SubmitFeedbackPayload {
  category: FeedbackCategory
  title: string
  content: string
  browser_info?: string
}

export interface UpdateFeedbackPayload {
  category?: FeedbackCategory
  title?: string
  content?: string
}

export interface AdminUpdateFeedbackPayload {
  status?: FeedbackStatus
  admin_note?: string
}

export interface AdminFeedbackFilterParams {
  status?: string
  category?: string
  days?: number
  page?: number
  page_size?: number
}

// ── 사용자 API ─────────────────────────────────────────────────────────────

export async function submitFeedback(payload: SubmitFeedbackPayload): Promise<FeedbackItem> {
  return api.post<FeedbackItem>('/api/feedbacks', payload)
}

export async function fetchMyFeedbacks(): Promise<{ reports: FeedbackItem[] }> {
  return api.get<{ reports: FeedbackItem[] }>('/api/feedbacks/my')
}

export async function updateMyFeedback(
  feedbackId: string,
  payload: UpdateFeedbackPayload,
): Promise<FeedbackItem> {
  return api.patch<FeedbackItem>(`/api/feedbacks/my/${feedbackId}`, payload)
}

export async function deleteMyFeedback(feedbackId: string): Promise<{ success: boolean }> {
  return api.delete<{ success: boolean }>(`/api/feedbacks/my/${feedbackId}`)
}

// ── 관리자 API ─────────────────────────────────────────────────────────────

export async function fetchAdminFeedbacks(
  params: AdminFeedbackFilterParams = {},
): Promise<AdminFeedbackListResponse> {
  const query = new URLSearchParams()
  if (params.status && params.status !== 'all') query.set('status', params.status)
  if (params.category && params.category !== 'all') query.set('category', params.category)
  if (params.days) query.set('days', String(params.days))
  if (params.page) query.set('page', String(params.page))
  if (params.page_size) query.set('page_size', String(params.page_size))

  const queryString = query.toString()
  const url = queryString ? `/api/admin/feedbacks?${queryString}` : '/api/admin/feedbacks'
  return api.get<AdminFeedbackListResponse>(url)
}

export async function updateAdminFeedback(
  feedbackId: string,
  payload: AdminUpdateFeedbackPayload,
): Promise<FeedbackItem> {
  return api.patch<FeedbackItem>(`/api/admin/feedbacks/${feedbackId}`, payload)
}

export async function deleteAdminFeedback(feedbackId: string): Promise<{ success: boolean }> {
  return api.delete<{ success: boolean }>(`/api/admin/feedbacks/${feedbackId}`)
}
