import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { Spinner, Typography } from '@maxhub/max-ui'

import { pathForStep } from '@/app/routes'
import { updateRole } from '@/api/users'
import { ApiError } from '@/api/client'
import { SplashScreen } from '@/components/SplashScreen'
import { useAuth } from '@/auth/AuthContext'
import type { UserRole } from '@/api/types'
import employerPhoto from '@/assets/role-employer.webp'
import candidatePhoto from '@/assets/role-candidate.webp'
import './RoleSelectionPage.css'

/**
 * Экран выбора роли (раздел 9 тех-доки, экран G02 в UX-карте). Роль нельзя
 * выбрать повторно — если backend уже вернул ненулевую роль, уводим на
 * актуальный шаг.
 */
export function RoleSelectionPage() {
  const { state, refresh } = useAuth()
  const [submitting, setSubmitting] = useState<UserRole | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (state.status !== 'authenticated') {
    // После отправки роли refresh() ненадолго переводит статус обратно в
    // 'loading' — показываем тот же экран G01, а не пустой экран.
    return <SplashScreen />
  }

  if (state.user.role !== null) {
    return <Navigate to={pathForStep(state.currentStep, state.applicationId)} replace />
  }

  async function handleSelect(role: UserRole) {
    setSubmitting(role)
    setError(null)
    try {
      await updateRole({ role })
      // current_step после выбора роли считает backend — переавторизуемся,
      // чтобы получить канонический следующий шаг (раздел 7).
      await refresh()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Не удалось сохранить роль')
      setSubmitting(null)
    }
  }

  const isBusy = submitting !== null

  return (
    <div className="roleScreen">
      <div className="roleScreen__brand">
        <span className="roleScreen__brandMax">MAX</span>
        <span className="roleScreen__brandName">Найм</span>
      </div>

      <div className="roleScreen__heading">
        <Typography.Display asChild>
          <span className="roleScreen__title">
            Что будем
            <br />
            делать?
          </span>
        </Typography.Display>
        <Typography.Body className="roleScreen__subtitle">Выберите свой сценарий</Typography.Body>
      </div>

      <div className="roleScreen__cards">
        <RoleCard
          variant="employer"
          title={['Найти', 'сотрудника']}
          description="Разместить вакансию и выбрать кандидата"
          photo={employerPhoto}
          busy={submitting === 'employer'}
          inactive={isBusy && submitting !== 'employer'}
          onSelect={() => void handleSelect('employer')}
        />
        <RoleCard
          variant="candidate"
          title={['Ищу', 'работу']}
          description="Смотреть вакансии и откликаться"
          photo={candidatePhoto}
          busy={submitting === 'candidate'}
          inactive={isBusy && submitting !== 'candidate'}
          onSelect={() => void handleSelect('candidate')}
        />
      </div>

      <Typography.Body className="roleScreen__footnote">Роль можно изменить позже</Typography.Body>
      {error ? <Typography.Body className="roleScreen__error">{error}</Typography.Body> : null}
    </div>
  )
}

function RoleCard({
  variant,
  title,
  description,
  photo,
  busy,
  inactive,
  onSelect,
}: {
  variant: 'employer' | 'candidate'
  title: [string, string]
  description: string
  photo: string
  busy: boolean
  inactive: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      className={`roleCard roleCard--${variant}`}
      data-busy={busy}
      data-inactive={inactive}
      disabled={busy || inactive}
      onClick={onSelect}
    >
      <span className="roleCard__photoBox" aria-hidden="true">
        <img className="roleCard__photo" src={photo} alt="" />
      </span>

      <span className="roleCard__arrow" aria-hidden="true">
        <ArrowIcon />
      </span>

      <span className="roleCard__text">
        <span className="roleCard__title">
          {title[0]}
          <br />
          {title[1]}
        </span>
        <span className="roleCard__desc">{description}</span>
      </span>

      {busy ? (
        <span className="roleCard__spinner">
          <Spinner size={24} appearance={variant === 'employer' ? 'contrast' : 'primary'} />
        </span>
      ) : null}
    </button>
  )
}

function ArrowIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M4 10h12M11 5l5 5-5 5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
