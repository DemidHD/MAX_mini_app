import { useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent, ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { getCalibrationProfiles, submitCalibration } from '@/api/p2'
import type { CalibrationCriterion, CalibrationProfile, CalibrationVote } from '@/api/p2'
import type { CriterionType } from '@/api/hiring'
import candidateA from '@/assets/calibration-candidate-a.webp'
import candidateB from '@/assets/calibration-candidate-b.webp'
import candidateC from '@/assets/calibration-candidate-c.webp'
import reservePortrait1 from '@/assets/reserve-candidate-1.webp'
import reservePortrait2 from '@/assets/reserve-candidate-2.webp'
import { BackButton } from '@/components/BackButton'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { BriefcaseIcon, CalendarIcon, ClockIcon, DocumentIcon, PinIcon, RubleIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import './CalibrationPage.css'

/** Буквы тестовых профилей: карточки синтетические, имён у них нет. */
const LETTERS = ['А', 'Б', 'В', 'Г', 'Д']

/**
 * Фото тестовых профилей — оформление из макета E17. Карточки синтетические
 * (`app/vacancies/calibration.py`), а веса считаются только по условиям
 * вакансии: фото в `POST .../calibration` не участвует (раздел 31 тех-доки).
 */
const PORTRAITS = [candidateA, reservePortrait1, reservePortrait2]

const CRITERION_ROWS: Record<CriterionType, { title: string; icon: ReactNode }> = {
  experience: { title: 'Опыт', icon: <BriefcaseIcon size={15} strokeWidth={2} /> },
  salary: { title: 'Ожидания', icon: <RubleIcon size={15} strokeWidth={2.4} /> },
  available_from: { title: 'Выход', icon: <ClockIcon size={15} strokeWidth={2.1} /> },
  schedule: { title: 'График', icon: <CalendarIcon size={15} strokeWidth={2} /> },
  location: { title: 'Город', icon: <PinIcon size={15} strokeWidth={2} /> },
  certificate: { title: 'Документ', icon: <DocumentIcon size={15} strokeWidth={2} /> },
}

/** Порог свайпа в пикселях: дальше — решение, ближе — карточка возвращается. */
const SWIPE_THRESHOLD = 90
const LEAVE_MS = 220

/**
 * E17 «Калибровка предпочтений» (P2, функция 25 UX-карты, раздел 66
 * тех-доки). Работодатель отмечает «подходит / не подходит» на 3–5
 * синтетических тестовых профилях (`GET /vacancies/{id}/calibration`),
 * backend пересчитывает веса желательных критериев
 * (`POST /vacancies/{id}/calibration`). Калибровку можно пропустить; после
 * неё — очередь кандидатов E07.
 */
export function CalibrationPage() {
  const vacancyId = Number(useParams().vacancyId)
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getCalibrationProfiles(vacancyId, signal), [vacancyId])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(-1)} />
  }
  return <Calibration vacancyId={vacancyId} profiles={state.data.profiles} />
}

