import { useNavigate } from 'react-router-dom'

import './VacancyStepHeader.css'

export function VacancyStepHeader({
  title,
  step,
  totalSteps,
  onBack,
}: {
  title: string
  step?: number
  totalSteps?: number
  onBack?: () => void
}) {
  const navigate = useNavigate()

  return (
    <div className="vacancyStepHeader">
      <button
        type="button"
        className="vacancyStepHeader__back"
        aria-label="Назад"
        onClick={() => (onBack ? onBack() : navigate(-1))}
      >
        <BackIcon />
      </button>
      <span className="vacancyStepHeader__title">{title}</span>
      {step && totalSteps ? (
        <span className="vacancyStepHeader__step">
          {step} из {totalSteps}
        </span>
      ) : (
        <span className="vacancyStepHeader__spacer" aria-hidden="true" />
      )}
    </div>
  )
}

function BackIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12.5 4.5 6 10l6.5 5.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
