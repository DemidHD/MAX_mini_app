import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import type { ApplicationSummary } from '@/api/hiring'

/**
 * Отклик на вакансию (`POST /vacancies/:id/apply`). Повторный отклик дубль не
 * создаёт: backend возвращает существующий, и мы ведём на его статус
 * (UX-карта, раздел 8 «Повторный отклик»).
 */
export function useApply(applyRequest: (vacancyId: number) => Promise<ApplicationSummary>) {
  const navigate = useNavigate()
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function apply(vacancyId: number) {
    setApplying(true)
    setError(null)
    try {
      const application = await applyRequest(vacancyId)
      navigate(
        application.status === 'screening'
          ? routes.candidateScreeningStart(application.id)
          : routes.candidateApplication(application.id),
      )
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.code === 'vacancy_not_published'
          ? 'Вакансия уже закрыта — откликнуться не получится.'
          : 'Не удалось отправить отклик. Попробуйте еще раз.',
      )
    } finally {
      setApplying(false)
    }
  }

  return { apply, applying, error }
}
