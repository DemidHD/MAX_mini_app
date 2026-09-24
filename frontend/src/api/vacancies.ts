import { api } from '@/api/client'
import type { Vacancy } from '@/api/hiring'

/**
 * `POST /vacancies` (раздел 27-29 тех-доки). У backend этот роутер ещё не
 * реализован — есть только модель `Vacancy` в БД (`backend/app/vacancies/models.py`),
 * без router/schemas/service. Запрос ниже честный: пока backend не подключен,
 * он закономерно вернёт 404, и `VacancyPreviewPage` должна это показать,
 * а не притворяться, что вакансия опубликована.
 *
 * Форма `criteria[].value` соответствует уже реализованному подбору
 * (docs/api-contracts.md, раздел «Формат vacancy_criteria.value») —
 * если backend когда-нибудь подключит этот роутер, значения будут сразу
 * понятны существующей ленте.
 */
export type CriterionType = 'location' | 'schedule' | 'salary' | 'available_from' | 'experience'

export interface VacancyCriterionInput {
  type: CriterionType
  required: boolean
  value: Record<string, unknown>
}

export interface CreateVacancyRequest {
  title: string
  location: string | null
  salary_min: number | null
  salary_max: number | null
  schedule: string | null
  status: 'published'
  criteria: VacancyCriterionInput[]
}

export interface VacancyResponse {
  id: number
  title: string
  location: string | null
  salary_min: number | null
  salary_max: number | null
  schedule: string | null
  status: string
  public_token: string | null
}

export function createVacancy(payload: CreateVacancyRequest, signal?: AbortSignal): Promise<VacancyResponse> {
  return api.post<VacancyResponse>('/vacancies', payload, signal)
}

/**
 * `GET /vacancies/public/{token}` — вакансия по публичной ссылке
 * `{APP_URL}/v/{token}` (раздел 15 тех-доки). В отличие от `createVacancy`
 * выше, этот роутер на backend уже реализован
 * (`backend/app/vacancies/router.py`), поэтому запрос настоящий, а не заглушка.
 *
 * Форма ответа — тот же `VacancyRead`, что кандидат получает по
 * `GET /vacancies/{id}`: владельческие поля (`public_token`, `public_url`,
 * `applications_count`) всегда `null`.
 */
export function getPublicVacancy(token: string, signal?: AbortSignal): Promise<PublicVacancy> {
  return api.get<PublicVacancy>(`/vacancies/public/${encodeURIComponent(token)}`, signal)
}

export interface PublicVacancy extends Vacancy {
  image_url: string | null
}
