import { createContext, useContext } from 'react'

import type { CurrentStep, User } from '@/api/types'

export interface AuthSession {
  user: User
  currentStep: CurrentStep
  applicationId: number | null
  /** Черновик вакансии, в который вернуть работодателя (`vacancy_create`). */
  vacancyId: number | null
}

export type AuthState =
  | { status: 'loading' }
  | ({ status: 'authenticated' } & AuthSession)
  | { status: 'error'; error: Error }

export interface AuthContextValue {
  state: AuthState
  /** Повторно авторизуется и получает канонический следующий шаг от backend. */
  refresh: () => Promise<void>
  /** Локально обновляет кэш пользователя после `PATCH /users/me/*`. */
  setUser: (user: User) => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth должен использоваться внутри AuthProvider')
  }
  return context
}
