import { useState } from 'react'

import { CloseIcon } from '@/components/icons'
import type { CandidateProfile } from '@/api/hiring'
import './ProfileFieldSheet.css'

export type ProfileField = 'desired_role' | 'city' | 'salary' | 'schedule' | 'experience_months' | 'available_from'

const TITLES: Record<ProfileField, string> = {
  desired_role: 'Желаемая роль',
  city: 'Город',
  salary: 'Зарплата от',
  schedule: 'График',
  experience_months: 'Опыт',
  available_from: 'Готов выйти',
}

const EXPERIENCE_OPTIONS = [
  { value: 0, label: 'Без опыта' },
  { value: 6, label: 'До года' },
  { value: 12, label: '1 год' },
  { value: 24, label: '2 года' },
  { value: 36, label: '3 года и больше' },
]

const READY_OPTIONS = [
  { days: 0, label: 'Сразу' },
  { days: 1, label: 'Завтра' },
  { days: 3, label: 'Через 3 дня' },
  { days: 7, label: 'Через неделю' },
  { days: 30, label: 'Через месяц' },
]

function shiftDay(todayKey: string, days: number): string {
  const date = new Date(`${todayKey}T00:00:00`)
  date.setDate(date.getDate() + days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

/** Нижняя панель редактирования одного поля профиля кандидата (C01). */
export function ProfileFieldSheet({
  field,
  profile,
  scheduleOptions,
  todayKey,
  onChange,
  onClose,
}: {
  field: ProfileField
  profile: CandidateProfile
  scheduleOptions: string[]
  todayKey: string
  onChange: (patch: Partial<CandidateProfile>) => void
  onClose: () => void
}) {
  const [text, setText] = useState(() => {
    if (field === 'desired_role') return profile.desired_role
    if (field === 'city') return profile.city ?? ''
    if (field === 'salary') return profile.salary ? String(Math.round(Number(profile.salary))) : ''
    // Свой график (например, из резюме) — в поле, готовые варианты — кнопками.
    if (field === 'schedule' && profile.schedule && !scheduleOptions.includes(profile.schedule)) return profile.schedule
    return ''
  })

  function commitText() {
    const value = text.trim()
    if (field === 'desired_role') onChange({ desired_role: value })
    if (field === 'city') onChange({ city: value || null })
    if (field === 'salary') onChange({ salary: value ? `${Number(value.replace(/\D/g, ''))}.00` : null })
    if (field === 'schedule') onChange({ schedule: value || null })
    onClose()
  }

  const isText = field === 'desired_role' || field === 'city' || field === 'salary'

  return (
    <div className="fieldSheet" role="dialog" aria-modal="true" aria-label={TITLES[field]}>
      <button type="button" className="fieldSheet__backdrop" aria-label="Закрыть" onClick={onClose} />
      <div className="fieldSheet__panel">
        <span className="fieldSheet__handle" aria-hidden="true" />
        <div className="fieldSheet__head">
          <h2 className="fieldSheet__title">{TITLES[field]}</h2>
          <button type="button" className="fieldSheet__close" aria-label="Закрыть" onClick={onClose}>
            <CloseIcon size={18} />
          </button>
        </div>

        {isText ? (
          <form
            className="fieldSheet__form"
            onSubmit={(event) => {
              event.preventDefault()
              commitText()
            }}
          >
            <input
              className="fieldSheet__input"
              autoFocus
              value={text}
              inputMode={field === 'salary' ? 'numeric' : 'text'}
              placeholder={field === 'desired_role' ? 'Например, бариста' : field === 'city' ? 'Москва' : '80 000'}
              maxLength={field === 'salary' ? 9 : 255}
              onChange={(event) =>
                setText(field === 'salary' ? event.target.value.replace(/\D/g, '') : event.target.value)
              }
            />
            <button type="submit" className="screenButton screenButton--primary">
              Готово
            </button>
          </form>
        ) : null}

        {field === 'schedule' ? (
          <>
            <Options
              options={scheduleOptions.map((value) => ({ key: value, label: value }))}
              selected={profile.schedule}
              onSelect={(key) => {
                onChange({ schedule: key })
                onClose()
              }}
            />
            <form
              className="fieldSheet__form fieldSheet__form--custom"
              onSubmit={(event) => {
                event.preventDefault()
                commitText()
              }}
            >
              <label className="fieldSheet__label" htmlFor="schedule-custom">
                Или укажите свой
              </label>
              <input
                id="schedule-custom"
                className="fieldSheet__input"
                value={text}
                placeholder="Например, 3/3 или только выходные"
                maxLength={100}
                onChange={(event) => setText(event.target.value)}
              />
              <button type="submit" className="screenButton screenButton--primary" disabled={!text.trim()}>
                Готово
              </button>
            </form>
          </>
        ) : null}

        {field === 'experience_months' ? (
          <Options
            options={EXPERIENCE_OPTIONS.map((option) => ({ key: String(option.value), label: option.label }))}
            selected={profile.experience_months === null ? null : String(profile.experience_months)}
            onSelect={(key) => {
              onChange({ experience_months: Number(key) })
              onClose()
            }}
          />
        ) : null}

        {field === 'available_from' ? (
          <Options
            options={READY_OPTIONS.map((option) => ({ key: shiftDay(todayKey, option.days), label: option.label }))}
            selected={profile.available_from}
            onSelect={(key) => {
              onChange({ available_from: key })
              onClose()
            }}
          />
        ) : null}
      </div>
    </div>
  )
}

function Options({
  options,
  selected,
  onSelect,
}: {
  options: { key: string; label: string }[]
  selected: string | null
  onSelect: (key: string) => void
}) {
  return (
    <div className="fieldSheet__options">
      {options.map((option) => (
        <button
          key={option.key}
          type="button"
          className={`fieldSheet__option${option.key === selected ? ' fieldSheet__option--active' : ''}`}
          onClick={() => onSelect(option.key)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
