import { useNavigate } from 'react-router-dom'

import { ChevronLeftIcon } from '@/components/icons'

/**
 * Круглая кнопка «назад» из макетов. Без `onClick` возвращает на предыдущий
 * экран истории; `variant` выбирает фон под светлую страницу, карточку или
 * фотографию.
 */
export function BackButton({
  onClick,
  variant = 'plain',
  label = 'Назад',
}: {
  onClick?: () => void
  variant?: 'plain' | 'raised' | 'glass'
  label?: string
}) {
  const navigate = useNavigate()
  const modifier = variant === 'plain' ? '' : ` backButton--${variant}`

  return (
    <button
      type="button"
      className={`backButton${modifier}`}
      aria-label={label}
      onClick={() => (onClick ? onClick() : navigate(-1))}
    >
      <ChevronLeftIcon size={22} strokeWidth={2.2} />
    </button>
  )
}
