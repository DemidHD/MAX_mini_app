import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import { candidateLabel, getEmployerVacancies, getVacancyCandidates } from '@/api/hiring'
import type { EmployerCandidate, Vacancy } from '@/api/hiring'
import artResume from '@/assets/art-resume.webp'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { BookmarkFilledIcon, BookmarkIcon, CalendarIcon, CloseIcon, FolderIcon, SearchIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { candidatePortrait } from '@/lib/candidatePhotos'
import { formatAvailableFrom, formatDayMonth, formatExperience } from '@/lib/format'
import './ReservePage.css'

interface ReserveItem {
  candidate: EmployerCandidate
  vacancy: Vacancy
  label: string
}

const MARKS_KEY = 'max-hiring:reserve-marks'

function loadMarks(): number[] {
  try {
    const raw = JSON.parse(localStorage.getItem(MARKS_KEY) ?? '[]')
    return Array.isArray(raw) ? raw.filter((id): id is number => typeof id === 'number') : []
  } catch {
    return []
  }
}

function saveMarks(ids: number[]): void {
  try {
    localStorage.setItem(MARKS_KEY, JSON.stringify(ids))
  } catch {
    // Отметки — личное удобство на этом устройстве, без них экран работает.
  }
}

/**
 * E16 «Резерв кандидатов» (P1, функция 23): сильные кандидаты, которых не
 * пригласили сейчас. Отдельного списка резерва backend не отдаёт, поэтому
 * он собирается по вакансиям работодателя из кандидатов со статусом
 * `reserved` (раздел 20: `decision.action = reserved`).
 *
 * Закладка на фото — личная отметка «вернуться первым» на этом устройстве:
 * отмеченные идут в начале списка. На статус отклика она не влияет.
 */
export function ReservePage() {
  const navigate = useNavigate()
  const { state, reload } = useAsync(async (signal): Promise<ReserveItem[]> => {
    const page = await getEmployerVacancies(signal, 50)
    const vacancies = page.items.filter((item) => item.status !== 'draft')
    const lists = await Promise.all(vacancies.map((vacancy) => getVacancyCandidates(vacancy.id, signal)))
    return vacancies.flatMap((vacancy, index) =>
      lists[index].items
        .filter((candidate) => candidate.status === 'reserved')
        .map((candidate) => ({
          candidate,
          vacancy,
          label: candidateLabel(lists[index].items, candidate.application_id),
        })),
    )
  }, [])
  const [marks, setMarks] = useState<number[]>(loadMarks)
  const [search, setSearch] = useState<string | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const trackRef = useRef<HTMLDivElement>(null)

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.employerHome)} />
  }

  const query = search?.trim().toLowerCase() ?? ''
  const items = state.data
    .filter(({ label, vacancy }) => !query || `${label} ${vacancy.title}`.toLowerCase().includes(query))
    .sort((a, b) => {
      const isMarked = (entry: ReserveItem) => Number(marks.includes(entry.candidate.application_id))
      return isMarked(b) - isMarked(a) || b.candidate.applied_at.localeCompare(a.candidate.applied_at)
    })

  function toggleMark(applicationId: number) {
    const next = marks.includes(applicationId) ? marks.filter((id) => id !== applicationId) : [...marks, applicationId]
    setMarks(next)
    saveMarks(next)
  }

  function handleScroll() {
    const track = trackRef.current
    const first = track?.firstElementChild as HTMLElement | null
    if (!track || !first) return
    const step = first.offsetWidth + 8
    setActiveIndex(Math.min(items.length - 1, Math.round(track.scrollLeft / step)))
  }

  function scrollTo(index: number) {
    const track = trackRef.current
    const card = track?.children[index] as HTMLElement | undefined
    if (track && card) track.scrollTo({ left: card.offsetLeft - track.offsetLeft - 16, behavior: 'smooth' })
  }

  return (
    <div className="p1Screen reserve">
      <div className="reserve__head">
        <button
          type="button"
          className={`p1IconButton${search !== null ? ' p1IconButton--active' : ''}`}
          aria-label={search !== null ? 'Закрыть поиск' : 'Поиск'}
          onClick={() => setSearch(search === null ? '' : null)}
        >
          {search !== null ? <CloseIcon size={20} strokeWidth={2.2} /> : <SearchIcon size={22} strokeWidth={2} />}
        </button>
      </div>

      <h1 className="p1Title reserve__title">Резерв</h1>
      <p className="p1Subtitle reserve__subtitle">Кандидаты, к которым можно вернуться</p>

      {search !== null ? (
        <input
          className="reserve__search"
          type="search"
          autoFocus
          value={search}
          placeholder="Кандидат или вакансия"
          aria-label="Поиск по резерву"
          onChange={(event) => {
            setSearch(event.target.value)
            setActiveIndex(0)
          }}
        />
      ) : null}

      {items.length === 0 ? (
        <div className="p1Empty reserve__empty">
          <img className="p1Empty__art" src={artResume} alt="" aria-hidden="true" />
          <p className="p1Empty__title">{query ? 'Никого не нашли' : 'Резерв пока пуст'}</p>
          <p className="p1Empty__text">
            {query
              ? 'Попробуйте другой запрос.'
              : 'На карточке кандидата нажмите «В резерв» — сильные кандидаты не потеряются.'}
          </p>
          {query ? null : (
            <Link to={routes.employerCandidates} className="p1Link">
              К доске найма
            </Link>
          )}
        </div>
      ) : (
        <>
          <div className="reserve__track" ref={trackRef} onScroll={handleScroll}>
            {items.map((item) => (
              <ReserveCard
                key={item.candidate.application_id}
                item={item}
                marked={marks.includes(item.candidate.application_id)}
                onToggleMark={() => toggleMark(item.candidate.application_id)}
              />
            ))}
          </div>

          {items.length > 1 ? (
            <div className="reserve__dots" role="tablist" aria-label="Кандидаты резерва">
              {items.map((item, index) => (
                <button
                  key={item.candidate.application_id}
                  type="button"
                  role="tab"
                  aria-selected={index === activeIndex}
                  aria-label={item.label}
                  className={`reserve__dot${index === activeIndex ? ' reserve__dot--active' : ''}`}
                  onClick={() => scrollTo(index)}
                />
              ))}
            </div>
          ) : null}
        </>
      )}

      <p className="reserve__banner">
        <FolderIcon size={24} strokeWidth={1.6} />
        При новой вакансии резерв можно проверить первым
      </p>
    </div>
  )
}

