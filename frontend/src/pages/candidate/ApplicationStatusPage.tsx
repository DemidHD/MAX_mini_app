import { Navigate, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import type { CandidateApplication } from '@/api/hiring'
import { BackButton } from '@/components/BackButton'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { ProgressSteps } from '@/components/ProgressSteps'
import { BellIcon, BookmarkIcon, ClockIcon, InfoIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { CRITERION_MISMATCH_REASONS, CRITERION_TITLES, criterionLabel, formatSalaryRange, plural } from '@/lib/format'
import { getCandidateApplication } from '@/mocks/demoApi'
import './ApplicationStatusPage.css'

/**
 * Статус отклика кандидата — экран, на который ведёт `current_step =
 * application_status` (раздел 7). По статусу показывает C06 «Не прошёл
 * обязательное условие» или C07 «Отклик ожидает решения»; при взаимном
 * интересе и назначенном интервью уводит в M01 / C10.
 */
export function ApplicationStatusPage() {
  const applicationId = Number(useParams().applicationId)
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getCandidateApplication(applicationId, signal), [applicationId])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.candidateFeed)} />
  }

  const application = state.data
  switch (application.status) {
    case 'created':
    case 'screening':
      return <Navigate to={routes.candidateScreeningStart(application.id)} replace />
    case 'hard_filter_failed':
      return <HardFilterFailed application={application} />
    case 'mutual_interest':
      if (application.match_id !== null) return <Navigate to={routes.candidateMatch(application.match_id)} replace />
      break
    case 'interview_scheduled':
    case 'interview_completed':
      if (application.interview_id !== null) {
        return <Navigate to={routes.candidateInterview(application.interview_id)} replace />
      }
      break
  }
  return <ApplicationPending application={application} />
}

/** C06: нейтральный итог без оценки личности — причина на уровне требования. */
function HardFilterFailed({ application }: { application: CandidateApplication }) {
  const navigate = useNavigate()
  const failed = application.failed_criteria
  const first = failed[0]
  const criterion = application.vacancy.criteria.find((item) => item.type === first)
  const count = Math.max(failed.length, 1)
  const countWord = count === 1 ? 'одно обязательное условие' : `${count} обязательных ${plural(count, 'условие', 'условия', 'условий')}`

  return (
    <div className="screen applicationStatus applicationStatus--failed">
      <BackButton onClick={() => navigate(routes.candidateFeed)} />
      {/* Место под иллюстрацию из макета — добавится отдельно. */}
      <span className="applicationStatus__art applicationStatus__art--failed" aria-hidden="true" />

      <span className="screen__eyebrow applicationStatus__eyebrow">Результат</span>
      <h1 className="screen__title applicationStatus__title">
        Эта вакансия
        <br />
        не подойдет
      </h1>
      <p className="screen__subtitle applicationStatus__subtitle">Не совпало {countWord}</p>

      <div className="mismatchCard">
        <div className="mismatchCard__top">
          <span className="mismatchCard__pill">Не совпало</span>
          <span className="mismatchCard__info" aria-hidden="true">
            i
          </span>
        </div>
        <span className="mismatchCard__title">
          {criterion ? criterionLabel(criterion) : first ? CRITERION_TITLES[first] : 'Обязательное условие'}
        </span>
        <span className="mismatchCard__reason">
          {first ? CRITERION_MISMATCH_REASONS[first] : 'Ответ не совпал с условием вакансии'}
        </span>
        {failed.length > 1 ? (
          <span className="mismatchCard__more">
            Еще: {failed.slice(1).map((type) => CRITERION_TITLES[type].toLowerCase()).join(', ')}
          </span>
        ) : null}
        <span className="mismatchCard__art" aria-hidden="true" />
      </div>

      <p className="applicationStatus__note">
        <span className="applicationStatus__noteIcon">
          <InfoIcon size={20} />
        </span>
        Это не влияет на другие отклики
      </p>

      <div className="screen__spacer" />

      <button type="button" className="screenButton screenButton--primary" onClick={() => navigate(routes.candidateFeed)}>
        Смотреть другие вакансии
      </button>
    </div>
  )
}

const PENDING_LABELS: Partial<Record<CandidateApplication['status'], string>> = {
  rejected: 'Работодатель выбрал другого кандидата',
  invited: 'Работодатель приглашает вас',
}

/** C07: действие завершено, дальше решение работодателя. */
function ApplicationPending({ application }: { application: CandidateApplication }) {
  const navigate = useNavigate()
  const { vacancy } = application

  return (
    <div className="screen applicationStatus">
      <BackButton onClick={() => navigate(routes.candidateFeed)} />
      <span className="applicationStatus__art applicationStatus__art--sent" aria-hidden="true" />

      <h1 className="screen__title applicationStatus__sentTitle">Отклик отправлен</h1>
      <p className="screen__subtitle applicationStatus__sentSubtitle">Теперь решение за работодателем</p>

      <article className="pendingCard">
        <div className="pendingCard__photo photoSlot" />
        <div className="pendingCard__body">
          <div className="pendingCard__head">
            <div>
              <h2 className="pendingCard__title">{vacancy.title}</h2>
              {vacancy.company_name ? <span className="pendingCard__company">{vacancy.company_name}</span> : null}
            </div>
            {/* Сохранение вакансий в P0 не предусмотрено — кнопка из макета неактивна. */}
            <button type="button" className="pendingCard__save" disabled aria-label="Сохранить вакансию">
              <BookmarkIcon size={24} strokeWidth={2} />
            </button>
          </div>
          <span className="pendingCard__salary">{formatSalaryRange(vacancy.salary_min, vacancy.salary_max)}</span>
          <span className="pendingCard__status">
            <ClockIcon size={26} strokeWidth={1.9} />
            {PENDING_LABELS[application.status] ?? 'Ожидает решения'}
          </span>
        </div>
      </article>

      <div className="applicationStatus__steps">
        <ProgressSteps
          steps={[
            { label: 'Отклик', state: 'done' },
            { label: 'Рассмотрение', state: 'current' },
            { label: 'Интервью', state: 'todo' },
          ]}
        />
      </div>

      <p className="applicationStatus__notice">
        <span className="applicationStatus__noticeIcon">
          <BellIcon size={22} />
        </span>
        Мы напишем в MAX, когда статус изменится
      </p>

      <div className="screen__spacer" />

      <button
        type="button"
        className="screenButton screenButton--outlinePrimary"
        onClick={() => navigate(routes.candidateFeed)}
      >
        Смотреть другие вакансии
      </button>
    </div>
  )
}
