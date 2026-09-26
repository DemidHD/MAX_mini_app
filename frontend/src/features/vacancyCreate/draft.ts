import type { ParsedVacancyDraft } from '@/api/ai'
import type { Vacancy } from '@/api/hiring'
import type { VacancyFieldsInput, VacancyQuestionInput } from '@/api/vacancies'
import { formatDayMonth } from '@/lib/format'

/**
 * Константы и типы черновика вакансии (экраны E02–E05 в UX-карте).
 *
 * Черновик живёт на сервере: первый «Далее» создаёт вакансию в статусе
 * `draft`, следующие шаги сохраняют её через `PATCH`, публикация — `PATCH
 * status: published`. В localStorage вкладки лежит только текущий ввод и id
 * серверного черновика, чтобы перезагрузка не теряла несохранённое.
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

/**
 * Срок выхода — обязательное условие `available_from` (кандидат готов выйти
 * не позже даты). «Как можно скорее» — не «сегодня»: договор, согласование и
 * подпись занимают минимум пару дней, поэтому это 3 дня от публикации.
 */
export const AVAILABLE_FROM_OPTIONS = [
  { id: 'asap', label: 'Как можно скорее', days: 3 },
  { id: 'week', label: 'В течение недели', days: 7 },
  { id: '2weeks', label: 'В течение двух недель', days: 14 },
  { id: 'month', label: 'В течение месяца', days: 30 },
] as const

export type AvailableFromId = (typeof AVAILABLE_FROM_OPTIONS)[number]['id']

export interface VacancyDraft {
  /** id серверного черновика; `null` — ещё ни разу не сохранялся. */
  vacancyId: number | null
  /** Фото, которое backend подобрал черновику при создании (только для показа). */
  imageUrl: string | null
  title: string
  companyName: string
  description: string
  salaryMin: string
  salaryMax: string
  location: string
  schedule: string
  experienceMonths: number
  availableFrom: AvailableFromId
  /** `true` — обязательное условие, `false` — желательное. */
  criteria: Record<CriterionKey, boolean>
  /** Свободный текст вакансии (E11/E13) — живёт только в форме, на сервер не уходит. */
  sourceText: string
}