function ReserveCard({
  item,
  marked,
  onToggleMark,
}: {
  item: ReserveItem
  marked: boolean
  onToggleMark: () => void
}) {
  const { candidate, vacancy, label } = item
  const tag = reserveTag(candidate)

  return (
    <article className="reserveCard">
      <div className="reserveCard__photo">
        <img src={candidatePortrait(candidate.application_id)} alt="" aria-hidden="true" />
        <button
          type="button"
          className={`reserveCard__mark${marked ? ' reserveCard__mark--on' : ''}`}
          aria-pressed={marked}
          aria-label={marked ? `Снять отметку: ${label}` : `Отметить: ${label}`}
          onClick={onToggleMark}
        >
          {marked ? <BookmarkFilledIcon size={24} /> : <BookmarkIcon size={24} strokeWidth={1.9} />}
        </button>
      </div>

      <div className="reserveCard__body">
        <h2 className="reserveCard__name">{label}</h2>
        <span className="reserveCard__role">{vacancy.title}</span>
        <span className="reserveCard__fact">
          <CalendarIcon size={18} strokeWidth={1.7} />
          {formatExperience(candidate.experience_months)}
        </span>
        <span className={`reserveCard__tag reserveCard__tag--${tag.tone}`}>{tag.text}</span>
        <span className="reserveCard__date">Отклик {formatDayMonth(candidate.applied_at)}</span>
        <Link to={routes.employerApplication(vacancy.id, candidate.application_id)} className="reserveCard__open">
          Открыть
        </Link>
      </div>
    </article>
  )
}

/**
 * Короткая метка карточки из объяснимости подбора (раздел 64) — только
 * объективные факторы (раздел 31): опыт против требования, совпавший
 * график или локация, иначе — срок выхода.
 */
function reserveTag(candidate: EmployerCandidate): { text: string; tone: 'blue' | 'green' | 'gray' } {
  const { candidate: months = null, required = null } = candidate.explanation?.experience ?? {}
  // На год и больше опытнее требования вакансии.
  if (months !== null && required !== null && months >= required + 12) {
    return { text: 'Сильный опыт', tone: 'blue' }
  }
  const matched = candidate.explanation?.matched ?? []
  if (matched.includes('schedule')) return { text: 'Подходит график', tone: 'green' }
  if (matched.includes('location')) return { text: 'Подходит локация', tone: 'green' }
  return { text: formatAvailableFrom(candidate.available_from), tone: 'gray' }
}
