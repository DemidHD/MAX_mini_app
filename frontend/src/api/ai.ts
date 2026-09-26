import { api } from '@/api/client'
import type { CriterionType, ScreeningQuestionType } from '@/api/hiring'

/**
 * ИИ-помощник создания вакансии (P1, раздел 58 тех-доки; контракты —
 * `docs/api-contracts.md`, «POST /api/ai/*»). Ничего не создаёт и не
 * публикует: результат — подсказка для экрана подтверждения E12.
 */

/** Черновик полей; любое поле может отсутствовать (частичный разбор). */
export interface ParsedVacancyDraft {
  title: string | null
  company_name: string | null
  description: string | null
  location: string | null
  salary_min: string | number | null
  salary_max: string | number | null
  schedule: string | null
  criteria: { type: CriterionType; required: boolean; value: Record<string, unknown> }[]
  questions: { question: string; type: ScreeningQuestionType }[]
}

export interface ParseVacancyResponse {
  parsed: ParsedVacancyDraft
  source_text: string
  provider: string | null
  /** `false` — ни один провайдер не ответил: переход на ручную форму (раздел 57). */
  ai_available: boolean
  /** Описана запрещённая деятельность — показать причину, а не E12. */
  rejected: boolean
  rejection_reason: string | null
}

export interface TranscribeVacancyResponse {
  /** Пустая строка с `provider: null` — распознать не удалось. */
  text: string
  provider: string | null
}

/** Максимальная длина текста вакансии на backend (`MAX_VACANCY_TEXT_LENGTH`). */
export const VACANCY_TEXT_MAX_LENGTH = 4000

export function parseVacancy(text: string, signal?: AbortSignal) {
  return api.post<ParseVacancyResponse>('/ai/parse-vacancy', { text }, signal)
}

export function transcribeVacancy(audio: Blob, signal?: AbortSignal) {
  const form = new FormData()
  form.append('file', audio, audio.type === 'audio/wav' ? 'voice.wav' : 'voice.ogg')
  return api.postForm<TranscribeVacancyResponse>('/ai/transcribe-vacancy', form, signal)
}
