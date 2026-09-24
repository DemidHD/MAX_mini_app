import { ApiError, api } from '@/api/client'
import type { CriterionType, ScreeningQuestionType, Vacancy } from '@/api/hiring'

/** Создание, правка и удаление вакансии работодателя (`docs/api-contracts.md`). */

export interface VacancyCriterionInput {
  type: CriterionType
  required: boolean
  value: Record<string, unknown>
}

export interface VacancyQuestionInput {
  question: string
  type: ScreeningQuestionType
  required: boolean
  validation_rules: Record<string, unknown> | null
}

/** Поля вакансии, которые заполняет форма создания (E02–E03). */
export interface VacancyFieldsInput {
  title: string
  location: string | null
  salary_min: number | null
  salary_max: number | null
  schedule: string | null
  /** Название заведения и описание — необязательные, в проверку публикации не входят. */
  company_name: string | null
  description: string | null
  criteria: VacancyCriterionInput[]
  questions: VacancyQuestionInput[]
}

export interface CreateVacancyRequest extends VacancyFieldsInput {
  status: 'draft' | 'published'
}

export type UpdateVacancyRequest = Partial<VacancyFieldsInput> & { status?: 'published' | 'closed' }

export type VacancyResponse = Vacancy

/**
 * Сколько незаконченных черновиков может быть у работодателя
 * (`VACANCY_DRAFT_LIMIT` на backend, по умолчанию 5). Лимит проверяет backend;
 * фронт знает число, чтобы заранее объяснить ограничение, а не показывать
 * ошибку после заполнения формы.
 */
export const DRAFT_LIMIT = 5

/** `POST /api/vacancies`. */
export function createVacancy(payload: CreateVacancyRequest, signal?: AbortSignal): Promise<VacancyResponse> {
  return api.post<VacancyResponse>('/vacancies', payload, signal)
}

/** `PATCH /api/vacancies/{id}`: `criteria` и `questions` заменяются целиком. */
export function updateVacancy(id: number, payload: UpdateVacancyRequest, signal?: AbortSignal): Promise<VacancyResponse> {
  return api.patch<VacancyResponse>(`/vacancies/${id}`, payload, signal)
}

/**
 * `DELETE /api/vacancies/{id}` — только черновик; опубликованные закрываются.
 * На backend эндпоинта ещё нет (сейчас 405): диалог удаления честно покажет ошибку.
 */
export function deleteVacancy(id: number, signal?: AbortSignal): Promise<void> {
  return api.delete<void>(`/vacancies/${id}`, signal)
}

/** Backend отказал в новом черновике из-за лимита: `409 draft_limit_reached`, `details.limit`. */
export function isDraftLimitError(cause: unknown): boolean {
  return cause instanceof ApiError && cause.code === 'draft_limit_reached'
}
