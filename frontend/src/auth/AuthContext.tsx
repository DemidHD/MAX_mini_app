import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { authMax } from '@/api/auth'
import { getInitData } from '@/bridge/maxBridge'
import type { CurrentStep, User } from '@/api/types'

interface AuthSession {
  user: User
  currentStep: CurrentStep
  applicationId: number | null
}

type AuthState =
  | { status: 'loading' }
  | ({ status: 'authenticated' } & AuthSession)
  | { status: 'error'; error: Error }

interface AuthContextValue {
  state: AuthState
  /**
   * Повторно проходит `/auth/max` и обновляет `currentStep`. Используется
   * после выбора роли — backend сам решает следующий шаг сценария (раздел 7),
   * frontend его не вычисляет.
   */
  refresh: () => Promise<void>
  /** Локально обновляет кэш пользователя после `PATCH /users/me/*`. */
  setUser: (user: User) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' })

  const refresh = useCallback(async () => {
    setState({ status: 'loading' })
    try {
      const initData = getInitData()
      const response = await authMax(initData)
      setState({
        status: 'authenticated',
        user: response.user,
        currentStep: response.current_step,
        applicationId: response.application_id,
      })
    } catch (error) {
      setState({ status: 'error', error: error as Error })
    }
  }, [])

  // React.StrictMode в dev монтирует эффекты дважды подряд. Без защиты это
  // отправляет два параллельных POST /auth/max для нового пользователя —
  // backend не гарантирует атомарность upsert (app/auth/service.py) и второй
  // запрос падает `IntegrityError` на уникальности `user_id`.
  const hasBootstrapped = useRef(false)
  useEffect(() => {
    if (hasBootstrapped.current) return
    hasBootstrapped.current = true
    void refresh()
  }, [refresh])

  const setUser = useCallback((user: User) => {
    setState((previous) =>
      previous.status === 'authenticated' ? { ...previous, user } : previous,
    )
  }, [])

  const value = useMemo(() => ({ state, refresh, setUser }), [state, refresh, setUser])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth должен использоваться внутри AuthProvider')
  }
  return context
}
