import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { candidateLabel, getEmployerVacancies, getSlots, getVacancyCandidates } from '@/api/hiring'
import type { ApplicationStatus, EmployerCandidate, Interview, Vacancy } from '@/api/hiring'
import artCalendar from '@/assets/art-calendar.webp'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { OptionSheet } from '@/components/OptionSheet'
import {
  CalendarIcon,
  ChatIcon,
  CheckIcon,
  CloseIcon,
  CupIcon,
  FileListIcon,
  MoreIcon,
  SearchIcon,
} from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { vacancyOptions } from '@/lib/vacancyOptions'
import { candidateThumbnail } from '@/lib/candidatePhotos'
import { dayKey, formatDayMonth, formatExperience, formatTime } from '@/lib/format'
import './HiringBoardPage.css'

type ColumnId = 'new' | 'mutual' | 'interview' | 'decision'

/**
 * Колонки доски (UX-карта, E15) поверх статусов отклика (раздел 17).
 * Отклонённые и резерв на доску не попадают: у резерва свой экран E16.
 */
const COLUMNS: { id: ColumnId; label: string; statuses: ApplicationStatus[]; badge: string }[] = [
  { id: 'new', label: 'Новые', statuses: ['passed', 'under_review'], badge: 'Новый' },
  { id: 'mutual', label: 'Взаимный интерес', statuses: ['invited', 'mutual_interest'], badge: 'Выбирает время' },
  { id: 'interview', label: 'Интервью', statuses: ['interview_scheduled'], badge: 'На интервью' },
  { id: 'decision', label: 'Решение', statuses: ['interview_completed'], badge: 'Ждет решения' },
]

const EMPTY_TEXT: Record<ColumnId, string> = {
  new: 'Новые отклики, прошедшие обязательные условия, появятся здесь.',
  mutual: 'Пригласите кандидата из «Новых» — он появится здесь, пока выбирает время.',
  interview: 'Когда кандидат выберет время, интервью появится здесь.',
  decision: 'После интервью кандидаты ждут вашего решения здесь.',
}

interface BoardRow {
  candidate: EmployerCandidate
  interview: Interview | null
  /** Когда: время интервью или время отклика — по нему строятся группы. */
  at: string
}

interface BoardData {
  vacancies: Vacancy[]
  vacancy: Vacancy | null
  candidates: EmployerCandidate[]
  interviews: Interview[]
}

/**
 * E15 «Доска найма» (P1, функция 24): контроль процесса без полноценной ATS.
 *
 * Отдельного `GET /employer/status-board` (раздел 62) backend пока не
 * отдаёт, поэтому доска собирается из того, что есть: кандидаты вакансии
 * (`GET /employer/vacancies/{id}/candidates`) и интервью из
 * `GET /vacancies/{id}/slots` — как и требует UX-карта («производится из
 * application/match/interview statuses»). Вакансия — `?vacancy=`.
 */
