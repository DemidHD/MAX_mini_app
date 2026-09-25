import { Link } from 'react-router-dom'

import { routes } from '@/app/routes'
import { getVacancyCandidates } from '@/api/hiring'
import type { Vacancy } from '@/api/hiring'
import { CoverImage } from '@/components/CoverImage'
import { TrashIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { formatSalaryRange, plural, scheduleLabel } from '@/lib/format'
import './VacancyTile.css'

const STATUS_LABELS: Record<Vacancy['status'], string> = {
  published: 'Опубликована',
  draft: 'Черновик',
  closed: 'Закрыта',
}

/**
 * Карточка вакансии работодателя с фото вакансии (главная E01 и раздел
 * «Вакансии»). Опубликованная ведёт к кандидатам, черновик — в форму создания.
 */
export function VacancyCard({ vacancy, onDelete }: { vacancy: Vacancy; onDelete: () => void }) {
  const count = vacancy.applications_count ?? 0
  const isDraft = vacancy.status === 'draft'
  const newCount = useNewCandidates(vacancy.id, !isDraft && count > 0)
  const meta = [vacancy.location, vacancy.schedule ? scheduleLabel(vacancy.schedule) : null].filter(Boolean).join(' · ')
  const to = isDraft ? routes.employerVacancyEdit(vacancy.id) : routes.employerVacancyCandidates(vacancy.id)

  return (
    <div className={`vacancyTile photoSlot photoSlot--dark photoSlot--shade${isDraft ? ' vacancyTile--draft' : ''}`}>
      <CoverImage url={vacancy.image_url} />
      {/* Ссылка растянута на всю карточку, кнопка удаления лежит поверх неё:
          вложить кнопку в <a> нельзя. */}
      <Link
        to={to}
        className="vacancyTile__link"
        aria-label={isDraft ? `Продолжить черновик «${vacancy.title}»` : `Кандидаты вакансии «${vacancy.title}»`}
      />
      {isDraft ? (
        <button type="button" className="vacancyTile__delete" aria-label="Удалить черновик" onClick={onDelete}>
          <TrashIcon size={18} />
        </button>
      ) : null}
      {vacancy.company_name ? <span className="vacancyTile__company">{vacancy.company_name}</span> : null}
      <span className="vacancyTile__title">{vacancy.title}</span>
      <span className="vacancyTile__salary">{formatSalaryRange(vacancy.salary_min, vacancy.salary_max)}</span>
      {meta ? <span className="vacancyTile__meta">{meta}</span> : null}
      <span className="vacancyTile__badges">
        <span className={`vacancyTile__status vacancyTile__status--${vacancy.status}`}>
          <i aria-hidden="true" />
          {STATUS_LABELS[vacancy.status]}
        </span>
        {newCount !== null && newCount > 0 ? (
          <span className="vacancyTile__count">
            {newCount} {plural(newCount, 'новый', 'новых', 'новых')}
          </span>
        ) : newCount === 0 && count > 0 ? (
          <span className="vacancyTile__count vacancyTile__count--muted">
            {count} {plural(count, 'отклик', 'отклика', 'откликов')}
          </span>
        ) : null}
        {isDraft ? <span className="vacancyTile__continue">Продолжить</span> : null}
      </span>
    </div>
  )
}

/**
 * Сколько новых кандидатов ждут решения (как «3 новых» в макете E01):
 * прошедшие отбор и ещё не разобранные. Общий `applications_count` сюда не
 * подходит — он считает и тех, кто не прошёл обязательные условия.
 * `null` — ещё считаем или считать нечего.
 */
function useNewCandidates(vacancyId: number, enabled: boolean): number | null {
  const { state } = useAsync(
    async (signal) => {
      if (!enabled) return null
      const page = await getVacancyCandidates(vacancyId, signal)
      return page.items.filter((item) => item.status === 'passed' || item.status === 'under_review').length
    },
    [vacancyId, enabled],
  )
  return state.status === 'success' ? state.data : null
}
