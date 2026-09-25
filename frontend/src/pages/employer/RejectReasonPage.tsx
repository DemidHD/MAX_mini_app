import { useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import { decide } from '@/api/hiring'
import type { RejectReason } from '@/api/hiring'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { CalendarIcon, CheckIcon, ClockIcon, CloseIcon, FileListIcon, MoreIcon, PinIcon, RubleIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { loadApplicationView, pathAfterDecision } from '@/pages/employer/applicationView'
import './RejectReasonPage.css'

/** Теги причины отказа (раздел 20, UX-карта «Тег причины»). */
const REASONS: { id: RejectReason; label: string; icon: ReactNode }[] = [
  { id: 'experience', label: 'Опыт', icon: <FileListIcon size={40} strokeWidth={1.6} /> },
  { id: 'salary', label: 'Зарплата', icon: <RubleIcon size={40} strokeWidth={1.7} /> },
  { id: 'schedule', label: 'График', icon: <CalendarIcon size={40} strokeWidth={1.6} /> },
  { id: 'location', label: 'Локация', icon: <PinIcon size={40} strokeWidth={1.6} /> },
  { id: 'available_from', label: 'Дата выхода', icon: <ClockIcon size={40} strokeWidth={1.6} /> },
  { id: 'other', label: 'Другое', icon: <MoreIcon size={40} /> },
]

/**
 * E14 «Причина отказа» (P1, функция 22). Открывается после «Отклонить» на
 * карточке E08. Причина необязательна: «Пропустить» отклоняет без неё, чтобы
 * не создавать трения (UX-карта). Крестик — передумать и вернуться к карточке.
 */
export function RejectReasonPage() {
  const params = useParams()
  const vacancyId = Number(params.vacancyId)
  const applicationId = Number(params.applicationId)
  const navigate = useNavigate()
  const { state, reload } = useAsync(
    (signal) => loadApplicationView(vacancyId, applicationId, signal),
    [vacancyId, applicationId],
  )
  const [reason, setReason] = useState<RejectReason | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(-1)} />
  }

  const view = state.data
  const cardPath = routes.employerApplication(vacancyId, applicationId)

  async function handleReject(withReason: RejectReason | null) {
    setSending(true)
    setError(null)
    try {
      await decide(applicationId, 'rejected', withReason)
      navigate(pathAfterDecision(view, applicationId), { replace: true })
    } catch (cause) {
      // Решение уже принято (например, с другого устройства) — к карточке.
      if (cause instanceof ApiError && cause.status === 409) {
        navigate(cardPath, { replace: true })
        return
      }
      setError('Не удалось отклонить. Попробуйте еще раз.')
      setSending(false)
    }
  }

  return (
    <div className="p1Screen rejectReason">
      <button
        type="button"
        className="p1IconButton rejectReason__close"
        aria-label="Не отклонять"
        onClick={() => navigate(cardPath, { replace: true })}
      >
        <CloseIcon size={24} strokeWidth={2.3} />
      </button>

      <h1 className="p1Title rejectReason__title">
        Почему
        <br />
        не подошел?
      </h1>
      <p className="p1Subtitle rejectReason__subtitle">Одно нажатие</p>

      <div className="rejectReason__grid" role="radiogroup" aria-label="Причина отказа">
        {REASONS.map((item) => {
          const selected = item.id === reason
          return (
            <button
              key={item.id}
              type="button"
              role="radio"
              aria-checked={selected}
              className={`rejectReason__tile${selected ? ' rejectReason__tile--selected' : ''}`}
              onClick={() => setReason(selected ? null : item.id)}
            >
              {selected ? (
                <span className="rejectReason__check" aria-hidden="true">
                  <CheckIcon size={16} strokeWidth={3} />
                </span>
              ) : null}
              <span className="rejectReason__icon">{item.icon}</span>
              <span className="rejectReason__label">{item.label}</span>
            </button>
          )
        })}
      </div>

      <p className="rejectReason__note">Причину можно не указывать</p>

      <div className="rejectReason__spacer" />

      {error ? <p className="p1Error">{error}</p> : null}

      <button
        type="button"
        className="p1Button rejectReason__save"
        disabled={reason === null || sending}
        onClick={() => void handleReject(reason)}
      >
        Сохранить
      </button>
      <button type="button" className="p1Link" disabled={sending} onClick={() => void handleReject(null)}>
        Пропустить
      </button>
    </div>
  )
}
