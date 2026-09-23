import { Link, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ErrorScreen } from '@/components/ErrorScreen'
import { InterviewTicket, MaxNotice } from '@/components/InterviewTicket'
import { LoadingScreen } from '@/components/LoadingScreen'
import { useAsync } from '@/hooks/useAsync'
import { getInterview } from '@/mocks/demoApi'
import './InterviewScheduledPage.css'

/**
 * C10 «Интервью назначено» — главный результат P0 для кандидата.
 * Повторное открытие показывает то же подтверждение (данные с backend).
 */
export function InterviewScheduledPage() {
  const interviewId = Number(useParams().interviewId)
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getInterview(interviewId, signal), [interviewId])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.candidateFeed)} />
  }

  const interview = state.data
  const { vacancy } = interview

  return (
    <div className="screen interviewScheduled">
      <span className="interviewScheduled__eyebrow">Готово</span>
      <h1 className="screen__title interviewScheduled__title">
        Интервью
        <br />
        назначено
      </h1>

      <InterviewTicket
        headingLarge
        startsAt={interview.starts_at}
        heading={vacancy.title}
        subheading={vacancy.company_name}
        place={vacancy.location ?? 'Адрес уточнит работодатель'}
      />

      <MaxNotice tone="card">
        {interview.notification_sent
          ? 'Подробности отправлены вам в MAX'
          : 'Интервью назначено. Уведомление в MAX придет чуть позже'}
      </MaxNotice>

      <div className="screen__spacer" />

      <Link to={routes.candidateFeed} className="screenButton screenButton--primary">
        Готово
      </Link>
      <Link to={routes.candidateApplications} className="screenButton screenButton--link interviewScheduled__link">
        Мои отклики
      </Link>
    </div>
  )
}
