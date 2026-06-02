import { api } from './client'
import type { TradesData } from '../types'

export const fetchTrades = (period = '7d', page = 1, pageSize = 50) =>
  api.get<TradesData>(`/api/trades?period=${period}&page=${page}&page_size=${pageSize}`)
