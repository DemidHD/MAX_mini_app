import type { ReactNode } from 'react'

import { CheckIcon, MaxChatIcon, PinIcon } from '@/components/icons'
import { formatDayMonth, formatTime } from '@/lib/format'
import { CoverImage } from '@/components/CoverImage'
import './InterviewTicket.css'

/**
 * Синяя карточка назначенного интервью — общая для C10 (кандидат) и E10
 * (работодатель). Справа — фото вакансии, растворяющееся в синем фоне.
 */
export function InterviewTicket({
  startsAt,
  heading,
  subheading,
  headingLarge = false,
  person,
  place,
  checkInBadge = false,
  imageUrl,
}: {
  startsAt: string
  heading: string
  subheading?: string | null
  headingLarge?: boolean
  person?: ReactNode
  place: ReactNode
  checkInBadge?: boolean
  imageUrl?: string | null
}) {
  return (
    <article className="interviewTicket">
      {imageUrl ? (
        <span className="interviewTicket__photo photoSlot" aria-hidden="true">
          <CoverImage url={imageUrl} />
        </span>
      ) : null}
      <span className="interviewTicket__badge">
        {checkInBadge ? (
          <span className="interviewTicket__badgeIcon">
            <CheckIcon size={14} strokeWidth={3} />
          </span>
        ) : null}
        Подтверждено
      </span>

      <span className={`interviewTicket__heading${headingLarge ? ' interviewTicket__heading--large' : ''}`}>
        {heading}
      </span>
      {subheading ? <span className="interviewTicket__subheading">{subheading}</span> : null}

      <span className="interviewTicket__date">{formatDayMonth(startsAt)}</span>
      <span className="interviewTicket__time">{formatTime(startsAt)}</span>

      {person ? <div className="interviewTicket__person">{person}</div> : null}

      <span className="interviewTicket__divider" aria-hidden="true" />

      <div className="interviewTicket__place">
        <PinIcon size={26} strokeWidth={1.8} />
        <span>{place}</span>
      </div>
    </article>
  )
}

/** Строка «уведомление в MAX» под карточкой интервью. */
export function MaxNotice({ children, tone = 'soft' }: { children: ReactNode; tone?: 'soft' | 'card' }) {
  return (
    <div className={`maxNotice maxNotice--${tone}`}>
      <span className="maxNotice__tile" aria-hidden="true">
        <MaxChatIcon size={24} />
      </span>
      <span className="maxNotice__text">{children}</span>
    </div>
  )
}
