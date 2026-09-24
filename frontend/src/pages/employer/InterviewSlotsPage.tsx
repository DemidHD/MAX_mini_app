import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import { cancelSlot, createSlot, getSlots } from '@/api/hiring'
import type { InterviewSlot } from '@/api/hiring'
import { BackButton } from '@/components/BackButton'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { CalendarIcon, CloseIcon, MinusIcon, PlusIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { dayKey, formatDayMonth, formatDayMonthShort, formatTime } from '@/lib/format'
import './InterviewSlotsPage.css'

const MIN_SLOTS = 2
const MAX_SLOTS = 5
const SLOT_MINUTES = 30
const DAYS_AHEAD = 7
const TIME_OPTIONS = Array.from({ length: 25 }, (_, index) => {
  const minutes = 9 * 60 + index * 30
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
})

interface DraftSlot {
  key: string
  /** `null` — новый интервал, ещё не сохранённый на сервере. */
  id: number | null
  starts_at: string
  ends_at: string
  booked: boolean
}

/**
 * E06 «Интервалы интервью»: 2–5 вариантов времени без внешнего календаря
 * (UX-карта; раздел 37 тех-доки). Забронированный интервал удалить нельзя.
 */
export function InterviewSlotsPage() {
  const vacancyId = Number(useParams().vacancyId)
  const { state, reload } = useAsync((signal) => getSlots(vacancyId, signal), [vacancyId])
  const navigate = useNavigate()

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(-1)} />
  }
  return <SlotsEditor vacancyId={vacancyId} initial={state.data.items} />
}

function toDraft(slot: InterviewSlot): DraftSlot {
  return {
    key: String(slot.id),
    id: slot.id,
    starts_at: slot.starts_at,
    ends_at: slot.ends_at,
    booked: slot.status === 'booked',
  }
}

