import { CheckIcon } from '@/components/icons'
import './ProgressSteps.css'

export interface ProgressStep {
  label: string
  state: 'done' | 'current' | 'todo'
  /** Номер шага; без него в кружке точка. */
  number?: number
}

/** Три шага сценария кандидата (C04: отклик → вопросы → решение, C07: отклик → рассмотрение → интервью). */
export function ProgressSteps({ steps }: { steps: ProgressStep[] }) {
  return (
    <ol className="progressSteps">
      {steps.map((step, index) => (
        <li key={step.label} className={`progressSteps__step progressSteps__step--${step.state}`}>
          {index > 0 ? (
            <span
              className={`progressSteps__line${step.state !== 'todo' ? ' progressSteps__line--active' : ''}`}
              aria-hidden="true"
            />
          ) : null}
          <span className="progressSteps__circle" aria-hidden="true">
            {step.state === 'done' ? (
              <CheckIcon size={20} strokeWidth={2.8} />
            ) : step.number !== undefined ? (
              step.number
            ) : (
              <i className="progressSteps__dot" />
            )}
          </span>
          <span className="progressSteps__label">{step.label}</span>
        </li>
      ))}
    </ol>
  )
}
