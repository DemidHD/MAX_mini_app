/**
 * Типы совпадают с Pydantic-схемами backend (раздел 8, 52 тех-доки).
 * Источник истины — `backend/app/users/schemas.py` и `backend/app/auth/schemas.py`.
 */

export type UserRole = 'candidate' | 'employer'

/** Значения вычисляются backend в `compute_current_step` (раздел 7 тех-доки). */
export type CurrentStep =
  | 'role_selection'
  | 'candidate_profile'
  | 'application_status'
  | 'feed'
  | 'vacancy_create'
  | 'employer_home'

export interface User {
  user_id: number
  first_name: string
  last_name: string | null
  username: string | null
  language_code: string | null
  role: UserRole | null
  has_avatar: boolean
  avatar_updated_at: string | null
}

export interface AuthMaxResponse {
  user: User
  current_step: CurrentStep
  application_id: number | null
  /**
   * Незаконченный черновик работодателя для шага `vacancy_create`. Backend
   * ещё не отдаёт поле — без него работодатель попадает на пустую форму.
   */
  vacancy_id?: number | null
  /**
   * Та же сессия, что уже установлена HTTP-only cookie — fallback для
   * web.max.ru, где cookie сторонняя и блокируется браузером (раздел 10
   * тех-доки). Используется как `Authorization: Bearer …` в `api/client.ts`.
   */
  session_token: string
}

export interface ProfileUpdateRequest {
  first_name?: string
  last_name?: string
}

export interface RoleUpdateRequest {
  role: UserRole
}
