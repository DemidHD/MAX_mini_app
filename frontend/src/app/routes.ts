import type { CurrentStep } from '@/api/types'

type Id = number | string

/**
 * Пути маршрутов Mini App. Экраны вне P0 (например, «Мои отклики» C12 — P2)
 * временно ведут на заглушку `StubPage`.
 */
export const routes = {
  root: '/',
  roleSelection: '/role',
  profile: '/profile',
  authError: '/error',
  candidateProfileSetup: '/candidate/profile-setup',
  candidateFeed: '/candidate/feed',
  candidateApplications: '/candidate/applications',
  candidateVacancy: (vacancyId: Id = ':vacancyId') => `/candidate/vacancies/${vacancyId}`,
  /** Публичная ссылка на вакансию `{APP_URL}/v/{token}` (раздел 15 тех-доки). */
  vacancyPublic: (token: Id = ':token') => `/v/${token}`,
  candidateApplication: (applicationId: Id = ':applicationId') => `/candidate/applications/${applicationId}`,
  candidateScreeningStart: (applicationId: Id = ':applicationId') =>
    `/candidate/applications/${applicationId}/start`,
  candidateScreening: (applicationId: Id = ':applicationId') =>
    `/candidate/applications/${applicationId}/screening`,
  candidateMatch: (matchId: Id = ':matchId') => `/candidate/matches/${matchId}`,
  candidateMatchSlots: (matchId: Id = ':matchId') => `/candidate/matches/${matchId}/slots`,
  candidateInterview: (interviewId: Id = ':interviewId') => `/candidate/interviews/${interviewId}`,
  employerHome: '/employer',
  employerVacancyCreate: '/employer/vacancies/new',
  employerVacancyCriteria: '/employer/vacancies/new/criteria',
  employerVacancyPreview: '/employer/vacancies/new/preview',
  employerVacancyPublished: '/employer/vacancies/new/published',
  employerVacancyList: '/employer/vacancies',
  employerVacancySlots: (vacancyId: Id = ':vacancyId') => `/employer/vacancies/${vacancyId}/slots`,
  employerCandidates: '/employer/candidates',
  employerVacancyCandidates: (vacancyId: Id = ':vacancyId') => `/employer/candidates/${vacancyId}`,
  employerApplication: (applicationId: Id = ':applicationId') => `/employer/applications/${applicationId}`,
  employerApplicationInvite: (applicationId: Id = ':applicationId') =>
    `/employer/applications/${applicationId}/invite`,
  employerInterview: (interviewId: Id = ':interviewId') => `/employer/interviews/${interviewId}`,
  devScreens: '/dev/screens',
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
