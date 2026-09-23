import { Link } from 'react-router-dom'
import { Avatar, Typography } from '@maxhub/max-ui'

import { routes } from '@/app/routes'
import { avatarUrl } from '@/api/users'
import { useAuth } from '@/auth/useAuth'
import heroPhoto from '@/assets/employer-home-hero.webp'
import './EmployerHomePage.css'

/**
 * Главная работодателя (экран E01 в UX-карте, `current_step = employer_home`
 * в разделе 7 тех-доки).
 *
 * У backend пока нет эндпоинта списка вакансий работодателя (в тех-доке,
 * раздел 27, есть только `POST /vacancies`, `GET /vacancies/:id` и
 * `GET /vacancies/feed` — `GET /employer/vacancies` из UX-карты ещё не
 * реализован). Блок «Мои вакансии» поэтому показывает честный пустой
 * экран, а не выдуманные карточки: у любого нового работодателя вакансий
 * действительно пока нет. Как только эндпоинт появится на backend, здесь
 * нужно будет заменить пустое состояние на реальный список.
 */
export function EmployerHomePage() {
  const { state } = useAuth()
  if (state.status !== 'authenticated') {
    return null
  }
  const { user } = state

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

          <Link to={routes.employerVacancyCreate} className="employerHero__cta">
            Создать вакансию
          </Link>
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

        <div className="employerVacancies__empty">
          <Typography.Body className="employerVacancies__emptyTitle">Пока нет вакансий</Typography.Body>
          <Typography.Body className="employerVacancies__emptyText">
            Создайте первую — она появится здесь
          </Typography.Body>
        </div>
      </section>
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
