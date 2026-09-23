import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import { BackButton } from '@/components/BackButton'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { AccentMarks, CalendarIcon, CheckIcon, SendIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { candidateLabel, decide, getEmployerApplication } from '@/mocks/demoApi'
import './InviteConfirmPage.css'

/**
 * E09 «Подтверждение приглашения»: защита от случайного нажатия. Повторное
 * приглашение дубль не создаёт — backend отвечает 409, и мы просто
 * возвращаемся к очереди (`POST /applications/:id/decision`, раздел 35).
 */
export function InviteConfirmPage() {
  const applicationId = Number(useParams().applicationId)
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getEmployerApplication(applicationId, signal), [applicationId])
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(-1)} />
  }

  const { vacancy, candidate } = state.data
  const required = candidate.hard_filters.filter((item) => item.required)
  const passed = required.filter((item) => item.passed === true).length
  const queuePath = routes.employerVacancyCandidates(vacancy.id)

  async function handleInvite() {
    setSending(true)
    setError(null)
    try {
      await decide(applicationId, 'invited')
      navigate(queuePath, {
        replace: true,
        state: { flash: 'Приглашение отправлено. Кандидат выберет удобное время интервью.' },
      })
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        navigate(queuePath, { replace: true })
        return
      }
      setError('Не удалось отправить приглашение. Попробуйте еще раз.')
      setSending(false)
    }
  }

  return (
    <div className="screen inviteConfirm">
      <BackButton />

      <h1 className="screen__title inviteConfirm__title">
        Пригласить
        <br />
        кандидата?
      </h1>

      <div className="inviteConfirm__scene">
        <AccentMarks className="inviteConfirm__marks inviteConfirm__marks--top" />
        <AccentMarks className="inviteConfirm__marks inviteConfirm__marks--bottom" />

        <div className="inviteConfirm__person">
          <span className="inviteConfirm__avatar photoSlot" aria-hidden="true" />
          <div className="inviteConfirm__personText">
            <span className="inviteConfirm__name">{candidateLabel(applicationId)}</span>
            <span className="inviteConfirm__role">{candidate.desired_role ?? vacancy.title}</span>
            <span className="inviteConfirm__match">
              <span className="inviteConfirm__matchIcon">
                <CheckIcon size={14} strokeWidth={3} />
              </span>
              {passed}/{required.length} обязательных
            </span>
          </div>
        </div>

        <div className="inviteConfirm__link" aria-hidden="true">
          <span className="inviteConfirm__dots" />
          <span className="inviteConfirm__send">
            <SendIcon size={24} strokeWidth={2} />
          </span>
          <span className="inviteConfirm__dots" />
        </div>

        <div className="inviteConfirm__interview" aria-hidden="true">
          <span className="inviteConfirm__ghost" />
          <div className="inviteConfirm__ticket">
            <div className="inviteConfirm__calendar">
              <div className="inviteConfirm__calendarHead">
                <CalendarIcon size={22} />
                <span>
                  <i />
                  <i />
                </span>
              </div>
              <div className="inviteConfirm__grid">
                {Array.from({ length: 12 }, (_, index) => (
                  <i key={index} className={index === 6 ? 'inviteConfirm__cell--active' : undefined} />
                ))}
              </div>
            </div>
            <div className="inviteConfirm__ticketText">
              <span>Интервью</span>
              <i />
              <i />
            </div>
          </div>
        </div>
      </div>

      <p className="inviteConfirm__hint">После приглашения кандидат сможет выбрать удобное время интервью.</p>

      <div className="screen__spacer" />

      {error ? <p className="screen__error">{error}</p> : null}
      <button type="button" className="screenButton screenButton--outline" disabled={sending} onClick={() => navigate(-1)}>
        Отмена
      </button>
      <button
        type="button"
        className="screenButton screenButton--primary inviteConfirm__submit"
        disabled={sending}
        onClick={() => void handleInvite()}
      >
        {sending ? 'Приглашаем…' : 'Пригласить'}
      </button>
    </div>
  )
}
