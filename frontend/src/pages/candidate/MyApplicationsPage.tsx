import { useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import { getCandidateProfile, getMyApplications } from '@/api/hiring'
import type { ApplicationStatus, CandidateApplicationListItem } from '@/api/hiring'
import artEmpty from '@/assets/art-applications-empty.webp'
import { CoverImage } from '@/components/CoverImage'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { BookmarkIcon, CalendarIcon, CheckIcon, ClockIcon, CloseIcon, DocumentIcon, HeartIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { dayKey, formatDayMonth, formatTime } from '@/lib/format'
import '@/pages/candidate/ProfileFieldSheet.css'
import './MyApplicationsPage.css'

type Filter = 'active' | 'all'

/** Итоговые статусы: в «Активных» их не показываем, только во «Всех». */
const CLOSED_STATUSES: ApplicationStatus[] = ['hard_filter_failed', 'rejected', 'interview_completed']

type Tone = 'blue' | 'yellow' | 'gray' | 'red' | 'green'

interface StatusView {
  tone: Tone
  icon: ReactNode
  title: string
  /** Подпись под статусом; без неё — «Обновлено …». */
  caption?: string
  to: string
}

interface MenuAction {
  label: string
  to: string
}

/**
 * C12 «Мои отклики» (`GET /applications`): карточка на каждый отклик со
 * статусом и переходом туда, где кандидату есть что делать дальше. Статусы
 * меняет только backend (раздел 26 тех-доки) — экран их лишь показывает.
 */
export function MyApplicationsPage() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('active')
  const [menu, setMenu] = useState<{ title: string; actions: MenuAction[] } | null>(null)
  const { state, reload } = useAsync(async (signal) => {
    const [applications, profile] = await Promise.all([getMyApplications(signal), getCandidateProfile(signal)])
    return { items: applications.items, hasProfile: profile !== null }
  }, [])

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') return <ErrorScreen error={state.error} onRetry={reload} />

  const { items, hasProfile } = state.data
  const visible = filter === 'active' ? items.filter((item) => !CLOSED_STATUSES.includes(item.status)) : items

  return (
    <div className="myApps">
      <header className="myApps__head">
        <h1 className="myApps__title">Мои отклики</h1>
        <button
          type="button"
          className="myApps__more"
          aria-label="Меню"
          onClick={() =>
            setMenu({
              title: 'Мои отклики',
              actions: [
                { label: 'Найти вакансии', to: routes.candidateFeed },
                { label: 'Мой профиль', to: routes.candidateProfileSetup },
              ],
            })
          }
        >
          <Dots />
        </button>
      </header>

      <div className="myApps__tabs" role="tablist" aria-label="Отклики">
        {(
          [
            ['active', 'Активные'],
            ['all', 'Все'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={filter === id}
            className={`myApps__tab${filter === id ? ' myApps__tab--active' : ''}`}
            onClick={() => setFilter(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="myApps__empty">
          <img className="myApps__art" src={artEmpty} alt="" aria-hidden="true" />
          <h2 className="myApps__emptyTitle">Пока нет откликов</h2>
          <p className="myApps__emptyText">
            Найдите подходящую вакансию
            <br />и отправьте свой первый отклик
          </p>
          <button type="button" className="myApps__button" onClick={() => navigate(routes.candidateFeed)}>
            Найти работу
          </button>
          {hasProfile ? null : (
            <Link to={routes.candidateProfileSetup} className="myApps__hint">
              <InfoCircle />
              <span>
                Заполните профиль, чтобы получать
                <br />
                подходящие вакансии
              </span>
            </Link>
          )}
        </div>
      ) : visible.length === 0 ? (
        <div className="myApps__none">
          <p className="myApps__emptyText">Активных откликов нет — все уже завершены.</p>
          <button type="button" className="myApps__link" onClick={() => setFilter('all')}>
            Показать все
          </button>
        </div>
      ) : (
        <ul className="myApps__list">
          {visible.map((item) => (
            <li key={item.id}>
              <ApplicationCard
                item={item}
                onMenu={(actions) => setMenu({ title: item.vacancy_title, actions })}
              />
            </li>
          ))}
        </ul>
      )}

      {menu ? <ActionSheet title={menu.title} actions={menu.actions} onClose={() => setMenu(null)} /> : null}
    </div>
  )
}

function ApplicationCard({
  item,
  onMenu,
}: {
  item: CandidateApplicationListItem
  onMenu: (actions: MenuAction[]) => void
}) {
  const view = statusView(item)
  const details = routes.candidateVacancy(item.vacancy_id)
  return (
    <article className="appCard">
      <div className="appCard__photo photoSlot">
        <CoverImage url={item.image_url} />
      </div>
      <div className="appCard__body">
        <div className="appCard__head">
          <h2 className="appCard__title">{item.vacancy_title}</h2>
          <button
            type="button"
            className="appCard__more"
            aria-label="Действия с откликом"
            onClick={() =>
              onMenu([
                { label: 'Статус отклика', to: view.to },
                { label: 'Открыть вакансию', to: details },
              ])
            }
          >
            <Dots small />
          </button>
        </div>
        {item.company_name ? <span className="appCard__company">{item.company_name}</span> : null}

        <Link to={view.to} className={`appCard__status appCard__status--${view.tone}`}>
          <span className="appCard__statusIcon">{view.icon}</span>
          <span className="appCard__statusText">
            <span className="appCard__statusTitle">{view.title}</span>
            <span className="appCard__statusCaption">{view.caption ?? updatedLabel(item.updated_at)}</span>
          </span>
          <Chevron />
        </Link>

        <Link to={details} className="appCard__details">
          Посмотреть детали
          <Chevron />
        </Link>
      </div>
    </article>
  )
}

/** Статус отклика словами кандидата и куда ведёт нажатие на него. */
function statusView(item: CandidateApplicationListItem): StatusView {
  const toStatus = routes.candidateApplication(item.id)
  switch (item.status) {
    case 'created':
    case 'screening':
      return {
        tone: 'blue',
        icon: <DocumentIcon size={20} strokeWidth={2} />,
        title: 'Ответьте на вопросы',
        caption: 'Отклик ещё не отправлен',
        to: routes.candidateScreeningStart(item.id),
      }
    case 'passed':
    case 'under_review':
      return { tone: 'yellow', icon: <ClockIcon size={21} strokeWidth={2} />, title: 'Ожидает решения', to: toStatus }
    case 'reserved':
      return { tone: 'gray', icon: <BookmarkIcon size={21} strokeWidth={2} />, title: 'В резерве', to: toStatus }
    case 'invited':
    case 'mutual_interest':
      return {
        tone: 'blue',
        icon: <HeartIcon size={20} strokeWidth={2} />,
        title: 'Вас пригласили',
        caption: 'Выберите время',
        to: routes.candidateMatch(item.vacancy_id),
      }
    case 'interview_scheduled':
      return {
        tone: 'blue',
        icon: <CalendarIcon size={21} strokeWidth={2} />,
        title: 'Интервью',
        caption: item.interview_starts_at
          ? `${formatDayMonth(item.interview_starts_at)} · ${formatTime(item.interview_starts_at)}`
          : 'Время назначено',
        to: routes.candidateInterview(item.vacancy_id),
      }
    case 'interview_completed':
      return {
        tone: 'green',
        icon: <CheckIcon size={20} strokeWidth={2.4} />,
        title: 'Интервью прошло',
        to: routes.candidateInterview(item.vacancy_id),
      }
    case 'hard_filter_failed':
      return { tone: 'red', icon: <CloseIcon size={20} strokeWidth={2.2} />, title: 'Не подошли условия', to: toStatus }
    case 'rejected':
      return { tone: 'gray', icon: <CloseIcon size={20} strokeWidth={2.2} />, title: 'Отказ', to: toStatus }
  }
}

function updatedLabel(value: string): string {
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  const key = dayKey(value)
  if (key === dayKey(today)) return 'Обновлено сегодня'
  if (key === dayKey(yesterday)) return 'Обновлено вчера'
  return `Обновлено ${formatDayMonth(value)}`
}

/** Нижняя шторка с действиями меню «…». */
function ActionSheet({ title, actions, onClose }: { title: string; actions: MenuAction[]; onClose: () => void }) {
  const navigate = useNavigate()
  return (
    <div className="fieldSheet p1Sheet" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" className="fieldSheet__backdrop" aria-label="Закрыть" onClick={onClose} />
      <div className="fieldSheet__panel">
        <span className="fieldSheet__handle" aria-hidden="true" />
        <div className="fieldSheet__head">
          <h2 className="fieldSheet__title">{title}</h2>
          <button type="button" className="fieldSheet__close" aria-label="Закрыть" onClick={onClose}>
            <CloseIcon size={18} />
          </button>
        </div>
        <div className="fieldSheet__options">
          {actions.map((action) => (
            <button key={action.label} type="button" className="fieldSheet__option" onClick={() => navigate(action.to)}>
              {action.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function Dots({ small = false }: { small?: boolean }) {
  const r = small ? 1.4 : 1.75
  const step = small ? 5.5 : 6.2
  return (
    <svg width={step * 2 + r * 2} height={r * 2} viewBox={`0 0 ${step * 2 + r * 2} ${r * 2}`} aria-hidden="true">
      {[0, 1, 2].map((index) => (
        <circle key={index} cx={r + step * index} cy={r} r={r} fill="currentColor" />
      ))}
    </svg>
  )
}

function Chevron() {
  return (
    <svg className="appCard__chevron" width="8" height="12" viewBox="0 0 8 12" fill="none" aria-hidden="true">
      <path d="M2 1.8 6 6l-4 4.2" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function InfoCircle() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="9" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="10" cy="6" r="1.1" fill="currentColor" />
      <path d="M10 9v5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}
