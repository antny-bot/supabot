import { api } from './client'

export interface LoginResponse {
  mfa_required?: boolean
}

export function loginWithPassword(email: string, password: string) {
  return api.post<LoginResponse>('/api/login', { email, password })
}

export function loginWithMfa(code: string, trustDevice: boolean) {
  return api.post<Record<string, never>>('/api/login/mfa', {
    code,
    trust_device: trustDevice,
  })
}
