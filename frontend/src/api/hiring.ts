import { ApiError, api } from '@/api/client'

/**
 * Сценарий найма: вакансии, отклики, первичный отбор, решения, слоты,
 * интервью. Поля и статусы — тех-дока (разделы 15–23, 26), формы запросов и
 * ответов — `docs/api-contracts.md`.
 */

/** Раздел 17 тех-доки; `reserved` — функция «Резерв» (P1, раздел 20). */
export type ApplicationStatus =
  | 'created'
  | 'screening'
  | 'hard_filter_failed'
  | 'passed'
  | 'under_review'
  | 'reserved'
  | 'rejected'
  | 'invited'
  | 'mutual_interest'
  | 'interview_scheduled'
  | 'interview_completed'

/** Раздел 16 тех-доки. */
export type CriterionType = 'location' | 'schedule' | 'salary' | 'available_from' | 'experience' | 'certificate'

export interface VacancyCriterion {
  id?: number
  type: CriterionType
  required: boolean
  /** Формат — `api-contracts.md`, «Формат vacancy_criteria.value». */
  value: Record<string, unknown>
  weight?: string | null
}

export type ScreeningQuestionType = 'text' | 'number' | 'boolean' | 'choice'

export interface VacancyQuestion {
  id: number
  question: string
  type: ScreeningQuestionType
  required: boolean
  sort_order: number
  validation_rules: Record<string, unknown> | null
}

/** Общая часть вакансии: её отдают и лента, и `GET /vacancies/{id}`. */
export interface VacancySummary {
  id: number
  title: string
  location: string | null
  salary_min: string | null
  salary_max: string | null
  schedule: string | null
  criteria: VacancyCriterion[]
  /** Фото по теме вакансии: backend подбирает его сам (Openverse), может не найтись. */
  image_url?: string | null
  /** Есть в `GET /vacancies/{id}` и списке работодателя; лента их не отдаёт. */
  company_name?: string | null
  description?: string | null
}

/** `GET /api/vacancies/{id}`. */
export interface Vacancy extends VacancySummary {
  employer_id: number
  status: 'draft' | 'published' | 'closed'
  public_token: string | null
  public_url: string | null
  applications_count: number | null
  questions: VacancyQuestion[]
  created_at: string
  updated_at: string
}

export interface Page<T> {
  items: T[]
  limit: number
  offset: number
  total: number
}

export interface ApplicationSummary {
  id: number
  vacancy_id: number
  status: ApplicationStatus
  created_at: string
}

export interface ScreeningQuestion {
  id: number
  question: string
  type: ScreeningQuestionType
  required: boolean
  sort_order: number
  rules: {
    options?: string[]
    min?: number
    max?: number
    min_length?: number
    max_length?: number
  }
}

export interface ScreeningAnswer {
  question_id: number
  value: string | number | boolean | null
}

/** `GET /api/applications/{id}/screening`. */
export interface ScreeningState {
  application_id: number
  vacancy_id: number
  status: ApplicationStatus
  can_submit: boolean
  questions: ScreeningQuestion[]
  answers: ScreeningAnswer[]
}

/** `POST /api/applications/{id}/screening`. */
export interface ScreeningResult {
  application_id: number
  status: 'passed' | 'hard_filter_failed'
  failed_criteria: CriterionType[]
  failed_questions: number[]
}

/**
 * `GET /api/applications/{id}` — отклик глазами кандидата (C06/C07).
 * `failed_criteria` восстанавливается из снимка отбора, поэтому причина
 * отказа переживает перезагрузку экрана.
 */
export interface CandidateApplication {
  id: number
  vacancy_id: number
  status: ApplicationStatus
  created_at: string
  vacancy: Vacancy
  failed_criteria: CriterionType[]
  /** Есть после взаимного интереса. */
  match_id: number | null
  /** Есть после назначенного интервью. */
  interview_id: number | null
}

/** Элемент `GET /api/employer/vacancies/{id}/candidates`. */
export interface EmployerCandidate {
  application_id: number
  status: ApplicationStatus
  applied_at: string
  desired_role: string | null
  city: string | null
  salary: string | null
  schedule: string | null
  experience_months: number | null
  available_from: string | null
  screening_answers: {
    question_id: number
    question: string
    type: ScreeningQuestionType
    value: string | number | boolean | null
  }[]
  hard_filters: { type: CriterionType; required: boolean; passed: boolean | null }[]
  /** Объяснимость подбора (P1, раздел 64): совпавшие условия и опыт против требования. */
  explanation?: {
    matched: CriterionType[]
    experience: { candidate: number | null; required: number | null } | null
  }
}

/** Действие работодателя (раздел 20). `reserved` — P1. */
export type DecisionAction = 'invited' | 'rejected' | 'reserved'

/** Причины отказа (раздел 20), экран E14. */
export type RejectReason = 'experience' | 'salary' | 'schedule' | 'location' | 'available_from' | 'other'

/** `POST /api/applications/{id}/decision`. */
export interface DecisionResult {
  application_id: number
  status: ApplicationStatus
  action: DecisionAction
  reject_reason: RejectReason | null
  match_id: number | null
  decided_at: string
}

