import { useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { Avatar, Button, Flex, Typography } from '@maxhub/max-ui'

import { ApiError } from '@/api/client'
import { avatarUrl, deleteAvatar, setAvatar } from '@/api/users'
import type { User } from '@/api/types'

interface AvatarEditorProps {
  user: User
  onChange: (user: User) => void
}

/**
 * Установка/замена/удаление аватарки (раздел 27 тех-доки). Отдельного
 * `POST` для установки нет: `PATCH /users/me/avatar` и заводит, и заменяет.
 */
export function AvatarEditor({ user, onChange }: AvatarEditorProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    setBusy(true)
    setError(null)
    try {
      const updated = await setAvatar(file)
      onChange(updated)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Не удалось загрузить файл')
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    setBusy(true)
    setError(null)
    try {
      await deleteAvatar()
      onChange({ ...user, has_avatar: false, avatar_updated_at: null })
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Не удалось удалить аватарку')
    } finally {
      setBusy(false)
    }
  }

  const initials = user.first_name.slice(0, 1).toUpperCase()

  return (
    <Flex direction="column" align="center" gap={12}>
      <Avatar.Container size={88} form="circle">
        {user.has_avatar ? (
          <Avatar.Image src={avatarUrl(user.avatar_updated_at)} alt="Аватарка" />
        ) : (
          <Avatar.Text>{initials}</Avatar.Text>
        )}
      </Avatar.Container>

      <Flex gap={8}>
        <Button
          size="small"
          variant="secondary"
          loading={busy}
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {user.has_avatar ? 'Заменить' : 'Загрузить фото'}
        </Button>
        {user.has_avatar ? (
          <Button size="small" variant="ghost" disabled={busy} onClick={() => void handleDelete()}>
            Удалить
          </Button>
        ) : null}
      </Flex>

      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        style={{ display: 'none' }}
        onChange={(event) => void handleFileChange(event)}
      />

      {error ? <Typography.Body>{error}</Typography.Body> : null}
    </Flex>
  )
}
