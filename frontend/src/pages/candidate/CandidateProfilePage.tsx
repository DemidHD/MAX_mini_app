import { useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import {
  AccentMarks,
  BriefcaseIcon,
  CalendarIcon,
  ChevronRightIcon,
  ClockIcon,
  CoinsIcon,
  DocumentIcon,
  GraduationIcon,
  PinIcon,
} from '@/components/icons'
import { SCHEDULE_OPTIONS } from '@/features/vacancyCreate/draft'
import { useAsync } from '@/hooks/useAsync'
import { dayKey, formatExperience, formatReadyShort, formatSalaryRange } from '@/lib/format'
import { getCandidateProfile, updateCandidateProfile } from '@/api/hiring'
import type { CandidateProfile } from '@/api/hiring'
import { ProfileFieldSheet } from '@/pages/candidate/ProfileFieldSheet'
import type { ProfileField } from '@/pages/candidate/ProfileFieldSheet'
import artCalendar from '@/assets/art-calendar.webp'
import profileCity from '@/assets/profile-city.webp'
import profileRole from '@/assets/profile-role.webp'
import profileSchedule from '@/assets/profile-schedule.webp'
import './CandidateProfilePage.css'

/**
 * C01 «Профиль кандидата»: минимум данных для подбора вакансий (раздел 14
 * тех-доки; `GET/PATCH /candidate/profile`). Каждая карточка открывает
 * редактирование поля; «Загрузить резюме» — функция P2 (C11), поэтому в P0
 * видна, но неактивна.
 */
export function CandidateProfilePage() {
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getCandidateProfile(signal), [])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(-1)} />
  }
  return <ProfileForm initial={state.data ?? EMPTY_PROFILE} />
}

/** Нового кандидата профиль ещё не создан — `GET` отвечает 404. */
const EMPTY_PROFILE: CandidateProfile = {
  desired_role: '',
  city: null,
  salary: null,
  schedule: null,
  experience_months: null,
  available_from: null,
}

