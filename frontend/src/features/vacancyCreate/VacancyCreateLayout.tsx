import { Outlet } from 'react-router-dom'

import { VacancyDraftProvider } from '@/features/vacancyCreate/VacancyDraftContext'

/** Общий провайдер черновика для всех шагов создания вакансии (E02–E05). */
export function VacancyCreateLayout() {
  return (
    <VacancyDraftProvider>
      <Outlet />
    </VacancyDraftProvider>
  )
}
