import { api } from '@/api/client'

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
