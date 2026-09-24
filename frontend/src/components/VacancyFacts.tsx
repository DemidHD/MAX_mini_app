import type { ReactNode } from 'react'

import type { CriterionType, VacancyCriterion, VacancySummary } from '@/api/hiring'
import { BoltIcon, BriefcaseIcon, CalendarIcon, ClockIcon, CoinsIcon, DocumentIcon, PinIcon } from '@/components/icons'
import { criterionLabel, formatDayMonthShort, scheduleLabel } from '@/lib/format'

/** Иконка условия вакансии — общая для карточки ленты (C02) и деталей (C03). */
export function criterionIcon(type: CriterionType, size = 22): ReactNode {
  switch (type) {
    case 'schedule':
      return <CalendarIcon size={size} />
    case 'location':
      return <PinIcon size={size} />
    case 'salary':
      return <CoinsIcon size={size} />
    case 'available_from':
      return <BoltIcon size={size} />
    case 'experience':
      return <BriefcaseIcon size={size} />
    case 'certificate':
      return <DocumentIcon size={size} />
  }
}

/** Три коротких факта вакансии: где, по какому графику, когда выходить. */
export function vacancyFacts(vacancy: VacancySummary, size = 22): { key: string; icon: ReactNode; label: string }[] {
  const facts: { key: string; icon: ReactNode; label: string }[] = []
  if (vacancy.location) facts.push({ key: 'location', icon: <PinIcon size={size} />, label: vacancy.location })
  if (vacancy.schedule) {
    facts.push({ key: 'schedule', icon: <CalendarIcon size={size} />, label: scheduleLabel(vacancy.schedule) })
  }
  const start = vacancy.criteria.find((criterion) => criterion.type === 'available_from')
  facts.push({
    key: 'start',
    icon: start ? <BoltIcon size={size} /> : <ClockIcon size={size} />,
    label: start ? startLabel(String(start.value.date ?? '')) : 'Выход по договоренности',
  })
  return facts
}

export function splitCriteria(criteria: VacancyCriterion[]) {
  return {
    required: criteria.filter((criterion) => criterion.required),
    desired: criteria.filter((criterion) => !criterion.required),
  }
}

export { criterionLabel }

/** Короткая подпись срока выхода для чипа: «Выход сразу» / «Выход до 26 сен». */
function startLabel(date: string): string {
  if (!date) return 'Выход по договоренности'
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return new Date(`${date}T00:00:00`) <= today ? 'Выход сразу' : `Выход до ${formatDayMonthShort(date)}`
}
