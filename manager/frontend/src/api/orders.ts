import { api } from './client'
import type { OrdersData } from '../types'

export const fetchOrders = (
  status?: string,
  exchange?: string,
  side?: string,
  dateFrom?: string,
  dateTo?: string,
  page = 1,
  pageSize = 50,
) => {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (exchange) params.set('exchange', exchange)
  if (side) params.set('side', side)
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  params.set('page', String(page))
  params.set('page_size', String(pageSize))
  return api.get<OrdersData>(`/api/orders?${params.toString()}`)
}
