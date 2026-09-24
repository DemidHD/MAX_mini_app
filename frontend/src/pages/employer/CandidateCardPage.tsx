import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { candidateLabel, decide } from '@/api/hiring'
import type { CriterionType, EmployerCandidate, Vacancy } from '@/api/hiring'
import { BackButton } from '@/components/BackButton'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import {
  BookmarkIcon,
  BriefcaseIcon,
  CheckIcon,
  ClockIcon,
  CloseIcon,
  CupIcon,
  MoreIcon,
  RubleIcon,
  SendIcon,
} from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { criterionLabel, formatAvailableFrom, formatExperience, formatMoney } from '@/lib/format'
import { loadApplicationView } from '@/pages/employer/applicationView'
import './CandidateCardPage.css'

const DECIDED_TEXT: Record<string, string> = {
  invited: 'Кандидат приглашен — ждем, когда он выберет время',
  rejected: 'Вы отклонили этого кандидата',
  mutual_interest: 'Есть взаимный интерес — кандидат выбирает время',
  interview_scheduled: 'Интервью назначено',
  interview_completed: 'Интервью прошло',
}

/**
 * E08 «Карточка кандидата»: решение без чтения резюме — рабочие факторы,
 * ответы первичного отбора и результат обязательных условий (раздел 34).
 * «В резерв» — P1 (раздел 20), поэтому в P0 кнопка видна, но неактивна.
 */
