import { useState } from 'react'
import { Navigate, Link } from 'react-router-dom'
import { Typography } from '@maxhub/max-ui'

import { routes } from '@/app/routes'
import { useVacancyDraft } from '@/features/vacancyCreate/useVacancyDraft'
import { formatSalaryRange } from '@/features/vacancyCreate/draft'
import heroPhoto from '@/assets/role-employer.webp'
import './VacancyPublishedPage.css'

/**
 * Шаг 4 — экран E05 «Вакансия опубликована». Доступен только после реального
 * успешного `createVacancy` (раздел «Данные с backend» — здесь этого
 * эндпоинта пока нет, см. `api/vacancies.ts`), поэтому без `publishedVacancy`
 * в контексте экран не рисует выдуманную вакансию, а уводит на главную.
 */
export function VacancyPublishedPage() {
  const { draft, publishedVacancy, resetDraft } = useVacancyDraft()
  const [copied, setCopied] = useState(false)

  if (!publishedVacancy) {
    return <Navigate to={routes.employerHome} replace />
  }
  const vacancy = publishedVacancy

  const publicUrl = vacancy.public_token ? `${window.location.origin}/v/${vacancy.public_token}` : null

  async function handleCopy() {
    if (!publicUrl) return
    try {
      await navigator.clipboard.writeText(publicUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Буфер обмена недоступен (нет разрешения/не https) — молча ничего не делаем,
      // ссылку всё равно можно скопировать вручную из текста.
    }
  }

  async function handleShare() {
    if (!publicUrl) return
    if (navigator.share) {
      try {
        await navigator.share({ title: vacancy.title, url: publicUrl })
      } catch {
        // Пользователь закрыл системный диалог — не ошибка.
      }
    } else {
      void handleCopy()
    }
  }

  return (
    <div className="vacancyPublished">
      <span className="vacancyPublished__badge">Готово</span>

      <Typography.Display className="vacancyPublished__title">
        Вакансия
        <br />
        опубликована
      </Typography.Display>

      <div className="vacancyPublished__stack">
        <div className="vacancyPublished__ghost vacancyPublished__ghost--back" />
        <div className="vacancyPublished__ghost vacancyPublished__ghost--mid" />
        <div className="vacancyPublished__card">
          <span className="vacancyPublished__status">Опубликована</span>
          <span className="vacancyPublished__cardTitle">{vacancy.title}</span>
          <span className="vacancyPublished__cardSalary">
            {formatSalaryRange(draft.salaryMin, draft.salaryMax)}
          </span>
          <span className="vacancyPublished__cardMeta">
            {vacancy.location} · {vacancy.schedule}
          </span>
          <span className="vacancyPublished__cardPhoto">
            <img src={heroPhoto} alt="" />
          </span>
        </div>
      </div>

      {publicUrl ? (
        <div className="vacancyPublished__link">
          <div className="vacancyPublished__linkText">
            <span className="vacancyPublished__linkLabel">Ссылка на вакансию</span>
            <span className="vacancyPublished__linkUrl">{publicUrl.replace(/^https?:\/\//, '')}</span>
          </div>
          <button type="button" className="vacancyPublished__copy" onClick={() => void handleCopy()}>
            {copied ? 'Скопировано' : 'Скопировать'}
          </button>
        </div>
      ) : null}

      <Link to={routes.employerVacancySlots(vacancy.id)} className="vacancyPublished__primary" onClick={() => resetDraft()}>
        Добавить интервалы
      </Link>
      <Link to={routes.employerVacancyCandidates(vacancy.id)} className="vacancyPublished__secondary" onClick={() => resetDraft()}>
        Смотреть кандидатов
      </Link>

      {publicUrl ? (
        <button type="button" className="vacancyPublished__share" onClick={() => void handleShare()}>
          <ShareIcon />
          Поделиться вакансией
        </button>
      ) : null}
    </div>
  )
}

function ShareIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12 15V4m0 0 3.5 3.5M12 4 8.5 7.5M5 12v7a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-7"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
