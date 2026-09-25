import { createContext, useContext } from 'react'

import type { Vacancy } from '@/api/hiring'
import type { VacancyResponse } from '@/api/vacancies'
import type { CriterionKey, VacancyDraft } from '@/features/vacancyCreate/draft'

export interface VacancyDraftContextValue {
  draft: VacancyDraft
  updateDraft: (patch: Partial<VacancyDraft>) => void
  /** Заменить форму целиком — например, результатом ИИ-разбора (E11/E13). */
  setDraft: (draft: VacancyDraft) => void
  setCriterionRequired: (key: CriterionKey, required: boolean) => void
  /** `POST` (первый раз) или `PATCH` черновика на сервере. */
  saveDraft: () => Promise<Vacancy>
  /** Публикация; после неё форма очищается, а вакансия лежит в `publishedVacancy`. */
  publish: () => Promise<Vacancy>
  /** Новая вакансия с пустой формой. */
  startNew: () => void
  /** Продолжить серверный черновик. */
  openDraft: (vacancy: Vacancy) => void
  /** Заполняется после успешной публикации — читает `VacancyPublishedPage`. */
  publishedVacancy: VacancyResponse | null
}

export const VacancyDraftContext = createContext<VacancyDraftContextValue | null>(null)

export function useVacancyDraft(): VacancyDraftContextValue {
  const context = useContext(VacancyDraftContext)
  if (!context) {
    throw new Error('useVacancyDraft должен использоваться внутри VacancyDraftProvider')
  }
  return context
}
