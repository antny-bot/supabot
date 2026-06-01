import { api } from './client'
import type { TradesData } from '../types'

export const fetchTrades = (period = '7d') =>
  api.get<TradesData>(`/api/trades?period=${period}`)
