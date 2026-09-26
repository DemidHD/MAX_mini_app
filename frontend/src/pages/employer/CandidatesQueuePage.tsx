import { useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { candidateLabel, getVacancy, getVacancyCandidates } from '@/api/hiring'
import type { ApplicationStatus, EmployerCandidate } from '@/api/hiring'
import { BackButton } from '@/components/BackButton'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import {
  ArrowRightIcon,
  BriefcaseIcon,
  CalendarIcon,
  ChartIcon,
  CheckIcon,
  MoreIcon,
  RubleIcon,
  ShareIcon,
  SlidersIcon,
  SortIcon,
} from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { formatAvailableFrom, formatExperience, formatMoney, plural } from '@/lib/format'
import './CandidatesQueuePage.css'

type Filter = 'new' | 'all' | 'processed'

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'new', label: 'Новые' },
  { id: 'all', label: 'Все' },
  { id: 'processed', label: 'Обработанные' },
]

const PROCESSED: ApplicationStatus[] = [
  'reserved',
  'invited',
  'rejected',
  'mutual_interest',
  'interview_scheduled',
  'interview_completed',
]

const STATUS_BADGES: Partial<Record<ApplicationStatus, string>> = {
  passed: 'Новый',
  reserved: 'В резерве',
  invited: 'Приглашен',
  rejected: 'Отклонен',
  mutual_interest: 'Взаимный интерес',
  interview_scheduled: 'Интервью',
  interview_completed: 'Интервью прошло',
}

/**
 * E07 «Очередь кандидатов»: только прошедшие первичный отбор, от новых к
 * старым (UX-карта; `GET /employer/vacancies/:id/candidates`).
 */
