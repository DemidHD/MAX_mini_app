import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { getEmployerVacancies } from '@/api/hiring'
import { getVacancyAnalytics } from '@/api/p2'
import type { VacancyAnalytics } from '@/api/p2'
import artCalendar from '@/assets/art-calendar.webp'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { OptionSheet } from '@/components/OptionSheet'
import {
  BoltFilledIcon,
  CalendarIcon,
  ChevronDownIcon,
  CupIcon,
  FileListIcon,
  PeopleIcon,
} from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { vacancyOptions } from '@/lib/vacancyOptions'
import { plural } from '@/lib/format'
import './AnalyticsPage.css'

type Period = 7 | 30 | 90 | 0

const PERIODS: { id: Period; label: string }[] = [
  { id: 7, label: '7 дней' },
  { id: 30, label: '30 дней' },
  { id: 90, label: '90 дней' },
  { id: 0, label: 'Все время' },
]

/**
 * E18 «Аналитика работодателя» (P2, функция 33 UX-карты, раздел 69
 * тех-доки): время до первого интервью, отклики, прошедшие обязательные
 * условия, взаимный интерес и интервью по одной вакансии
 * (`GET /employer/vacancies/{id}/analytics`). Вакансия — `?vacancy=`, как на
 * доске найма; этап воронки открывает доску найма этой вакансии.
 */
export function AnalyticsPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedId = Number(searchParams.get('vacancy')) || null
  const [period, setPeriod] = useState<Period>(30)
  const [sheet, setSheet] = useState<'vacancy' | 'period' | null>(null)

  const { state, reload } = useAsync(
    async (signal) => {
      const page = await getEmployerVacancies(signal, 50)
      const vacancies = page.items.filter((item) => item.status !== 'draft')
      const vacancy = vacancies.find((item) => item.id === requestedId) ?? vacancies[0] ?? null
      if (!vacancy) return { vacancies, vacancy: null, analytics: null }
      const analytics = await getVacancyAnalytics(vacancy.id, periodStart(period), signal)
      return { vacancies, vacancy, analytics }
    },
    [requestedId, period],
  )

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.employerHome)} />
  }

  const { vacancies, vacancy, analytics } = state.data

  if (!vacancy || !analytics) {
    return (
      <div className="p1Screen analytics">
        <h1 className="p1Title analytics__title">
          Как идет
          <br />
          найм?
        </h1>
        <div className="p1Empty">
          <img className="p1Empty__art" src={artCalendar} alt="" aria-hidden="true" />
          <p className="p1Empty__title">Пока нечего считать</p>
          <p className="p1Empty__text">Опубликуйте вакансию — здесь появятся отклики, воронка и время до интервью.</p>
          <Link to={routes.employerVacancyAi} state={{ fresh: true }} className="p1Button">
            Создать вакансию
          </Link>
        </div>
      </div>
    )
  }

  const periodLabel = PERIODS.find(({ id }) => id === period)?.label ?? ''
  const board = `${routes.employerCandidates}?vacancy=${vacancy.id}`
  const enoughData = analytics.applications_total > 0

  return (
    <div className="p1Screen analytics">
      <button
        type="button"
        className="analytics__vacancy"
        disabled={vacancies.length < 2}
        aria-label={`Вакансия: ${vacancy.title}. Сменить`}
        onClick={() => setSheet('vacancy')}
      >
        <span className="analytics__vacancyIcon" aria-hidden="true">
          <CupIcon size={21} strokeWidth={2} />
        </span>
        <span className="analytics__vacancyTitle">{vacancy.title}</span>
        {vacancies.length > 1 ? (
          <span className="analytics__vacancyChevron" aria-hidden="true">
            <ChevronDownIcon size={17} strokeWidth={2.3} />
          </span>
        ) : null}
      </button>

      <div className="analytics__heading">
        <h1 className="p1Title analytics__title">
          Как идет
          <br />
          найм?
        </h1>
        <button type="button" className="analytics__period" onClick={() => setSheet('period')}>
          <CalendarIcon size={15} strokeWidth={2} />
          {periodLabel}
        </button>
      </div>

      <section className="analytics__hero">
        <p className="analytics__heroLabel">До первого интервью</p>
        <TimeToInterview seconds={analytics.time_to_first_interview_seconds} />
        <p className="analytics__heroNote">
          {analytics.time_to_first_interview_seconds === null ? (
            <>
              Интервью пока не назначено —
              <br />
              покажем, как только появится
            </>
          ) : (
            <>
              От создания вакансии
              <br />
              до первого собеседования
            </>
          )}
        </p>
        <span className="analytics__heroBadge" aria-hidden="true">
          <BoltFilledIcon size={30} />
        </span>
      </section>

      <div className="analytics__tiles">
        <StatTile
          icon={<PeopleIcon size={20} strokeWidth={1.9} />}
          value={analytics.applications_total}
          label={plural(analytics.applications_total, 'Отклик', 'Отклика', 'Откликов')}
        />
        <StatTile
          icon={<FileListIcon size={20} strokeWidth={1.9} />}
          value={analytics.passed_hard_filters}
          label={
            <>
              Прошли
              <br />
              условия
            </>
          }
        />
        <StatTile icon={<CalendarIcon size={20} strokeWidth={1.9} />} value={analytics.interviews_booked} label="Интервью" />
      </div>

      <h2 className="analytics__funnelTitle">Воронка</h2>
      <Funnel analytics={analytics} to={board} />

      <p className="analytics__caption">
        {enoughData ? `Данные по вакансии ${vacancy.title}` : 'Недостаточно данных: откликов за период пока нет'}
      </p>

      {sheet === 'vacancy' ? (
        <OptionSheet
          title="Вакансия"
          options={vacancyOptions(vacancies)}
          selectedId={vacancy.id}
          onSelect={(id) => {
            setSheet(null)
            setSearchParams(id === vacancies[0]?.id ? {} : { vacancy: String(id) }, { replace: true })
          }}
          onClose={() => setSheet(null)}
        />
      ) : null}
      {sheet === 'period' ? (
        <OptionSheet
          title="Период"
          options={PERIODS}
          selectedId={period}
          onSelect={(id) => {
            setSheet(null)
            setPeriod(id)
          }}
          onClose={() => setSheet(null)}
        />
      ) : null}
    </div>
  )
}

