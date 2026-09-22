import { useState } from 'react'
import { Button, Flex, Input, Typography } from '@maxhub/max-ui'

import { ApiError } from '@/api/client'
import { updateProfile } from '@/api/users'
import { AvatarEditor } from '@/components/AvatarEditor'
import { useAuth } from '@/auth/useAuth'
import type { User } from '@/api/types'

const LANGUAGE_LABELS: Record<string, string> = {
  ru: 'Русский',
  en: 'English',
}

/**
 * Экран пользователя (раздел 61 тех-доки). Обёртка ждёт готового
 * пользователя из AuthContext и монтирует форму заново на каждый
 * user_id — состояние формы инициализируется из props при монтировании,
 * без синхронизирующего эффекта.
 */
export function ProfilePage() {
  const { state } = useAuth()

  if (state.status !== 'authenticated') {
    return null
  }

  return <ProfileForm key={state.user.user_id} />
}

function ProfileForm() {
  const { state, setUser } = useAuth()
  // ProfilePage монтирует этот компонент только при status === 'authenticated'
  // и пересоздаёт его (через key) при смене user_id, поэтому на весь срок
  // жизни этого инстанса пользователь гарантированно есть уже на первом рендере.
  const initialUser = state.status === 'authenticated' ? state.user : null

  const [firstName, setFirstName] = useState(initialUser?.first_name ?? '')
  const [lastName, setLastName] = useState(initialUser?.last_name ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  if (state.status !== 'authenticated') {
    return null
  }
  const { user } = state

  const isDirty = firstName !== user.first_name || lastName !== (user.last_name ?? '')

  async function handleSave() {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const updated = await updateProfile({
        first_name: firstName,
        last_name: lastName,
      })
      setUser(updated)
      setSaved(true)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Не удалось сохранить изменения')
    } finally {
      setSaving(false)
    }
  }

  function handleAvatarChange(updated: User) {
    setUser(updated)
  }

  return (
    <Flex direction="column" gap={24} style={{ padding: 24 }}>
      <Typography.Title>Профиль</Typography.Title>

      <AvatarEditor user={user} onChange={handleAvatarChange} />

      <Flex direction="column" gap={12}>
        <Input
          placeholder="Имя"
          value={firstName}
          onChange={(event) => {
            setFirstName(event.target.value)
            setSaved(false)
          }}
        />
        <Input
          placeholder="Фамилия"
          value={lastName}
          onChange={(event) => {
            setLastName(event.target.value)
            setSaved(false)
          }}
        />

        <Flex direction="column" gap={4}>
          <Typography.Label>Username</Typography.Label>
          <Typography.Body>{user.username ? `@${user.username}` : 'не указан в MAX'}</Typography.Body>
        </Flex>

        <Flex direction="column" gap={4}>
          <Typography.Label>Язык</Typography.Label>
          <Typography.Body>
            {user.language_code ? LANGUAGE_LABELS[user.language_code] ?? user.language_code : '—'}
          </Typography.Body>
        </Flex>

        <Button
          size="large"
          stretched
          loading={saving}
          disabled={saving || !isDirty || firstName.trim().length === 0}
          onClick={() => void handleSave()}
        >
          Сохранить
        </Button>

        {saved ? <Typography.Body>Сохранено</Typography.Body> : null}
        {error ? <Typography.Body>{error}</Typography.Body> : null}
      </Flex>
    </Flex>
  )
}
