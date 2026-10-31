import { api } from './client'

export interface TemplateParams {
  buy_rsi_range?: string
  sell_rsi_range?: string
  weighted?: boolean
  schedule?: string
  exec_time?: string
  amount_type?: 'budget' | 'volume'
  max_runs?: number | null
  side?: 'bid' | 'ask'
  [key: string]: any
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

export const fetchTemplates = async (): Promise<Template[]> => {
  try {
    const res = await api.get<any>('/api/templates')
    if (Array.isArray(res)) return res
    if (res && Array.isArray(res.data)) return res.data
    return []
  } catch {
    return []
  }
}

export const createTemplate = async (payload: TemplatePayload): Promise<Template> => {
  const res = await api.post<any>('/api/templates', payload)
  return res && res.data ? res.data : res
}

export const updateTemplate = async (id: number, payload: TemplatePayload): Promise<Template> => {
  const res = await api.patch<any>(`/api/templates/${id}`, payload)
  return res && res.data ? res.data : res
}

export const deleteTemplate = (id: number) => api.delete<Record<string, never>>(`/api/templates/${id}`)
export const duplicateTemplate = (id: number) => api.post<Record<string, never>>(`/api/templates/${id}/duplicate`, {})
export const executeTemplate = (id: number) => api.post<TemplateActionResponse>(`/api/templates/${id}/execute`, {})

export const toggleTemplateHolding = (id: number, is_holding: boolean) =>
  api.post<any>(`/api/templates/${id}/holding`, { is_holding })

export const stopTemplate = (id: number, mode: 'pause' | 'stop_and_cancel' | 'terminate_and_liquidate') =>
  api.post<any>(`/api/templates/${id}/stop`, { mode })

export const updateBudgetPlan = (id: number, payload: { new_plan_config: any; apply_today_diff?: boolean; memo?: string }) =>
  api.post<any>(`/api/templates/${id}/budget-plan`, payload)

export const resetBudgetPlan = (id: number, payload: { new_config?: any; initial_carryover?: number; reset_cycle?: boolean; cancel_pending?: boolean; memo?: string }) =>
  api.post<any>(`/api/templates/${id}/budget-reset`, payload)

export const fetchBudgetLedger = (id: number, epoch?: number) => {
  const q = epoch !== undefined ? `?budget_epoch=${epoch}` : ''
  return api.get<any>(`/api/templates/${id}/budget-ledger${q}`)
}

export const fetchBudgetHealth = (exchange = 'toss') =>
  api.get<any>(`/api/templates/budget-health?exchange=${exchange}`)
