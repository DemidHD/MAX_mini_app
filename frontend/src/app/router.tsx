import { createBrowserRouter } from 'react-router-dom'

import { AppLayout } from '@/components/AppLayout'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { ProfilePage } from '@/pages/ProfilePage'
import { RoleSelectionPage } from '@/pages/RoleSelectionPage'
import { RootRedirect } from '@/pages/RootRedirect'
import { StubPage } from '@/pages/StubPage'
import { routes } from '@/app/routes'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: routes.root, element: <RootRedirect /> },
      { path: routes.roleSelection, element: <RoleSelectionPage /> },
      { path: routes.profile, element: <ProfilePage /> },
      {
        path: routes.candidateProfileSetup,
        element: <StubPage title="Профиль кандидата" />,
      },
      { path: routes.candidateFeed, element: <StubPage title="Лента вакансий" /> },
      {
        path: routes.candidateApplication(),
        element: <StubPage title="Статус отклика" />,
      },
      { path: routes.employerHome, element: <StubPage title="Кабинет работодателя" /> },
      {
        path: routes.employerVacancyCreate,
        element: <StubPage title="Создание вакансии" />,
      },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
