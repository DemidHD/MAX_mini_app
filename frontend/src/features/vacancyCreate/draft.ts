/**
 * Константы и типы черновика вакансии. Экраны создания вакансии
 * (E02–E05 в UX-карте) работают с этим черновиком локально — backend ещё
 * не умеет ни создавать, ни хранить вакансии (см. комментарий в
 * `api/vacancies.ts`), поэтому черновик живёт в localStorage вкладки, а не
 * на сервере.
 */

export type CriterionKey = 'schedule' | 'location' | 'experience' | 'available_from' | 'salary'

export const CRITERION_KEYS: CriterionKey[] = [
  'schedule',
  'location',
  'experience',
  'available_from',
  'salary',
]

export const SCHEDULE_OPTIONS = ['2/2', '5/2', 'Полный день', 'Гибкий график'] as const

export const EXPERIENCE_OPTIONS = [
  { months: 0, label: 'Неважен' },
  { months: 6, label: 'От 6 месяцев' },
  { months: 12, label: 'От 1 года' },
  { months: 36, label: 'От 3 лет' },
] as const

export const AVAILABLE_FROM_OPTIONS = [
  { id: 'asap', label: 'Как можно скорее', days: 0 },
  { id: '3d', label: 'В течение 3 дней', days: 3 },
  { id: 'week', label: 'В течение недели', days: 7 },
  { id: 'month', label: 'В течение месяца', days: 30 },
] as const

export type AvailableFromId = (typeof AVAILABLE_FROM_OPTIONS)[number]['id']

export interface VacancyDraft {
  title: string
  salaryMin: string
  salaryMax: string
  location: string
  schedule: string
  experienceMonths: number
  availableFrom: AvailableFromId
  /** `true` — обязательное условие, `false` — желательное. */
  criteria: Record<CriterionKey, boolean>
}

export const EMPTY_DRAFT: VacancyDraft = {
  title: '',
  salaryMin: '',
  salaryMax: '',
  location: '',
  schedule: SCHEDULE_OPTIONS[0],
  experienceMonths: EXPERIENCE_OPTIONS[1].months,
  availableFrom: 'asap',
  criteria: {
    schedule: true,
    location: true,
    experience: false,
    available_from: true,
    salary: false,
  },
}

export function availableFromLabel(id: AvailableFromId): string {
  return AVAILABLE_FROM_OPTIONS.find((option) => option.id === id)?.label ?? id
}

export function experienceLabel(months: number): string {
  return EXPERIENCE_OPTIONS.find((option) => option.months === months)?.label ?? `От ${months} мес.`
}

export function availableFromDate(id: AvailableFromId): string {
  const option = AVAILABLE_FROM_OPTIONS.find((item) => item.id === id) ?? AVAILABLE_FROM_OPTIONS[0]
  const date = new Date()
  date.setDate(date.getDate() + option.days)
  return date.toISOString().slice(0, 10)
}

export function formatSalaryRange(min: string, max: string): string {
  const parts = [min, max].filter((value) => value.trim() !== '')
  if (parts.length === 0) return 'Зарплата не указана'
  const formatted = parts.map((value) => Number(value).toLocaleString('ru-RU'))
  return `${formatted.join('–')} ₽`
}

export function isBasicsComplete(draft: VacancyDraft): boolean {
  return draft.title.trim().length > 0 && draft.location.trim().length > 0
}

/**
 * Собирает тело `POST /vacancies` из черновика. Форма `value` — по
 * `docs/api-contracts.md` («Формат vacancy_criteria.value»), чтобы уже
 * реализованный подбор кандидатов понимал критерии, если backend когда-нибудь
 * подключит этот роутер.
 */
export function buildCreateVacancyPayload(draft: VacancyDraft) {
  const criteria = CRITERION_KEYS.map((key) => ({
    type: key,
    required: draft.criteria[key],
    value: criterionValue(key, draft),
  }))

  return {
    title: draft.title.trim(),
    location: draft.location.trim() || null,
    salary_min: draft.salaryMin.trim() ? Number(draft.salaryMin) : null,
    salary_max: draft.salaryMax.trim() ? Number(draft.salaryMax) : null,
    schedule: draft.schedule || null,
    status: 'published' as const,
    criteria,
  }
}

function criterionValue(key: CriterionKey, draft: VacancyDraft): Record<string, unknown> {
  switch (key) {
    case 'schedule':
      return { schedule: draft.schedule }
    case 'location':
      return { city: draft.location.trim() }
    case 'experience':
      return { min_months: draft.experienceMonths }
    case 'available_from':
      return { date: availableFromDate(draft.availableFrom) }
    case 'salary':
      return draft.salaryMax.trim() ? { max: Number(draft.salaryMax) } : {}
  }
}

/** Короткая подпись критерия для чипов на экране предпросмотра. */
export function criterionChipLabel(key: CriterionKey, draft: VacancyDraft): string {
  switch (key) {
    case 'schedule':
      return `График ${draft.schedule}`
    case 'location':
      return draft.location || 'Локация не указана'
    case 'experience':
      return `Опыт ${experienceLabel(draft.experienceMonths).toLowerCase()}`
    case 'available_from':
      return `Выход: ${availableFromLabel(draft.availableFrom).toLowerCase()}`
    case 'salary': {
      const { salaryMin, salaryMax } = draft
      if (salaryMax.trim()) return `До ${Number(salaryMax).toLocaleString('ru-RU')} ₽`
      if (salaryMin.trim()) return `От ${Number(salaryMin).toLocaleString('ru-RU')} ₽`
      return 'Зарплата не указана'
    }
  }
}