/** Начало периода; `0` — за все время, без фильтра по дате. */
function periodStart(days: Period): Date | null {
  if (days === 0) return null
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  start.setDate(start.getDate() - days + 1)
  return start
}

/** «2 дня» / «18 часов»; длинная подпись мельче, чтобы не наезжать на значок. */
function TimeToInterview({ seconds }: { seconds: number | null }) {
  let text = '—'
  if (seconds !== null) {
    const days = Math.round(seconds / 86_400)
    if (days >= 1) {
      text = `${days} ${plural(days, 'день', 'дня', 'дней')}`
    } else {
      const hours = Math.max(1, Math.round(seconds / 3_600))
      text = `${hours} ${plural(hours, 'час', 'часа', 'часов')}`
    }
  }
  const size = text.length <= 5 ? '' : text.length <= 7 ? ' analytics__heroValue--medium' : ' analytics__heroValue--small'
  return <p className={`analytics__heroValue${size}`}>{text}</p>
}

function StatTile({ icon, value, label }: { icon: ReactNode; value: number; label: ReactNode }) {
  return (
    <div className="analytics__tile">
      <span className="analytics__tileIcon" aria-hidden="true">
        {icon}
      </span>
      <span className="analytics__tileValue">{value}</span>
      <span className="analytics__tileLabel">{label}</span>
    </div>
  )
}

/**
 * Воронка по этапам. Ширина полосы растет как корень от доли самого
 * большого этапа (так в макете: малые этапы остаются читаемыми); подпись
 * всегда помещается — полоса не уже своего текста.
 */
function Funnel({ analytics, to }: { analytics: VacancyAnalytics; to: string }) {
  const stages = [
    { label: 'Отклики', value: analytics.applications_total },
    { label: 'Прошли', value: analytics.passed_hard_filters },
    { label: 'Взаимный интерес', value: analytics.mutual_interest },
    { label: 'Интервью', value: analytics.interviews_booked },
  ]
  const max = Math.max(1, stages[0].value, ...stages.map(({ value }) => value))
  return (
    <ol className="analytics__funnel">
      {stages.map((stage, index) => (
        <li key={stage.label}>
          <Link
            to={to}
            className={`analytics__stage analytics__stage--${index + 1}`}
            style={{ width: `${Math.max(36, (1.1 * Math.sqrt(stage.value / max) - 0.1) * 100)}%` }}
            aria-label={`${stage.label}: ${stage.value}. Открыть на доске найма`}
          >
            <span className="analytics__stageValue">{stage.value}</span>
            <span className="analytics__stageDot" aria-hidden="true">
              ·
            </span>
            <span className="analytics__stageLabel">{stage.label}</span>
          </Link>
        </li>
      ))}
    </ol>
  )
}
