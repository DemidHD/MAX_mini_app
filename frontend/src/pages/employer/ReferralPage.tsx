import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { getVacancy } from '@/api/hiring'
import { ensureReferralLink, isNotPublishedError } from '@/api/p2'
import type { ReferralLink } from '@/api/p2'
import cafePhoto from '@/assets/referral-cafe.webp'
import { BackButton } from '@/components/BackButton'
import { ErrorScreen } from '@/components/ErrorScreen'
import { LoadingScreen } from '@/components/LoadingScreen'
import { AccentMarks, CopyIcon, HeartIcon, PinFilledIcon, ShareIcon } from '@/components/icons'
import { useAsync } from '@/hooks/useAsync'
import { criterionLabel, formatSalaryRange, scheduleLabel } from '@/lib/format'
import './ReferralPage.css'

/**
 * R01 «Реферальная ссылка» (P2, функция 32 UX-карты, раздел 68 тех-доки):
 * отдельная ссылка на вакансию с источником рекомендации
 * (`referral_links`: code + source_user_id + vacancy_id). Уже созданная
 * ссылка переиспользуется (`GET .../referral`), иначе создается новая
 * (`POST .../referral`). Персональные данные откликнувшихся источнику
 * ссылки не показываются.
 */
export function ReferralPage() {
  const vacancyId = Number(useParams().vacancyId)
  const navigate = useNavigate()
  const { state, reload } = useAsync(
    async (signal) => {
      const vacancy = await getVacancy(vacancyId, signal)
      let link: ReferralLink | null = null
      try {
        link = await ensureReferralLink(vacancyId, signal)
      } catch (cause) {
        // Черновику ссылку не создать: экран объясняет, что нужно опубликовать.
        if (!isNotPublishedError(cause)) throw cause
      }
      return { vacancy, link }
    },
    [vacancyId],
  )
  const [copied, setCopied] = useState(false)

  if (state.status === 'loading') return <LoadingScreen />
  if (state.status === 'error') {
    return <ErrorScreen error={state.error} onRetry={reload} onBack={() => navigate(-1)} />
  }

  const { vacancy, link } = state.data
  const meta = [vacancy.location, vacancy.schedule ? scheduleLabel(vacancy.schedule) : null].filter(Boolean).join(' · ')
  // Чипы — короткие условия вакансии; город и зарплата уже есть строками выше.
  const chips = vacancy.criteria
    .filter((criterion) => criterion.type !== 'location' && criterion.type !== 'salary')
    .map(criterionLabel)
    .filter((label) => label.length <= 18)
    .slice(0, 3)

  async function copy() {
    if (!link) return
    try {
      await navigator.clipboard.writeText(link.url)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      // Буфер обмена недоступен (нет разрешения / не https) — ссылка видна
      // целиком, её можно выделить вручную.
    }
  }

  async function share() {
    if (!link) return
    if (navigator.share) {
      try {
        await navigator.share({ title: vacancy.title, text: `Вакансия «${vacancy.title}» в МЭТЧ`, url: link.url })
      } catch {
        // Пользователь закрыл системное меню — не ошибка.
      }
    } else {
      void copy()
    }
  }

  return (
    <div className="p1Screen referral">
      <BackButton />

      <h1 className="p1Title referral__title">
        Порекомендуйте
        <br />
        знакомому
      </h1>
      <p className="p1Subtitle referral__subtitle">Отправьте вакансию напрямую</p>

      <div className="referral__stage">
        <AccentMarks className="referral__marks" />

        <section className="referral__card">
          <p className="referral__brand">
            <b>МЭТЧ</b>
          </p>
          <h2 className={`referral__vacancy${titleSizeClass(vacancy.title)}`}>{vacancy.title}</h2>
          {vacancy.company_name ? <p className="referral__company">{vacancy.company_name}</p> : null}

          <ul className="referral__facts">
            <li className="referral__fact">
              <span className="referral__factIcon referral__factIcon--ruble" aria-hidden="true">
                ₽
              </span>
              {formatSalaryRange(vacancy.salary_min, vacancy.salary_max)}
            </li>
            {meta ? (
              <li className="referral__fact">
                <span className="referral__factIcon" aria-hidden="true">
                  <PinFilledIcon size={21} />
                </span>
                {meta}
              </li>
            ) : null}
          </ul>

          {chips.length > 0 ? (
            <ul className="referral__chips">
              {chips.map((chip) => (
                <li key={chip} className="referral__chip">
                  {chip}
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        <span className="referral__photo" aria-hidden="true">
          <img
            src={vacancy.image_url ?? cafePhoto}
            alt=""
            referrerPolicy="no-referrer"
            onError={(event) => {
              if (!event.currentTarget.src.endsWith(cafePhoto)) event.currentTarget.src = cafePhoto
            }}
          />
        </span>
        <span className="referral__sticker" aria-hidden="true">
          <b>Вакансия</b>
          <span>
            ждет своего <HeartIcon size={11} strokeWidth={2.3} />
          </span>
          <b>человека</b>
        </span>
      </div>

      {link ? (
        <section className="referral__link">
          <span className="referral__linkLabel">Ваша ссылка</span>
          <div className="referral__linkRow">
            <span className="referral__linkField">{link.url.replace(/^https?:\/\//, '')}</span>
            <button type="button" className="referral__copy" onClick={() => void copy()}>
              <span className="referral__copyIcon" aria-hidden="true">
                <CopyIcon size={20} strokeWidth={1.8} />
              </span>
              {copied ? 'Скопировано' : 'Скопировать'}
            </button>
          </div>
        </section>
      ) : (
        <section className="referral__link referral__link--empty">
          <span className="referral__linkLabel">Ссылка появится после публикации</span>
          <p className="referral__linkHint">Опубликуйте вакансию — и ей можно будет поделиться со знакомыми.</p>
        </section>
      )}

      <button type="button" className="p1Button referral__share" disabled={!link} onClick={() => void share()}>
        <ShareIcon size={22} strokeWidth={1.8} />
        Поделиться
      </button>
      <p className="referral__caption">Мы сохраним источник рекомендации</p>
    </div>
  )
}

/** Длинное название уменьшается, чтобы не залезать под фото. */
function titleSizeClass(title: string): string {
  if (title.length <= 9) return ''
  return title.length <= 14 ? ' referral__vacancy--medium' : ' referral__vacancy--small'
}
