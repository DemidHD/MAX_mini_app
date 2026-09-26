import { useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import { getScreening, submitScreening } from '@/api/hiring'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { ProgressSteps } from '@/components/ProgressSteps'
import { ClockIcon, SendIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { plural } from '@/lib/format'
import artCup from '@/assets/art-cup.webp'
import './ScreeningStartPage.css'

/**
 * C04 «Старт первичного отбора»: отклик уже создан, впереди 3–4 коротких
 * вопроса (раздел 18). Если отбор уже пройден — сразу статус отклика.
 */
export function ScreeningStartPage() {
  const applicationId = Number(useParams().applicationId)
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getScreening(applicationId, signal), [applicationId])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.candidateFeed)} />
  }
  if (!state.data.can_submit) {
    return <Navigate to={routes.candidateApplication(applicationId)} replace />
  }

  const count = state.data.questions.length

  // Вакансия без вопросов: отбор идёт только по профилю — отправляем пустой
  // набор ответов тем же запросом, что и экран вопросов.
  async function submitEmpty() {
    setSending(true)
    setError(null)
    try {
      const result = await submitScreening(applicationId, [])
      navigate(routes.candidateApplication(applicationId), { replace: true, state: { screening: result } })
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'screening_already_completed') {
        navigate(routes.candidateApplication(applicationId), { replace: true })
        return
      }
      setError('Не удалось отправить отклик. Попробуйте еще раз.')
      setSending(false)
    }
  }
  const questionsLabel = count > 0 ? `${count} ${plural(count, 'вопрос', 'вопроса', 'вопросов')}` : 'Проверка'

  return (
    <div className="screen screeningStart">
      <span className="screeningStart__badge">
        <SendIcon size={22} strokeWidth={2.1} />
        Отклик отправлен
      </span>

      <h1 className="screen__title screeningStart__title">
        {count > 0 ? (
          <>
            Еще
            <br />
            {questionsLabel}
          </>
        ) : (
          <>
            Почти
            <br />
            готово
          </>
        )}
      </h1>

      <div className="screeningStart__art" aria-hidden="true">
        <img className="screeningStart__artImage" src={artCup} alt="" />
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

      {error ? <p className="screen__error">{error}</p> : null}
      <button
        type="button"
        className="screenButton screenButton--primary"
        disabled={sending}
        onClick={() => (count > 0 ? navigate(routes.candidateScreening(applicationId)) : void submitEmpty())}
      >
        {count > 0 ? 'Начать' : sending ? 'Отправляем…' : 'Отправить отклик'}
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