export function HiringBoardPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedId = Number(searchParams.get('vacancy')) || null
  const { state, reload } = useAsync(
    async (signal): Promise<BoardData> => {
      const page = await getEmployerVacancies(signal, 50)
      const vacancies = page.items.filter((item) => item.status !== 'draft')
      const vacancy = vacancies.find((item) => item.id === requestedId) ?? vacancies[0] ?? null
      if (!vacancy) return { vacancies, vacancy: null, candidates: [], interviews: [] }
      const [candidates, slots] = await Promise.all([
        getVacancyCandidates(vacancy.id, signal),
        getSlots(vacancy.id, signal),
      ])
      return { vacancies, vacancy, candidates: candidates.items, interviews: slots.interviews }
    },
    [requestedId],
  )
  const [column, setColumn] = useState<ColumnId | null>(null)
  const [search, setSearch] = useState<string | null>(null)
  const [picker, setPicker] = useState(false)

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.employerHome)} />
  }

  const { vacancies, vacancy, candidates, interviews } = state.data

  if (!vacancy) {
    return (
      <div className="p1Screen board">
        <h1 className="p1Title board__title">Доска найма</h1>
        <div className="p1Empty">
          <img className="p1Empty__art" src={artCalendar} alt="" aria-hidden="true" />
          <p className="p1Empty__title">Пока нет вакансий</p>
          <p className="p1Empty__text">Опубликуйте вакансию — отклики и интервью соберутся на этой доске.</p>
          <Link to={routes.employerVacancyAi} state={{ fresh: true }} className="p1Button">
            Создать вакансию
          </Link>
        </div>
      </div>
    )
  }

  const interviewByApplication = new Map(interviews.map((item) => [item.application_id, item]))
  const counts = Object.fromEntries(
    COLUMNS.map(({ id, statuses }) => [id, candidates.filter((item) => statuses.includes(item.status)).length]),
  ) as Record<ColumnId, number>
  // По умолчанию — первая непустая колонка слева направо.
  const active = column ?? COLUMNS.find(({ id }) => counts[id] > 0)?.id ?? 'new'
  const activeColumn = COLUMNS.find(({ id }) => id === active)!

  const query = search?.trim().toLowerCase() ?? ''
  const rows: BoardRow[] = candidates
    .filter((item) => activeColumn.statuses.includes(item.status))
    .filter((item) => {
      if (!query) return true
      const haystack = `${candidateLabel(candidates, item.application_id)} ${item.desired_role ?? ''}`.toLowerCase()
      return haystack.includes(query)
    })
    .map((item) => {
      const interview = interviewByApplication.get(item.application_id) ?? null
      return { candidate: item, interview, at: interview?.slot.starts_at ?? item.applied_at }
    })
    // Интервью — по ближайшему времени, отклики — от новых к старым.
    .sort((a, b) => (active === 'interview' ? a.at.localeCompare(b.at) : b.at.localeCompare(a.at)))

  const groups: { key: string; rows: BoardRow[] }[] = []
  for (const row of rows) {
    const key = dayKey(row.at)
    const last = groups.at(-1)
    if (last && last.key === key) last.rows.push(row)
    else groups.push({ key, rows: [row] })
  }

  function selectVacancy(id: number) {
    setPicker(false)
    setColumn(null)
    setSearchParams(id === vacancies[0]?.id ? {} : { vacancy: String(id) }, { replace: true })
  }

  return (
    <div className="p1Screen board">
      <div className="board__head">
        <button
          type="button"
          className="board__vacancy"
          disabled={vacancies.length < 2}
          aria-label={`Вакансия: ${vacancy.title}. Сменить`}
          onClick={() => setPicker(true)}
        >
          {vacancy.title}
        </button>
        <div className="board__tools">
          <button
            type="button"
            className={`p1IconButton${search !== null ? ' p1IconButton--active' : ''}`}
            aria-label={search !== null ? 'Закрыть поиск' : 'Поиск'}
            onClick={() => setSearch(search === null ? '' : null)}
          >
            {search !== null ? <CloseIcon size={20} strokeWidth={2.2} /> : <SearchIcon size={22} strokeWidth={2} />}
          </button>
          <button type="button" className="p1IconButton" aria-label="Выбрать вакансию" onClick={() => setPicker(true)}>
            <MoreIcon size={22} />
          </button>
        </div>
      </div>

      <h1 className="p1Title board__title">Доска найма</h1>

      {search !== null ? (
        <input
          className="board__search"
          type="search"
          autoFocus
          value={search}
          placeholder="Кандидат или должность"
          aria-label="Поиск по кандидатам"
          onChange={(event) => setSearch(event.target.value)}
        />
      ) : null}

      <div className="board__tabs" role="tablist" aria-label="Этапы найма">
        {COLUMNS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={active === id}
            className={`board__tab${active === id ? ' board__tab--active' : ''}`}
            onClick={() => setColumn(id)}
          >
            {label} · {counts[id]}
          </button>
        ))}
      </div>

      {groups.length === 0 ? (
        <div className="p1Empty board__empty">
          <img className="p1Empty__art" src={artCalendar} alt="" aria-hidden="true" />
          <p className="p1Empty__title">{query ? 'Никого не нашли' : 'Здесь пока пусто'}</p>
          <p className="p1Empty__text">{query ? 'Попробуйте другой запрос.' : EMPTY_TEXT[active]}</p>
          {active === 'new' && !query ? (
            <Link to={routes.employerVacancyCandidates(vacancy.id)} className="p1Link">
              Все кандидаты вакансии
            </Link>
          ) : null}
        </div>
      ) : (
        <div className="board__timeline">
          {groups.map((group, index) => (
            <section key={group.key} className="board__group">
              <h2 className="board__day">
                <span className={`board__dot${index === 0 ? ' board__dot--current' : ''}`} aria-hidden="true" />
                {dayTitle(group.key)}
              </h2>
              {group.rows.map((row) => (
                <BoardCard
                  key={row.candidate.application_id}
                  row={row}
                  label={candidateLabel(candidates, row.candidate.application_id)}
                  vacancy={vacancy}
                  column={activeColumn}
                />
              ))}
            </section>
          ))}
        </div>
      )}

      {picker ? (
        <OptionSheet
          title="Вакансия"
          options={vacancyOptions(vacancies)}
          selectedId={vacancy.id}
          onSelect={selectVacancy}
          onClose={() => setPicker(false)}
        />
      ) : null}
    </div>
  )
}