export function CandidateCardPage() {
  const params = useParams()
  const vacancyId = Number(params.vacancyId)
  const applicationId = Number(params.applicationId)
  const navigate = useNavigate()
  const { state, reload } = useAsync(
    (signal) => loadApplicationView(vacancyId, applicationId, signal, true),
    [vacancyId, applicationId],
  )
  const [rejecting, setRejecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(-1)} />
  }

  const { vacancy, candidate, items, queue, interviewId } = state.data
  const position = queue.indexOf(applicationId)
  const queuePath = routes.employerVacancyCandidates(vacancy.id)
  const decided = candidate.status !== 'passed'

  async function handleReject() {
    setRejecting(true)
    setError(null)
    try {
      await decide(applicationId, 'rejected')
      // После решения — следующий кандидат или возврат к очереди (UX-карта, раздел 9).
      const next = queue.slice(position + 1)[0] ?? queue.find((id) => id !== applicationId)
      navigate(next ? routes.employerApplication(vacancyId, next) : queuePath, { replace: true })
    } catch {
      setError('Не удалось отклонить. Попробуйте еще раз.')
    } finally {
      setRejecting(false)
    }
  }

  return (
    <div className="screen candidateCard">
      <div className="candidateCard__top">
        <BackButton variant="raised" onClick={() => navigate(queuePath)} />
        {position >= 0 && !decided ? (
          <span className="candidateCard__position">
            {position + 1} из {queue.length}
          </span>
        ) : null}
        <span className="candidateCard__topMore" aria-hidden="true">
          <MoreIcon size={22} />
        </span>
      </div>

      <article className="candidateCard__card">
        <div className="candidateCard__photo photoSlot photoSlot--dark">
          <div className="candidateCard__photoText">
            <h1 className="candidateCard__name">{candidateLabel(items, applicationId)}</h1>
            <span className="candidateCard__role">{candidate.desired_role ?? vacancy.title}</span>
          </div>
        </div>

        <div className="candidateCard__body">
          <MatchSummary candidate={candidate} />

          <h2 className="candidateCard__section">Почему подходит</h2>
          <ul className="candidateCard__reasons">
            {reasons(candidate, vacancy).map((reason) => (
              <li key={reason}>
                <span className="candidateCard__check">
                  <CheckIcon size={14} strokeWidth={3} />
                </span>
                {reason}
              </li>
            ))}
          </ul>

          <div className="candidateCard__stats">
            <div className="candidateCard__stat">
              <BriefcaseIcon size={24} />
              <span>
                <span className="candidateCard__statLabel">Опыт</span>
                <span className="candidateCard__statValue">{formatExperience(candidate.experience_months, true)}</span>
              </span>
            </div>
            <span className="candidateCard__statDivider" aria-hidden="true" />
            <div className="candidateCard__stat">
              <RubleIcon size={24} />
              <span>
                <span className="candidateCard__statLabel">Ожидания</span>
                <span className="candidateCard__statValue">
                  {candidate.salary ? formatMoney(candidate.salary) : '—'}
                </span>
              </span>
            </div>
          </div>

          {candidate.screening_answers.length > 0 ? (
            <>
              <h2 className="candidateCard__section candidateCard__section--small">Первичный отбор</h2>
              <ul className="candidateCard__answers">
                {candidate.screening_answers.map((answer, index) => (
                  <li key={answer.question_id}>
                    {index % 2 === 0 ? <CupIcon size={22} /> : <ClockIcon size={22} />}
                    <span className="candidateCard__question">{answer.question}</span>
                    <span className="candidateCard__answer">{answerLabel(answer.value)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      </article>

      <div className="screen__spacer" />

      {error ? <p className="screen__error">{error}</p> : null}

      {decided ? (
        <div className="candidateCard__decided">
          <p>{DECIDED_TEXT[candidate.status] ?? 'Решение уже принято'}</p>
          {interviewId !== null ? (
            <Link to={routes.employerInterview(vacancyId, interviewId)} className="screenButton screenButton--primary">
              Детали интервью
            </Link>
          ) : (
            <Link to={queuePath} className="screenButton screenButton--outlinePrimary">
              К списку кандидатов
            </Link>
          )}
        </div>
      ) : (
        <div className="candidateCard__actions">
          <button
            type="button"
            className="candidateCard__round"
            disabled={rejecting}
            onClick={() => void handleReject()}
          >
            <span className="candidateCard__roundIcon">
              <CloseIcon size={30} strokeWidth={2.2} />
            </span>
            Отклонить
          </button>
          <button
            type="button"
            className="candidateCard__round"
            disabled
            title="Резерв появится в следующей версии"
          >
            <span className="candidateCard__roundIcon">
              <BookmarkIcon size={26} strokeWidth={2.1} />
            </span>
            В резерв
          </button>
          <Link to={routes.employerApplicationInvite(vacancyId, applicationId)} className="candidateCard__invite">
            <SendIcon size={26} />
            Пригласить
          </Link>
        </div>
      )}
    </div>
  )
}

function MatchSummary({ candidate }: { candidate: EmployerCandidate }) {
  const required = candidate.hard_filters.filter((item) => item.required)
  const passed = required.filter((item) => item.passed === true).length
  return (
    <span className="candidateCard__match">
      <span className="candidateCard__matchIcon">
        <CheckIcon size={16} strokeWidth={3} />
      </span>
      {passed}/{required.length} обязательных
    </span>
  )
}

/** Выполненные обязательные условия человеческими словами (без P1-объяснимости). */
function reasons(candidate: EmployerCandidate, vacancy: Vacancy): string[] {
  const criterionByType = new Map<CriterionType, Vacancy['criteria'][number]>(
    vacancy.criteria.map((criterion) => [criterion.type, criterion]),
  )
  return candidate.hard_filters
    .filter((item) => item.passed === true)
    .map((item) => {
      if (item.type === 'available_from') {
        return formatAvailableFrom(candidate.available_from).replace(/^Выход/, 'Готов выйти')
      }
      if (item.type === 'location' && vacancy.location) return vacancy.location
      const criterion = criterionByType.get(item.type)
      return criterion ? criterionLabel(criterion) : item.type
    })
}

function answerLabel(value: string | number | boolean | null): string {
  if (value === true) return 'Да'
  if (value === false) return 'Нет'
  if (value === null) return '—'
  return String(value)
}
