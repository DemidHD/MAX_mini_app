import { Link, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { AccentMarks, CheckIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { getMatch } from '@/mocks/demoApi'
import './MatchPage.css'

/**
 * M01 «Взаимный интерес» (сторона кандидата): обе стороны заинтересованы,
 * следующий шаг один — выбрать время интервью (C09).
 */
export function MatchPage() {
  const matchId = Number(useParams().matchId)
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getMatch(matchId, signal), [matchId])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.candidateFeed)} />
  }

  const { vacancy } = state.data

  return (
    <div className="screen matchPage">
      <div className="matchPage__top">
        <p className="matchPage__brand">MAX Найм</p>
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
          <span className="matchPage__cardPhoto photoSlot" />
        </div>

        <div className="matchPage__card matchPage__card--employer">
          <span className="matchPage__cardLabel">{vacancy.company_name ?? 'Работодатель'}</span>
          <span className="matchPage__cardTitle">Приглашение</span>
          <span className="matchPage__cardPhoto photoSlot photoSlot--dark" />
        </div>

        <span className="matchPage__check">
          <CheckIcon size={30} strokeWidth={2.8} />
        </span>
      </div>

      <div className="matchPage__sheet">
        <span className="matchPage__handle" aria-hidden="true" />
        <h2 className="matchPage__sheetTitle">Выберите удобное время</h2>
        <p className="matchPage__sheetText">Без переписки с работодателем</p>
        <Link to={routes.candidateMatchSlots(matchId)} className="screenButton screenButton--primary matchPage__cta">
          Выбрать время
        </Link>
      </div>
    </div>
  )
}
