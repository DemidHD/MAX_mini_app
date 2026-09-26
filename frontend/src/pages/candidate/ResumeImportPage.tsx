import { useRef, useState } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import { ApiError } from '@/api/client'
import {
  RESUME_ACCEPT,
  RESUME_MAX_SIZE_BYTES,
  isProfileMissingError,
  parseResume,
  uploadResume,
} from '@/api/p2'
import type { ResumeParsedDraft } from '@/api/p2'
import { BackButton } from '@/components/BackButton'
import {
  BriefcaseIcon,
  ClockIcon,
  CoinsIcon,
  DocCheckIcon,
  GraduationIcon,
  ListIcon,
  PinIcon,
} from '@/components/icons'
import { formatExperience, formatMoney, formatReadyShort, scheduleLabel } from '@/lib/format'
import './ResumeImportPage.css'

type Phase =
  | { kind: 'idle' }
  | { kind: 'uploading'; fileName: string }
  | { kind: 'parsing'; fileName: string }
  | { kind: 'parsed'; fileName: string; draft: ResumeParsedDraft }
  | { kind: 'unparsed'; fileName: string }
  | { kind: 'profileMissing' }

interface DraftRow {
  key: keyof ResumeParsedDraft
  label: string
  icon: ReactNode
  value: string
}

/** Поля черновика в порядке карточки C11; пустое поле в резюме не нашлось. */
const FIELDS: { key: keyof ResumeParsedDraft; label: string; icon: ReactNode; format: (value: string | number) => string }[] = [
  { key: 'desired_role', label: 'Роль', icon: <BriefcaseIcon size={21} />, format: String },
  { key: 'experience_months', label: 'Опыт', icon: <GraduationIcon size={22} />, format: (value) => formatExperience(Number(value)) },
  { key: 'city', label: 'Город', icon: <PinIcon size={21} />, format: String },
  { key: 'schedule', label: 'График', icon: <ListIcon size={21} />, format: (value) => scheduleLabel(String(value)) },
  { key: 'salary', label: 'Зарплата', icon: <CoinsIcon size={21} />, format: formatMoney },
  { key: 'available_from', label: 'Выход', icon: <ClockIcon size={21} />, format: (value) => formatReadyShort(String(value)) },
]

function draftRows(draft: ResumeParsedDraft): DraftRow[] {
  return FIELDS.flatMap(({ key, label, icon, format }) => {
    const raw = draft[key]
    if (raw === null || raw === undefined || raw === '') return []
    return [{ key, label, icon, value: format(raw) }]
  })
}

/**
 * C11 «Импорт резюме» (P2, функция 29 UX-карты): PDF/DOCX → предложенные
 * поля профиля → обязательное подтверждение кандидатом. Файл загружается
 * (`PATCH /candidate/resume`) и разбирается (`POST /candidate/resume/parse`),
 * но черновик никогда не сохраняется как истина: «Подтвердить» переносит его
 * в форму профиля C01, где кандидат проверяет поля и сохраняет их сам.
 * Файл не обязателен — «Заполнить вручную» ведёт в ту же форму без черновика.
 */
