/**
 * Типы сценария найма: вакансии, отклики, первичный отбор, решения, слоты,
 * интервью. Поля и статусы — по тех-доке (разделы 15–23, 26) и
 * `docs/api-contracts.md`.
 *
 * Экраны пока не подключены к backend (см. `mocks/demoApi.ts`), но работают
 * с этими формами данных, чтобы подключение свелось к замене источника.
 */

/** Раздел 17 тех-доки. `reserved` появится вместе с P1. */
export type ApplicationStatus =
  | 'created'
  | 'screening'
  | 'hard_filter_failed'
  | 'passed'
  | 'under_review'
  | 'rejected'
  | 'invited'
  | 'mutual_interest'
  | 'interview_scheduled'
  | 'interview_completed'

/** Раздел 16 тех-доки. */
export type CriterionType = 'location' | 'schedule' | 'salary' | 'available_from' | 'experience' | 'certificate'

export interface VacancyCriterion {
  type: CriterionType
  required: boolean
  /** Формат — `docs/api-contracts.md`, «Формат vacancy_criteria.value». */
  value: Record<string, unknown>
}

export interface Vacancy {
  id: number
  title: string
  location: string | null
  salary_min: string | null
  salary_max: string | null
  schedule: string | null
  status: 'draft' | 'published' | 'closed'
  criteria: VacancyCriterion[]
  /**
   * Название заведения и описание есть в макетах (C02, C03, C07, M01), но
   * в таблице `vacancies` (раздел 15 тех-доки) таких полей нет — вопрос к
   * продуктовой команде. Пока поля необязательные: без них экраны не ломаются.
   */
  company_name?: string | null
  description?: string | null
}

export interface ApplicationSummary {
  id: number
  vacancy_id: number
  status: ApplicationStatus
  created_at: string
}

export type ScreeningQuestionType = 'text' | 'number' | 'boolean' | 'choice'

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

/** Отклик глазами кандидата: статус + вакансия (экраны C06/C07). */
export interface CandidateApplication extends ApplicationSummary {
  vacancy: Vacancy
  failed_criteria: CriterionType[]
  /** Есть после взаимного интереса / бронирования — для перехода в M01 / C10. */
  match_id: number | null
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
}

/** Раздел 22 тех-доки. */
export interface InterviewSlot {
  id: number
  vacancy_id: number
  starts_at: string
  ends_at: string
  status: 'available' | 'booked' | 'cancelled'
}

/** Раздел 21 тех-доки + вакансия для экрана M01. */
export interface Match {
  id: number
  application_id: number
  vacancy: Vacancy
  created_at: string
}

/** Раздел 23 тех-доки + данные для экранов C10/E10. */
export interface Interview {
  id: number
  match_id: number
  slot_id: number
  status: 'scheduled' | 'completed' | 'cancelled' | 'no_show'
  starts_at: string
  ends_at: string
  vacancy: Vacancy
  application_id: number
  /** Удалось ли отправить уведомление в MAX (раздел 48, `notification_sent`). */
  notification_sent: boolean
}
