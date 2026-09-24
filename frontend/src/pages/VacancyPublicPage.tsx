import { useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { getPublicVacancy } from '@/api/vacancies'
import { BackButton } from '@/components/BackButton'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { criterionIcon, criterionLabel, splitCriteria, vacancyFacts } from '@/components/VacancyFacts'
import { useAsync } from '@/hooks/useAsync'
import { useAuth } from '@/auth/useAuth'
import { formatSalaryRange } from '@/lib/format'
import '@/pages/candidate/VacancyDetailsPage.css'

/**
 * Публичная ссылка на вакансию `{APP_URL}/v/{token}` (раздел 15 тех-доки).
 *
 * В отличие от C03 (`VacancyDetailsPage`), сюда попадают по прямой ссылке —
 * без прохода через `RootRedirect`, поэтому сессия MAX ещё может не успеть
 * подняться (`AuthProvider` авторизуется асинхронно при монтировании
 * приложения). Экран ждёт `authenticated` сам, а не полагается на layout.
 *
 * Отклика с этого экрана нет: сценарий отклика в P0 завязан на моковые данные
 * (`mocks/demoApi.ts`), а эта страница ходит в настоящий backend — смешивать
 * их означало бы обещать действие, которое ни к чему не приведёт.
 */
export function VacancyPublicPage() {
  const token = useParams().token ?? ''
  const navigate = useNavigate()
  const { state: authState, refresh } = useAuth()
  const authenticated = authState.status === 'authenticated'

  const { state, reload } = useAsync(
    (signal) => (authenticated ? getPublicVacancy(token, signal) : new Promise<never>(() => {})),
    [token, authenticated],
  )

  if (authState.status === 'error') {
    return <ErrorScreen error={authState.error} onRetry={() => void refresh()} />
  }
  if (!authenticated || state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.root)} />
  }

  const vacancy = state.data
  const { required, desired } = splitCriteria(vacancy.criteria)

  return (
    <div className="screen vacancyDetails">
      <header className="vacancyDetails__hero photoSlot photoSlot--dark">
        <div className="vacancyDetails__heroTop">
          <BackButton variant="glass" onClick={() => navigate(routes.root)} />
        </div>
        <div className="vacancyDetails__heroText">
          {vacancy.company_name ? <span className="vacancyDetails__company">{vacancy.company_name}</span> : null}
          <h1 className="vacancyDetails__title">{vacancy.title}</h1>
          <span className="vacancyDetails__salary">{formatSalaryRange(vacancy.salary_min, vacancy.salary_max)}</span>
        </div>
      </header>

      <div className="vacancyDetails__body">
        <div className="vacancyDetails__facts">
          {vacancyFacts(vacancy, 24).map((fact) => (
            <span key={fact.key} className="vacancyDetails__fact">
              {fact.icon}
              {fact.label}
            </span>
          ))}
        </div>

        {vacancy.description ? (
          <section className="vacancyDetails__section">
            <h2 className="vacancyDetails__sectionTitle">О вакансии</h2>
            <p className="vacancyDetails__description">{vacancy.description}</p>
          </section>
        ) : null}

        <CriteriaSection title="Обязательно" criteria={required} />
        <CriteriaSection title="Желательно" criteria={desired} />

        <div className="screen__spacer" />

        <button type="button" className="screenButton screenButton--primary" onClick={() => navigate(routes.root)}>
          На главную
        </button>
      </div>
    </div>
  )
}

function CriteriaSection({
  title,
  criteria,
}: {
  title: string
  criteria: ReturnType<typeof splitCriteria>['required']
}) {
  if (criteria.length === 0) return null
  return (
    <section className="vacancyDetails__section">
      <h2 className="vacancyDetails__sectionTitle">{title}</h2>
      <div className="vacancyDetails__chips">
        {criteria.map((criterion) => (
          <span key={criterion.type} className="vacancyDetails__chip">
            {criterionIcon(criterion.type, 24)}
            {criterionLabel(criterion)}
          </span>
        ))}
      </div>
    </section>
  )
}
