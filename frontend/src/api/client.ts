/**
 * Тонкая обёртка над fetch для REST API backend (`/api/*`, раздел 27 тех-доки).
 *
 * Идентичность пользователя определяется только серверной сессией
 * (раздел 10) — client всегда шлёт credentials и никогда не добавляет
 * `user_id`/`candidate_id`/`employer_id` в запрос.
 *
 * Сессия передаётся cookie ИЛИ заголовком `Authorization: Bearer …`.
 * Заголовок — fallback для web.max.ru: там Mini App открыт во фрейме на
 * стороннем домене, и браузер блокирует cookie backend как стороннюю.
 * Токен живёт только в памяти вкладки (см. `setSessionToken`) — на каждом
 * монтировании `AuthProvider` заново вызывает `/auth/max`, поэтому
 * персистентность через localStorage не нужна.
 */

// В dev-режиме запросы проксируются Vite (см. vite.config.ts), поэтому базовый
// путь по умолчанию относительный. В production можно переопределить через env,
// если backend разместится на другом origin.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

let sessionToken: string | null = null

/** Сохраняет токен сессии из ответа `/auth/max` для заголовка Authorization. */
export function setSessionToken(token: string | null): void {
  sessionToken = token
}

export interface ApiErrorBody {
  code: string
  message: string
  details?: unknown
}

/** Ошибка API в формате `register_exception_handlers` (backend/app/core/errors.py). */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.details = body.details
  }
}

/** Не удалось достучаться до сервера (офлайн, DNS, backend не поднят). */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super('Не удалось соединиться с сервером')
    this.name = 'NetworkError'
    this.cause = cause
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  json?: unknown
  body?: BodyInit
  signal?: AbortSignal
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', json, body, signal } = options
  const headers: Record<string, string> = {}
  let requestBody = body

  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(json)
  }

  if (sessionToken) {
    headers['Authorization'] = `Bearer ${sessionToken}`
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: requestBody,
      credentials: 'include',
      signal,
    })
  } catch (cause) {
    throw new NetworkError(cause)
  }

  if (response.status === 204) {
    return undefined as T
  }

  const isJson = response.headers.get('content-type')?.includes('application/json')
  const payload = isJson ? await response.json() : undefined

  if (!response.ok) {
    const errorBody: ApiErrorBody = payload?.error ?? {
      code: 'unknown_error',
      message: response.statusText || 'Неизвестная ошибка сервера',
    }
    throw new ApiError(response.status, errorBody)
  }

  return payload as T
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { method: 'GET', signal }),
  post: <T>(path: string, json?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: 'POST', json, signal }),
  patch: <T>(path: string, json?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: 'PATCH', json, signal }),
  postForm: <T>(path: string, body: FormData, signal?: AbortSignal) =>
    request<T>(path, { method: 'POST', body, signal }),
  patchForm: <T>(path: string, body: FormData, signal?: AbortSignal) =>
    request<T>(path, { method: 'PATCH', body, signal }),
  delete: <T>(path: string, signal?: AbortSignal) => request<T>(path, { method: 'DELETE', signal }),
}

export { API_BASE_URL }
