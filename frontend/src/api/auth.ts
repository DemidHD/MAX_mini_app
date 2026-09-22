import { api } from '@/api/client'
import type { AuthMaxResponse } from '@/api/types'

/**
 * POST /auth/max (раздел 7 тех-доки).
 *
 * `initData` отправляется исходной строкой, без разбора и пересборки на
 * frontend — подпись проверяет только backend.
 */
export function authMax(initData: string, signal?: AbortSignal): Promise<AuthMaxResponse> {
  return api.post<AuthMaxResponse>('/auth/max', { init_data: initData }, signal)
}
