import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { getVacancy } from '@/api/hiring'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { useVacancyDraft } from '@/features/vacancyCreate/useVacancyDraft'
import { useAsync } from '@/hooks/useAsync'

/**
 * Продолжение серверного черновика (с главной или после повторного открытия
 * Mini App): загружает вакансию в форму и открывает первый шаг. Если вакансию
 * уже опубликовали, ведёт на её кандидатов — править там больше нечего.
 */
export function EditDraftPage() {
  const vacancyId = Number(useParams().vacancyId)
  const navigate = useNavigate()
  const { openDraft } = useVacancyDraft()
  const { state, reload } = useAsync((signal) => getVacancy(vacancyId, signal), [vacancyId])

  useEffect(() => {
    if (state.status !== 'success') return
    const vacancy = state.data
    if (vacancy.status === 'draft') {
      openDraft(vacancy)
      navigate(routes.employerVacancyCreate, { replace: true })
    } else {
      navigate(routes.employerVacancyCandidates(vacancy.id), { replace: true })
    }
  }, [state, openDraft, navigate])

  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.employerHome)} />
  }
  return <LoadingScreen />
}
