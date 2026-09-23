import { Navigate, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { ProgressSteps } from '@/components/ProgressSteps'
import { AccentMarks, ClockIcon, SendIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { plural } from '@/lib/format'
import { getScreening } from '@/mocks/demoApi'
import './ScreeningStartPage.css'

/**
 * C04 «Старт первичного отбора»: отклик уже создан, впереди 3–4 коротких
 * вопроса (раздел 18). Если отбор уже пройден — сразу статус отклика.
 */
export function ScreeningStartPage() {
  const applicationId = Number(useParams().applicationId)
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getScreening(applicationId, signal), [applicationId])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.candidateFeed)} />
  }
  if (!state.data.can_submit) {
    return <Navigate to={routes.candidateApplication(applicationId)} replace />
  }

  const count = state.data.questions.length
  const questionsLabel = `${count} ${plural(count, 'вопрос', 'вопроса', 'вопросов')}`

  return (
    <div className="screen screeningStart">
      <span className="screeningStart__badge">
        <SendIcon size={22} strokeWidth={2.1} />
        Отклик отправлен
      </span>

      <h1 className="screen__title screeningStart__title">
        Еще
        <br />
        {questionsLabel}
      </h1>

      {/* Место под иллюстрацию из макета (объёмная цифра); картинка добавится отдельно. */}
      <div className="screeningStart__art" aria-hidden="true">
        <AccentMarks className="screeningStart__marks" />
      </div>

      <div className="screeningStart__card">
        <div className="screeningStart__cardHead">
          <span className="screeningStart__clock">
            <ClockIcon size={24} strokeWidth={2} />
          </span>
          около 1 минуты
        </div>
        <p className="screeningStart__cardText">
          Ответьте на короткие вопросы, чтобы работодатель сразу увидел подходящий отклик.
        </p>
      </div>

      <div className="screeningStart__steps">
        <ProgressSteps
          steps={[
            { label: 'Отклик', state: 'done' },
            { label: questionsLabel, state: 'current', number: 2 },
            { label: 'Решение', state: 'todo', number: 3 },
          ]}
        />
      </div>

      <div className="screen__spacer" />

      <button
        type="button"
        className="screenButton screenButton--primary"
        onClick={() => navigate(routes.candidateScreening(applicationId))}
      >
        Начать
      </button>
      <button
        type="button"
        className="screenButton screenButton--link screeningStart__later"
        onClick={() => navigate(routes.candidateFeed)}
      >
        Вернуться позже
      </button>
    </div>
  )
}
