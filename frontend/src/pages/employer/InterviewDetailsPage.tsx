import { Link, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import { candidateLabel, getSlots, getVacancy, getVacancyCandidates } from '@/api/hiring'
import { ErrorScreen } from '@/components/ErrorScreen'
import { InterviewTicket, MaxNotice } from '@/components/InterviewTicket'
import { LoadingScreen } from '@/components/LoadingScreen'
import { AccentMarks } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import './InterviewDetailsPage.css'

/**
 * E10 «Детали интервью»: итог маршрута работодателя — когда и с кем.
 * Собеседования работодателя по вакансии приходят в `interviews` ответа
 * `GET /vacancies/{id}/slots`.
 */
export function InterviewDetailsPage() {
  const params = useParams()
  const vacancyId = Number(params.vacancyId)
  const interviewId = Number(params.interviewId)
  const navigate = useNavigate()
  const { state, reload } = useAsync(async (signal) => {
    const [vacancy, slots, candidates] = await Promise.all([
      getVacancy(vacancyId, signal),
      getSlots(vacancyId, signal),
      getVacancyCandidates(vacancyId, signal),
    ])
    const interview = slots.interviews.find((item) => item.id === interviewId)
    if (!interview) throw new ApiError(404, { code: 'interview_not_found', message: 'Интервью не найдено' })
    return { vacancy, interview, candidates: candidates.items }
  }, [vacancyId, interviewId])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.employerHome)} />
  }

  const { vacancy, interview, candidates } = state.data

  return (
    <div className="screen interviewDetails">
      <span className="screen__eyebrow">Интервью</span>
      <div className="interviewDetails__heading">
        <h1 className="screen__title interviewDetails__title">Все назначено</h1>
        <AccentMarks className="interviewDetails__marks" />
      </div>

      <InterviewTicket
        checkInBadge
        imageUrl={vacancy.image_url}
        startsAt={interview.slot.starts_at}
        heading={vacancy.title}
        person={
          <>
            <span className="interviewDetails__avatar photoSlot" aria-hidden="true" />
            {candidateLabel(candidates, interview.application_id)}
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
        {/* Доставку уведомления backend фронту не сообщает (раздел 48 —
            журнал на сервере), поэтому формулировка без «уже получил». */}
        Кандидату придет уведомление в MAX
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
