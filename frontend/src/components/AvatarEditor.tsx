import { useRef, useState } from 'react'
import type { ChangeEvent } from 'react'

import { ApiError } from '@/api/client'
import { avatarUrl, deleteAvatar, setAvatar } from '@/api/users'
import type { User } from '@/api/types'
import { CameraIcon } from '@/components/icons'
import './AvatarEditor.css'

interface AvatarEditorProps {
  user: User
  onChange: (user: User) => void
  /** Ошибка загрузки/удаления — показывает родитель, у себя в раскладке. */
  onError: (message: string | null) => void
}

/**
 * Установка/замена/удаление аватарки (раздел 27 тех-доки). Отдельного
 * `POST` для установки нет: `PATCH /users/me/avatar` и заводит, и заменяет.
 * Круглое фото с кнопкой-камерой; «Удалить фото» — ссылкой под ним.
 */
export function AvatarEditor({ user, onChange, onError }: AvatarEditorProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    setBusy(true)
    onError(null)
    try {
      onChange(await setAvatar(file))
    } catch (cause) {
      onError(cause instanceof ApiError ? cause.message : 'Не удалось загрузить фото')
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    setBusy(true)
    onError(null)
    try {
      await deleteAvatar()
      onChange({ ...user, has_avatar: false, avatar_updated_at: null })
    } catch (cause) {
      onError(cause instanceof ApiError ? cause.message : 'Не удалось удалить фото')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="avatarEditor">
      <button
        type="button"
        className={`avatarEditor__photo${busy ? ' avatarEditor__photo--busy' : ''}`}
        aria-label={user.has_avatar ? 'Заменить фото' : 'Загрузить фото'}
        disabled={busy}
        onClick={() => inputRef.current?.click()}
      >
        {user.has_avatar ? (
          <img src={avatarUrl(user.avatar_updated_at)} alt="" />
        ) : (
          <span className="avatarEditor__initials">{user.first_name.slice(0, 1).toUpperCase()}</span>
        )}
        <span className="avatarEditor__camera" aria-hidden="true">
          <CameraIcon size={18} strokeWidth={2} />
        </span>
      </button>

      {user.has_avatar ? (
        <button type="button" className="avatarEditor__delete" disabled={busy} onClick={() => void handleDelete()}>
          Удалить фото
        </button>
      ) : null}

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        hidden
        onChange={(event) => void handleFileChange(event)}
      />
    </div>
  )
}
