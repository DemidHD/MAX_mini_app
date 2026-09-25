import type { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'

import { EmployerBottomNav } from '@/components/EmployerBottomNav'
import './EmployerLayout.css'

/**
 * Общий каркас кабинета работодателя: контент экрана + закреплённое снизу
 * меню разделов (Главная / Вакансии / Кандидаты / Резерв / Профиль).
 */
export function EmployerLayout({ children }: { children?: ReactNode }) {
  return (
    <div className="employerLayout">
      <div className="employerLayout__content">{children ?? <Outlet />}</div>
      <EmployerBottomNav />
    </div>
  )
}
