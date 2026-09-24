import { useCallback, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import type { Vacancy } from '@/api/hiring'
import { ApiError } from '@/api/client'
import { createVacancy, updateVacancy } from '@/api/vacancies'
import type { VacancyFieldsInput, VacancyResponse } from '@/api/vacancies'
import { VacancyDraftContext } from '@/features/vacancyCreate/useVacancyDraft'
import { AVAILABLE_FROM_OPTIONS, EMPTY_DRAFT, buildVacancyFields, draftFromVacancy } from '@/features/vacancyCreate/draft'
import type { CriterionKey, VacancyDraft } from '@/features/vacancyCreate/draft'

const STORAGE_KEY = 'max-hiring:vacancy-draft'

function loadDraft(): VacancyDraft {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return EMPTY_DRAFT
    const draft: VacancyDraft = { ...EMPTY_DRAFT, ...JSON.parse(raw) }
    // Черновик мог сохраниться со сроком выхода, которого больше нет в списке.
    if (!AVAILABLE_FROM_OPTIONS.some((option) => option.id === draft.availableFrom)) {
      draft.availableFrom = EMPTY_DRAFT.availableFrom
    }
    return draft
  } catch {
    return EMPTY_DRAFT
  }
}

function persistDraft(draft: VacancyDraft): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(draft))
  } catch {
    // Приватный режим/переполненное хранилище — несохранённый ввод просто не
    // переживёт перезагрузку; серверный черновик от этого не страдает.
  }
}

export function VacancyDraftProvider({ children }: { children: ReactNode }) {
  const [draft, setDraftState] = useState<VacancyDraft>(loadDraft)
  const [publishedVacancy, setPublishedVacancy] = useState<VacancyResponse | null>(null)
  // Сохранение читает актуальный ввод, даже если его вызвали из обработчика,
  // который замкнул предыдущий рендер.
  const draftRef = useRef(draft)

  const setDraft = useCallback((next: VacancyDraft) => {
    draftRef.current = next
    persistDraft(next)
    setDraftState(next)
  }, [])

  const updateDraft = useCallback(
    (patch: Partial<VacancyDraft>) => setDraft({ ...draftRef.current, ...patch }),
    [setDraft],
  )

  const setCriterionRequired = useCallback(
    (key: CriterionKey, required: boolean) =>
      setDraft({ ...draftRef.current, criteria: { ...draftRef.current.criteria, [key]: required } }),
    [setDraft],
  )

  /**
   * Сохраняет черновик на сервере: первый раз — `POST` со статусом `draft`
   * (здесь backend проверяет лимит черновиков), дальше — `PATCH`.
   */
  const saveDraft = useCallback(async (): Promise<Vacancy> => {
    const current = draftRef.current
    const fields = buildVacancyFields(current)
    const vacancy =
      current.vacancyId === null
        ? await createVacancy({ ...fields, status: 'draft' })
        : await updateOrRecreate(current.vacancyId, fields, 'draft')
    const imageUrl = vacancy.image_url ?? null
    if (draftRef.current.vacancyId !== vacancy.id || draftRef.current.imageUrl !== imageUrl) {
      setDraft({ ...draftRef.current, vacancyId: vacancy.id, imageUrl })
    }
    return vacancy
  }, [setDraft])

  /** Публикует вакансию и очищает форму: следующая «Создать вакансию» начнётся с нуля. */
  const publish = useCallback(async (): Promise<Vacancy> => {
    const current = draftRef.current
    const fields = buildVacancyFields(current)
    const vacancy =
      current.vacancyId === null
        ? await createVacancy({ ...fields, status: 'published' })
        : await updateOrRecreate(current.vacancyId, fields, 'published')
    setPublishedVacancy(vacancy)
    setDraft(EMPTY_DRAFT)
    return vacancy
  }, [setDraft])

  const startNew = useCallback(() => setDraft(EMPTY_DRAFT), [setDraft])

  const openDraft = useCallback((vacancy: Vacancy) => setDraft(draftFromVacancy(vacancy)), [setDraft])

  const value = useMemo(
    () => ({ draft, updateDraft, setCriterionRequired, saveDraft, publish, startNew, openDraft, publishedVacancy }),
    [draft, updateDraft, setCriterionRequired, saveDraft, publish, startNew, openDraft, publishedVacancy],
  )

  return <VacancyDraftContext.Provider value={value}>{children}</VacancyDraftContext.Provider>
}

/**
 * `PATCH` черновика; если его на сервере уже нет (удалили с главной или с
 * другого устройства), введённое не теряем — создаём черновик заново.
 */
async function updateOrRecreate(
  vacancyId: number,
  fields: VacancyFieldsInput,
  status: 'draft' | 'published',
): Promise<Vacancy> {
  try {
    return await updateVacancy(vacancyId, status === 'published' ? { ...fields, status } : fields)
  } catch (cause) {
    if (!(cause instanceof ApiError && cause.status === 404)) throw cause
    return createVacancy({ ...fields, status })
  }
}
