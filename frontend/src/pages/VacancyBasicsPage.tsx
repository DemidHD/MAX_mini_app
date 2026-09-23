import { useNavigate } from 'react-router-dom'
import { Typography } from '@maxhub/max-ui'
import type { ReactNode } from 'react'

import { routes } from '@/app/routes'
import { useVacancyDraft } from '@/features/vacancyCreate/useVacancyDraft'
import { VacancyStepHeader } from '@/features/vacancyCreate/VacancyStepHeader'
import { AVAILABLE_FROM_OPTIONS, EXPERIENCE_OPTIONS, SCHEDULE_OPTIONS, isBasicsComplete } from '@/features/vacancyCreate/draft'
import decorPhoto from '@/assets/vacancy-basics-decor.webp'
import './VacancyBasicsPage.css'

/** Шаг 1 создания вакансии — экран E02 «Кого вы ищете?» в UX-карте. */
export function VacancyBasicsPage() {
  const { draft, updateDraft } = useVacancyDraft()
  const navigate = useNavigate()

  const canContinue = isBasicsComplete(draft)

  return (
    <div className="vacancyBasics">
      <VacancyStepHeader title="Новая вакансия" step={1} totalSteps={3} onBack={() => navigate(routes.employerHome)} />

      <div className="vacancyBasics__body">
        <img className="vacancyBasics__decor" src={decorPhoto} alt="" aria-hidden="true" />

        <Typography.Display className="vacancyBasics__heading">
          Кого вы
          <br />
          ищете?
        </Typography.Display>
        <Typography.Body className="vacancyBasics__subtitle">Основные условия</Typography.Body>

        <VacancyTextField
          label="Должность"
          value={draft.title}
          placeholder="Например, бариста"
          onChange={(value) => updateDraft({ title: value })}
        />

        <div className="vacancyBasics__row">
          <VacancyTextField
            label="Зарплата от"
            value={draft.salaryMin}
            placeholder="0"
            type="number"
            onChange={(value) => updateDraft({ salaryMin: value })}
          />
          <VacancyTextField
            label="Зарплата до"
            value={draft.salaryMax}
            placeholder="0"
            type="number"
            onChange={(value) => updateDraft({ salaryMax: value })}
          />
        </div>

        <VacancyTextField
          label="Город / адрес"
          value={draft.location}
          placeholder="Например, Москва, м. Белорусская"
          onChange={(value) => updateDraft({ location: value })}
        />

        <div className="vacancyBasics__pickers">
          <PickerCard
            icon={<CalendarIcon />}
            label="График"
            value={draft.schedule}
            onChange={(value) => updateDraft({ schedule: value })}
            options={SCHEDULE_OPTIONS.map((value) => ({ value, label: value }))}
          />
          <PickerCard
            icon={<BriefcaseIcon />}
            label="Опыт"
            value={String(draft.experienceMonths)}
            onChange={(value) => updateDraft({ experienceMonths: Number(value) })}
            options={EXPERIENCE_OPTIONS.map((option) => ({ value: String(option.months), label: option.label }))}
          />
          <PickerCard
            icon={<ClockIcon />}
            label="Когда нужен выход"
            value={draft.availableFrom}
            onChange={(value) => updateDraft({ availableFrom: value as typeof draft.availableFrom })}
            options={AVAILABLE_FROM_OPTIONS.map((option) => ({ value: option.id, label: option.label }))}
          />
        </div>

        <Typography.Body className="vacancyBasics__autosave">Черновик сохраняется автоматически</Typography.Body>

        <button
          type="button"
          className="vacancyBasics__next"
          disabled={!canContinue}
          onClick={() => navigate(routes.employerVacancyCriteria)}
        >
          Далее
        </button>
      </div>
    </div>
  )
}

function VacancyTextField({
  label,
  value,
  placeholder,
  type = 'text',
  onChange,
}: {
  label: string
  value: string
  placeholder: string
  type?: 'text' | 'number'
  onChange: (value: string) => void
}) {
  return (
    <div className="vacancyField">
      <span className="vacancyField__label">{label}</span>
      <div className="vacancyField__row">
        <input
          className="vacancyField__input"
          type={type}
          inputMode={type === 'number' ? 'numeric' : undefined}
          min={type === 'number' ? 0 : undefined}
          value={value}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
        />
        {value ? (
          <button
            type="button"
            className="vacancyField__clear"
            aria-label={`Очистить поле «${label}»`}
            onClick={() => onChange('')}
          >
            <CloseIcon />
          </button>
        ) : null}
      </div>
    </div>
  )
}

function CloseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

function PickerCard({
  icon,
  label,
  value,
  options,
  onChange,
}: {
  icon: ReactNode
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}) {
  const currentLabel = options.find((option) => option.value === value)?.label ?? value
  return (
    <label className="pickerCard">
      <span className="pickerCard__top">
        <span className="pickerCard__icon">{icon}</span>
        <span className="pickerCard__chevron" aria-hidden="true">
          <ChevronIcon />
        </span>
      </span>
      <span className="pickerCard__label">{label}</span>
      <span className="pickerCard__value">{currentLabel}</span>
      <select
        className="pickerCard__select"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label={label}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function CalendarIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3.5" y="5.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3.5 10h17M8 3.5v3M16 3.5v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function BriefcaseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3.5" y="7.5" width="17" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8.5 7.5V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 7.5V12l3 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function ChevronIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M6 3.5 10.5 8 6 12.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