/** Раздел 22 тех-доки. */
export interface InterviewSlot {
  id: number
  vacancy_id: number
  starts_at: string
  ends_at: string
  status: 'available' | 'booked' | 'cancelled'
}

/** Раздел 23 тех-доки, формат элемента `interviews` из `GET .../slots`. */
export interface Interview {
  id: number
  match_id: number
  application_id: number
  vacancy_id: number
  slot: InterviewSlot
  status: 'scheduled' | 'completed' | 'cancelled' | 'no_show'
  application_status: ApplicationStatus
  created_at: string
}

/** `GET /api/vacancies/{id}/slots`: состав зависит от роли. */
export interface SlotsResponse {
  vacancy_id: number
  items: InterviewSlot[]
  /** Кандидату — с чем идти в `POST /matches/{id}/book`; работодателю `null`. */
  match_id: number | null
  interviews: Interview[]
}

export interface CandidateProfile {
  desired_role: string
  city: string | null
  salary: string | null
  schedule: string | null
  experience_months: number | null
  available_from: string | null
}

// ------------------------------------------------------------- кандидат

/** `GET /api/candidate/profile`; профиля ещё нет — `null` (404 — нормальное состояние). */
export async function getCandidateProfile(signal?: AbortSignal): Promise<CandidateProfile | null> {
  try {
    return await api.get<CandidateProfile>('/candidate/profile', signal)
  } catch (error) {
    if (error instanceof ApiError && error.code === 'candidate_profile_not_found') return null
    throw error
  }
}

export function updateCandidateProfile(profile: Partial<CandidateProfile>, signal?: AbortSignal) {
  return api.patch<CandidateProfile>('/candidate/profile', profile, signal)
}

export function getFeed(signal?: AbortSignal, limit = 20, offset = 0) {
  return api.get<Page<VacancySummary>>(`/vacancies/feed?limit=${limit}&offset=${offset}`, signal)
}

export function getVacancy(id: number, signal?: AbortSignal) {
  return api.get<Vacancy>(`/vacancies/${id}`, signal)
}

/** Повторный вызов возвращает существующий отклик (раздел 57). */
export function applyToVacancy(vacancyId: number, signal?: AbortSignal) {
  return api.post<ApplicationSummary>(`/vacancies/${vacancyId}/apply`, undefined, signal)
}

export function getApplication(applicationId: number, signal?: AbortSignal) {
  return api.get<CandidateApplication>(`/applications/${applicationId}`, signal)
}

export function getScreening(applicationId: number, signal?: AbortSignal) {
  return api.get<ScreeningState>(`/applications/${applicationId}/screening`, signal)
}

export function submitScreening(applicationId: number, answers: ScreeningAnswer[], signal?: AbortSignal) {
  return api.post<ScreeningResult>(`/applications/${applicationId}/screening`, { answers }, signal)
}

/** `POST /api/matches/{id}/book`; занятый слот — `409 slot_taken`. */
export function bookSlot(matchId: number, slotId: number, signal?: AbortSignal) {
  return api.post<Interview>(`/matches/${matchId}/book`, { slot_id: slotId }, signal)
}

// ---------------------------------------------------------- работодатель

export function getEmployerVacancies(signal?: AbortSignal, limit = 20, offset = 0) {
  return api.get<Page<Vacancy>>(`/employer/vacancies?limit=${limit}&offset=${offset}`, signal)
}

export function getVacancyCandidates(vacancyId: number, signal?: AbortSignal) {
  return api.get<Page<EmployerCandidate>>(`/employer/vacancies/${vacancyId}/candidates?limit=50`, signal)
}

/**
 * Приглашение сразу создаёт взаимный интерес и возвращает `match_id`.
 * `rejectReason` — только вместе с отказом и необязательна (E14).
 */
export function decide(
  applicationId: number,
  action: DecisionAction,
  rejectReason: RejectReason | null = null,
  signal?: AbortSignal,
) {
  const body = action === 'rejected' && rejectReason ? { action, reject_reason: rejectReason } : { action }
  return api.post<DecisionResult>(`/applications/${applicationId}/decision`, body, signal)
}

export function getSlots(vacancyId: number, signal?: AbortSignal) {
  return api.get<SlotsResponse>(`/vacancies/${vacancyId}/slots`, signal)
}

/** Один запрос — один слот; время только со смещением (api-contracts). */
export function createSlot(vacancyId: number, slot: { starts_at: string; ends_at: string }, signal?: AbortSignal) {
  return api.post<InterviewSlot>(`/vacancies/${vacancyId}/slots`, slot, signal)
}

export function cancelSlot(vacancyId: number, slotId: number, signal?: AbortSignal) {
  return api.delete<void>(`/vacancies/${vacancyId}/slots/${slotId}`, signal)
}

// ------------------------------------------------------------- помощники

/**
 * «Кандидат 01» — порядковый номер отклика по времени поступления: имени и
 * фото в карточке P0 нет (api-contracts, «GET .../candidates»).
 */
export function candidateLabel(items: EmployerCandidate[], applicationId: number): string {
  const ordered = [...items].sort((a, b) => a.applied_at.localeCompare(b.applied_at))
  const index = ordered.findIndex((item) => item.application_id === applicationId)
  return index >= 0 ? `Кандидат ${String(index + 1).padStart(2, '0')}` : 'Кандидат'
}
