import { createContext, useContext } from 'react'
import type { AuthUser } from '../types'

interface AuthContextValue {
  user: AuthUser | null
  loading: boolean
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
})

export function useAuthContext(): AuthContextValue {
  return useContext(AuthContext)
}
