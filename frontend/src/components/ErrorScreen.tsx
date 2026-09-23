import { NetworkError } from '@/api/client'
import './ErrorScreen.css'

/**
 * G03 «Общая ошибка / повтор» (UX-карта, раздел 4): короткое сообщение без
 * технического жаргона, «Повторить» и «Вернуться», когда есть куда вернуться.
 * Введённые данные экраны держат у себя, поэтому повтор их не теряет.
 */
export function ErrorScreen({
  error,
  title = 'Не получилось загрузить',
  description,
  onRetry,
  onBack,
}: {
  error?: unknown
  title?: string
  description?: string
  onRetry?: () => void
  onBack?: () => void
}) {
  const text = description ?? describeError(error)

  return (
    <div className="screen errorScreen">
      <p className="screen__logo">
        <span>MAX</span> Найм
      </p>
      <h1 className="screen__title errorScreen__title">{title}</h1>
      <p className="screen__subtitle errorScreen__subtitle">{text}</p>

      {/* Место под иллюстрацию из макета; картинка будет добавлена отдельно. */}
      <div className="errorScreen__art" aria-hidden="true" />

      <div className="screen__spacer" />

      {onRetry ? (
        <button type="button" className="screenButton screenButton--primary" onClick={onRetry}>
          Повторить
        </button>
      ) : null}
      {onBack ? (
        <button type="button" className="screenButton screenButton--outline errorScreen__back" onClick={onBack}>
          Вернуться
        </button>
      ) : null}
      <p className="screen__note errorScreen__note">Сохраненные данные не потеряны</p>
    </div>
  )
}

function describeError(error: unknown): string {
  if (error instanceof NetworkError || (typeof navigator !== 'undefined' && !navigator.onLine)) {
    return 'Проверьте соединение и попробуйте еще раз'
  }
  if (error && typeof error === 'object' && 'status' in error) {
    const status = Number((error as { status: number }).status)
    if (status === 404) return 'Этот экран больше недоступен'
    if (status === 401) return 'Сессия истекла — откройте приложение заново'
    if (status >= 500) return 'Сервер временно недоступен, попробуйте чуть позже'
  }
  return 'Проверьте соединение и попробуйте еще раз'
}