export function CandidatesQueuePage() {
  const vacancyId = Number(useParams().vacancyId)
  const navigate = useNavigate()
  const flash = (useLocation().state as { flash?: string } | null)?.flash
  const { state, reload } = useAsync(async (signal) => {
    const [vacancy, candidates] = await Promise.all([
      getVacancy(vacancyId, signal),
      getVacancyCandidates(vacancyId, signal),
    ])
    return { vacancy, items: candidates.items }
  }, [vacancyId])
  const [filter, setFilter] = useState<Filter>('new')
  const [activeIndex, setActiveIndex] = useState(0)
  const trackRef = useRef<HTMLDivElement>(null)

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.employerHome)} />
  }

  const { vacancy, items } = state.data
  const newCount = items.filter((item) => item.status === 'passed').length
  const visible = items.filter((item) =>
    filter === 'new' ? item.status === 'passed' : filter === 'processed' ? PROCESSED.includes(item.status) : true,
  )

  function handleScroll() {
    const track = trackRef.current
    if (!track || !track.firstElementChild) return
    const step = (track.firstElementChild as HTMLElement).offsetWidth + 12
    setActiveIndex(Math.round(track.scrollLeft / step))
  }

  return (
    <div className="screen queuePage">
      <div className="queuePage__top">
        <BackButton onClick={() => navigate(routes.employerHome)} />
        {/* P2: калибровка (E17), аналитика (E18) и реферальная ссылка (R01) этой вакансии. */}
        <div className="queuePage__tools">
          <Link to={routes.employerVacancyCalibration(vacancyId)} className="backButton" aria-label="Калибровка подбора">
            <SlidersIcon size={21} strokeWidth={1.9} />
          </Link>
          <Link to={`${routes.employerAnalytics}?vacancy=${vacancyId}`} className="backButton" aria-label="Аналитика вакансии">
            <ChartIcon size={21} strokeWidth={2} />
          </Link>
          {vacancy.status === 'published' ? (
            <Link to={routes.employerVacancyReferral(vacancyId)} className="backButton" aria-label="Порекомендовать знакомому">
              <ShareIcon size={21} strokeWidth={1.9} />
            </Link>
          ) : null}
        </div>
      </div>

      <span className="screen__eyebrow queuePage__eyebrow">{vacancy.title}</span>
      <div className="queuePage__heading">
        <h1 className="screen__title queuePage__title">Кандидаты</h1>
        {newCount > 0 ? (
          <span className="queuePage__count">
            {newCount} {plural(newCount, 'новый', 'новых', 'новых')}
          </span>
        ) : null}
      </div>

      <div className="queuePage__filters" role="tablist" aria-label="Фильтр кандидатов">
        {FILTERS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={filter === id}
            className={`queuePage__filter${filter === id ? ' queuePage__filter--active' : ''}`}
            onClick={() => {
              setFilter(id)
              setActiveIndex(0)
              trackRef.current?.scrollTo({ left: 0 })
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {flash ? <p className="queuePage__flash">{flash}</p> : null}

      {visible.length === 0 ? (
        <EmptyQueue filter={filter} vacancyId={vacancyId} />
      ) : (
        <>
          <div className="queuePage__track" ref={trackRef} onScroll={handleScroll}>
            {visible.map((candidate) => (
              <CandidateCard
                key={candidate.application_id}
                candidate={candidate}
                label={candidateLabel(items, candidate.application_id)}
                vacancyId={vacancyId}
              />
            ))}
          </div>

          {visible.length > 1 ? (
            <div className="queuePage__dots" aria-hidden="true">
              {visible.map((candidate, index) => (
                <span
                  key={candidate.application_id}
                  className={`queuePage__dot${index === activeIndex ? ' queuePage__dot--active' : ''}`}
                />
              ))}
            </div>
          ) : null}

          <p className="queuePage__sort">
            <SortIcon size={20} />
            Сначала новые отклики
          </p>
        </>
      )}
    </div>
  )
}

function CandidateCard({
  candidate,
  label,
  vacancyId,
}: {
  candidate: EmployerCandidate
  label: string
  vacancyId: number
}) {
  const required = candidate.hard_filters.filter((item) => item.required)
  const passed = required.filter((item) => item.passed === true).length
  const cardPath = routes.employerApplication(vacancyId, candidate.application_id)

  return (
    <article className="queueCard">
      <div className="queueCard__photo photoSlot">
        <span className={`queueCard__badge${candidate.status === 'passed' ? '' : ' queueCard__badge--muted'}`}>
          <i aria-hidden="true" />
          {STATUS_BADGES[candidate.status] ?? 'Отклик'}
        </span>
        <span className="queueCard__more" aria-hidden="true">
          <MoreIcon size={22} />
        </span>
      </div>

      <div className="queueCard__body">
        <h2 className="queueCard__name">{label}</h2>
        <span className="queueCard__match">
          <span className="queueCard__matchIcon">
            <CheckIcon size={14} strokeWidth={3} />
          </span>
          {passed}/{required.length} обязательных
        </span>

        <ul className="queueCard__facts">
          <li>
            <BriefcaseIcon size={20} />
            {formatExperience(candidate.experience_months)}
          </li>
          <li>
            <RubleIcon size={20} />
            {candidate.salary ? formatMoney(candidate.salary) : 'Не указаны'}
          </li>
          <li>
            <CalendarIcon size={20} />
            {formatAvailableFrom(candidate.available_from)}
          </li>
        </ul>

        <Link to={cardPath} className="queueCard__open" aria-label={`Открыть карточку: ${label}`}>
          <ArrowRightIcon size={26} strokeWidth={2.4} />
        </Link>
      </div>
    </article>
  )
}

function EmptyQueue({ filter, vacancyId }: { filter: Filter; vacancyId: number }) {
  return (
    <div className="queuePage__empty">
      <p className="queuePage__emptyTitle">
        {filter === 'processed' ? 'Пока нет обработанных' : 'Пока нет новых кандидатов'}
      </p>
      <p className="queuePage__emptyText">
        Сюда попадают только те, кто прошел обязательные условия. Пока ждете откликов — добавьте время для
        интервью.
      </p>
      <Link to={routes.employerVacancySlots(vacancyId)} className="screenButton screenButton--outlinePrimary">
        Настроить интервалы
      </Link>
    </div>
  )
}
