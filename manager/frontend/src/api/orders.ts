import { api } from './client'
import type { Order } from '../types'

export const fetchOrders = (status?: string, exchange?: string) => {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (exchange) params.set('exchange', exchange)
  const qs = params.toString()
  return api.get<Order[]>(`/api/orders${qs ? `?${qs}` : ''}`)
}
