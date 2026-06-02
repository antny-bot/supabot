import { api } from './client'
import type { OrdersData } from '../types'

export const fetchOrders = (status?: string, exchange?: string, page = 1, pageSize = 50) => {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (exchange) params.set('exchange', exchange)
  params.set('page', String(page))
  params.set('page_size', String(pageSize))
  const qs = params.toString()
  return api.get<OrdersData>(`/api/orders?${qs}`)
}
