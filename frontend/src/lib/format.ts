import type { CriterionType, VacancyCriterion } from '@/api/hiring'

/** Форматирование значений для экранов сценария найма (русская локаль). */

const MONTHS_GENITIVE = [
  'января',
  'февраля',
  'марта',
  'апреля',
  'мая',
  'июня',
  'июля',
  'августа',
  'сентября',
  'октября',
  'ноября',
  'декабря',
]
const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
const WEEKDAYS_SHORT = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']

export function plural(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

/** Неразрывный пробел: «₽» и предлог не отрываются от суммы при переносе. */
const NBSP = '\u00a0'

export function formatMoney(value: string | number): string {
  return `${Math.round(Number(value)).toLocaleString('ru-RU')}${NBSP}₽`
}

export function formatSalaryRange(min: string | null, max: string | null): string {
  if (min && max) {
    return `${Math.round(Number(min)).toLocaleString('ru-RU')}–${formatMoney(max)}`
  }
  if (min) return `от${NBSP}${formatMoney(min)}`
  if (max) return `до${NBSP}${formatMoney(max)}`
  return 'Зарплата не указана'
}

/** «1 год 4 месяца»; `short` — «1 год 4 мес.» для плотных карточек. */
export function formatExperience(months: number | null, short = false): string {
  if (months === null) return 'Опыт не указан'
  if (months === 0) return 'Без опыта'
  const years = Math.floor(months / 12)
  const rest = months % 12
  const parts: string[] = []
  if (years > 0) parts.push(`${years} ${plural(years, 'год', 'года', 'лет')}`)
  if (rest > 0) parts.push(short ? `${rest} мес.` : `${rest} ${plural(rest, 'месяц', 'месяца', 'месяцев')}`)
  return parts.join(' ')
}

function toDate(value: string | Date): Date {
  if (value instanceof Date) return value
  // Дата без времени (`YYYY-MM-DD`) — локальная, а не UTC-полночь.
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value)
}

export function formatDayMonth(value: string | Date): string {
  const date = toDate(value)
  return `${date.getDate()} ${MONTHS_GENITIVE[date.getMonth()]}`
}

export function formatDayMonthShort(value: string | Date): string {
  const date = toDate(value)
  return `${date.getDate()} ${MONTHS_SHORT[date.getMonth()]}`
}

export function monthShort(value: string | Date): string {
  return MONTHS_SHORT[toDate(value).getMonth()]
}

export function weekdayShort(value: string | Date): string {
  return WEEKDAYS_SHORT[toDate(value).getDay()]
}

export function formatTime(value: string | Date): string {
  const date = toDate(value)
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

export function dayKey(value: string | Date): string {
  const date = toDate(value)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function daysFromToday(value: string | Date): number {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const date = toDate(value)
  date.setHours(0, 0, 0, 0)
  return Math.round((date.getTime() - today.getTime()) / 86_400_000)
}

/** «Выход завтра» / «Выход через 3 дня» / «Выход с 12 октября». */
export function formatAvailableFrom(value: string | null): string {
  if (!value) return 'Дата выхода не указана'
  const days = daysFromToday(value)
  if (days <= 0) return 'Выход сразу'
  if (days === 1) return 'Выход завтра'
  if (days <= 7) return `Выход через ${days} ${plural(days, 'день', 'дня', 'дней')}`
  return `Выход с ${formatDayMonth(value)}`
}

/** Коротко для профиля кандидата: «Сразу» / «Завтра» / «Через 3 дня». */
export function formatReadyShort(value: string | null): string {
  if (!value) return 'Не указано'
  const label = formatAvailableFrom(value).replace(/^Выход\s/, '')
  return label.charAt(0).toUpperCase() + label.slice(1)
}

const SCHEDULE_LABELS: Record<string, string> = {
  full_time: 'Полный день',
  part_time: 'Неполный день',
  shift: 'Сменный',
  night: 'Ночной',
  flexible: 'Гибкий',
}

export function scheduleLabel(value: string | null): string {
  if (!value) return 'Не указан'
  return SCHEDULE_LABELS[value] ?? value
}

function readString(value: Record<string, unknown>, key: string): string | null {
  const raw = value[key]
  return typeof raw === 'string' || typeof raw === 'number' ? String(raw) : null
}

/** Подпись условия вакансии для чипов и списков («График 2/2», «Опыт от 6 месяцев»). */
export function criterionLabel(criterion: VacancyCriterion): string {
  const { value } = criterion
  switch (criterion.type) {
    case 'schedule':
      return `График ${scheduleLabel(readString(value, 'schedule'))}`
    case 'location':
      return readString(value, 'city') ?? 'Локация'
    case 'salary': {
      const max = readString(value, 'max')
      return max ? `До ${formatMoney(max)}` : 'Зарплата'
    }
    case 'available_from': {
      const date = readString(value, 'date')
      if (!date) return 'Дата выхода'
      const days = daysFromToday(date)
      if (days <= 0) return 'Выход сразу'
      if (days <= 7) return `Выход в ближайшие ${days} ${plural(days, 'день', 'дня', 'дней')}`
      return `Выход до ${formatDayMonth(date)}`
    }
    case 'experience': {
      const months = Number(readString(value, 'min_months') ?? 0)
      if (!months) return 'Опыт не обязателен'
      return months % 12 === 0
        ? `Опыт от ${months / 12} ${plural(months / 12, 'года', 'лет', 'лет')}`
        : `Опыт от ${months} ${plural(months, 'месяца', 'месяцев', 'месяцев')}`
    }
    case 'certificate':
      return readString(value, 'name') ?? 'Документ'
  }
}

/** Короткое название типа условия — для экрана «не прошёл обязательное условие». */
export const CRITERION_TITLES: Record<CriterionType, string> = {
  location: 'Локация',
  schedule: 'График',
  salary: 'Зарплата',
  available_from: 'Дата выхода',
  experience: 'Опыт',
  certificate: 'Документ',
}

/** Нейтральное пояснение причины несовпадения (UX-карта, C06: без оценки личности). */
export const CRITERION_MISMATCH_REASONS: Record<CriterionType, string> = {
  location: 'Вы указали другой город',
  schedule: 'Вы указали другой график',
  salary: 'Ваши ожидания выше предложения',
  available_from: 'Вы готовы выйти позже',
  experience: 'Нужно больше опыта',
  certificate: 'Нужен документ, которого пока нет',
}
