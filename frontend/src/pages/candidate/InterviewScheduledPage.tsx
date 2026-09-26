import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { getSlots, getVacancy } from '@/api/hiring'
import { ErrorScreen } from '@/components/ErrorScreen'
import { InterviewTicket, MaxNotice } from '@/components/InterviewTicket'
import { LoadingScreen } from '@/components/LoadingScreen'
import { useAsync } from '@/hooks/useAsync'
import './InterviewScheduledPage.css'

/**
 * C10 «Интервью назначено» — главный результат P0 для кандидата.
 * Повторное открытие показывает то же подтверждение: своё собеседование
 * кандидат получает в `interviews` ответа `GET /vacancies/{id}/slots`.
 */
export function InterviewScheduledPage() {
  const vacancyId = Number(useParams().vacancyId)
  const navigate = useNavigate()
  const { state, reload } = useAsync(async (signal) => {
    const [vacancy, slots] = await Promise.all([getVacancy(vacancyId, signal), getSlots(vacancyId, signal)])
    return { vacancy, interview: slots.interviews[0] ?? null }
  }, [vacancyId])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.candidateFeed)} />
  }

  const { vacancy, interview } = state.data
  if (!interview) return <Navigate to={routes.candidateMatchSlots(vacancyId)} replace />

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
        imageUrl={vacancy.image_url}
        startsAt={interview.slot.starts_at}
        heading={vacancy.title}
        subheading={vacancy.company_name}
        place={vacancy.location ?? 'Адрес уточнит работодатель'}
      />

      <MaxNotice tone="card">
        {/* Доставку уведомления backend фронту не сообщает (раздел 48 —
            журнал на сервере), поэтому формулировка без «уже получили». */}
        Подробности придут вам в MAX
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
