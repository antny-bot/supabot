import { api } from './client'

export interface StockCacheRow {
  name: string
  code: string
  updated_at: string
}

export interface StockCacheUploadResult {
  added: number
  skipped: number
  errors: number
}

export interface StockCacheRefreshResult {
  added: number
}

export const fetchStockCache = (search = '') => {
  const params = search ? `?search=${encodeURIComponent(search)}` : ''
  return api.get<StockCacheRow[]>(`/api/stock-cache${params}`)
}

export const createStockCacheEntry = (name: string, code: string) =>
  api.post<StockCacheRow>('/api/stock-cache', { name, code })

export const deleteStockCacheEntry = (name: string) =>
  api.delete<Record<string, never>>(`/api/stock-cache/${encodeURIComponent(name)}`)

export const uploadStockCache = (file: File, overwrite: boolean) => {
  const form = new FormData()
  form.append('file', file)
  return api.postForm<StockCacheUploadResult>(`/api/stock-cache/upload?overwrite=${overwrite}`, form)
}

export const refreshStockCache = () => api.post<StockCacheRefreshResult>('/api/stock-cache/refresh', {})

export function exportStockCache() {
  window.location.href = '/api/stock-cache/export'
}
