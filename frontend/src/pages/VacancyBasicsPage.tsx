import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Typography } from '@maxhub/max-ui'
import type { ReactNode } from 'react'

import { routes } from '@/app/routes'
import { DRAFT_LIMIT, isDraftLimitError } from '@/api/vacancies'
import { DeleteDraftDialog, DraftLimitDialog } from '@/features/vacancyCreate/DeleteDraftDialog'
import { useVacancyDraft } from '@/features/vacancyCreate/useVacancyDraft'
import { VacancyStepHeader } from '@/features/vacancyCreate/VacancyStepHeader'
import {
  AVAILABLE_FROM_OPTIONS,
  COMPANY_NAME_MAX_LENGTH,
  DESCRIPTION_MAX_LENGTH,
  EXPERIENCE_OPTIONS,
  SCHEDULE_OPTIONS,
  isBasicsComplete,
} from '@/features/vacancyCreate/draft'
import decorPhoto from '@/assets/vacancy-basics-decor.webp'
import './VacancyBasicsPage.css'

/**
 * Шаг 1 создания вакансии — экран E02 «Кого вы ищете?» в UX-карте.
 * «Далее» сохраняет черновик на сервере (первый раз — создаёт его).
 */
export function VacancyBasicsPage() {
  const { draft, updateDraft, saveDraft, startNew } = useVacancyDraft()
  const navigate = useNavigate()
  const location = useLocation()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dialog, setDialog] = useState<'delete' | 'limit' | null>(null)

  // «Создать вакансию» на главной открывает форму с `fresh`: если в форме
  // был открыт серверный черновик, начинаем новую вакансию, а не правим его.
  // Несохранённый ввод без черновика оставляем — это та же новая вакансия.
  const fresh = (location.state as { fresh?: boolean } | null)?.fresh === true
  useEffect(() => {
    if (!fresh) return
    if (draft.vacancyId !== null) startNew()
    navigate(location.pathname, { replace: true, state: null })
  }, [fresh, draft.vacancyId, startNew, navigate, location.pathname])

  const canContinue = isBasicsComplete(draft)

  async function handleNext() {
    setSaving(true)
    setError(null)
    try {
      await saveDraft()
      navigate(routes.employerVacancyCriteria)
    } catch (cause) {
      if (draft.vacancyId === null && isDraftLimitError(cause)) {
        setDialog('limit')
      } else {
        setError('Не удалось сохранить черновик. Введённые данные на месте — попробуйте еще раз.')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="vacancyBasics">
      <VacancyStepHeader title="Новая вакансия" step={1} totalSteps={3} onBack={() => navigate(routes.employerHome)} />

      <div className="vacancyBasics__body">
        <img className="vacancyBasics__decor" src={decorPhoto} alt="" aria-hidden="true" />

        <Typography.Display className="vacancyBasics__heading">
          Кого вы
          <br />
          ищете?
        </Typography.Display>
        <Typography.Body className="vacancyBasics__subtitle">Основные условия</Typography.Body>

        <VacancyTextField
          label="Должность"
          value={draft.title}
          placeholder="Например, бариста"
          onChange={(value) => updateDraft({ title: value })}
        />

        <VacancyTextField
          label="Название заведения"
          value={draft.companyName}
          placeholder="Например, Кофейня Mokka"
          maxLength={COMPANY_NAME_MAX_LENGTH}
          onChange={(value) => updateDraft({ companyName: value })}
        />

        <div className="vacancyBasics__row">
          <VacancyTextField
            label="Зарплата от"
            value={draft.salaryMin}
            placeholder="0"
            type="money"
            onChange={(value) => updateDraft({ salaryMin: value })}
          />
          <VacancyTextField
            label="Зарплата до"
            value={draft.salaryMax}
            placeholder="0"
            type="money"
            onChange={(value) => updateDraft({ salaryMax: value })}
          />
        </div>

        <VacancyTextField
          label="Город / адрес"
          value={draft.location}
          placeholder="Например, Москва, м. Белорусская"
          onChange={(value) => updateDraft({ location: value })}
        />

        <div className="vacancyBasics__pickers">
          <PickerCard
            icon={<CalendarIcon />}
            label="График"
            value={draft.schedule}
            onChange={(value) => updateDraft({ schedule: value })}
            options={SCHEDULE_OPTIONS.map((value) => ({ value, label: value }))}
          />
          <PickerCard
            icon={<BriefcaseIcon />}
            label="Опыт"
            value={String(draft.experienceMonths)}
            onChange={(value) => updateDraft({ experienceMonths: Number(value) })}
            options={EXPERIENCE_OPTIONS.map((option) => ({ value: String(option.months), label: option.label }))}
          />
          <PickerCard
            icon={<ClockIcon />}
            label="Когда нужен выход"
            value={draft.availableFrom}
            onChange={(value) => updateDraft({ availableFrom: value as typeof draft.availableFrom })}
            options={AVAILABLE_FROM_OPTIONS.map((option) => ({ value: option.id, label: option.label }))}
          />
        </div>

        <VacancyTextArea
          label="Описание вакансии"
          value={draft.description}
          placeholder="Чем предстоит заниматься, что вы предлагаете"
          maxLength={DESCRIPTION_MAX_LENGTH}
          onChange={(value) => updateDraft({ description: value })}
        />

        <Typography.Body className="vacancyBasics__autosave">Черновик сохраняется автоматически</Typography.Body>

        {error ? <Typography.Body className="vacancyBasics__error">{error}</Typography.Body> : null}

        <button
          type="button"
          className="vacancyBasics__next"
          disabled={!canContinue || saving}
          onClick={() => void handleNext()}
        >
          {saving ? 'Сохраняем…' : 'Далее'}
        </button>

        {draft.vacancyId !== null ? (
          <button type="button" className="vacancyBasics__delete" disabled={saving} onClick={() => setDialog('delete')}>
            Удалить черновик
          </button>
        ) : null}
      </div>

      {dialog === 'delete' && draft.vacancyId !== null ? (
        <DeleteDraftDialog
          vacancyId={draft.vacancyId}
          title={draft.title}
          onClose={() => setDialog(null)}
          onDeleted={() => {
            startNew()
            navigate(routes.employerHome, { replace: true })
          }}
        />
      ) : null}
      {dialog === 'limit' ? <DraftLimitDialog limit={DRAFT_LIMIT} onClose={() => setDialog(null)} /> : null}
    </div>
  )
}

/** Многострочное поле в стиле остальных карточек формы. */
function VacancyTextArea({
  label,
  value,
  placeholder,
  maxLength,
  onChange,
}: {
  label: string
  value: string
  placeholder: string
  maxLength: number
  onChange: (value: string) => void
}) {
  return (
    <label className="vacancyField vacancyField--area">
      <span className="vacancyField__labelRow">
        <span className="vacancyField__label">{label}</span>
        <span className="vacancyField__counter">
          {value.length}/{maxLength}
        </span>
      </span>
      <textarea
        className="vacancyField__textarea"
        value={value}
        placeholder={placeholder}
        maxLength={maxLength}
        rows={3}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

function VacancyTextField({
  label,
  value,
  placeholder,
  type = 'text',
  maxLength,
  onChange,
}: {
  label: string
  value: string
  placeholder: string
  /** `money` — сумма в рублях: в поле «80 000», в черновике только цифры. */
  type?: 'text' | 'money'
  maxLength?: number
  onChange: (value: string) => void
}) {
  const money = type === 'money'
  const shown = money && value ? Number(value).toLocaleString('ru-RU') : value
  const input = (
    <input
      className={`vacancyField__input${money ? ' vacancyField__input--money' : ''}`}
      type="text"
      inputMode={money ? 'numeric' : undefined}
      value={shown}
      placeholder={placeholder}
      maxLength={maxLength}
      aria-label={label}
      onChange={(event) =>
        onChange(money ? event.target.value.replace(/\D/g, '').replace(/^0+(?=\d)/, '').slice(0, 9) : event.target.value)
      }
    />
  )

  return (
    <div className="vacancyField">
      <span className="vacancyField__label">{label}</span>
      <div className="vacancyField__row">
        {money ? (
          // Поле суммы по ширине числа (невидимая копия текста задаёт ширину) —
          // «₽» стоит сразу после суммы, как в макете.
          <span className="vacancyField__sizer" data-value={shown || placeholder}>
            {input}
          </span>
        ) : (
          input
        )}
        {money && value ? (
          <span className="vacancyField__suffix" aria-hidden="true">
            ₽
          </span>
        ) : null}
        {value ? (
          <button
            type="button"
            className="vacancyField__clear"
            aria-label={`Очистить поле «${label}»`}
            onClick={() => onChange('')}
          >
            <CloseIcon />
          </button>
        ) : null}
      </div>
    </div>
  )
}

function CloseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M2 2l8 8M10 2l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

function PickerCard({
  icon,
  label,
  value,
  options,
  onChange,
}: {
  icon: ReactNode
  label: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}) {
  const currentLabel = options.find((option) => option.value === value)?.label ?? value
  return (
    <label className="pickerCard">
      <span className="pickerCard__top">
        <span className="pickerCard__icon">{icon}</span>
        <span className="pickerCard__chevron" aria-hidden="true">
          <ChevronIcon />
        </span>
      </span>
      <span className="pickerCard__label">{label}</span>
      <span className="pickerCard__value">{currentLabel}</span>
      <select
        className="pickerCard__select"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label={label}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function CalendarIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3.5" y="5.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3.5 10h17M8 3.5v3M16 3.5v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function BriefcaseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3.5" y="7.5" width="17" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8.5 7.5V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M12 7.5V12l3 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function ChevronIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M6 3.5 10.5 8 6 12.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
