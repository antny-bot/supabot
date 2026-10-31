import { api } from './client'
import type { OrdersData, OrderBatchListResponse } from '../types'

export const fetchOrders = (
  status?: string,
  exchange?: string,
  side?: string,
  dateFrom?: string,
  dateTo?: string,
  page = 1,
  pageSize = 50,
  groupNo?: number,
) => {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (exchange) params.set('exchange', exchange)
  if (side) params.set('side', side)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  if (groupNo !== undefined) params.set('group_no', String(groupNo))
  params.set('page', String(page))
  params.set('page_size', String(pageSize))
  return api.get<OrdersData>(`/api/orders?${params.toString()}`)
}

export const cancelOrder = (uuid: string) =>
  api.post<{ ok: boolean; error?: string }>(`/api/orders/${encodeURIComponent(uuid)}/cancel`, {})

export const cancelAllOrders = () =>
  api.post<{ ok: boolean; total: number; cancelled_count: number; failed_count: number; errors?: string[] }>('/api/orders/cancel-all', {})

export const syncOrder = (uuid: string) =>
  api.post<{ ok: boolean; error?: string; data?: any }>(`/api/orders/${encodeURIComponent(uuid)}/sync`, {})

export const forceUpdateOrder = (uuid: string, state: string, filledVolume: number) =>
  api.post<{ ok: boolean; error?: string }>(`/api/orders/${encodeURIComponent(uuid)}/force-update`, {
    state,
    filled_volume: filledVolume,
  })

export const fetchOrderBatches = (
  templateId?: number,
  exchange?: string,
  page = 1,
  pageSize = 20,
) => {
  const params = new URLSearchParams()
  if (templateId !== undefined) params.set('template_id', String(templateId))
  if (exchange) params.set('exchange', exchange)
  params.set('page', String(page))
  params.set('page_size', String(pageSize))
  return api.get<OrderBatchListResponse>(`/api/orders/batches?${params.toString()}`)
}
