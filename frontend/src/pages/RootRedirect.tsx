import { Navigate } from 'react-router-dom'

import { pathForStep } from '@/app/routes'
import { useAuth } from '@/auth/useAuth'
import { ErrorScreen } from '@/components/ErrorScreen'
import { SplashScreen } from '@/components/SplashScreen'
import { MaxBridgeUnavailableError } from '@/bridge/maxBridge'

/**
 * Точка входа Mini App. Ждёт результат `/auth/max` и уводит пользователя на
 * маршрут, соответствующий `current_step` (раздел 7 тех-доки), — экран
 * восстанавливается по серверному состоянию, а не всегда со старта.
 * Загрузочный экран — G01 «Загрузка и авторизация», ошибка — G03 в UX-карте.
 */
export function RootRedirect() {
  const { state, refresh } = useAuth()

  if (state.status === 'loading') {
    return <SplashScreen />
  }

  if (state.status === 'error') {
    const isBridgeUnavailable = state.error instanceof MaxBridgeUnavailableError
    return (
      <ErrorScreen
        error={state.error}
        description={isBridgeUnavailable ? state.error.message : undefined}
        onRetry={() => void refresh()}
      />
    )
  }

  return <Navigate to={pathForStep(state.currentStep, state.applicationId)} replace />
}
