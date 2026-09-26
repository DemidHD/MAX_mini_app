import { useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import { isDraftLimitError } from '@/api/vacancies'
import { BackButton } from '@/components/BackButton'
import {
  BriefcaseIcon,
  CalendarIcon,
  ClockIcon,
  CloseIcon,
  FileListIcon,
  PencilIcon,
  PinIcon,
  RubleIcon,
} from '@/components/icons'
import {
  AVAILABLE_FROM_OPTIONS,
  EXPERIENCE_OPTIONS,
  SCHEDULE_OPTIONS,
  availableFromLabel,
  experienceLabel,
  isBasicsComplete,
} from '@/features/vacancyCreate/draft'
import type { CriterionKey, VacancyDraft } from '@/features/vacancyCreate/draft'
import { useVacancyDraft } from '@/features/vacancyCreate/useVacancyDraft'
import { formatSalaryRange, scheduleLabel } from '@/lib/format'
import '@/pages/candidate/ProfileFieldSheet.css'
import './VacancyAiCheckPage.css'

type Field = 'title' | 'salary' | 'schedule' | 'location' | 'experience' | 'availableFrom'

const FIELD_TITLES: Record<Field, string> = {
  title: 'Должность',
  salary: 'Зарплата',
  schedule: 'График',
  location: 'Локация',
  experience: 'Опыт',
  availableFrom: 'Выход',
}

/** Условия, приоритет которых показывает макет E12. Остальные — на E03. */
const PRIORITY_KEYS: { key: CriterionKey; label: string }[] = [
  { key: 'schedule', label: 'график' },
  { key: 'location', label: 'локация' },
  { key: 'experience', label: 'опыт' },
]

/**
 * E12 «Подтверждение разбора ИИ» (P1, функция 16). Каждое извлечённое поле
 * можно исправить, незаполненные подсвечены. «Подтвердить» сохраняет
 * черновик и ведёт на предпросмотр E04 — публикует только работодатель.
 */
export function VacancyAiCheckPage() {
  const { draft, updateDraft, setCriterionRequired, saveDraft } = useVacancyDraft()
  const navigate = useNavigate()
  const [editing, setEditing] = useState<Field | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasSalary = Boolean(draft.salaryMin || draft.salaryMax)
  const salary = hasSalary ? formatSalaryRange(draft.salaryMin || null, draft.salaryMax || null) : null
  const ready = isBasicsComplete(draft)

  async function handleConfirm() {
    if (!ready) {
      setError('Укажите должность и локацию — без них вакансию не опубликовать.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await saveDraft()
      navigate(routes.employerVacancyPreview)
    } catch (cause) {
      setError(
        isDraftLimitError(cause)
          ? 'Достигнут лимит черновиков. Опубликуйте или удалите один из них на главной.'
          : 'Не удалось сохранить. Данные на месте — попробуйте еще раз.',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="p1Screen aiCheck">
      <div className="p1Top p1Top--centered">
        <BackButton onClick={() => navigate(routes.employerVacancyAi)} />
        <span className="p1Top__title">Проверка</span>
      </div>

      <h1 className="p1Title aiCheck__title">Все правильно?</h1>
      <p className="p1Subtitle aiCheck__subtitle">Проверьте условия перед публикацией</p>

      <div className="aiCheck__grid">
        <FieldCard
          wide
          large
          icon={<BriefcaseIcon size={22} strokeWidth={1.7} />}
          label="Должность"
          value={draft.title.trim() || null}
          empty="Не указана"
          onEdit={() => setEditing('title')}
        />
        <FieldCard
          icon={<RubleIcon size={22} strokeWidth={1.8} />}
          label="Зарплата"
          value={salary}
          empty="Не указана"
          onEdit={() => setEditing('salary')}
        />
        <FieldCard
          icon={<CalendarIcon size={22} strokeWidth={1.7} />}
          label="График"
          value={draft.schedule ? scheduleLabel(draft.schedule) : null}
          empty="Не указан"
          onEdit={() => setEditing('schedule')}
        />
        <FieldCard
          wide
          icon={<PinIcon size={22} strokeWidth={1.7} />}
          label="Локация"
          value={draft.location.trim() || null}
          empty="Не указана"
          onEdit={() => setEditing('location')}
        />
        <FieldCard
          icon={<FileListIcon size={22} strokeWidth={1.7} />}
          label="Опыт"
          value={experienceLabel(draft.experienceMonths)}
          empty="Не указан"
          onEdit={() => setEditing('experience')}
        />
        <FieldCard
          icon={<ClockIcon size={22} strokeWidth={1.7} />}
          label="Выход"
          value={availableFromLabel(draft.availableFrom)}
          empty="Не указан"
          onEdit={() => setEditing('availableFrom')}
        />
      </div>

      <h2 className="aiCheck__section">Приоритет</h2>
      <div className="aiCheck__chips">
        {PRIORITY_KEYS.map(({ key, label }) => {
          const required = draft.criteria[key]
          return (
            <button
              key={key}
              type="button"
              aria-pressed={required}
              className={`aiCheck__chip${required ? ' aiCheck__chip--required' : ''}`}
              onClick={() => setCriterionRequired(key, !required)}
            >
              {required ? 'Обязательно' : 'Желательно'} · {label}
            </button>
          )
        })}
      </div>

      <div className="aiCheck__spacer" />

      {error ? <p className="p1Error">{error}</p> : null}

      <button type="button" className="p1Button" disabled={saving} onClick={() => void handleConfirm()}>
        {saving ? 'Сохраняем…' : 'Подтвердить'}
      </button>
      <button type="button" className="p1Link aiCheck__manual" onClick={() => navigate(routes.employerVacancyCreate)}>
        Изменить вручную
      </button>

      {editing ? (
        <FieldSheet field={editing} draft={draft} onChange={updateDraft} onClose={() => setEditing(null)} />
      ) : null}
    </div>
  )
}

function FieldCard({
  icon,
  label,
  value,
  empty,
  wide = false,
  large = false,
  onEdit,
}: {
  icon: ReactNode
  label: string
  value: string | null
  empty: string
  wide?: boolean
  large?: boolean
  onEdit: () => void
}) {
  const classes = ['aiField']
  if (wide) classes.push('aiField--wide')
  if (large) classes.push('aiField--large')
  if (value === null) classes.push('aiField--missing')

  return (
    <div className={classes.join(' ')}>
      <div className="aiField__head">
        <span className="aiField__icon">{icon}</span>
        <span className="aiField__label">{label}</span>
        <button type="button" className="aiField__edit" aria-label={`Изменить: ${label}`} onClick={onEdit}>
          <PencilIcon size={17} strokeWidth={2} />
        </button>
      </div>
      <span className={`aiField__value${!wide && (value ?? '').length > 13 ? ' aiField__value--long' : ''}`}>
        {value ?? empty}
      </span>
    </div>
  )
}

/** Нижняя панель правки одного поля — та же, что у профиля кандидата (C01). */
function FieldSheet({
  field,
  draft,
  onChange,
  onClose,
}: {
  field: Field
  draft: VacancyDraft
  onChange: (patch: Partial<VacancyDraft>) => void
  onClose: () => void
}) {
  const [text, setText] = useState(field === 'title' ? draft.title : field === 'location' ? draft.location : '')
  const [salaryMin, setSalaryMin] = useState(draft.salaryMin)
  const [salaryMax, setSalaryMax] = useState(draft.salaryMax)

  function commit() {
    if (field === 'title') onChange({ title: text.trim() })
    if (field === 'location') onChange({ location: text.trim() })
    if (field === 'salary') onChange({ salaryMin, salaryMax })
    onClose()
  }

  const digits = (value: string) => value.replace(/\D/g, '').slice(0, 9)
  const scheduleOptions: string[] = [...SCHEDULE_OPTIONS]
  if (draft.schedule && !scheduleOptions.includes(draft.schedule)) scheduleOptions.unshift(draft.schedule)

  return (
    <div className="fieldSheet p1Sheet" role="dialog" aria-modal="true" aria-label={FIELD_TITLES[field]}>
      <button type="button" className="fieldSheet__backdrop" aria-label="Закрыть" onClick={onClose} />
      <div className="fieldSheet__panel">
        <span className="fieldSheet__handle" aria-hidden="true" />
        <div className="fieldSheet__head">
          <h2 className="fieldSheet__title">{FIELD_TITLES[field]}</h2>
          <button type="button" className="fieldSheet__close" aria-label="Закрыть" onClick={onClose}>
            <CloseIcon size={18} />
          </button>
        </div>

        {field === 'title' || field === 'location' || field === 'salary' ? (
          <form
            className="fieldSheet__form"
            onSubmit={(event) => {
              event.preventDefault()
              commit()
            }}
          >
            {field === 'salary' ? (
              <div className="aiCheck__salaryInputs">
                <input
                  className="fieldSheet__input"
                  inputMode="numeric"
                  placeholder="От"
                  aria-label="Зарплата от"
                  value={salaryMin}
                  onChange={(event) => setSalaryMin(digits(event.target.value))}
                />
                <input
                  className="fieldSheet__input"
                  autoFocus
                  inputMode="numeric"
                  placeholder="До"
                  aria-label="Зарплата до"
                  value={salaryMax}
                  onChange={(event) => setSalaryMax(digits(event.target.value))}
                />
              </div>
            ) : (
              <input
                className="fieldSheet__input"
                autoFocus
                value={text}
                maxLength={255}
                placeholder={field === 'title' ? 'Например, бариста' : 'Москва, Белорусская'}
                onChange={(event) => setText(event.target.value)}
              />
            )}
            <button type="submit" className="p1Button">
              Готово
            </button>
          </form>
        ) : null}

        {field === 'schedule' ? (
          <Options
            options={scheduleOptions.map((value) => ({ key: value, label: scheduleLabel(value) }))}
            selected={draft.schedule}
            onSelect={(key) => {
              onChange({ schedule: key })
              onClose()
            }}
          />
        ) : null}

        {field === 'experience' ? (
          <Options
            options={EXPERIENCE_OPTIONS.map((option) => ({ key: String(option.months), label: option.label }))}
            selected={String(draft.experienceMonths)}
            onSelect={(key) => {
              onChange({ experienceMonths: Number(key) })
              onClose()
            }}
          />
        ) : null}

        {field === 'availableFrom' ? (
          <Options
            options={AVAILABLE_FROM_OPTIONS.map((option) => ({ key: option.id, label: option.label }))}
            selected={draft.availableFrom}
            onSelect={(key) => {
              onChange({ availableFrom: key as VacancyDraft['availableFrom'] })
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
