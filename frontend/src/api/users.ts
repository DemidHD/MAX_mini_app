import { API_BASE_URL, api } from '@/api/client'
import type { ProfileUpdateRequest, RoleUpdateRequest, User } from '@/api/types'

/** Раздел 27 тех-доки — эндпоинты пользователя. */

export function getMe(signal?: AbortSignal): Promise<User> {
  return api.get<User>('/users/me', signal)
}

export function updateProfile(payload: ProfileUpdateRequest, signal?: AbortSignal): Promise<User> {
  return api.patch<User>('/users/me/profile', payload, signal)
}

export function updateRole(payload: RoleUpdateRequest, signal?: AbortSignal): Promise<User> {
  return api.patch<User>('/users/me/role', payload, signal)
}

export function setAvatar(file: File, signal?: AbortSignal): Promise<User> {
  const formData = new FormData()
  formData.append('file', file)
  return api.patchForm<User>('/users/me/avatar', formData, signal)
}

export function deleteAvatar(signal?: AbortSignal): Promise<void> {
  return api.delete<void>('/users/me/avatar', signal)
}

/**
 * URL для `<img src>` аватарки. Отдаётся тем же backend origin через
 * относительный путь — cookie сессии (раздел 10) идёт вместе с запросом
 * браузера, отдельный токен не нужен.
 *
 * `updatedAt` в query — техника cache-busting: после замены/удаления
 * аватарки путь один и тот же, а браузер должен перезапросить файл.
 */
export function avatarUrl(updatedAt: string | null): string {
  const version = updatedAt ? encodeURIComponent(updatedAt) : 'none'
  return `${API_BASE_URL}/users/me/avatar?v=${version}`
}
