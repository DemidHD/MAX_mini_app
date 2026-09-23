import { NavLink, Outlet } from 'react-router-dom'

import { routes } from '@/app/routes'
import { BriefcaseIcon, FileListIcon, UserIcon } from '@/components/icons'
import './CandidateLayout.css'

const ITEMS = [
  { to: routes.candidateFeed, label: 'Вакансии', icon: BriefcaseIcon },
  { to: routes.candidateApplications, label: 'Отклики', icon: FileListIcon },
  { to: routes.candidateProfileSetup, label: 'Профиль', icon: UserIcon },
] as const

/** Каркас разделов кандидата с нижним меню (экран C02 в UX-карте). */
export function CandidateLayout() {
  return (
    <div className="candidateLayout">
      <div className="candidateLayout__content">
        <Outlet />
      </div>
      <nav className="candidateNav" aria-label="Разделы кандидата">
        {ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `candidateNav__item${isActive ? ' candidateNav__item--active' : ''}`}
          >
            <Icon size={26} strokeWidth={1.9} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
