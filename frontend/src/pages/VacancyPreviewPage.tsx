import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Typography } from '@maxhub/max-ui'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import { useVacancyDraft } from '@/features/vacancyCreate/useVacancyDraft'
import { VacancyStepHeader } from '@/features/vacancyCreate/VacancyStepHeader'
import {
  CRITERION_KEYS,
  availableFromLabel,
  criterionChipLabel,
  formatSalaryRange,
} from '@/features/vacancyCreate/draft'
import heroPhoto from '@/assets/role-employer.webp'
import './VacancyPreviewPage.css'

/**
 * Шаг 3 создания вакансии — экран E04 «Предпросмотр» в UX-карте: вакансия так,
 * как её увидит кандидат. «Опубликовать» переводит черновик в `published`.
 */
export function VacancyPreviewPage() {
  const { draft, publish } = useVacancyDraft()
  const navigate = useNavigate()
  const [publishing, setPublishing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const requiredKeys = CRITERION_KEYS.filter((key) => draft.criteria[key])
  const desiredKeys = CRITERION_KEYS.filter((key) => !draft.criteria[key])

  async function handlePublish() {
    setPublishing(true)
    setError(null)
    try {
      await publish()
      navigate(routes.employerVacancyPublished)
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'vacancy_incomplete') {
        setError('Не хватает данных для публикации: проверьте должность, адрес, зарплату и график.')
      } else {
        setError(cause instanceof ApiError ? cause.message : 'Не удалось опубликовать вакансию')
      }
    } finally {
      setPublishing(false)
    }
  }

  return (
    <div className="vacancyPreview">
      <VacancyStepHeader title="Предпросмотр" />

      <div className="vacancyPreview__body">
        <div className="vacancyPreview__photoCard">
          {/* Фото, которое backend подобрал вакансии; пока его нет — иллюстрация. */}
          <img
            className="vacancyPreview__photo"
            src={draft.imageUrl ?? heroPhoto}
            alt=""
            referrerPolicy="no-referrer"
            onError={(event) => {
            if (!event.currentTarget.src.endsWith(heroPhoto)) event.currentTarget.src = heroPhoto
          }}
          />
        </div>

        {draft.companyName.trim() ? (
          <Typography.Body className="vacancyPreview__company">{draft.companyName.trim()}</Typography.Body>
        ) : null}
        <Typography.Title className="vacancyPreview__title">
          {draft.title || 'Без названия'}
        </Typography.Title>
        <Typography.Display className="vacancyPreview__salary">
          {formatSalaryRange(draft.salaryMin, draft.salaryMax)}
        </Typography.Display>

        <div className="vacancyPreview__pills">
          <span className="vacancyPreview__pill">
            <PinIcon />
            {draft.location || 'Не указана'}
          </span>
          <span className="vacancyPreview__pill">
            <CalendarIcon />
            {draft.schedule}
          </span>
          <span className="vacancyPreview__pill">
            <BoltIcon />
            {availableFromLabel(draft.availableFrom)}
          </span>
        </div>

        {draft.description.trim() ? (
          <section className="vacancyPreview__section">
            <Typography.Title className="vacancyPreview__sectionTitle">О вакансии</Typography.Title>
            <Typography.Body className="vacancyPreview__description">{draft.description.trim()}</Typography.Body>
          </section>
        ) : null}

        {requiredKeys.length > 0 ? (
          <section className="vacancyPreview__section">
            <Typography.Title className="vacancyPreview__sectionTitle">Обязательно</Typography.Title>
            <div className="vacancyPreview__chips">
              {requiredKeys.map((key) => (
                <span className="vacancyPreview__chip" key={key}>
                  {criterionChipLabel(key, draft)}
                </span>
              ))}
            </div>
          </section>
        ) : null}

        {desiredKeys.length > 0 ? (
          <section className="vacancyPreview__section">
            <Typography.Title className="vacancyPreview__sectionTitle">Желательно</Typography.Title>
            <div className="vacancyPreview__chips">
              {desiredKeys.map((key) => (
                <span className="vacancyPreview__chip" key={key}>
                  {criterionChipLabel(key, draft)}
                </span>
              ))}
            </div>
          </section>
        ) : null}

        {error ? <Typography.Body className="vacancyPreview__error">{error}</Typography.Body> : null}

        <div className="vacancyPreview__actions">
          <button
            type="button"
            className="vacancyPreview__secondary"
            disabled={publishing}
            onClick={() => navigate(routes.employerVacancyCreate)}
          >
            Изменить
          </button>
          <button type="button" className="vacancyPreview__primary" disabled={publishing} onClick={() => void handlePublish()}>
            {publishing ? 'Публикуем…' : 'Опубликовать'}
          </button>
        </div>
      </div>
    </div>
  )
}

function PinIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12 21s7-6.5 7-11.5a7 7 0 1 0-14 0C5 14.5 12 21 12 21Z"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="9.5" r="2.5" stroke="currentColor" strokeWidth="1.9" />
    </svg>
  )
}

function CalendarIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3.5" y="5.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.9" />
      <path d="M3.5 10h17M8 3.5v3M16 3.5v3" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  )
}

function BoltIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12.5 3 5 13.5h5.5L11 21l7.5-10.5H13l-0.5-7.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  )
}