function ProfileForm({ initial }: { initial: CandidateProfile }) {
  const navigate = useNavigate()
  const [profile, setProfile] = useState(initial)
  const [editing, setEditing] = useState<ProfileField | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const update = (patch: Partial<CandidateProfile>) => {
    setProfile((previous) => ({ ...previous, ...patch }))
    setError(null)
  }

  async function handleSave() {
    if (!profile.desired_role.trim()) {
      setError('Укажите, какую работу вы ищете')
      setEditing('desired_role')
      return
    }
    setSaving(true)
    setError(null)
    try {
      // Только поля профиля: GET отдаёт ещё user_id и даты, их не отправляем.
      const { city, salary, schedule, experience_months, available_from } = profile
      await updateCandidateProfile({
        desired_role: profile.desired_role.trim(),
        city,
        salary,
        schedule,
        experience_months,
        available_from,
      })
      navigate(routes.candidateFeed)
    } catch (cause) {
      setError(
        cause instanceof ApiError && cause.status === 422
          ? 'Проверьте поля профиля: одно из значений не подходит.'
          : 'Не удалось сохранить профиль. Данные на месте — попробуйте еще раз.',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="screen profileSetup">
      <p className="screen__logo">
        <span>MAX</span> Найм
      </p>

      <div className="profileSetup__heading">
        <h1 className="screen__title profileSetup__title">
          Какую работу
          <br />
          вы ищете?
        </h1>
        <AccentMarks className="profileSetup__marks" />
        {/* Рукописная заметка со стрелкой — декор из макета C01. */}
        <span className="profileSetup__note" aria-hidden="true">
          Больше
          <br />
          возможностей
          <br />
          рядом
          <svg className="profileSetup__noteArrow" viewBox="0 0 24 24" fill="none">
            <path d="M18 3c1 7-3 12-11 14M7 17l1-5M7 17l5 1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </div>
      <p className="screen__subtitle profileSetup__subtitle">Настроим ленту под вас</p>

      <div className="profileSetup__grid">
        <FieldCard
          wide
          icon={<BriefcaseIcon size={24} />}
          label="Желаемая роль"
          value={profile.desired_role || 'Не указана'}
          valueClass="profileCard__value--large"
          art="profileCard__art--role"
          artSrc={profileRole}
          invalid={error !== null && !profile.desired_role.trim()}
          onClick={() => setEditing('desired_role')}
        />

        <FieldCard
          icon={<PinIcon size={24} />}
          label="Город"
          value={profile.city || 'Не указан'}
          art="profileCard__art--city"
          artSrc={profileCity}
          chevronTop
          onClick={() => setEditing('city')}
        />
        <FieldCard
          icon={<CoinsIcon size={24} />}
          label="Зарплата"
          value={profile.salary ? formatSalaryRange(profile.salary, null) : 'Не указана'}
          chevronTop
          onClick={() => setEditing('salary')}
        >
          <span className="profileCard__bars" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </span>
        </FieldCard>

        <FieldCard
          wide
          icon={<CalendarIcon size={24} />}
          label="График"
          value={
            profile.schedule ? <span className="profileCard__chip">{profile.schedule}</span> : 'Не указан'
          }
          art="profileCard__art--schedule"
          artSrc={profileSchedule}
          onClick={() => setEditing('schedule')}
        />

        <FieldCard
          icon={<GraduationIcon size={24} />}
          label="Опыт"
          value={profile.experience_months === null ? 'Не указан' : formatExperience(profile.experience_months)}
          chevronTop
          onClick={() => setEditing('experience_months')}
        >
          <svg className="profileCard__hills" viewBox="0 0 120 64" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="profileHillBack" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor="#8fb8ff" />
                <stop offset="1" stopColor="#cfe0ff" />
              </linearGradient>
              <linearGradient id="profileHillFront" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stopColor="#2f7bff" />
                <stop offset="1" stopColor="#0a5cf0" />
              </linearGradient>
            </defs>
            <path d="M0 64c14-22 28-30 44-30 10 0 16 4 26 4 20 0 28-30 50-38v64Z" fill="url(#profileHillBack)" />
            <path d="M34 64c10-24 24-40 38-40 14 0 30 24 48 32v8Z" fill="url(#profileHillFront)" />
          </svg>
        </FieldCard>
        <FieldCard
          icon={<ClockIcon size={24} />}
          label="Готов выйти"
          value={formatReadyShort(profile.available_from)}
          art="profileCard__art--ready"
          artSrc={artCalendar}
          chevronTop
          onClick={() => setEditing('available_from')}
        />
      </div>

      <button type="button" className="profileSetup__resume" disabled title="Импорт резюме появится в следующей версии">
        <span className="profileSetup__resumeIcon">
          <DocumentIcon size={24} />
        </span>
        <span className="profileSetup__resumeText">Загрузить резюме</span>
        <ChevronRightIcon size={22} />
      </button>

      <div className="screen__spacer" />

      {error ? <p className="screen__error">{error}</p> : null}
      <button type="button" className="screenButton screenButton--primary" disabled={saving} onClick={() => void handleSave()}>
        {saving ? 'Сохраняем…' : 'Сохранить'}
      </button>
      <p className="screen__note">Профиль можно изменить позже</p>

      {editing ? (
        <ProfileFieldSheet
          field={editing}
          profile={profile}
          scheduleOptions={[...SCHEDULE_OPTIONS]}
          todayKey={dayKey(new Date())}
          onChange={update}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </div>
  )
}

function FieldCard({
  icon,
  label,
  value,
  valueClass = '',
  art,
  artSrc,
  wide = false,
  chevronTop = false,
  invalid = false,
  onClick,
  children,
}: {
  icon: ReactNode
  label: string
  value: ReactNode
  valueClass?: string
  art?: string
  artSrc?: string
  wide?: boolean
  chevronTop?: boolean
  invalid?: boolean
  onClick: () => void
  children?: ReactNode
}) {
  return (
    <button
      type="button"
      className={`profileCard${wide ? ' profileCard--wide' : ''}${invalid ? ' profileCard--invalid' : ''}`}
      onClick={onClick}
    >
      <span className="profileCard__icon">{icon}</span>
      <span className="profileCard__text">
        <span className="profileCard__label">{label}</span>
        <span className={`profileCard__value ${valueClass}${isEmptyValue(value) ? ' profileCard__value--empty' : ''}`}>
          {value}
        </span>
      </span>
      {/* Иллюстрация из макета; у карточек без картинки остаётся пустое место. */}
      {art ? (
        <span className={`profileCard__art ${art}`} aria-hidden="true">
          {artSrc ? <img src={artSrc} alt="" /> : null}
        </span>
      ) : null}
      {children}
      <span className={`profileCard__chevron${chevronTop ? ' profileCard__chevron--top' : ''}`} aria-hidden="true">
        <ChevronRightIcon size={22} />
      </span>
    </button>
  )
}

/** Незаполненное поле показывается приглушённо, как подсказка. */
function isEmptyValue(value: ReactNode): boolean {
  return typeof value === 'string' && value.startsWith('Не указан')
}
