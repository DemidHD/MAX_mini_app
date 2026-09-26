import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import { getEmployerVacancies } from '@/api/hiring'
import type { Vacancy } from '@/api/hiring'
import { DRAFT_LIMIT } from '@/api/vacancies'
import artCalendar from '@/assets/art-calendar.webp'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { PlusIcon } from '@/components/icons'
import { VacancyCard } from '@/components/VacancyTile'
import { DeleteDraftDialog, DraftLimitDialog } from '@/features/vacancyCreate/DeleteDraftDialog'
import { useAsync } from '@/hooks/useAsync'
import { plural } from '@/lib/format'
import './VacanciesPage.css'

type Filter = 'all' | Vacancy['status']

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'Все' },
  { id: 'published', label: 'Опубликованы' },
  { id: 'draft', label: 'Черновики' },
  { id: 'closed', label: 'Закрыты' },
]

const EMPTY_TEXT: Record<Filter, string> = {
  all: 'Создайте первую вакансию — она появится здесь.',
  published: 'Опубликованных вакансий пока нет.',
  draft: 'Незаконченных черновиков нет.',
  closed: 'Закрытых вакансий нет.',
}

type Dialog = { kind: 'limit' } | { kind: 'delete'; vacancy: Vacancy } | null

/**
 * Раздел «Вакансии» нижнего меню работодателя: все его вакансии
 * (`GET /employer/vacancies`) с фильтром по статусу. Отдельного макета у
 * экрана нет — он собран из карточки E01 и оформления экранов P1.
 * Опубликованная вакансия ведёт к кандидатам, черновик — в форму, где его
 * можно продолжить; черновик можно удалить (`DELETE /vacancies/{id}`).
 */
export function VacanciesPage() {
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getEmployerVacancies(signal, 50), [])
  const [filter, setFilter] = useState<Filter>('all')
  const [dialog, setDialog] = useState<Dialog>(null)

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.employerHome)} />
  }

  const items = state.data.items
  const count = (status: Filter) =>
    status === 'all' ? items.length : items.filter((item) => item.status === status).length
  const visible = filter === 'all' ? items : items.filter((item) => item.status === filter)
  const drafts = count('draft')
  const published = count('published')
  const limitReached = drafts >= DRAFT_LIMIT

  function handleCreate() {
    if (limitReached) setDialog({ kind: 'limit' })
    else navigate(routes.employerVacancyAi, { state: { fresh: true } })
  }

  return (
    <div className="p1Screen vacanciesPage">
      <div className="vacanciesPage__head">
        <h1 className="p1Title vacanciesPage__title">Вакансии</h1>
        <button type="button" className="vacanciesPage__create" aria-label="Создать вакансию" onClick={handleCreate}>
          <PlusIcon size={24} strokeWidth={2.4} />
        </button>
      </div>
      <p className="p1Subtitle vacanciesPage__subtitle">
        {published} {plural(published, 'опубликована', 'опубликованы', 'опубликовано')}
        {drafts > 0 ? ` · черновиков ${drafts} из ${DRAFT_LIMIT}` : ''}
      </p>

      <div className="vacanciesPage__filters" role="tablist" aria-label="Статус вакансии">
        {FILTERS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={filter === id}
            className={`vacanciesPage__filter${filter === id ? ' vacanciesPage__filter--active' : ''}`}
            onClick={() => setFilter(id)}
          >
            {label} · {count(id)}
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <div className="p1Empty vacanciesPage__empty">
          <img className="p1Empty__art" src={artCalendar} alt="" aria-hidden="true" />
          <p className="p1Empty__title">Здесь пока пусто</p>
          <p className="p1Empty__text">{EMPTY_TEXT[filter]}</p>
          {filter === 'all' || filter === 'draft' ? (
            <button type="button" className="p1Button vacanciesPage__emptyAction" onClick={handleCreate}>
              Создать вакансию
            </button>
          ) : null}
        </div>
      ) : (
        <div className="vacanciesPage__list">
          {visible.map((vacancy) => (
            <VacancyCard key={vacancy.id} vacancy={vacancy} onDelete={() => setDialog({ kind: 'delete', vacancy })} />
          ))}
        </div>
      )}

      {published > 0 ? (
        <>
          <Link to={routes.employerCandidates} className="p1Link vacanciesPage__board">
            Открыть доску найма
          </Link>
          <Link to={routes.employerAnalytics} className="p1Link">
            Аналитика найма
          </Link>
        </>
      ) : null}

      {dialog?.kind === 'limit' ? <DraftLimitDialog limit={DRAFT_LIMIT} onClose={() => setDialog(null)} /> : null}
      {dialog?.kind === 'delete' ? (
        <DeleteDraftDialog
          vacancyId={dialog.vacancy.id}
          title={dialog.vacancy.title}
          onClose={() => setDialog(null)}
          onDeleted={() => {
            setDialog(null)
            reload()
          }}
        />
      ) : null}
    </div>
  )
}
