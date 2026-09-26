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
  // Отдельного `GET /matches/{id}` у backend нет: взаимный интерес, слоты и
  // интервью кандидат получает по вакансии (`GET /vacancies/{id}/slots`).
  candidateMatch: (vacancyId: Id = ':vacancyId') => `/candidate/vacancies/${vacancyId}/match`,
  candidateMatchSlots: (vacancyId: Id = ':vacancyId') => `/candidate/vacancies/${vacancyId}/slots`,
  candidateInterview: (vacancyId: Id = ':vacancyId') => `/candidate/vacancies/${vacancyId}/interview`,
  employerHome: '/employer',
  employerVacancyCreate: '/employer/vacancies/new',
  // P1: создание вакансии свободным текстом (E11), голосом (E13) и
  // подтверждение разбора ИИ (E12). Ручная форма E02 остаётся fallback.
  employerVacancyAi: '/employer/vacancies/new/ai',
  employerVacancyAiCheck: '/employer/vacancies/new/ai/check',
  employerVacancyVoice: '/employer/vacancies/new/voice',
  employerVacancyCriteria: '/employer/vacancies/new/criteria',
  employerVacancyPreview: '/employer/vacancies/new/preview',
  employerVacancyPublished: '/employer/vacancies/new/published',
  employerVacancyEdit: (vacancyId: Id = ':vacancyId') => `/employer/vacancies/${vacancyId}/edit`,
  employerVacancyList: '/employer/vacancies',
  employerVacancySlots: (vacancyId: Id = ':vacancyId') => `/employer/vacancies/${vacancyId}/slots`,
  // Доска найма (E15, P1); вакансия выбирается параметром `?vacancy=`.
  employerCandidates: '/employer/candidates',
  employerReserve: '/employer/reserve',
  employerVacancyCandidates: (vacancyId: Id = ':vacancyId') => `/employer/candidates/${vacancyId}`,
  // Отдельного чтения одного отклика у backend нет: карточка берётся из
  // списка кандидатов вакансии, поэтому в пути есть и вакансия.
  employerApplication: (vacancyId: Id = ':vacancyId', applicationId: Id = ':applicationId') =>
    `/employer/candidates/${vacancyId}/${applicationId}`,
  employerApplicationInvite: (vacancyId: Id = ':vacancyId', applicationId: Id = ':applicationId') =>
    `/employer/candidates/${vacancyId}/${applicationId}/invite`,
  employerApplicationReject: (vacancyId: Id = ':vacancyId', applicationId: Id = ':applicationId') =>
    `/employer/candidates/${vacancyId}/${applicationId}/reject`,
  employerInterview: (vacancyId: Id = ':vacancyId', interviewId: Id = ':interviewId') =>
    `/employer/vacancies/${vacancyId}/interviews/${interviewId}`,
} as const

/**
 * Путь для текущего шага сценария (раздел 7 тех-доки). Единственное место,
 * которое переводит `current_step` backend в маршрут frontend.
 */
export function pathForStep(step: CurrentStep, applicationId: number | null, vacancyId: number | null = null): string {
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
      return vacancyId !== null ? routes.employerVacancyEdit(vacancyId) : routes.employerVacancyCreate
    case 'employer_home':
      return routes.employerHome
  }
}
