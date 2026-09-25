import { Navigate, useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { getPublicVacancy } from '@/api/vacancies'
import { BackButton } from '@/components/BackButton'
import { CoverImage } from '@/components/CoverImage'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { criterionIcon, criterionLabel, splitCriteria, vacancyFacts } from '@/components/VacancyFacts'
import { useAsync } from '@/hooks/useAsync'
import { useAuth } from '@/auth/useAuth'
import { formatSalaryRange } from '@/lib/format'
import '@/pages/candidate/VacancyDetailsPage.css'

/**
 * Публичная ссылка на вакансию `{APP_URL}/v/{token}` (раздел 15 тех-доки,
 * `GET /vacancies/public/{token}`).
 *
 * Сюда попадают по прямой ссылке; вход в MAX к этому моменту уже выполнен
 * общим шлюзом `AppLayout`. Дальше — по роли:
 * - кандидат сразу уходит на C03 по id вакансии: там настоящий отклик и
 *   обработка закрытой вакансии (правило видимости у эндпоинтов одинаковое);
 * - работодатель видит карточку, а свою вакансию может открыть в кандидатах;
 * - без роли (`role = NULL`) карточка ведёт на выбор роли — роль назначает
 *   только пользователь (раздел 9).
 */
export function VacancyPublicPage() {
  const token = useParams().token ?? ''
  const navigate = useNavigate()
  const { state: authState } = useAuth()
  const { state, reload } = useAsync((signal) => getPublicVacancy(token, signal), [token])

  if (authState.status !== 'authenticated' || state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.root)} />
  }

  const vacancy = state.data
  const { user } = authState
  if (user.role === 'candidate') {
    return <Navigate to={routes.candidateVacancy(vacancy.id)} replace />
  }

  const { required, desired } = splitCriteria(vacancy.criteria)
  const own = user.role === 'employer' && vacancy.employer_id === user.user_id
  const action = own
    ? { label: 'Кандидаты вакансии', to: routes.employerVacancyCandidates(vacancy.id) }
    : user.role === null
      ? { label: 'Откликнуться', to: routes.roleSelection }
      : { label: 'На главную', to: routes.root }

  return (
    <div className="screen vacancyDetails">
      <header className="vacancyDetails__hero photoSlot photoSlot--dark photoSlot--shade">
        <CoverImage url={vacancy.image_url} />
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

        {user.role === null ? (
          <p className="screen__note">Чтобы откликнуться, выберите роль «Ищу работу»</p>
        ) : null}
        <button type="button" className="screenButton screenButton--primary" onClick={() => navigate(action.to)}>
          {action.label}
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
