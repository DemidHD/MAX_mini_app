import type { CurrentStep } from '@/api/types'

/**
 * Пути маршрутов Mini App. Экраны, ещё не реализованные в этом этапе
 * (профиль кандидата, лента, вакансии — см. Этапы 2-3 в распределении задач),
 * временно ведут на заглушку `StubPage`.
 */
export const routes = {
  root: '/',
  roleSelection: '/role',
  profile: '/profile',
  authError: '/error',
  candidateProfileSetup: '/candidate/profile-setup',
  candidateFeed: '/candidate/feed',
  candidateApplication: (applicationId: number | string = ':applicationId') =>
    `/candidate/applications/${applicationId}`,
  employerHome: '/employer',
  employerVacancyCreate: '/employer/vacancies/new',
} as const

/**
 * Путь для текущего шага сценария (раздел 7 тех-доки). Единственное место,
 * которое переводит `current_step` backend в маршрут frontend.
 */
export function pathForStep(step: CurrentStep, applicationId: number | null): string {
  switch (step) {
    case 'role_selection':
      return routes.roleSelection
    case 'candidate_profile':
      return routes.candidateProfileSetup
    case 'feed':
      return routes.candidateFeed
    case 'application_status':
      return applicationId !== null ? routes.candidateApplication(applicationId) : routes.candidateFeed
    case 'vacancy_create':
      return routes.employerVacancyCreate
    case 'employer_home':
      return routes.employerHome
  }
}
