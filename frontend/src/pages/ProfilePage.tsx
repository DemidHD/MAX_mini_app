import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import { getEmployerVacancies, getVacancyCandidates } from '@/api/hiring'
import { updateProfile } from '@/api/users'
import type { User } from '@/api/types'
import { useAuth } from '@/auth/useAuth'
import { AvatarEditor } from '@/components/AvatarEditor'
import { EmployerLayout } from '@/components/EmployerLayout'
import {
  AccentMarks,
  AtIcon,
  BriefcaseIcon,
  CloseIcon,
  GlobeIcon,
  HashIcon,
  PeopleFilledIcon,
} from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { plural } from '@/lib/format'
import './ProfilePage.css'

const LANGUAGE_LABELS: Record<string, string> = {
  ru: 'Русский',
  en: 'English',
}

const ROLE_LABELS: Record<NonNullable<User['role']>, string> = {
  employer: 'Работодатель',
  candidate: 'Ищет работу',
}

/**
 * Экран пользователя (раздел 61 тех-доки): фото, имя и фамилия
 * (`PATCH /users/me/profile`, раздел 8 — MAX их больше не перезаписывает) и
 * данные аккаунта MAX. У работодателя «Профиль» — раздел нижнего меню, оно
 * остаётся на экране, а сверху — быстрые переходы к вакансиям и кандидатам.
 *
 * Обёртка ждёт пользователя из AuthContext и монтирует форму заново на
 * каждый user_id — состояние формы берётся из props при монтировании.
 */
export function ProfilePage() {
  const { state } = useAuth()

  if (state.status !== 'authenticated') {
    return null
  }

  const form = <ProfileForm key={state.user.user_id} />
  return state.user.role === 'employer' ? <EmployerLayout>{form}</EmployerLayout> : form
}

function ProfileForm() {
  const { state, setUser } = useAuth()
  // ProfilePage монтирует этот компонент только при status === 'authenticated'.
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

  const isDirty = firstName.trim() !== user.first_name || lastName.trim() !== (user.last_name ?? '')
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ')

  function edit(setter: (value: string) => void, value: string) {
    setter(value)
    setSaved(false)
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      setUser(await updateProfile({ first_name: firstName.trim(), last_name: lastName.trim() }))
      setSaved(true)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Не удалось сохранить изменения')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p1Screen profilePage">
      <span className="profilePage__eyebrow">MAX Найм</span>
      <h1 className="p1Title profilePage__title">Профиль</h1>

      <section className="profileHero">
        <AccentMarks className="profileHero__marks accentMarks--light" />
        <AvatarEditor user={user} onChange={setUser} onError={setError} />
        <div className="profileHero__text">
          <span className="profileHero__name">{fullName}</span>
          {user.role ? <span className="profileHero__role">{ROLE_LABELS[user.role]}</span> : null}
        </div>
      </section>

      {user.role === 'employer' ? <EmployerShortcuts /> : null}

      <h2 className="profilePage__section">Личные данные</h2>
      <NameField
        label="Имя"
        value={firstName}
        placeholder="Как к вам обращаться"
        onChange={(value) => edit(setFirstName, value)}
      />
      <NameField
        label="Фамилия"
        value={lastName}
        placeholder="Необязательно"
        onChange={(value) => edit(setLastName, value)}
      />

      {error ? <p className="p1Error profilePage__message">{error}</p> : null}
      {saved ? <p className="profilePage__saved">Изменения сохранены</p> : null}

      {/* Кнопка появляется, только когда есть что сохранять. */}
      {isDirty || saving ? (
        <button
          type="button"
          className="p1Button profilePage__save"
          disabled={saving || firstName.trim().length === 0}
          onClick={() => void handleSave()}
        >
          {saving ? 'Сохраняем…' : 'Сохранить'}
        </button>
      ) : null}

      <h2 className="profilePage__section">Аккаунт MAX</h2>
      <div className="profileInfo">
        <InfoRow
          icon={<AtIcon size={20} />}
          label="Имя пользователя"
          value={user.username ? `@${user.username}` : 'Не указано'}
        />
        <InfoRow
          icon={<GlobeIcon size={20} />}
          label="Язык"
          value={user.language_code ? LANGUAGE_LABELS[user.language_code] ?? user.language_code : 'Не указан'}
        />
        <InfoRow icon={<HashIcon size={20} />} label="ID в MAX" value={String(user.user_id)} />
      </div>
      <p className="profilePage__note">Эти данные приходят из MAX и меняются там</p>
    </div>
  )
}

/** Быстрые переходы работодателя: сколько вакансий и сколько новых кандидатов. */
function EmployerShortcuts() {
  const { state } = useAsync(async (signal) => {
    const page = await getEmployerVacancies(signal, 50)
    const published = page.items.filter((item) => item.status === 'published')
    const lists = await Promise.all(published.map((vacancy) => getVacancyCandidates(vacancy.id, signal)))
    const fresh = lists
      .flatMap((list) => list.items)
      .filter((item) => item.status === 'passed' || item.status === 'under_review').length
    return { published: published.length, fresh }
  }, [])
  const data = state.status === 'success' ? state.data : null

  return (
    <div className="profileShortcuts">
      <Link to={routes.employerVacancyList} className="profileShortcut">
        <span className="profileShortcut__icon">
          <BriefcaseIcon size={22} strokeWidth={1.8} />
        </span>
        <span className="profileShortcut__value">{data ? data.published : '—'}</span>
        <span className="profileShortcut__label">
          {data ? plural(data.published, 'вакансия', 'вакансии', 'вакансий') : 'вакансии'} в работе
        </span>
      </Link>
      <Link to={routes.employerCandidates} className="profileShortcut profileShortcut--accent">
        <span className="profileShortcut__icon">
          <PeopleFilledIcon size={22} />
        </span>
        <span className="profileShortcut__value">{data ? data.fresh : '—'}</span>
        <span className="profileShortcut__label">
          {data ? plural(data.fresh, 'новый кандидат', 'новых кандидата', 'новых кандидатов') : 'новых кандидатов'}
        </span>
      </Link>
    </div>
  )
}

/** Поле имени в стиле карточек формы вакансии (E02): подпись и крупный ввод. */
function NameField({
  label,
  value,
  placeholder,
  onChange,
}: {
  label: string
  value: string
  placeholder: string
  onChange: (value: string) => void
}) {
  return (
    <label className="profileField">
      <span className="profileField__label">{label}</span>
      <span className="profileField__row">
        <input
          className="profileField__input"
          value={value}
          placeholder={placeholder}
          maxLength={100}
          onChange={(event) => onChange(event.target.value)}
        />
        {value ? (
          <button
            type="button"
            className="profileField__clear"
            aria-label={`Очистить поле «${label}»`}
            onClick={() => onChange('')}
          >
            <CloseIcon size={14} strokeWidth={2.2} />
          </button>
        ) : null}
      </span>
    </label>
  )
}

function InfoRow({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="profileInfo__row">
      <span className="profileInfo__icon">{icon}</span>
      <span className="profileInfo__label">{label}</span>
      <span className="profileInfo__value">{value}</span>
    </div>
  )
}
