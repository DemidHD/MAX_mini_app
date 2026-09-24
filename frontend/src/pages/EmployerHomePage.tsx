import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Avatar, Typography } from '@maxhub/max-ui'

import { routes } from '@/app/routes'
import { avatarUrl } from '@/api/users'
import { getEmployerVacancies } from '@/api/hiring'
import type { Page, Vacancy } from '@/api/hiring'
import type { User } from '@/api/types'
import { DRAFT_LIMIT } from '@/api/vacancies'
import { CoverImage } from '@/components/CoverImage'
import { TrashIcon } from '@/components/icons'
import { DeleteDraftDialog, DraftLimitDialog } from '@/features/vacancyCreate/DeleteDraftDialog'
import { useAsync } from '@/hooks/useAsync'
import type { AsyncState } from '@/hooks/useAsync'
import { formatSalaryRange, plural, scheduleLabel } from '@/lib/format'
import { useAuth } from '@/auth/useAuth'
import heroPhoto from '@/assets/employer-home-hero.webp'
import './EmployerHomePage.css'

/**
 * Главная работодателя (экран E01 в UX-карте, `current_step = employer_home`
 * в разделе 7 тех-доки). Список «Мои вакансии» — `GET /employer/vacancies`,
 * черновики в нём можно продолжить или удалить. Новых черновиков не больше
 * `DRAFT_LIMIT`: лимит проверяет backend, главная заранее объясняет его.
 */
export function EmployerHomePage() {
  const { state } = useAuth()
  if (state.status !== 'authenticated') {
    return null
  }
  return <EmployerHome user={state.user} />
}

type Dialog = { kind: 'limit' } | { kind: 'delete'; vacancy: Vacancy } | null