export const EMPTY_DRAFT: VacancyDraft = {
  vacancyId: null,
  imageUrl: null,
  title: '',
  companyName: '',
  description: '',
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
  sourceText: '',
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

export const COMPANY_NAME_MAX_LENGTH = 255
export const DESCRIPTION_MAX_LENGTH = 1000

/**
 * Поля вакансии для `POST` / `PATCH /vacancies`, статус задаёт вызывающий.
 * Форма `criteria[].value` — по `docs/api-contracts.md` («Формат
 * vacancy_criteria.value»): так её понимает подбор ленты.
 */
export function buildVacancyFields(draft: VacancyDraft): VacancyFieldsInput {
  const criteria = CRITERION_KEYS.map((key) => ({
    type: key,
    required: draft.criteria[key],
    value: criterionValue(key, draft),
  })).filter((criterion) => Object.keys(criterion.value).length > 0)

  return {
    title: draft.title.trim(),
    location: draft.location.trim() || null,
    salary_min: draft.salaryMin.trim() ? Number(draft.salaryMin) : null,
    salary_max: draft.salaryMax.trim() ? Number(draft.salaryMax) : null,
    schedule: draft.schedule || null,
    company_name: draft.companyName.trim() || null,
    description: draft.description.trim() || null,
    criteria,
    questions: buildScreeningQuestions(draft),
  }
}

/**
 * Вопросы первичного отбора (C05) по обязательным условиям.
 *
 * Решение продукта: вопросы составляются из условий вакансии, отдельного
 * экрана вопросов у работодателя нет. Отказ на вопрос по обязательному
 * условию — отсекающий (`must_equal`, api-contracts).
 */
function buildScreeningQuestions(draft: VacancyDraft): VacancyQuestionInput[] {
  const questions: VacancyQuestionInput[] = []
  const mustBeYes = { must_equal: true }
  if (draft.criteria.schedule && draft.schedule) {
    questions.push({
      question: `Сможете работать по графику ${draft.schedule}?`,
      type: 'boolean',
      required: true,
      validation_rules: mustBeYes,
    })
  }
  if (draft.criteria.available_from) {
    questions.push({
      question: `Готовы выйти на работу до ${formatDayMonth(availableFromDate(draft.availableFrom))}?`,
      type: 'boolean',
      required: true,
      validation_rules: mustBeYes,
    })
  }
  return questions
}

/**
 * Город для критерия `location`. Подбор сравнивает город профиля с
 * `{"city": ...}` целиком, а в поле адреса пишут «Москва, м. Белорусская» —
 * берём часть до первой запятой.
 */
function cityFromLocation(location: string): string {
  return location.split(',')[0].trim()
}

function criterionValue(key: CriterionKey, draft: VacancyDraft): Record<string, unknown> {
  switch (key) {
    case 'schedule':
      return draft.schedule ? { schedule: draft.schedule } : {}
    case 'location': {
      const city = cityFromLocation(draft.location)
      return city ? { city } : {}
    }
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

/**
 * Черновик с сервера → состояние формы: для продолжения незаконченной
 * вакансии с главной (E01) или после повторного открытия Mini App.
 */
export function draftFromVacancy(vacancy: Vacancy): VacancyDraft {
  const criterion = (key: CriterionKey) => vacancy.criteria.find((item) => item.type === key)
  const required = { ...EMPTY_DRAFT.criteria }
  for (const key of CRITERION_KEYS) {
    const found = criterion(key)
    if (found) required[key] = found.required
  }

  const minMonths = Number(criterion('experience')?.value.min_months)
  const startDate = criterion('available_from')?.value.date

  return {
    vacancyId: vacancy.id,
    imageUrl: vacancy.image_url ?? null,
    title: vacancy.title,
    companyName: vacancy.company_name ?? '',
    description: vacancy.description ?? '',
    salaryMin: moneyToInput(vacancy.salary_min),
    salaryMax: moneyToInput(vacancy.salary_max),
    location: vacancy.location ?? '',
    schedule: vacancy.schedule ?? EMPTY_DRAFT.schedule,
    experienceMonths: Number.isFinite(minMonths) ? minMonths : EMPTY_DRAFT.experienceMonths,
    availableFrom: typeof startDate === 'string' ? availableFromIdForDate(startDate) : EMPTY_DRAFT.availableFrom,
    criteria: required,
    sourceText: '',
  }
}

function moneyToInput(value: string | null): string {
  return value === null ? '' : String(Math.round(Number(value)))
}

/** Ближайший вариант срока выхода, который не раньше сохранённой даты. */
export function availableFromIdForDate(date: string): AvailableFromId {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = Math.round((new Date(`${date}T00:00:00`).getTime() - today.getTime()) / 86_400_000)
  return (AVAILABLE_FROM_OPTIONS.find((option) => option.days >= days) ?? AVAILABLE_FROM_OPTIONS.at(-1)!).id
}

export function isDraftEmpty(draft: VacancyDraft): boolean {
  return (
    draft.vacancyId === null &&
    !draft.title.trim() &&
    !draft.companyName.trim() &&
    !draft.description.trim() &&
    !draft.location.trim() &&
    !draft.salaryMin.trim() &&
    !draft.salaryMax.trim()
  )
}

/**
 * Результат ИИ-разбора (E11/E13) → форма. Разбор — подсказка, а не готовые
 * данные: всё, чего в тексте нет, остаётся пустым, чтобы экран
 * подтверждения E12 подсветил это поле, а не выдумал значение.
 * id серверного черновика сохраняется — правка идёт в тот же черновик.
 */
export function draftFromParsed(current: VacancyDraft, parsed: ParsedVacancyDraft, sourceText: string): VacancyDraft {
  const criterion = (key: CriterionKey) => parsed.criteria.find((item) => item.type === key)
  const required = { ...EMPTY_DRAFT.criteria }
  for (const key of CRITERION_KEYS) {
    const found = criterion(key)
    if (found) required[key] = found.required
  }

  const minMonths = Number(criterion('experience')?.value.min_months)
  const startDate = criterion('available_from')?.value.date
  const salaryMax = parsed.salary_max ?? criterion('salary')?.value.max

  return {
    ...EMPTY_DRAFT,
    vacancyId: current.vacancyId,
    imageUrl: current.imageUrl,
    title: parsed.title?.trim() ?? '',
    companyName: parsed.company_name?.trim().slice(0, COMPANY_NAME_MAX_LENGTH) ?? '',
    description: parsed.description?.trim().slice(0, DESCRIPTION_MAX_LENGTH) ?? '',
    salaryMin: parsedMoney(parsed.salary_min),
    salaryMax: parsedMoney(salaryMax),
    location: parsed.location?.trim() ?? '',
    schedule: parsed.schedule?.trim() ?? '',
    experienceMonths: Number.isFinite(minMonths) ? minMonths : 0,
    availableFrom: typeof startDate === 'string' ? availableFromIdForDate(startDate) : EMPTY_DRAFT.availableFrom,
    criteria: required,
    sourceText,
  }
}

/** Сумма из ответа ИИ: число, строка или мусор — в поле формы попадает только число. */
function parsedMoney(value: unknown): string {
  const amount = typeof value === 'number' || typeof value === 'string' ? Number(value) : Number.NaN
  return Number.isFinite(amount) && amount > 0 ? String(Math.round(amount)) : ''
}
