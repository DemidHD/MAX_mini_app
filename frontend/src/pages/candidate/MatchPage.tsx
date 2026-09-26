import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { getSlots, getVacancy } from '@/api/hiring'
import { CoverImage } from '@/components/CoverImage'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { AccentMarks, CheckIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import profileRole from '@/assets/profile-role.webp'
import './MatchPage.css'

/**
 * M01 «Взаимный интерес» (сторона кандидата): обе стороны заинтересованы,
 * следующий шаг один — выбрать время интервью (C09). Слоты кандидату
 * открываются только после взаимного интереса, поэтому `GET .../slots`
 * заодно подтверждает, что match есть.
 */
export function MatchPage() {
  const vacancyId = Number(useParams().vacancyId)
  const navigate = useNavigate()
  const { state, reload } = useAsync(async (signal) => {
    const [vacancy, slots] = await Promise.all([getVacancy(vacancyId, signal), getSlots(vacancyId, signal)])
    return { vacancy, slots }
  }, [vacancyId])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.candidateFeed)} />
  }

  const { vacancy, slots } = state.data
  if (slots.interviews.length > 0) return <Navigate to={routes.candidateInterview(vacancyId)} replace />

  return (
    <div className="screen matchPage">
      <div className="matchPage__top">
        <p className="matchPage__brand">МЭТЧ</p>
        <h1 className="screen__title matchPage__title">
          Есть взаимный
          <br />
          интерес
        </h1>
        <p className="matchPage__subtitle">
          Работодатель приглашает вас
          <br />
          на интервью
        </p>
      </div>

      <div className="matchPage__scene" aria-hidden="true">
        <AccentMarks className="accentMarks--light matchPage__marks matchPage__marks--top" />
        <AccentMarks className="accentMarks--light matchPage__marks matchPage__marks--bottom" />

        <div className="matchPage__card matchPage__card--you">
          <span className="matchPage__cardLabel">Вы</span>
          <span className="matchPage__cardTitle">{vacancy.title}</span>
          <span className="matchPage__cardPhoto photoSlot">
            <CoverImage url={profileRole} />
          </span>
        </div>

        <div className="matchPage__card matchPage__card--employer">
          <span className="matchPage__cardLabel">{vacancy.company_name ?? 'Работодатель'}</span>
          <span className="matchPage__cardTitle">Приглашение</span>
          <span className="matchPage__cardPhoto photoSlot photoSlot--dark">
            <CoverImage url={vacancy.image_url} />
          </span>
        </div>

        <span className="matchPage__check">
          <CheckIcon size={30} strokeWidth={2.8} />
        </span>
      </div>

      <div className="matchPage__sheet">
        <span className="matchPage__handle" aria-hidden="true" />
        <h2 className="matchPage__sheetTitle">Выберите удобное время</h2>
        <p className="matchPage__sheetText">Без переписки с работодателем</p>
        <Link to={routes.candidateMatchSlots(vacancyId)} className="screenButton screenButton--primary matchPage__cta">
          Выбрать время
        </Link>
      </div>
    </div>
  )
}
