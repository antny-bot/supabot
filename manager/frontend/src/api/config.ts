import { api } from './client'
import type { ConfigItem } from '../types'

export const fetchConfig = () => api.get<ConfigItem[]>('/api/sysconfig')

export const saveConfig = (values: Record<string, string>) =>
  api.post<{ saved: boolean }>('/api/sysconfig', values)
