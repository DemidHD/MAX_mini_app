import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import type { Vacancy } from '@/api/hiring'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { vacancyFacts } from '@/components/VacancyFacts'
import { CheckIcon, CloseIcon, InfoIcon, PinIcon, SendIcon, SlidersIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { formatSalaryRange, plural } from '@/lib/format'
import { applyToVacancy, getFeed } from '@/mocks/demoApi'
import { useApply } from '@/pages/candidate/useApply'
import './VacancyFeedPage.css'

/**
 * C02 «Лента вакансий»: одна карточка за раз с действиями «Пропустить» /
 * «Подробнее» / «Откликнуться» (`GET /vacancies/feed`). Свайпы — P1, кнопки
 * остаются в любом случае (UX-карта, раздел 7).
 */
export function VacancyFeedPage() {
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getFeed(signal), [])
  const [index, setIndex] = useState(0)
  const { apply, applying, error } = useApply(applyToVacancy)

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} />
  }

  const vacancies = state.data
  const vacancy = vacancies[index]

  if (!vacancy) {
    return (
      <div className="screen feedPage feedPage--empty">
        <div className="feedPage__empty">
          <h1 className="feedPage__emptyTitle">Подходящие вакансии закончились</h1>
          <p className="feedPage__emptyText">
            Мы показываем только те, где совпадают обязательные условия. Загляните позже или уточните профиль.
          </p>
          <button
            type="button"
            className="screenButton screenButton--primary"
            onClick={() => {
              setIndex(0)
              reload()
            }}
          >
            Обновить ленту
          </button>
          <button
            type="button"
            className="screenButton screenButton--link"
            onClick={() => navigate(routes.candidateProfileSetup)}
          >
            Изменить профиль
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="screen feedPage">
      <div className="feedPage__stack">
        {vacancies.length - index > 2 ? <span className="feedPage__ghost feedPage__ghost--far" aria-hidden="true" /> : null}
        {vacancies.length - index > 1 ? <span className="feedPage__ghost" aria-hidden="true" /> : null}
        <FeedCard vacancy={vacancy} />
      </div>

      {error ? <p className="screen__error feedPage__error">{error}</p> : null}

      <div className="feedPage__actions">
        <button type="button" className="feedPage__round" onClick={() => setIndex((value) => value + 1)}>
          <span className="feedPage__roundIcon">
            <CloseIcon size={28} strokeWidth={2.1} />
          </span>
          Пропустить
        </button>
        <button type="button" className="feedPage__round" onClick={() => navigate(routes.candidateVacancy(vacancy.id))}>
          <span className="feedPage__roundIcon">
            <InfoIcon size={28} strokeWidth={1.9} />
          </span>
          Подробнее
        </button>
        <button type="button" className="feedPage__apply" disabled={applying} onClick={() => void apply(vacancy.id)}>
          <SendIcon size={26} strokeWidth={2} />
          {applying ? 'Отправляем…' : 'Откликнуться'}
        </button>
      </div>
    </div>
  )
}

function FeedCard({ vacancy }: { vacancy: Vacancy }) {
  const required = vacancy.criteria.filter((criterion) => criterion.required).length
  const city = vacancy.criteria.find((criterion) => criterion.type === 'location')?.value.city

  return (
    <article className="feedCard photoSlot photoSlot--dark">
      <div className="feedCard__top">
        {typeof city === 'string' ? (
          <span className="feedCard__city">
            <PinIcon size={22} strokeWidth={2} />
            {city}
          </span>
        ) : (
          <span />
        )}
        {/* Фильтры ленты в P0 не предусмотрены — кнопка из макета декоративная. */}
        <span className="feedCard__filters" aria-hidden="true">
          <SlidersIcon size={24} />
        </span>
      </div>

      <div className="feedCard__info">
        {vacancy.company_name ? <span className="feedCard__company">{vacancy.company_name}</span> : null}
        <h1 className="feedCard__title">{vacancy.title}</h1>
        <span className="feedCard__salary">{formatSalaryRange(vacancy.salary_min, vacancy.salary_max)}</span>

        <div className="feedCard__chips">
          {vacancyFacts(vacancy, 20).map((fact) => (
            <span key={fact.key} className="feedCard__chip">
              {fact.icon}
              {fact.label}
            </span>
          ))}
        </div>

        {required > 0 ? (
          <span className="feedCard__match">
            <span className="feedCard__matchIcon">
              <CheckIcon size={14} strokeWidth={3} />
            </span>
            {required} {plural(required, 'условие совпало', 'условия совпали', 'условий совпали')}
          </span>
        ) : null}
      </div>
    </article>
  )
}