export function ResumeImportPage() {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [error, setError] = useState<string | null>(null)

  const busy = phase.kind === 'uploading' || phase.kind === 'parsing'
  const rows = phase.kind === 'parsed' ? draftRows(phase.draft) : []
  const partial = phase.kind === 'parsed' && (!phase.draft.desired_role || rows.length < 3)

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // Сбрасываем значение, чтобы повторный выбор того же файла снова сработал.
    event.target.value = ''
    if (!file) return

    const validation = validateFile(file)
    if (validation) {
      setError(validation)
      return
    }
    setError(null)
    setPhase({ kind: 'uploading', fileName: file.name })
    try {
      await uploadResume(file)
      setPhase({ kind: 'parsing', fileName: file.name })
      const result = await parseResume()
      const found = draftRows(result.parsed).length > 0
      setPhase(
        result.ai_available && found
          ? { kind: 'parsed', fileName: file.name, draft: result.parsed }
          : { kind: 'unparsed', fileName: file.name },
      )
    } catch (cause) {
      if (isProfileMissingError(cause)) {
        setPhase({ kind: 'profileMissing' })
        return
      }
      setPhase({ kind: 'idle' })
      setError(uploadErrorText(cause))
    }
  }

  function handleConfirm() {
    if (phase.kind !== 'parsed') return
    navigate(routes.candidateProfileSetup, { state: { resumeDraft: phase.draft } })
  }

  const hasResult = phase.kind === 'parsed' || phase.kind === 'unparsed' || phase.kind === 'profileMissing'

  return (
    <div className="p1Screen resumeImport">
      <BackButton />

      <h1 className="p1Title resumeImport__title">
        Добавьте
        <br />
        резюме
      </h1>
      <p className="p1Subtitle resumeImport__subtitle">Мы предложим заполнить профиль</p>

      <section className={`resumeImport__upload${hasResult ? ' resumeImport__upload--withResult' : ''}`}>
        <DocumentArt />
        <p className="resumeImport__formats">PDF или DOCX</p>
        <p className="resumeImport__limit">
          {busy ? fileLabel(phase.fileName) : 'до 10 МБ'}
        </p>
        <button
          type="button"
          className="resumeImport__pick"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {phase.kind === 'uploading'
            ? 'Загружаем…'
            : phase.kind === 'parsing'
              ? 'Разбираем резюме…'
              : 'Выбрать файл'}
        </button>
        <input
          ref={inputRef}
          className="resumeImport__input"
          type="file"
          accept={RESUME_ACCEPT}
          tabIndex={-1}
          aria-hidden="true"
          onChange={(event) => void handleFile(event)}
        />
      </section>

      {phase.kind === 'parsed' ? (
        <section className="resumeImport__result" aria-live="polite">
          <div className="resumeImport__resultHead">
            <span className={`resumeImport__badge${partial ? ' resumeImport__badge--partial' : ''}`}>
              {partial ? 'Найдено частично' : 'Найдено'}
            </span>
            <span className="resumeImport__resultIcon" aria-hidden="true">
              <DocCheckIcon size={22} strokeWidth={1.7} />
            </span>
          </div>
          <dl className="resumeImport__rows">
            {rows.map((row) => (
              <div key={row.key} className="resumeImport__row">
                <span className="resumeImport__rowIcon" aria-hidden="true">
                  {row.icon}
                </span>
                <dt className="resumeImport__rowLabel">{row.label}</dt>
                <dd className="resumeImport__rowValue">{row.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      {phase.kind === 'unparsed' || phase.kind === 'profileMissing' ? (
        <section className="resumeImport__result resumeImport__result--message" aria-live="polite">
          <div className="resumeImport__resultHead">
            <span className="resumeImport__badge resumeImport__badge--error">
              {phase.kind === 'unparsed' ? 'Не распознано' : 'Нужен профиль'}
            </span>
            <span className="resumeImport__resultIcon" aria-hidden="true">
              <DocCheckIcon size={22} strokeWidth={1.7} />
            </span>
          </div>
          <p className="resumeImport__message">
            {phase.kind === 'unparsed'
              ? 'Не удалось извлечь данные из файла. Резюме сохранено — заполните профиль вручную.'
              : 'Резюме прикрепляется к профилю. Сначала заполните и сохраните профиль, затем загрузите файл.'}
          </p>
        </section>
      ) : null}

      <p className="resumeImport__note">
        {phase.kind === 'parsed' ? 'Проверьте данные перед сохранением' : 'Файл не обязателен — можно заполнить вручную'}
      </p>

      <div className="resumeImport__spacer" />

      {error ? <p className="p1Error">{error}</p> : null}
      <button type="button" className="p1Button resumeImport__confirm" disabled={phase.kind !== 'parsed'} onClick={handleConfirm}>
        Подтвердить
      </button>
      <Link to={routes.candidateProfileSetup} className="p1Link resumeImport__manual">
        Заполнить вручную
      </Link>
    </div>
  )
}

/** Проверка до загрузки — те же ограничения, что и на backend. */
function validateFile(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!name.endsWith('.pdf') && !name.endsWith('.docx')) {
    return 'Подойдет файл PDF или DOCX.'
  }
  if (file.size === 0) return 'Файл пустой — выберите другой.'
  if (file.size > RESUME_MAX_SIZE_BYTES) return 'Файл больше 10 МБ — выберите файл поменьше.'
  return null
}

function uploadErrorText(cause: unknown): string {
  if (cause instanceof ApiError && (cause.status === 413 || cause.status === 422)) {
    return 'Файл не подошел: нужен PDF или DOCX до 10 МБ.'
  }
  return 'Не удалось загрузить резюме. Попробуйте еще раз или заполните профиль вручную.'
}

/** Длинное имя файла сокращается посередине, чтобы расширение оставалось видно. */
function fileLabel(name: string): string {
  return name.length > 32 ? `${name.slice(0, 20)}…${name.slice(-9)}` : name
}

/** Белый лист с загнутым углом из макета C11 — рисуется SVG, не картинкой. */
function DocumentArt() {
  return (
    <svg className="resumeImport__art" viewBox="0 0 68 80" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="resumeDocSheet" x1="0" y1="0" x2="0.6" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#e9f0fc" />
        </linearGradient>
        <linearGradient id="resumeDocFold" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#d6e5fd" />
          <stop offset="1" stopColor="#9fc2fb" />
        </linearGradient>
      </defs>
      <path d="M10 0h35l23 23v47a10 10 0 0 1-10 10H10A10 10 0 0 1 0 70V10A10 10 0 0 1 10 0Z" fill="url(#resumeDocSheet)" />
      <path d="M45 0v14a9 9 0 0 0 9 9h14L45 0Z" fill="url(#resumeDocFold)" />
      <rect x="15.5" y="28.5" width="24" height="5.6" rx="2.8" fill="#a3c9fb" />
      <rect x="15.5" y="40" width="24" height="5.6" rx="2.8" fill="#a3c9fb" />
      <rect x="15.5" y="51.5" width="37.5" height="5.6" rx="2.8" fill="#a3c9fb" />
    </svg>
  )
}
