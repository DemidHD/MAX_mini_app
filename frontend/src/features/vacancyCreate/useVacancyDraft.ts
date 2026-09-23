import { createContext, useContext } from 'react'

import type { VacancyResponse } from '@/api/vacancies'
import type { CriterionKey, VacancyDraft } from '@/features/vacancyCreate/draft'

export interface VacancyDraftContextValue {
  draft: VacancyDraft
  updateDraft: (patch: Partial<VacancyDraft>) => void
  setCriterionRequired: (key: CriterionKey, required: boolean) => void
  resetDraft: () => void
  /** Заполняется после успешного `createVacancy` — читает `VacancyPublishedPage`. */
  publishedVacancy: VacancyResponse | null
  setPublishedVacancy: (vacancy: VacancyResponse | null) => void
}

export const VacancyDraftContext = createContext<VacancyDraftContextValue | null>(null)

export function useVacancyDraft(): VacancyDraftContextValue {
  const context = useContext(VacancyDraftContext)
  if (!context) {
    throw new Error('useVacancyDraft должен использоваться внутри VacancyDraftProvider')
  }
  return context
}
