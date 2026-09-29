import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { Typography } from '@maxhub/max-ui'

import { pathForStep, routes } from '@/app/routes'
import { SplashScreen } from '@/components/SplashScreen'
import { useAuth } from '@/auth/useAuth'
import manPhoto from '@/assets/welcome-man.webp'
import womanPhoto from '@/assets/welcome-woman.webp'
import './WelcomePage.css'

/**
 * Приветственный экран — первое, что видит новый пользователь при входе в
 * Mini App (до выбора роли, G02). Только презентация: никакие данные тут не
 * собираются, «Начать» ведёт на выбор роли. Пользователь с уже выбранной
 * ролью сюда не попадает — его уводит на актуальный шаг `RootRedirect`.
 */
export function WelcomePage() {
  const { state } = useAuth()
  const [searchParams] = useSearchParams()

  if (state.status !== 'authenticated') return <SplashScreen />

  // `?preview` (только в dev) — посмотреть экран, не будучи новым пользователем.
  const isPreview = import.meta.env.DEV && searchParams.has('preview')

  if (state.user.role !== null && !isPreview) {
    return <Navigate to={pathForStep(state.currentStep, state.applicationId, state.vacancyId)} replace />
  }

  return (
    <div className="welcome">
      <div className="welcome__hero" aria-hidden="true">
        <span className="welcome__tag welcome__tag--programmer">программист</span>
        <span className="welcome__tag welcome__tag--economist">экономист</span>
        <span className="welcome__tag welcome__tag--designer">дизайнер</span>
        <span className="welcome__tag welcome__tag--manager">менеджер</span>
        <span className="welcome__tag welcome__tag--barista">бариста</span>

        <img className="welcome__photo welcome__photo--man" src={manPhoto} alt="" />
        <img className="welcome__photo welcome__photo--woman" src={womanPhoto} alt="" />

        <span className="welcome__match">Мэтч!</span>
      </div>

      <div className="welcome__body">
        <div className="welcome__text">
          <Typography.Display asChild>
            <h1 className="welcome__title">
              Добро пожаловать
              <br />в <span className="welcome__brand">МЭТЧ</span>
            </h1>
          </Typography.Display>
          <Typography.Body className="welcome__subtitle">
            Место, где работа и люди находят друг друга. Быстро и без лишней переписки
          </Typography.Body>
        </div>

        <Link className="welcome__cta" to={routes.roleSelection} replace>
          Начать
        </Link>
      </div>
    </div>
  )
}