function SlotsEditor({ vacancyId, initial }: { vacancyId: number; initial: InterviewSlot[] }) {
  const navigate = useNavigate()
  const [slots, setSlots] = useState<DraftSlot[]>(() => initial.map(toDraft))
  const days = useMemo(() => upcomingDays(), [])
  const [selectedDay, setSelectedDay] = useState(() => (initial[0] ? dayKey(initial[0].starts_at) : days[0]))
  const [picking, setPicking] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const daySlots = slots
    .filter((slot) => dayKey(slot.starts_at) === selectedDay)
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
  const freeCount = slots.filter((slot) => !slot.booked).length
  const takenTimes = new Set(daySlots.map((slot) => formatTime(slot.starts_at)))

  function addSlot(time: string) {
    const [hours, minutes] = time.split(':').map(Number)
    const starts = new Date(`${selectedDay}T00:00:00`)
    starts.setHours(hours, minutes)
    const ends = new Date(starts.getTime() + SLOT_MINUTES * 60_000)
    setSlots((previous) => [
      ...previous,
      { key: `new-${starts.getTime()}`, id: null, starts_at: starts.toISOString(), ends_at: ends.toISOString(), booked: false },
    ])
    setPicking(false)
    setError(null)
  }

  async function handleSave() {
    if (freeCount < MIN_SLOTS) {
      setError(`Добавьте хотя бы ${MIN_SLOTS} свободных варианта`)
      return
    }
    setSaving(true)
    setError(null)
    try {
      // Пакетного сохранения у backend нет: убранные интервалы отменяются, новые
      // создаются по одному (api-contracts, «POST/DELETE .../slots»). Успешно
      // созданные сразу получают id, поэтому повтор после ошибки их не дублирует.
      const keptIds = new Set(slots.map((slot) => slot.id))
      for (const slot of initial) {
        if (slot.status === 'available' && !keptIds.has(slot.id)) await cancelSlot(vacancyId, slot.id)
      }
      for (const slot of slots.filter((item) => item.id === null)) {
        const created = await createSlot(vacancyId, { starts_at: slot.starts_at, ends_at: slot.ends_at })
        setSlots((previous) => previous.map((item) => (item.key === slot.key ? { ...item, id: created.id } : item)))
      }
      navigate(routes.employerVacancyCandidates(vacancyId))
    } catch (cause) {
      setError(slotErrorMessage(cause))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="screen slotsPage">
      <BackButton />

      <span className="screen__eyebrow slotsPage__eyebrow">Интервью</span>
      <h1 className="screen__title slotsPage__title">
        Когда вы
        <br />
        свободны?
      </h1>
      <p className="screen__subtitle slotsPage__subtitle">
        Добавьте от {MIN_SLOTS} до {MAX_SLOTS} вариантов
      </p>

      <div className="slotsPage__days" role="tablist" aria-label="Дата интервью">
        {days.map((day) => {
          const active = day === selectedDay
          return (
            <button
              key={day}
              type="button"
              role="tab"
              aria-selected={active}
              className={`slotsPage__day${active ? ' slotsPage__day--active' : ''}`}
              onClick={() => {
                setSelectedDay(day)
                setPicking(false)
              }}
            >
              <CalendarIcon size={24} strokeWidth={1.9} />
              <span>{formatDayMonthShort(day)}</span>
            </button>
          )
        })}
      </div>

      <h2 className="slotsPage__dayTitle">{formatDayMonth(selectedDay)}</h2>

      <ul className="slotsPage__list">
        {daySlots.map((slot) => (
          <li key={slot.key} className="slotsPage__slot">
            <span className="slotsPage__slotText">
              <span className="slotsPage__slotTime">
                {formatTime(slot.starts_at)}–{formatTime(slot.ends_at)}
              </span>
              <span className={`slotsPage__slotStatus${slot.booked ? ' slotsPage__slotStatus--booked' : ''}`}>
                {slot.booked ? 'Забронировано' : 'Свободно'}
              </span>
            </span>
            <button
              type="button"
              className="slotsPage__remove"
              aria-label={`Удалить интервал ${formatTime(slot.starts_at)}`}
              disabled={slot.booked}
              onClick={() => setSlots((previous) => previous.filter((item) => item.key !== slot.key))}
            >
              <MinusIcon size={22} strokeWidth={2.4} />
            </button>
          </li>
        ))}
      </ul>

      {picking ? (
        <div className="slotsPage__picker">
          <div className="slotsPage__pickerHead">
            <span>Начало интервала</span>
            <button type="button" className="slotsPage__pickerClose" aria-label="Закрыть" onClick={() => setPicking(false)}>
              <CloseIcon size={18} />
            </button>
          </div>
          <div className="slotsPage__times">
            {TIME_OPTIONS.filter((time) => !takenTimes.has(time)).map((time) => (
              <button key={time} type="button" className="slotsPage__time" onClick={() => addSlot(time)}>
                {time}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="slotsPage__add"
          disabled={freeCount >= MAX_SLOTS}
          onClick={() => setPicking(true)}
        >
          <PlusIcon size={26} strokeWidth={2.4} />
          {freeCount >= MAX_SLOTS ? `Максимум ${MAX_SLOTS} вариантов` : 'Добавить интервал'}
        </button>
      )}

      <p className="slotsPage__hint">Кандидат выберет один свободный вариант</p>

      <div className="screen__spacer" />

      {error ? <p className="screen__error">{error}</p> : null}
      <button type="button" className="screenButton screenButton--primary" disabled={saving} onClick={() => void handleSave()}>
        {saving ? 'Сохраняем…' : 'Сохранить'}
      </button>
    </div>
  )
}

function upcomingDays(): string[] {
  return Array.from({ length: DAYS_AHEAD }, (_, index) => {
    const date = new Date()
    date.setDate(date.getDate() + index + 1)
    return dayKey(date)
  })
}

function slotErrorMessage(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.code === 'slot_overlaps') return 'Один из интервалов пересекается с уже назначенным временем.'
    if (cause.code === 'slot_in_past') return 'Один из интервалов уже в прошлом — уберите его.'
  }
  return 'Не удалось сохранить. Интервалы на месте — попробуйте еще раз.'
}
