import { useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ErrorScreen } from '@/components/ErrorScreen'

/** Маршрут `/error` — G03 как самостоятельный экран: повтор ведёт на старт. */
export function ErrorRoutePage() {
  const navigate = useNavigate()
  return (
    <ErrorScreen
      onRetry={() => navigate(routes.root, { replace: true })}
      onBack={window.history.length > 1 ? () => navigate(-1) : undefined}
    />
  )
}
