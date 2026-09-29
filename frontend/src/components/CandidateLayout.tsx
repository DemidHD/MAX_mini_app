import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

import { routes } from '@/app/routes'
import { SearchIcon, UserIcon } from '@/components/icons'
import './CandidateLayout.css'

interface NavItem {
  to: string
  label: string
  icon: (active: boolean) => ReactNode
}

const ITEMS: NavItem[] = [
  { to: routes.candidateFeed, label: 'Вакансии', icon: () => <SearchIcon size={26.5} strokeWidth={2} /> },
  { to: routes.candidateApplications, label: 'Отклики', icon: (active) => <ApplicationsIcon filled={active} /> },
  { to: routes.candidateProfileSetup, label: 'Профиль', icon: () => <UserIcon size={27.5} strokeWidth={1.8} /> },
]

/** Каркас разделов кандидата с нижним меню (экран C02 в UX-карте). */
export function CandidateLayout() {
  return (
    <div className="candidateLayout">
      <div className="candidateLayout__content">
        <Outlet />
      </div>
      <nav className="candidateNav" aria-label="Разделы кандидата">
        {ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end
            className={({ isActive }) => `candidateNav__item${isActive ? ' candidateNav__item--active' : ''}`}
          >
            {({ isActive }) => (
              <>
                <span className="candidateNav__icon">{icon(isActive)}</span>
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

/** «Отклики»: документ; в активном пункте — залитый, со светлыми строками. */
function ApplicationsIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="24.5" height="24.5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M5.3 1.8h8.2l6.8 6.8v11.6a2 2 0 0 1-2 2H5.3a2 2 0 0 1-2-2V3.8a2 2 0 0 1 2-2Z"
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth={filled ? 1.2 : 1.9}
        strokeLinejoin="round"
      />
      {filled ? <path d="M13.5 1.8v5a1.8 1.8 0 0 0 1.8 1.8h5" fill="#fff" fillOpacity="0.55" /> : null}
      <path
        d="M7.3 11h4.4M7.3 14.4h8.6M7.3 17.8h5.6"
        stroke={filled ? '#fff' : 'currentColor'}
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  )
}
