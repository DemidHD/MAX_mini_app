/**
 * Код реферальной ссылки (R01, функция 32): ссылка `{APP_URL}/v/{token}?ref={code}`
 * открывает публичную вакансию, а засчитывается код при отклике
 * (`POST /vacancies/{id}/apply?ref=`). Между этими шагами кандидат может
 * выбрать роль или заполнить профиль, поэтому код запоминается на время
 * сессии по id вакансии. Хранилище может быть недоступно — тогда отклик
 * просто уходит без источника (backend тоже считает его best-effort).
 */

const key = (vacancyId: number) => `max-hiring:ref:${vacancyId}`

export function rememberReferral(vacancyId: number, code: string): void {
  try {
    sessionStorage.setItem(key(vacancyId), code)
  } catch {
    // Хранилище недоступно — источник не сохранится, отклик от этого не ломается.
  }
}

export function readReferral(vacancyId: number): string | null {
  try {
    return sessionStorage.getItem(key(vacancyId))
  } catch {
    return null
  }
}

export function forgetReferral(vacancyId: number): void {
  try {
    sessionStorage.removeItem(key(vacancyId))
  } catch {
    // См. rememberReferral.
  }
}
