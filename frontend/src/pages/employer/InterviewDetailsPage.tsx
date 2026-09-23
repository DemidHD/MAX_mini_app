import { Link, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ErrorScreen } from '@/components/ErrorScreen'
import { InterviewTicket, MaxNotice } from '@/components/InterviewTicket'
import { LoadingScreen } from '@/components/LoadingScreen'
import { AccentMarks } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { candidateLabel, getInterview } from '@/mocks/demoApi'
import './InterviewDetailsPage.css'

/**
 * E10 «Детали интервью»: итог маршрута работодателя — когда и с кем.
 * Ошибка уведомления в MAX интервью не отменяет (раздел 83), поэтому строка
 * об уведомлении честно показывает, дошло ли оно.
 */
export function InterviewDetailsPage() {
  const interviewId = Number(useParams().interviewId)
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getInterview(interviewId, signal), [interviewId])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.employerHome)} />
  }

  const interview = state.data
  const { vacancy } = interview

  return (
    <div className="screen interviewDetails">
      <span className="screen__eyebrow">Интервью</span>
      <div className="interviewDetails__heading">
        <h1 className="screen__title interviewDetails__title">Все назначено</h1>
        <AccentMarks className="interviewDetails__marks" />
      </div>

      <InterviewTicket
        checkInBadge
        startsAt={interview.starts_at}
        heading={vacancy.title}
        person={
          <>
            <span className="interviewDetails__avatar photoSlot" aria-hidden="true" />
            {candidateLabel(interview.application_id)}
          </>
        }
        place={
          <>
            {vacancy.company_name ? <span>{vacancy.company_name}</span> : null}
            {vacancy.location ? <span>{vacancy.location}</span> : null}
          </>
        }
      />

      <MaxNotice>
        {interview.notification_sent
          ? 'Кандидат получил уведомление в MAX'
          : 'Уведомление в MAX не дошло, но интервью назначено'}
      </MaxNotice>

      <div className="screen__spacer" />

      <Link to={routes.employerVacancyCandidates(vacancy.id)} className="screenButton screenButton--outlinePrimary">
        Вернуться к кандидатам
      </Link>
      <Link to={routes.employerHome} className="screenButton screenButton--link interviewDetails__link">
        Открыть вакансию
      </Link>
    </div>
  )
}
