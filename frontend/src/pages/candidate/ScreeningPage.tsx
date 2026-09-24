import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import { getScreening, submitScreening } from '@/api/hiring'
import type { ScreeningAnswer, ScreeningQuestion } from '@/api/hiring'
import { BackButton } from '@/components/BackButton'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { CheckIcon, CloseIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import './ScreeningPage.css'

type AnswerValue = ScreeningAnswer['value']

/**
 * C05 «Вопрос первичного отбора»: один вопрос на экран, прогресс «1 из N».
 * Ответы копятся локально и уходят одним запросом (`POST
 * /applications/:id/screening`); при ошибке отправки они не теряются.
 */
export function ScreeningPage() {
  const applicationId = Number(useParams().applicationId)
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getScreening(applicationId, signal), [applicationId])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(-1)} />
  }
  if (!state.data.can_submit) {
    return <Navigate to={routes.candidateApplication(applicationId)} replace />
  }

  const questions = [...state.data.questions].sort((a, b) => a.sort_order - b.sort_order)
  if (questions.length === 0) return <Navigate to={routes.candidateScreeningStart(applicationId)} replace />
  return <ScreeningFlow applicationId={applicationId} questions={questions} />
}

function storageKey(applicationId: number) {
  return `max-hiring:screening:${applicationId}`
}

function loadAnswers(applicationId: number): Record<number, AnswerValue> {
  try {
    return JSON.parse(sessionStorage.getItem(storageKey(applicationId)) ?? '{}')
  } catch {
    return {}
  }
}

function ScreeningFlow({ applicationId, questions }: { applicationId: number; questions: ScreeningQuestion[] }) {
  const navigate = useNavigate()
  const [answers, setAnswers] = useState<Record<number, AnswerValue>>(() => loadAnswers(applicationId))
  const [index, setIndex] = useState(0)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    try {
      sessionStorage.setItem(storageKey(applicationId), JSON.stringify(answers))
    } catch {
      // Хранилище недоступно — ответы всё равно живут в состоянии экрана.
    }
  }, [answers, applicationId])

  const question = questions[index]
  const value = answers[question.id] ?? null
  const answered = value !== null && value !== ''
  const isLast = index === questions.length - 1

  function setValue(next: AnswerValue) {
    setAnswers((previous) => ({ ...previous, [question.id]: next }))
    setError(null)
  }

  async function handleNext() {
    if (!isLast) {
      setIndex(index + 1)
      return
    }
    setSending(true)
    setError(null)
    try {
      const result = await submitScreening(
        applicationId,
        questions
          .filter((item) => answers[item.id] !== undefined && answers[item.id] !== null && answers[item.id] !== '')
          .map((item) => ({ question_id: item.id, value: answers[item.id] })),
      )
      try {
        sessionStorage.removeItem(storageKey(applicationId))
      } catch {
        // Не критично.
      }
      // Какие условия не совпали, backend отдаёт только в ответе на отправку —
      // передаём их экрану результата (C06).
      navigate(routes.candidateApplication(applicationId), { replace: true, state: { screening: result } })
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'screening_already_completed') {
        navigate(routes.candidateApplication(applicationId), { replace: true })
        return
      }
      if (cause instanceof ApiError && cause.code === 'screening_answers_invalid') {
        const invalid = Array.isArray(cause.details) ? (cause.details as { question_id: number }[]) : []
        const first = questions.findIndex((item) => invalid.some((problem) => problem.question_id === item.id))
        if (first >= 0) setIndex(first)
        setError('Проверьте ответ на этот вопрос.')
        return
      }
      setError('Не удалось отправить ответы. Они сохранены — попробуйте еще раз.')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="screen screening">
      <div className="screening__header">
        <BackButton onClick={() => (index > 0 ? setIndex(index - 1) : navigate(-1))} />
        <span className="screening__headerTitle">Первичный отбор</span>
        <span className="screening__counter">
          {index + 1} из {questions.length}
        </span>
      </div>

      <div
        className="screening__progress"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={questions.length}
        aria-valuenow={index + 1}
      >
        <span style={{ width: `${((index + 1) / questions.length) * 100}%` }} />
      </div>

      <h1 className="screen__title screening__question">{question.question}</h1>
      <p className="screen__subtitle screening__kind">
        {question.required ? 'Обязательное условие' : 'Желательное условие'}
      </p>

      <div className="screening__answers" role="radiogroup" aria-label={question.question}>
        <AnswerInput question={question} value={value} onChange={setValue} />
      </div>

      <p className="screening__hint">Ответ можно изменить до завершения</p>

      <div className="screen__spacer" />

      {error ? <p className="screen__error">{error}</p> : null}
      <button
        type="button"
        className="screenButton screenButton--primary"
        disabled={(question.required && !answered) || sending}
        onClick={() => void handleNext()}
      >
        {sending ? 'Отправляем…' : isLast ? 'Отправить' : 'Далее'}
      </button>
    </div>
  )
}

function AnswerInput({
  question,
  value,
  onChange,
}: {
  question: ScreeningQuestion
  value: AnswerValue
  onChange: (value: AnswerValue) => void
}) {
  if (question.type === 'boolean') {
    return (
      <>
        <BigOption label="Да" selected={value === true} icon={<CheckIcon size={30} strokeWidth={2.6} />} onClick={() => onChange(true)} />
        <BigOption label="Нет" selected={value === false} icon={<CloseIcon size={30} strokeWidth={2.4} />} onClick={() => onChange(false)} />
      </>
    )
  }

  if (question.type === 'choice') {
    return (
      <>
        {(question.rules.options ?? []).map((option) => (
          <button
            key={option}
            type="button"
            className={`screening__choice${value === option ? ' screening__choice--selected' : ''}`}
            onClick={() => onChange(option)}
          >
            {option}
            {value === option ? <CheckIcon size={22} strokeWidth={2.6} /> : null}
          </button>
        ))}
      </>
    )
  }

  return (
    <input
      className="screening__input"
      inputMode={question.type === 'number' ? 'numeric' : 'text'}
      value={value === null ? '' : String(value)}
      min={question.rules.min}
      max={question.rules.max}
      maxLength={question.rules.max_length}
      placeholder={question.type === 'number' ? 'Введите число' : 'Ваш ответ'}
      onChange={(event) => {
        const raw = event.target.value
        onChange(question.type === 'number' ? (raw === '' ? null : Number(raw.replace(/\D/g, ''))) : raw)
      }}
    />
  )
}

function BigOption({
  label,
  selected,
  icon,
  onClick,
}: {
  label: string
  selected: boolean
  icon: ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      aria-label={label}
      className={`screening__option${selected ? ' screening__option--selected' : ''}`}
      onClick={onClick}
    >
      <span className="screening__optionLabel">{label}</span>
      <span className="screening__optionIcon">{icon}</span>
    </button>
  )
}

