import { Link } from 'react-router-dom'

import { routes } from '@/app/routes'
import { DEMO_EMPLOYER_VACANCY_ID } from '@/mocks/demoApi'

/**
 * Оглавление P0-экранов с демо-данными (`mocks/demoApi.ts`) для проверки
 * вёрстки без backend. Доступно только в dev-сборке (см. `router.tsx`).
 */
const SCREENS: { id: string; title: string; to: string }[] = [
  { id: 'G03', title: 'Общая ошибка', to: routes.authError },
  { id: 'E06', title: 'Интервалы интервью', to: routes.employerVacancySlots(DEMO_EMPLOYER_VACANCY_ID) },
  { id: 'E07', title: 'Очередь кандидатов', to: routes.employerVacancyCandidates(DEMO_EMPLOYER_VACANCY_ID) },
  { id: 'E08', title: 'Карточка кандидата', to: routes.employerApplication(21) },
  { id: 'E09', title: 'Подтверждение приглашения', to: routes.employerApplicationInvite(21) },
  { id: 'E10', title: 'Детали интервью', to: routes.employerInterview(5) },
  { id: 'C01', title: 'Профиль кандидата', to: routes.candidateProfileSetup },
  { id: 'C02', title: 'Лента вакансий', to: routes.candidateFeed },
  { id: 'C03', title: 'Детали вакансии', to: routes.candidateVacancy(12) },
  { id: 'C04–C05', title: 'Отклик и первичный отбор', to: routes.candidateVacancy(12) },
  { id: 'C06', title: 'Не прошел обязательное условие', to: routes.candidateApplication(8) },
  { id: 'C07', title: 'Отклик ожидает решения', to: routes.candidateApplication(7) },
  { id: 'M01', title: 'Взаимный интерес', to: routes.candidateMatch(3) },
  { id: 'C09–C10', title: 'Выбор интервала → интервью назначено', to: routes.candidateMatchSlots(3) },
]

export function DevScreensPage() {
  return (
    <div className="screen">
      <h1 className="screen__title" style={{ fontSize: 32 }}>
        Экраны P0
      </h1>
      <p className="screen__subtitle">Демо-данные, без backend. Только dev.</p>
      <ul style={{ listStyle: 'none', margin: '20px 0 0', padding: 0, display: 'grid', gap: 8 }}>
        {SCREENS.map((screen) => (
          <li key={screen.id}>
            <Link
              to={screen.to}
              style={{
                display: 'flex',
                gap: 12,
                padding: '14px 16px',
                borderRadius: 16,
                background: '#fff',
                boxShadow: 'var(--screen-card-shadow)',
                color: 'var(--screen-ink)',
                textDecoration: 'none',
              }}
            >
              <b style={{ minWidth: 64, color: 'var(--screen-primary)' }}>{screen.id}</b>
              {screen.title}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
