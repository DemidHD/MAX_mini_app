import type { Vacancy } from '@/api/hiring'
import type { SheetOption } from '@/components/OptionSheet'

/** Вакансии работодателя как варианты шторки выбора; закрытая помечается. */
export function vacancyOptions(vacancies: Vacancy[]): SheetOption<number>[] {
  return vacancies.map((item) => ({
    id: item.id,
    label: item.status === 'closed' ? `${item.title} · закрыта` : item.title,
  }))
}