function Calibration({ vacancyId, profiles }: { vacancyId: number; profiles: CalibrationProfile[] }) {
  const navigate = useNavigate()
  const [votes, setVotes] = useState<CalibrationVote[]>([])
  const [leaving, setLeaving] = useState<'left' | 'right' | null>(null)
  const [dragX, setDragX] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const drag = useRef<{ startX: number; pointerId: number } | null>(null)

  const total = profiles.length
  const index = Math.min(votes.length, total - 1)
  const profile = profiles[index]
  const queue = routes.employerVacancyCandidates(vacancyId)
  const busy = leaving !== null || submitting

  async function finish(allVotes: CalibrationVote[]) {
    setSubmitting(true)
    setError(null)
    try {
      await submitCalibration(vacancyId, allVotes)
      navigate(queue, { replace: true, state: { flash: 'Порядок кандидатов настроен по вашим ответам' } })
    } catch {
      setSubmitting(false)
      setError('Не удалось сохранить ответы. Попробуйте еще раз — они на месте.')
    }
  }

  function vote(fit: boolean) {
    if (busy || !profile) return
    setLeaving(fit ? 'right' : 'left')
    window.setTimeout(() => {
      const next = [...votes, { pattern_token: profile.pattern_token, fit }]
      setVotes(next)
      // Последняя карточка остаётся «улетевшей», пока сохраняются ответы.
      if (next.length >= total) {
        void finish(next)
        return
      }
      setLeaving(null)
      setDragX(0)
    }, LEAVE_MS)
  }

  function handleBack() {
    if (votes.length > 0 && !submitting) {
      setError(null)
      setLeaving(null)
      setDragX(0)
      setVotes(votes.slice(0, -1))
    } else {
      navigate(-1)
    }
  }

  function onPointerDown(event: ReactPointerEvent<HTMLElement>) {
    if (busy) return
    drag.current = { startX: event.clientX, pointerId: event.pointerId }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function onPointerMove(event: ReactPointerEvent<HTMLElement>) {
    if (drag.current?.pointerId !== event.pointerId) return
    setDragX(event.clientX - drag.current.startX)
  }

  function onPointerUp(event: ReactPointerEvent<HTMLElement>) {
    if (drag.current?.pointerId !== event.pointerId) return
    drag.current = null
    if (Math.abs(dragX) >= SWIPE_THRESHOLD) vote(dragX > 0)
    else setDragX(0)
  }

  const cardMotion =
    leaving === 'left'
      ? 'translateX(-130%) rotate(-14deg)'
      : leaving === 'right'
        ? 'translateX(130%) rotate(14deg)'
        : dragX !== 0
          ? `translateX(${dragX}px) rotate(${dragX / 22}deg)`
          : undefined

  return (
    <div className="p1Screen calibration">
      <div className="calibration__top">
        <BackButton variant="raised" onClick={handleBack} />
        {total > 0 ? <Progress index={index} total={total} /> : null}
      </div>

      <span className="calibration__eyebrow">Калибровка</span>
      <h1 className="p1Title calibration__title">
        Кто вам
        <br />
        ближе?
      </h1>
      <p className="calibration__subtitle">
        {total > 0 ? (
          <>
            {total} {total === 1 ? 'пример поможет' : total < 5 ? 'примера помогут' : 'примеров помогут'} настроить
            <br />
            порядок кандидатов
          </>
        ) : (
          'У вакансии нет желательных условий — порядок кандидатов настраивать не по чему'
        )}
      </p>

      {profile ? (
        <div className="calibration__stack">
          <SideCard side="left" photo={candidateB} />
          <SideCard side="right" photo={candidateC} />
          <div className="calibration__main">
            <article
              key={profile.pattern_token + index}
              className={`calibrationCard${profile.criteria.length > 3 ? ' calibrationCard--dense' : ''}${
                dragX !== 0 && !leaving ? ' calibrationCard--dragging' : ''
              }`}
              style={cardMotion ? { transform: cardMotion } : undefined}
              aria-label={`Тестовый профиль: кандидат ${LETTERS[index] ?? index + 1}`}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
            >
              <span className="calibrationCard__photo">
                <img src={PORTRAITS[index % PORTRAITS.length]} alt="" draggable={false} />
              </span>
              <span className="calibrationCard__chip">Тестовый профиль</span>
              <h2 className="calibrationCard__name">Кандидат {LETTERS[index] ?? index + 1}</h2>
              <ul className="calibrationCard__rows">
                {profile.criteria.map((criterion) => (
                  <CriterionRow key={criterion.type} criterion={criterion} />
                ))}
              </ul>
            </article>
          </div>
        </div>
      ) : (
        <div className="calibration__spacer" />
      )}

      {error ? (
        <p className="calibration__error" role="alert">
          {error}
        </p>
      ) : null}

      {profile ? (
        <>
          <div className="calibration__actions">
            <button type="button" className="calibration__no" disabled={busy} onClick={() => vote(false)}>
              Не подходит
            </button>
            <button type="button" className="calibration__yes" disabled={busy} onClick={() => vote(true)}>
              {submitting ? 'Сохраняем…' : 'Подходит'}
            </button>
          </div>
          {error && votes.length >= total ? (
            <button type="button" className="calibration__skip" onClick={() => void finish(votes)}>
              Повторить
            </button>
          ) : (
            <button type="button" className="calibration__skip" disabled={submitting} onClick={() => navigate(queue)}>
              Пропустить
            </button>
          )}
        </>
      ) : (
        <button type="button" className="calibration__no calibration__no--wide" onClick={() => navigate(queue)}>
          К кандидатам
        </button>
      )}
    </div>
  )
}

/** «1 из 3» и точки шагов; заполненная линия дотягивается до середины пути к следующей. */
function Progress({ index, total }: { index: number; total: number }) {
  const fill = total > 1 ? Math.min(1, (index + 0.5) / (total - 1)) : 1
  return (
    <div className="calibration__progress" aria-label={`Пример ${index + 1} из ${total}`}>
      <span className="calibration__progressText">
        {index + 1} из {total}
      </span>
      <span className="calibration__track" aria-hidden="true">
        <span className="calibration__trackFill" style={{ width: `${fill * 100}%` }} />
        {Array.from({ length: total }, (_, step) => (
          <i
            key={step}
            className={`calibration__dot${step <= index ? ' calibration__dot--done' : ''}`}
            style={{ left: total > 1 ? `${(step / (total - 1)) * 100}%` : '0%' }}
          />
        ))}
      </span>
    </div>
  )
}

function SideCard({ side, photo }: { side: 'left' | 'right'; photo: string }) {
  return (
    <span className={`calibrationSide calibrationSide--${side}`} aria-hidden="true">
      <span className="calibrationSide__photo">
        <img src={photo} alt="" draggable={false} />
      </span>
      <i className="calibrationSide__row" />
      <i className="calibrationSide__row" />
    </span>
  )
}

function CriterionRow({ criterion }: { criterion: CalibrationCriterion }) {
  const row = CRITERION_ROWS[criterion.type]
  return (
    <li className="calibrationCard__row">
      <span className="calibrationCard__rowIcon" aria-hidden="true">
        {row.icon}
      </span>
      <span className="calibrationCard__rowLabel">{row.title}</span>
      <span className="calibrationCard__rowValue">{criterionValue(criterion)}</span>
    </li>
  )
}

/**
 * `value_label` приходит строчными словами («ожидания в пределах 95000 ₽»):
 * заголовок строки уже говорит «Ожидания», поэтому повтор убирается, число
 * получает разряды, первая буква — заглавная.
 */
function criterionValue({ type, value_label }: CalibrationCriterion): string {
  let text = value_label.trim()
  if (type === 'salary') text = text.replace(/^ожидания\s+/i, '')
  if (type === 'experience') text = text.replace(/^опыт\s+/i, '')
  text = text.replace(/\d{4,}/g, (digits) => Number(digits).toLocaleString('ru-RU'))
  return text.charAt(0).toUpperCase() + text.slice(1)
}