function EmployerHome({ user }: { user: User }) {
  const { state: vacancies, reload } = useAsync((signal) => getEmployerVacancies(signal, 50), [])
  const [dialog, setDialog] = useState<Dialog>(null)
  const draftsCount =
    vacancies.status === 'success' ? vacancies.data.items.filter((item) => item.status === 'draft').length : 0
  const limitReached = draftsCount >= DRAFT_LIMIT

  return (
    <div className="employerHome">
      <header className="employerHome__top">
        <div className="employerHome__greetingBlock">
          <Typography.Body className="employerHome__greeting">{greetingForNow()}</Typography.Body>
          <Typography.Display className="employerHome__name">{user.first_name}</Typography.Display>
        </div>

        <div className="employerHome__topActions">
          <Link to={routes.profile} className="employerHome__avatar" aria-label="Открыть профиль">
            <Avatar.Container size={48} form="circle">
              {user.has_avatar ? (
                <Avatar.Image src={avatarUrl(user.avatar_updated_at)} alt="" />
              ) : (
                <Avatar.Text>{user.first_name.slice(0, 1).toUpperCase()}</Avatar.Text>
              )}
            </Avatar.Container>
          </Link>

          {/* Уведомлений на backend ещё нет (P0 — только бот-сообщения, раздел
              46 тех-доки; экрана со списком уведомлений в API нет вовсе) —
              иконка декоративная, без обработчика и без выдуманного счётчика. */}
          <span className="employerHome__bell" aria-hidden="true">
            <BellIcon />
          </span>
        </div>
      </header>

      <section className="employerHero">
        <span className="employerHero__badge">Быстрый старт</span>

        <span className="employerHero__photoBox" aria-hidden="true">
          <img className="employerHero__photo" src={heroPhoto} alt="" />
        </span>

        <div className="employerHero__text">
          <Typography.Display className="employerHero__title">
            Кого ищем
            <br />
            сегодня?
          </Typography.Display>
          <Typography.Body className="employerHero__subtitle">
            Создайте вакансию
            <br />
            за пару минут
          </Typography.Body>

          {limitReached ? (
            <button type="button" className="employerHero__cta" onClick={() => setDialog({ kind: 'limit' })}>
              Создать вакансию
            </button>
          ) : (
            <Link to={routes.employerVacancyCreate} state={{ fresh: true }} className="employerHero__cta">
              Создать вакансию
            </Link>
          )}
        </div>
      </section>

      <section className="employerVacancies">
        <div className="employerVacancies__header">
          <Typography.Title className="employerVacancies__heading">Мои вакансии</Typography.Title>
          <Link to={routes.employerVacancyList} className="employerVacancies__all">
            Все
            <ChevronIcon />
          </Link>
        </div>

        {draftsCount > 0 ? (
          <Typography.Body
            className={`employerVacancies__drafts${limitReached ? ' employerVacancies__drafts--full' : ''}`}
          >
            Черновиков: {draftsCount} из {DRAFT_LIMIT}
          </Typography.Body>
        ) : null}

        <MyVacancies state={vacancies} reload={reload} onDelete={(vacancy) => setDialog({ kind: 'delete', vacancy })} />
      </section>

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

function greetingForNow(): string {
  const hour = new Date().getHours()
  if (hour < 5) return 'Доброй ночи'
  if (hour < 12) return 'Доброе утро'
  if (hour < 18) return 'Добрый день'
  return 'Добрый вечер'
}

function BellIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M6 10a6 6 0 1 1 12 0c0 4 1.5 5.5 1.5 5.5h-15S6 14 6 10Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M10 19a2 2 0 0 0 4 0" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}

function ChevronIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M6 3.5 10.5 8 6 12.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function MyVacancies({
  state,
  reload,
  onDelete,
}: {
  state: AsyncState<Page<Vacancy>>
  reload: () => void
  onDelete: (vacancy: Vacancy) => void
}) {
  if (state.status === 'loading') {
    return <div className="employerVacancies__skeleton" aria-label="Загрузка" />
  }
  if (state.status === 'error') {
    return (
      <div className="employerVacancies__empty">
        <Typography.Body className="employerVacancies__emptyTitle">Не удалось загрузить вакансии</Typography.Body>
        <button type="button" className="employerVacancies__retry" onClick={reload}>
          Повторить
        </button>
      </div>
    )
  }
  if (state.data.items.length === 0) {
    return (
      <div className="employerVacancies__empty">
        <Typography.Body className="employerVacancies__emptyTitle">Пока нет вакансий</Typography.Body>
        <Typography.Body className="employerVacancies__emptyText">Создайте первую — она появится здесь</Typography.Body>
      </div>
    )
  }
  return (
    <div className="employerVacancies__track">
      {state.data.items.map((vacancy) => (
        <VacancyCard key={vacancy.id} vacancy={vacancy} onDelete={() => onDelete(vacancy)} />
      ))}
    </div>
  )
}

const STATUS_LABELS: Record<Vacancy['status'], string> = {
  published: 'Опубликована',
  draft: 'Черновик',
  closed: 'Закрыта',
}

/**
 * Карточка вакансии в ленте «Мои вакансии» с фото вакансии. Опубликованная
 * ведёт к кандидатам, черновик — в форму создания.
 */
function VacancyCard({ vacancy, onDelete }: { vacancy: Vacancy; onDelete: () => void }) {
  const count = vacancy.applications_count ?? 0
  const isDraft = vacancy.status === 'draft'
  const meta = [vacancy.location, vacancy.schedule ? scheduleLabel(vacancy.schedule) : null].filter(Boolean).join(' · ')
  const to = isDraft ? routes.employerVacancyEdit(vacancy.id) : routes.employerVacancyCandidates(vacancy.id)

  return (
    <div className={`vacancyTile photoSlot photoSlot--dark photoSlot--shade${isDraft ? ' vacancyTile--draft' : ''}`}>
      <CoverImage url={vacancy.image_url} />
      {/* Ссылка растянута на всю карточку, кнопка удаления лежит поверх неё:
          вложить кнопку в <a> нельзя. */}
      <Link
        to={to}
        className="vacancyTile__link"
        aria-label={isDraft ? `Продолжить черновик «${vacancy.title}»` : `Кандидаты вакансии «${vacancy.title}»`}
      />
      {isDraft ? (
        <button type="button" className="vacancyTile__delete" aria-label="Удалить черновик" onClick={onDelete}>
          <TrashIcon size={18} />
        </button>
      ) : null}
      {vacancy.company_name ? <span className="vacancyTile__company">{vacancy.company_name}</span> : null}
      <span className="vacancyTile__title">{vacancy.title}</span>
      <span className="vacancyTile__salary">{formatSalaryRange(vacancy.salary_min, vacancy.salary_max)}</span>
      {meta ? <span className="vacancyTile__meta">{meta}</span> : null}
      <span className="vacancyTile__badges">
        <span className={`vacancyTile__status vacancyTile__status--${vacancy.status}`}>
          <i aria-hidden="true" />
          {STATUS_LABELS[vacancy.status]}
        </span>
        {count > 0 ? (
          <span className="vacancyTile__count">
            {count} {plural(count, 'отклик', 'отклика', 'откликов')}
          </span>
        ) : null}
        {isDraft ? <span className="vacancyTile__continue">Продолжить</span> : null}
      </span>
    </div>
  )
}
