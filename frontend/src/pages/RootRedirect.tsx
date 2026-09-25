import { Navigate } from 'react-router-dom'

import { pathForStep } from '@/app/routes'
import { useAuth } from '@/auth/useAuth'

/**
 * Точка входа Mini App: уводит пользователя на маршрут, соответствующий
 * `current_step` (раздел 7 тех-доки), — экран восстанавливается по серверному
 * состоянию, а не всегда со старта. Загрузку (G01) и ошибку входа (G03)
 * показывает общий шлюз в `AppLayout`, сюда попадают уже после входа.
 */
export function RootRedirect() {
  const { state } = useAuth()
  if (state.status !== 'authenticated') return null
  return <Navigate to={pathForStep(state.currentStep, state.applicationId, state.vacancyId)} replace />
}
