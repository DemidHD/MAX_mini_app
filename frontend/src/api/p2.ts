import { ApiError, api } from '@/api/client'
import type { CriterionType } from '@/api/hiring'

/**
 * Функции P2 (раздел 2 тех-доки): импорт резюме (C11), калибровка
 * работодателя (E17, раздел 66), реферальная ссылка (R01, раздел 68) и
 * аналитика вакансии (E18, раздел 69). Формы ответов совпадают с
 * Pydantic-схемами backend (`app/ai/schemas.py`, `app/vacancies/schemas.py`).
 */

// ------------------------------------------------------ резюме (C11)

/** Допустимые файлы и лимит — `RESUME_MIME_TO_EXTENSION` и `resume_max_size_bytes` backend. */
export const RESUME_ACCEPT = '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'
export const RESUME_MAX_SIZE_BYTES = 10 * 1024 * 1024

/** Черновик полей профиля из резюме: любое поле может отсутствовать (частичный разбор). */
export interface ResumeParsedDraft {
  desired_role: string | null
  city: string | null
  salary: string | number | null
  schedule: string | null
  experience_months: number | null
  available_from: string | null
}

export interface ParseResumeResponse {
  parsed: ResumeParsedDraft
  provider: string | null
  /** `false` — разобрать не удалось: переход на ручное заполнение (раздел 57). */
  ai_available: boolean
}

/**
 * `POST /api/candidate/resume/draft` — черновик полей прямо из файла. Работает
 * и без сохранённого профиля; ни файл, ни профиль не сохраняются —
 * подтверждение идёт обычным `PATCH /candidate/profile` из C01.
 */
export function parseResumeDraft(file: File, signal?: AbortSignal): Promise<ParseResumeResponse> {
  const form = new FormData()
  form.append('file', file, file.name)
  return api.postForm<ParseResumeResponse>('/candidate/resume/draft', form, signal)
}

// ------------------------------------------------- калибровка (E17)

export interface CalibrationCriterion {
  type: CriterionType
  matches: boolean
  /** Описание условия, не персональные данные: «Москва», «другой график». */
  value_label: string
}

/** Синтетическая тестовая карточка: `pattern_token` возвращается вместе с решением. */
export interface CalibrationProfile {
  pattern_token: string
  criteria: CalibrationCriterion[]
}

export interface CalibrationVote {
  pattern_token: string
  fit: boolean
}

/** `GET /api/vacancies/{id}/calibration`; пусто — у вакансии нет желательных критериев. */
export function getCalibrationProfiles(vacancyId: number, signal?: AbortSignal) {
  return api.get<{ profiles: CalibrationProfile[] }>(`/vacancies/${vacancyId}/calibration`, signal)
}

/** `POST /api/vacancies/{id}/calibration` → веса желательных критериев. */
export function submitCalibration(vacancyId: number, votes: CalibrationVote[], signal?: AbortSignal) {
  return api.post<{ weights: Partial<Record<CriterionType, string>> }>(
    `/vacancies/${vacancyId}/calibration`,
    { votes },
    signal,
  )
}

// ------------------------------------------ реферальная ссылка (R01)

export interface ReferralLink {
  code: string
  /** `{APP_URL}/v/{public_token}?ref={code}` — собирает backend. */
  url: string
  created_at: string
}

export function getReferralLinks(vacancyId: number, signal?: AbortSignal) {
  return api.get<{ items: ReferralLink[] }>(`/vacancies/${vacancyId}/referral`, signal)
}

/** `POST /api/vacancies/{id}/referral`; черновик — `409 vacancy_not_published`. */
export function createReferralLink(vacancyId: number, signal?: AbortSignal) {
  return api.post<ReferralLink>(`/vacancies/${vacancyId}/referral`, undefined, signal)
}

/** Уже созданная ссылка переиспользуется: новая на каждое открытие экрана не нужна. */
export async function ensureReferralLink(vacancyId: number, signal?: AbortSignal): Promise<ReferralLink> {
  const { items } = await getReferralLinks(vacancyId, signal)
  return items[0] ?? createReferralLink(vacancyId, signal)
}

export function isNotPublishedError(cause: unknown): boolean {
  return cause instanceof ApiError && cause.code === 'vacancy_not_published'
}

// ---------------------------------------------------- аналитика (E18)

export interface VacancyAnalytics {
  vacancy_id: number
  applications_total: number
  passed_hard_filters: number
  invited: number
  mutual_interest: number
  interviews_booked: number
  /** `null` — по вакансии ещё не было ни одного собеседования. */
  time_to_first_interview_seconds: number | null
}

/** `GET /api/employer/vacancies/{id}/analytics`; период фильтрует сущности по `created_at`. */
export function getVacancyAnalytics(vacancyId: number, dateFrom: Date | null, signal?: AbortSignal) {
  const query = dateFrom ? `?date_from=${encodeURIComponent(dateFrom.toISOString())}` : ''
  return api.get<VacancyAnalytics>(`/employer/vacancies/${vacancyId}/analytics${query}`, signal)
}
