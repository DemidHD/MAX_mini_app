import { createBrowserRouter } from 'react-router-dom'
import type { RouteObject } from 'react-router-dom'

import { AppLayout } from '@/components/AppLayout'
import { CandidateLayout } from '@/components/CandidateLayout'
import { EmployerLayout } from '@/components/EmployerLayout'
import { EmployerHomePage } from '@/pages/EmployerHomePage'
import { ErrorRoutePage } from '@/pages/ErrorRoutePage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { ProfilePage } from '@/pages/ProfilePage'
import { RoleSelectionPage } from '@/pages/RoleSelectionPage'
import { RootRedirect } from '@/pages/RootRedirect'
import { StubPage } from '@/pages/StubPage'
import { VacancyBasicsPage } from '@/pages/VacancyBasicsPage'
import { VacancyCriteriaPage } from '@/pages/VacancyCriteriaPage'
import { VacancyPreviewPage } from '@/pages/VacancyPreviewPage'
import { VacancyPublishedPage } from '@/pages/VacancyPublishedPage'
import { ApplicationStatusPage } from '@/pages/candidate/ApplicationStatusPage'
import { CandidateProfilePage } from '@/pages/candidate/CandidateProfilePage'
import { InterviewScheduledPage } from '@/pages/candidate/InterviewScheduledPage'
import { MatchPage } from '@/pages/candidate/MatchPage'
import { ScreeningPage } from '@/pages/candidate/ScreeningPage'
import { ScreeningStartPage } from '@/pages/candidate/ScreeningStartPage'
import { SlotPickerPage } from '@/pages/candidate/SlotPickerPage'
import { VacancyDetailsPage } from '@/pages/candidate/VacancyDetailsPage'
import { VacancyFeedPage } from '@/pages/candidate/VacancyFeedPage'
import { DevScreensPage } from '@/pages/DevScreensPage'
import { CandidateCardPage } from '@/pages/employer/CandidateCardPage'
import { CandidatesQueuePage } from '@/pages/employer/CandidatesQueuePage'
import { InterviewDetailsPage } from '@/pages/employer/InterviewDetailsPage'
import { InterviewSlotsPage } from '@/pages/employer/InterviewSlotsPage'
import { InviteConfirmPage } from '@/pages/employer/InviteConfirmPage'
import { VacancyCreateLayout } from '@/features/vacancyCreate/VacancyCreateLayout'
import { routes } from '@/app/routes'

// Оглавление экранов с демо-данными — только для локальной разработки.
const devRoutes: RouteObject[] = import.meta.env.DEV ? [{ path: routes.devScreens, element: <DevScreensPage /> }] : []

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: routes.root, element: <RootRedirect /> },
      { path: routes.roleSelection, element: <RoleSelectionPage /> },
      { path: routes.profile, element: <ProfilePage /> },
      { path: routes.authError, element: <ErrorRoutePage /> },

      // Кандидат: C01 и полноэкранные шаги отклика — без нижнего меню.
      { path: routes.candidateProfileSetup, element: <CandidateProfilePage /> },
      {
        element: <CandidateLayout />,
        children: [
          { path: routes.candidateFeed, element: <VacancyFeedPage /> },
          { path: routes.candidateApplications, element: <StubPage title="Мои отклики" /> },
        ],
      },
      { path: routes.candidateVacancy(), element: <VacancyDetailsPage /> },
      { path: routes.candidateApplication(), element: <ApplicationStatusPage /> },
      { path: routes.candidateScreeningStart(), element: <ScreeningStartPage /> },
      { path: routes.candidateScreening(), element: <ScreeningPage /> },
      { path: routes.candidateMatch(), element: <MatchPage /> },
      { path: routes.candidateMatchSlots(), element: <SlotPickerPage /> },
      { path: routes.candidateInterview(), element: <InterviewScheduledPage /> },

      // Работодатель.
      {
        element: <EmployerLayout />,
        children: [
          { path: routes.employerHome, element: <EmployerHomePage /> },
          { path: routes.employerVacancyList, element: <StubPage title="Вакансии" /> },
          { path: routes.employerCandidates, element: <StubPage title="Кандидаты" /> },
          { path: routes.employerVacancyCandidates(), element: <CandidatesQueuePage /> },
        ],
      },
      {
        // Создание вакансии (E02-E05) — самостоятельный полноэкранный поток
        // без нижнего меню, как в референсе, поэтому не под EmployerLayout.
        element: <VacancyCreateLayout />,
        children: [
          { path: routes.employerVacancyCreate, element: <VacancyBasicsPage /> },
          { path: routes.employerVacancyCriteria, element: <VacancyCriteriaPage /> },
          { path: routes.employerVacancyPreview, element: <VacancyPreviewPage /> },
          { path: routes.employerVacancyPublished, element: <VacancyPublishedPage /> },
        ],
      },
      { path: routes.employerVacancySlots(), element: <InterviewSlotsPage /> },
      { path: routes.employerApplication(), element: <CandidateCardPage /> },
      { path: routes.employerApplicationInvite(), element: <InviteConfirmPage /> },
      { path: routes.employerInterview(), element: <InterviewDetailsPage /> },

      ...devRoutes,
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
