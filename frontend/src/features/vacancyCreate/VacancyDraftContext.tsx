import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import type { VacancyResponse } from '@/api/vacancies'
import { VacancyDraftContext } from '@/features/vacancyCreate/useVacancyDraft'
import { EMPTY_DRAFT } from '@/features/vacancyCreate/draft'
import type { CriterionKey, VacancyDraft } from '@/features/vacancyCreate/draft'

const STORAGE_KEY = 'max-hiring:vacancy-draft'

function loadDraft(): VacancyDraft {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return EMPTY_DRAFT
    return { ...EMPTY_DRAFT, ...JSON.parse(raw) }
  } catch {
    return EMPTY_DRAFT
  }
}

function persistDraft(draft: VacancyDraft): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(draft))
  } catch {
    // Приватный режим/переполненное хранилище — черновик просто не переживёт
    // перезагрузку, ничего критичного.
  }
}

export function VacancyDraftProvider({ children }: { children: ReactNode }) {
  const [draft, setDraft] = useState<VacancyDraft>(loadDraft)
  const [publishedVacancy, setPublishedVacancy] = useState<VacancyResponse | null>(null)

  const updateDraft = useCallback((patch: Partial<VacancyDraft>) => {
    setDraft((previous) => {
      const next = { ...previous, ...patch }
      persistDraft(next)
      return next
    })
  }, [])

  const setCriterionRequired = useCallback((key: CriterionKey, required: boolean) => {
    setDraft((previous) => {
      const next = { ...previous, criteria: { ...previous.criteria, [key]: required } }
      persistDraft(next)
      return next
    })
  }, [])

  const resetDraft = useCallback(() => {
    setDraft(EMPTY_DRAFT)
    persistDraft(EMPTY_DRAFT)
    setPublishedVacancy(null)
  }, [])

  const value = useMemo(
    () => ({ draft, updateDraft, setCriterionRequired, resetDraft, publishedVacancy, setPublishedVacancy }),
    [draft, updateDraft, setCriterionRequired, resetDraft, publishedVacancy],
  )

  return <VacancyDraftContext.Provider value={value}>{children}</VacancyDraftContext.Provider>
}
