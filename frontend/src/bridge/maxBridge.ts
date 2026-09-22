/**
 * Интеграция с MAX Mini App (раздел 5 тех-доки).
 *
 * Тех-дока фиксирует только контракт, важный для авторизации:
 * `window.WebApp.initData` — исходная строка, которую нужно целиком
 * отправить на `/auth/max`; `initDataUnsafe` не доверенный источник и для
 * авторизации не используется. Остальной API `window.WebApp` (события,
 * тема, safe area и т.д.) тех-докой не описан — при необходимости его нужно
 * сверить с https://dev.max.ru/docs/webapps/bridge и расширить объявление
 * ниже, а не угадывать.
 */

export interface MaxWebApp {
  /** Исходная строка `key=value&...&hash=...`, подписанная MAX. */
  initData: string
  /** Разобранные данные без проверки подписи — не источник истины. */
  initDataUnsafe?: unknown
}

declare global {
  interface Window {
    WebApp?: MaxWebApp
  }
}

/**
 * В dev-режиме за пределами клиента MAX `window.WebApp` не существует.
 * Для локальной разработки backend умеет подписать тестовую initData
 * (`backend/scripts/dev_check.py --init-data`) — её можно один раз положить
 * в `.env.local` фронтенда как `VITE_DEV_INIT_DATA`, чтобы не открывать
 * настоящий Mini App на каждый запуск.
 */
function readDevInitData(): string | null {
  if (!import.meta.env.DEV) {
    return null
  }
  return import.meta.env.VITE_DEV_INIT_DATA || null
}

export class MaxBridgeUnavailableError extends Error {
  constructor() {
    super(
      'Mini App запущен вне MAX: window.WebApp недоступен. ' +
        'Для локальной разработки задайте VITE_DEV_INIT_DATA в .env.local.',
    )
    this.name = 'MaxBridgeUnavailableError'
  }
}

/** Возвращает исходную `initData` для отправки на `/auth/max`. */
export function getInitData(): string {
  const fromWebApp = window.WebApp?.initData
  if (fromWebApp) {
    return fromWebApp
  }

  const devInitData = readDevInitData()
  if (devInitData) {
    return devInitData
  }

  throw new MaxBridgeUnavailableError()
}