function BoardCard({
  row,
  label,
  vacancy,
  column,
}: {
  row: BoardRow
  label: string
  vacancy: Vacancy
  column: (typeof COLUMNS)[number]
}) {
  const navigate = useNavigate()
  const { candidate, interview } = row
  const cardPath = routes.employerApplication(vacancy.id, candidate.application_id)
  const required = candidate.hard_filters.filter((item) => item.required)
  const passed = required.filter((item) => item.passed === true).length

  let third: { label: string; icon: ReactNode; to: string } | null = null
  const calendar = <CalendarIcon size={24} strokeWidth={1.7} />
  if (interview) {
    third = { label: 'Изменить', icon: calendar, to: routes.employerInterview(vacancy.id, interview.id) }
  } else if (column.id === 'mutual') {
    third = { label: 'Слоты', icon: calendar, to: routes.employerVacancySlots(vacancy.id) }
  } else if (column.id === 'new') {
    third = { label: 'Решить', icon: <CheckIcon size={24} strokeWidth={2} />, to: cardPath }
  }

  return (
    <article className="boardCard">
      <div className="boardCard__main">
        <img className="boardCard__photo" src={candidateThumbnail(candidate.application_id)} alt="" aria-hidden="true" />
        <div className="boardCard__info">
          <div className="boardCard__nameRow">
            <h3 className="boardCard__name">{label}</h3>
            <button
              type="button"
              className="boardCard__more"
              aria-label={`Открыть карточку: ${label}`}
              onClick={() => navigate(cardPath)}
            >
              <MoreIcon size={22} />
            </button>
          </div>
          <div className="boardCard__chips">
            <span className="boardCard__chip boardCard__chip--day">{dayChip(row.at)}</span>
            <span className="boardCard__chip">{column.badge}</span>
          </div>
          {interview ? (
            <span className="boardCard__time">{formatTime(interview.slot.starts_at)}</span>
          ) : (
            <span className="boardCard__value">
              {required.length > 0
                ? `${passed}/${required.length} условий`
                : formatExperience(candidate.experience_months, true)}
            </span>
          )}
          <span className="boardCard__role">
            <CupIcon size={22} strokeWidth={1.8} />
            {candidate.desired_role ?? vacancy.title}
          </span>
        </div>
      </div>

      <div className="boardCard__actions">
        <Link to={cardPath} className="boardCard__action">
          <FileListIcon size={24} strokeWidth={1.7} />
          Резюме
        </Link>
        <button
          type="button"
          className="boardCard__action"
          disabled
          title="Чат с кандидатом появится после раскрытия контактов"
        >
          <ChatIcon size={24} strokeWidth={1.7} />
          Написать
        </button>
        {third ? (
          <Link to={third.to} className="boardCard__action">
            {third.icon}
            {third.label}
          </Link>
        ) : (
          <span className="boardCard__action" aria-hidden="true" />
        )}
      </div>
    </article>
  )
}

function daysFromToday(key: string): number {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((new Date(`${key}T00:00:00`).getTime() - today.getTime()) / 86_400_000)
}

/** «Сегодня, 12 октября» / «Завтра, 13 октября» / «10 октября». */
function dayTitle(key: string): string {
  const days = daysFromToday(key)
  const date = formatDayMonth(key)
  if (days === 0) return `Сегодня, ${date}`
  if (days === 1) return `Завтра, ${date}`
  if (days === -1) return `Вчера, ${date}`
  return date.charAt(0).toUpperCase() + date.slice(1)
}

function dayChip(at: string): string {
  const days = daysFromToday(dayKey(at))
  if (days === 0) return 'Сегодня'
  if (days === 1) return 'Завтра'
  if (days === -1) return 'Вчера'
  return formatDayMonth(at)
}
