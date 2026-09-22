import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { authMax } from '@/api/auth'
import { getInitData } from '@/bridge/maxBridge'
import { AuthContext } from '@/auth/useAuth'
import type { AuthState } from '@/auth/useAuth'
import type { User } from '@/api/types'

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

  // React.StrictMode в dev повторно запускает эффекты. Backend обрабатывает
  // параллельную первую авторизацию атомарно, но локальная защита всё равно
  // не создаёт лишние HTTP-запросы и серверные сессии.
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
