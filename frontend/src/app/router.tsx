import { createBrowserRouter } from 'react-router-dom'

import { AppLayout } from '@/components/AppLayout'
import { CandidateLayout } from '@/components/CandidateLayout'
import { EmployerLayout } from '@/components/EmployerLayout'
import { EmployerHomePage } from '@/pages/EmployerHomePage'
import { ErrorRoutePage } from '@/pages/ErrorRoutePage'
import { NotFoundPage } from '@/pages/NotFoundPage'
import { ProfilePage } from '@/pages/ProfilePage'
import { RoleSelectionPage } from '@/pages/RoleSelectionPage'
import { RootRedirect } from '@/pages/RootRedirect'
import { VacancyAiCheckPage } from '@/pages/VacancyAiCheckPage'
import { VacancyAiTextPage } from '@/pages/VacancyAiTextPage'
import { VacancyBasicsPage } from '@/pages/VacancyBasicsPage'
import { VacancyCriteriaPage } from '@/pages/VacancyCriteriaPage'
import { VacancyPreviewPage } from '@/pages/VacancyPreviewPage'
import { VacancyPublicPage } from '@/pages/VacancyPublicPage'
import { VacancyPublishedPage } from '@/pages/VacancyPublishedPage'
import { VacancyVoicePage } from '@/pages/VacancyVoicePage'
import { WelcomePage } from '@/pages/WelcomePage'
import { ApplicationStatusPage } from '@/pages/candidate/ApplicationStatusPage'
import { CandidateProfilePage } from '@/pages/candidate/CandidateProfilePage'
import { InterviewScheduledPage } from '@/pages/candidate/InterviewScheduledPage'
import { MatchPage } from '@/pages/candidate/MatchPage'
import { MyApplicationsPage } from '@/pages/candidate/MyApplicationsPage'
import { ResumeImportPage } from '@/pages/candidate/ResumeImportPage'
import { ScreeningPage } from '@/pages/candidate/ScreeningPage'
import { ScreeningStartPage } from '@/pages/candidate/ScreeningStartPage'
import { SlotPickerPage } from '@/pages/candidate/SlotPickerPage'
import { VacancyDetailsPage } from '@/pages/candidate/VacancyDetailsPage'
import { VacancyFeedPage } from '@/pages/candidate/VacancyFeedPage'
import { AnalyticsPage } from '@/pages/employer/AnalyticsPage'
import { CalibrationPage } from '@/pages/employer/CalibrationPage'
import { CandidateCardPage } from '@/pages/employer/CandidateCardPage'
import { CandidatesQueuePage } from '@/pages/employer/CandidatesQueuePage'
import { HiringBoardPage } from '@/pages/employer/HiringBoardPage'
import { InterviewDetailsPage } from '@/pages/employer/InterviewDetailsPage'
import { InterviewSlotsPage } from '@/pages/employer/InterviewSlotsPage'
import { InviteConfirmPage } from '@/pages/employer/InviteConfirmPage'
import { ReferralPage } from '@/pages/employer/ReferralPage'
import { RejectReasonPage } from '@/pages/employer/RejectReasonPage'
import { ReservePage } from '@/pages/employer/ReservePage'
import { VacanciesPage } from '@/pages/employer/VacanciesPage'
import { EditDraftPage } from '@/features/vacancyCreate/EditDraftPage'
import { VacancyCreateLayout } from '@/features/vacancyCreate/VacancyCreateLayout'
import { routes } from '@/app/routes'

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: routes.root, element: <RootRedirect /> },
      { path: routes.welcome, element: <WelcomePage /> },
      { path: routes.roleSelection, element: <RoleSelectionPage /> },
      { path: routes.profile, element: <ProfilePage /> },
      { path: routes.authError, element: <ErrorRoutePage /> },

      // Кандидат: C01 и полноэкранные шаги отклика — без нижнего меню.
      { path: routes.candidateProfileSetup, element: <CandidateProfilePage /> },
      // P2: импорт резюме (C11) — полноэкранный шаг перед C01.
      { path: routes.candidateResumeImport, element: <ResumeImportPage /> },
      {
        element: <CandidateLayout />,
        children: [
          { path: routes.candidateFeed, element: <VacancyFeedPage /> },
          { path: routes.candidateApplications, element: <MyApplicationsPage /> },
        ],
      },
      { path: routes.candidateVacancy(), element: <VacancyDetailsPage /> },
      { path: routes.vacancyPublic(), element: <VacancyPublicPage /> },
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
          { path: routes.employerVacancyList, element: <VacanciesPage /> },
          { path: routes.employerVacancyCandidates(), element: <CandidatesQueuePage /> },
          // P1: доска найма (E15) и резерв (E16).
          { path: routes.employerCandidates, element: <HiringBoardPage /> },
          { path: routes.employerReserve, element: <ReservePage /> },
          // P2: аналитика работодателя (E18) — раздел кабинета.
          { path: routes.employerAnalytics, element: <AnalyticsPage /> },
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
          { path: routes.employerVacancyEdit(), element: <EditDraftPage /> },
          // P1: ИИ-разбор текста (E11 → E12) и голосовой ввод (E13).
          { path: routes.employerVacancyAi, element: <VacancyAiTextPage /> },
          { path: routes.employerVacancyAiCheck, element: <VacancyAiCheckPage /> },
          { path: routes.employerVacancyVoice, element: <VacancyVoicePage /> },
        ],
      },
      { path: routes.employerVacancySlots(), element: <InterviewSlotsPage /> },
      { path: routes.employerApplication(), element: <CandidateCardPage /> },
      { path: routes.employerApplicationInvite(), element: <InviteConfirmPage /> },
      { path: routes.employerApplicationReject(), element: <RejectReasonPage /> },
      { path: routes.employerInterview(), element: <InterviewDetailsPage /> },
      // P2: калибровка (E17) и реферальная ссылка (R01, любая роль) — полноэкранные.
      { path: routes.employerVacancyCalibration(), element: <CalibrationPage /> },
      { path: routes.vacancyReferral(), element: <ReferralPage /> },

      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
