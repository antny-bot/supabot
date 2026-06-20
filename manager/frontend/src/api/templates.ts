import { api } from './client'

export interface TemplateParams {
  buy_rsi_range?: string
  sell_rsi_range?: string
  weighted?: boolean
}

export interface Template {
  id: number
  user_id: string
  name: string
  exchange: string
  ticker: string
  start_price: number
  end_price: number
  count: number
  budget: number
  created_at: string
  strategy_type?: string
  params?: TemplateParams
}

export interface TemplatePayload {
  name: string
  exchange: string
  ticker: string
  start_price: number
  end_price: number
  count: number
  budget: number
  strategy_type: string
  params: TemplateParams
}

export interface TemplateActionResponse {
  message?: string
  error?: string
}

export const fetchTemplates = () => api.get<Template[]>('/api/templates')
export const createTemplate = (payload: TemplatePayload) => api.post<Template>('/api/templates', payload)
export const updateTemplate = (id: number, payload: TemplatePayload) => api.patch<Template>(`/api/templates/${id}`, payload)
export const deleteTemplate = (id: number) => api.delete<Record<string, never>>(`/api/templates/${id}`)
export const duplicateTemplate = (id: number) => api.post<Record<string, never>>(`/api/templates/${id}/duplicate`, {})
export const executeTemplate = (id: number) => api.post<TemplateActionResponse>(`/api/templates/${id}/execute`, {})
