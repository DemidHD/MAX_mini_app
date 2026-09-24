import { useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import { bookSlot, getSlots, getVacancy } from '@/api/hiring'
import type { InterviewSlot, Vacancy } from '@/api/hiring'
import { BackButton } from '@/components/BackButton'
import { CoverImage } from '@/components/CoverImage'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { CalendarIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { dayKey, formatDayMonth, formatTime, monthShort, weekdayShort } from '@/lib/format'
import './SlotPickerPage.css'

/**
 * C09 «Выбор интервала интервью»: свободные даты и время, подтверждение
 * бронирует слот (`POST /matches/:id/book`). Если слот заняли между
 * просмотром и подтверждением (409), список обновляется (раздел 37).
 */
export function SlotPickerPage() {
  const vacancyId = Number(useParams().vacancyId)
  const navigate = useNavigate()
  const { state, reload } = useAsync(async (signal) => {
    const [vacancy, slots] = await Promise.all([getVacancy(vacancyId, signal), getSlots(vacancyId, signal)])
    return { vacancy, slots }
  }, [vacancyId])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(-1)} />
  }
  const { vacancy, slots } = state.data
  // Интервью уже назначено — повторный выбор не нужен (перенос — P1).
  if (slots.interviews.length > 0) return <Navigate to={routes.candidateInterview(vacancyId)} replace />
  if (slots.match_id === null) return <Navigate to={routes.candidateFeed} replace />
  return <SlotPicker vacancy={vacancy} matchId={slots.match_id} initialSlots={slots.items} />
}

function SlotPicker({
  vacancy,
  matchId,
  initialSlots,
}: {
  vacancy: Vacancy
  matchId: number
  initialSlots: InterviewSlot[]
}) {
  const navigate = useNavigate()
  const [slots, setSlots] = useState(initialSlots)
  const available = slots
    .filter((slot) => slot.status === 'available')
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
  const days = [...new Set(available.map((slot) => dayKey(slot.starts_at)))]
  const [day, setDay] = useState(days[0] ?? null)
  const [slotId, setSlotId] = useState<number | null>(available[0]?.id ?? null)
  const [booking, setBooking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const activeDay = day && days.includes(day) ? day : (days[0] ?? null)
  const daySlots = available.filter((slot) => dayKey(slot.starts_at) === activeDay)
  const selected = available.find((slot) => slot.id === slotId) ?? null

  async function handleConfirm() {
    if (!selected) return
    setBooking(true)
    setError(null)
    try {
      await bookSlot(matchId, selected.id)
      navigate(routes.candidateInterview(vacancy.id), { replace: true })
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'interview_already_scheduled') {
        navigate(routes.candidateInterview(vacancy.id), { replace: true })
        return
      }
      if (cause instanceof ApiError && cause.status === 409) {
        setError('Это время только что заняли. Выберите другое — список обновлен.')
        const fresh = await getSlots(vacancy.id).catch(() => null)
        if (fresh) setSlots(fresh.items)
      } else {
        setError('Не удалось подтвердить время. Попробуйте еще раз.')
      }
      setSlotId(null)
    } finally {
      setBooking(false)
    }
  }

  return (
    <div className="screen slotPicker">
      <BackButton />

      <h1 className="screen__title slotPicker__title">Когда удобно?</h1>
      <p className="screen__subtitle slotPicker__subtitle">
        Интервью{vacancy.company_name ? ` · ${vacancy.company_name}` : ''}
      </p>

      {days.length === 0 ? (
        <div className="slotPicker__empty">
          <p className="slotPicker__emptyTitle">Работодатель еще не добавил время</p>
          <p className="slotPicker__emptyText">Мы напишем в MAX, как только появятся свободные варианты.</p>
        </div>
      ) : (
        <>
          <div className="slotPicker__days" role="tablist" aria-label="Дата">
            {days.map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={key === activeDay}
                className={`slotPicker__day${key === activeDay ? ' slotPicker__day--active' : ''}`}
                onClick={() => {
                  setDay(key)
                  setSlotId(available.find((slot) => dayKey(slot.starts_at) === key)?.id ?? null)
                }}
              >
                <span className="slotPicker__dayNumber">{Number(key.slice(8))}</span>
                <span className="slotPicker__dayMonth">{monthShort(key)}</span>
                <span className="slotPicker__weekday">{weekdayShort(key)}</span>
              </button>
            ))}
          </div>

          <h2 className="slotPicker__section">Свободное время</h2>
          <div className="slotPicker__times">
            {daySlots.map((slot) => (
              <button
                key={slot.id}
                type="button"
                className={`slotPicker__time${slot.id === slotId ? ' slotPicker__time--active' : ''}`}
                aria-pressed={slot.id === slotId}
                onClick={() => {
                  setSlotId(slot.id)
                  setError(null)
                }}
              >
                {formatTime(slot.starts_at)}
              </button>
            ))}
          </div>

          {selected ? (
            <div className="slotPicker__summary">
              <span className="slotPicker__thumb photoSlot" aria-hidden="true">
                <CoverImage url={vacancy.image_url} />
              </span>
              <span className="slotPicker__summaryText">
                <span className="slotPicker__summaryDate">{formatDayMonth(selected.starts_at)}</span>
                <span className="slotPicker__summaryTime">
                  {formatTime(selected.starts_at)} – {formatTime(selected.ends_at)}
                </span>
                <span className="slotPicker__summaryRole">{vacancy.title}</span>
              </span>
              <span className="slotPicker__summaryIcon" aria-hidden="true">
                <CalendarIcon size={24} />
              </span>
            </div>
          ) : null}
        </>
      )}

      <div className="screen__spacer" />

      {error ? <p className="screen__error">{error}</p> : null}
      <button
        type="button"
        className="screenButton screenButton--primary"
        disabled={!selected || booking}
        onClick={() => void handleConfirm()}
      >
        {booking ? 'Бронируем…' : 'Подтвердить'}
      </button>
      <p className="screen__note">
        После подтверждения время будет
        <br />
        закреплено за вами
      </p>
    </div>
  )
}
