import { useNavigate, useParams } from 'react-router-dom'

import { routes } from '@/app/routes'
import { applyToVacancy, getVacancy } from '@/api/hiring'
import type { VacancyCriterion } from '@/api/hiring'
import { BackButton } from '@/components/BackButton'
import { CoverImage } from '@/components/CoverImage'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { criterionIcon, criterionLabel, splitCriteria, vacancyFacts } from '@/components/VacancyFacts'
import { MoreIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { formatSalaryRange } from '@/lib/format'
import { useApply } from '@/pages/candidate/useApply'
import './VacancyDetailsPage.css'

/**
 * C03 «Детали вакансии»: полные условия и обязательные/желательные требования
 * (`GET /vacancies/:id`). У закрытой вакансии отклик отключён.
 */
export function VacancyDetailsPage() {
  const vacancyId = Number(useParams().vacancyId)
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => getVacancy(vacancyId, signal), [vacancyId])
  const { apply, applying, error } = useApply(applyToVacancy)

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(routes.candidateFeed)} />
  }

  const vacancy = state.data
  const { required, desired } = splitCriteria(vacancy.criteria)
  const closed = vacancy.status !== 'published'

  return (
    <div className="screen vacancyDetails">
      <header className="vacancyDetails__hero photoSlot photoSlot--dark photoSlot--shade">
        <CoverImage url={vacancy.image_url} />
        <div className="vacancyDetails__heroTop">
          <BackButton variant="glass" onClick={() => navigate(routes.candidateFeed)} />
          <span className="vacancyDetails__more" aria-hidden="true">
            <MoreIcon size={22} />
          </span>
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

        {error ? <p className="screen__error">{error}</p> : null}
        <button
          type="button"
          className="screenButton screenButton--primary vacancyDetails__apply"
          disabled={closed || applying}
          onClick={() => void apply(vacancy.id)}
        >
          {closed ? 'Вакансия закрыта' : applying ? 'Отправляем…' : 'Откликнуться'}
        </button>
        {closed ? (
          <button type="button" className="screenButton screenButton--link" onClick={() => navigate(routes.candidateFeed)}>
            Смотреть другие вакансии
          </button>
        ) : null}
      </div>
    </div>
  )
}

function CriteriaSection({ title, criteria }: { title: string; criteria: VacancyCriterion[] }) {
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
