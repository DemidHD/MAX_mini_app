import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Typography } from '@maxhub/max-ui'

import { routes } from '@/app/routes'
import { useVacancyDraft } from '@/features/vacancyCreate/useVacancyDraft'
import { VacancyStepHeader } from '@/features/vacancyCreate/VacancyStepHeader'
import { availableFromLabel, experienceLabel } from '@/features/vacancyCreate/draft'
import type { CriterionKey } from '@/features/vacancyCreate/draft'
import './VacancyCriteriaPage.css'

interface CriterionRow {
  key: CriterionKey
  icon: ReactNode
  label: string
  value: string
}

/** Шаг 2 создания вакансии — экран «Что действительно важно?» в UX-карте. */
export function VacancyCriteriaPage() {
  const { draft, setCriterionRequired } = useVacancyDraft()
  const navigate = useNavigate()

  const rows: CriterionRow[] = [
    { key: 'schedule', icon: <CalendarIcon />, label: 'График', value: draft.schedule },
    { key: 'location', icon: <PinIcon />, label: 'Локация', value: draft.location || 'Не указана' },
    {
      key: 'experience',
      icon: <BriefcaseIcon />,
      label: 'Опыт',
      value: experienceLabel(draft.experienceMonths),
    },
    {
      key: 'available_from',
      icon: <ClockIcon />,
      label: 'Дата выхода',
      value: availableFromLabel(draft.availableFrom),
    },
    { key: 'salary', icon: <CoinIcon />, label: 'Зарплата', value: salaryValueLabel(draft.salaryMax, draft.salaryMin) },
  ]

  return (
    <div className="vacancyCriteria">
      <VacancyStepHeader title="Новая вакансия" step={2} totalSteps={3} />

      <div className="vacancyCriteria__body">
        <Typography.Display className="vacancyCriteria__heading">
          Что действительно
          <br />
          важно?
        </Typography.Display>
        <Typography.Body className="vacancyCriteria__subtitle">
          Разделите условия на обязательные
          <br />и желательные
        </Typography.Body>

        <div className="vacancyCriteria__list">
          {rows.map((row) => (
            <div className="criterionCard" key={row.key}>
              <div className="criterionCard__top">
                <span className="criterionCard__icon">{row.icon}</span>
                <span className="criterionCard__text">
                  <span className="criterionCard__label">{row.label}</span>
                  <span className="criterionCard__value">{row.value}</span>
                </span>
              </div>
              <div className="criterionCard__toggle" role="radiogroup" aria-label={`Важность условия «${row.label}»`}>
                <button
                  type="button"
                  role="radio"
                  aria-checked={draft.criteria[row.key]}
                  className={`criterionCard__option${draft.criteria[row.key] ? ' criterionCard__option--active' : ''}`}
                  onClick={() => setCriterionRequired(row.key, true)}
                >
                  Обязательно
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-checked={!draft.criteria[row.key]}
                  className={`criterionCard__option criterionCard__option--desired${!draft.criteria[row.key] ? ' criterionCard__option--active' : ''}`}
                  onClick={() => setCriterionRequired(row.key, false)}
                >
                  Желательно
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="vacancyCriteria__hint">
          <InfoIcon />
          <Typography.Body className="vacancyCriteria__hintText">
            Обязательные условия используются для первичного отбора
          </Typography.Body>
        </div>

        <button type="button" className="vacancyCriteria__next" onClick={() => navigate(routes.employerVacancyPreview)}>
          Предпросмотр
        </button>
      </div>
    </div>
  )
}

function salaryValueLabel(max: string, min: string): string {
  if (max.trim()) return `До ${Number(max).toLocaleString('ru-RU')} ₽`
  if (min.trim()) return `От ${Number(min).toLocaleString('ru-RU')} ₽`
  return 'Не указана'
}

function CalendarIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3.5" y="5.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3.5 10h17M8 3.5v3M16 3.5v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function PinIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12 21s7-6.5 7-11.5a7 7 0 1 0-14 0C5 14.5 12 21 12 21Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="9.5" r="2.5" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  )
}

function BriefcaseIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3.5" y="7.5" width="17" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8.5 7.5V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 7.5V12l3 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function CoinIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="9.5" cy="9.5" r="6" stroke="currentColor" strokeWidth="1.8" />
      <path d="M14 14c2.5 1 6 0.3 6 -2.5S17 8.5 14.5 9.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function InfoIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 11v5.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="8" r="1" fill="currentColor" />
    </svg>
  )
}
