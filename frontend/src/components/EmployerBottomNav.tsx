import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'

import { routes } from '@/app/routes'
import { BookmarkFilledIcon, BookmarkIcon, PeopleFilledIcon } from '@/components/icons'
import './EmployerBottomNav.css'

interface NavItem {
  to: string
  label: string
  icon: () => ReactNode
  /** Залитая иконка активного пункта. */
  activeIcon?: () => ReactNode
  end: boolean
}

const HOME: NavItem = { to: routes.employerHome, label: 'Главная', icon: HomeIcon, end: true }
const VACANCIES: NavItem = { to: routes.employerVacancyList, label: 'Вакансии', icon: BriefcaseIcon, end: false }
const CANDIDATES: NavItem = {
  to: routes.employerCandidates,
  label: 'Кандидаты',
  icon: PeopleIcon,
  activeIcon: () => <PeopleFilledIcon size={26} />,
  end: false,
}
const RESERVE: NavItem = {
  to: routes.employerReserve,
  label: 'Резерв',
  icon: () => <BookmarkIcon size={24} strokeWidth={1.8} />,
  activeIcon: () => <BookmarkFilledIcon size={26} />,
  end: false,
}
const PROFILE: NavItem = { to: routes.profile, label: 'Профиль', icon: ProfileIcon, end: false }

const ITEMS: NavItem[] = [HOME, VACANCIES, CANDIDATES, RESERVE, PROFILE]

/**
 * Нижнее меню кабинета работодателя — одно на всех его экранах, с разделом
 * «Резерв» (функция 23). Подключается через `EmployerLayout`, а не
 * дублируется на каждой странице.
 */
export function EmployerBottomNav() {
  return (
    <nav className="employerNav" aria-label="Разделы кабинета">
      {ITEMS.map(({ to, label, icon: Icon, activeIcon: ActiveIcon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) => `employerNav__item${isActive ? ' employerNav__item--active' : ''}`}
        >
          {({ isActive }) => (
            <>
              <span className="employerNav__iconWrap">
                {isActive && ActiveIcon ? <ActiveIcon /> : <Icon />}
              </span>
              <span className="employerNav__label">{label}</span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

function HomeIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path
        d="M4 11.5 12 4l8 7.5M6 10v9a1 1 0 0 0 1 1h3v-5a2 2 0 0 1 2-2 2 2 0 0 1 2 2v5h3a1 1 0 0 0 1-1v-9"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function BriefcaseIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3.5" y="7.5" width="17" height="12" rx="2" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M8.5 7.5V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1.5M3.5 12.5h17"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}

function PeopleIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="9" cy="8.5" r="3" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5M15.5 6.5a3 3 0 0 1 0 5.9M18 13.6c1.9.5 3.5 2.1 3.5 4.4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}

function ProfileIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="10" r="2.7" stroke="currentColor" strokeWidth="1.8" />
      <path d="M6.5 18c1-2.2 3.1-3.3 5.5-3.3s4.5 1.1 5.5 3.3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  )
}
