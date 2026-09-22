import { Navigate } from 'react-router-dom'

import { pathForStep } from '@/app/routes'
import { useAuth } from '@/auth/AuthContext'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MaxBridgeUnavailableError } from '@/bridge/maxBridge'

/**
 * Точка входа Mini App. Ждёт результат `/auth/max` и уводит пользователя на
 * маршрут, соответствующий `current_step` (раздел 7 тех-доки), — экран
 * восстанавливается по серверному состоянию, а не всегда со старта.
 */
export function RootRedirect() {
  const { state, refresh } = useAuth()

  if (state.status === 'loading') {
    return <LoadingState label="Открываем MAX Найм…" />
  }

  if (state.status === 'error') {
    const isBridgeUnavailable = state.error instanceof MaxBridgeUnavailableError
    return (
      <ErrorState
        title="Не удалось авторизоваться"
        description={
          isBridgeUnavailable
            ? state.error.message
            : 'Проверьте соединение и попробуйте снова.'
        }
        onRetry={() => void refresh()}
      />
    )
  }

  return <Navigate to={pathForStep(state.currentStep, state.applicationId)} replace />
}
