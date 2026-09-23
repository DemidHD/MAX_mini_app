import { Outlet } from 'react-router-dom'

import { EmployerBottomNav } from '@/components/EmployerBottomNav'
import './EmployerLayout.css'

/**
 * Общий каркас кабинета работодателя: контент экрана + закреплённое снизу
 * меню разделов (Главная / Вакансии / Кандидаты / Профиль).
 */
export function EmployerLayout() {
  return (
    <div className="employerLayout">
      <div className="employerLayout__content">
        <Outlet />
      </div>
      <EmployerBottomNav />
    </div>
  )
}
