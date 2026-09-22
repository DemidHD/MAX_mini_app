import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Button, Flex, Typography } from '@maxhub/max-ui'

import { pathForStep } from '@/app/routes'
import { updateRole } from '@/api/users'
import { ApiError } from '@/api/client'
import { useAuth } from '@/auth/AuthContext'
import type { UserRole } from '@/api/types'

/**
 * Экран выбора роли (раздел 9 тех-доки). Роль нельзя выбрать повторно —
 * если backend уже вернул ненулевую роль, уводим на актуальный шаг.
 */
export function RoleSelectionPage() {
  const { state, refresh } = useAuth()
  const [submitting, setSubmitting] = useState<UserRole | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (state.status !== 'authenticated') {
    return null
  }

  if (state.user.role !== null) {
    return <Navigate to={pathForStep(state.currentStep, state.applicationId)} replace />
  }

  async function handleSelect(role: UserRole) {
    setSubmitting(role)
    setError(null)
    try {
      await updateRole({ role })
      // current_step после выбора роли считает backend — переавторизуемся,
      // чтобы получить канонический следующий шаг (раздел 7).
      await refresh()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Не удалось сохранить роль')
      setSubmitting(null)
    }
  }

  return (
    <Flex direction="column" gap={24} style={{ padding: 24, minHeight: '100vh' }} justify="center">
      <Flex direction="column" gap={8}>
        <Typography.Title>Кто вы в MAX Найм?</Typography.Title>
        <Typography.Body>Это определяет, какой сценарий вы увидите дальше.</Typography.Body>
      </Flex>

      <Flex direction="column" gap={12}>
        <Button
          size="large"
          stretched
          loading={submitting === 'employer'}
          disabled={submitting !== null}
          onClick={() => void handleSelect('employer')}
        >
          Я ищу сотрудника
        </Button>
        <Button
          size="large"
          variant="secondary"
          stretched
          loading={submitting === 'candidate'}
          disabled={submitting !== null}
          onClick={() => void handleSelect('candidate')}
        >
          Я ищу работу
        </Button>
      </Flex>

      {error ? <Typography.Body>{error}</Typography.Body> : null}
    </Flex>
  )
}
