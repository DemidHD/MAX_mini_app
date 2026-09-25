import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import { getSlots, getVacancy, getVacancyCandidates } from '@/api/hiring'
import type { EmployerCandidate, Vacancy } from '@/api/hiring'

export interface ApplicationView {
  vacancy: Vacancy
  candidate: EmployerCandidate
  /** Все кандидаты вакансии — для номера «Кандидат 01». */
  items: EmployerCandidate[]
  /** Новые кандидаты очереди (от новых к старым) — для «1 из 3» и перехода к следующему. */
  queue: number[]
  interviewId: number | null
}

/**
 * Данные карточки кандидата (E08/E09). Чтения одного отклика у backend нет,
 * поэтому карточка берётся из списка кандидатов вакансии, а назначенное
 * интервью — из `interviews` ответа `GET /vacancies/{id}/slots`.
 */
export async function loadApplicationView(
  vacancyId: number,
  applicationId: number,
  signal: AbortSignal,
  withInterview = false,
): Promise<ApplicationView> {
  const [vacancy, candidates, slots] = await Promise.all([
    getVacancy(vacancyId, signal),
    getVacancyCandidates(vacancyId, signal),
    withInterview ? getSlots(vacancyId, signal) : Promise.resolve(null),
  ])
  const candidate = candidates.items.find((item) => item.application_id === applicationId)
  if (!candidate) {
    throw new ApiError(404, { code: 'application_not_found', message: 'Кандидат не найден' })
  }
  const queue = candidates.items
    .filter((item) => item.status === 'passed' || item.application_id === applicationId)
    .map((item) => item.application_id)
  const interviewId = slots?.interviews.find((item) => item.application_id === applicationId)?.id ?? null
  return { vacancy, candidate, items: candidates.items, queue, interviewId }
}

/**
 * Куда идти после решения по кандидату: к следующему новому в очереди или
 * обратно к очереди (UX-карта, «Правила навигации»).
 */
export function pathAfterDecision(view: ApplicationView, applicationId: number): string {
  const position = view.queue.indexOf(applicationId)
  const next = view.queue.slice(position + 1)[0] ?? view.queue.find((id) => id !== applicationId)
  return next ? routes.employerApplication(view.vacancy.id, next) : routes.employerVacancyCandidates(view.vacancy.id)
}
