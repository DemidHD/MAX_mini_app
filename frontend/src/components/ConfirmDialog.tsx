import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'

import './ConfirmDialog.css'

/**
 * Модальное окно подтверждения. Закрывается «Отменой», Esc и тапом по фону —
 * но не во время выполнения действия (`busy`), чтобы не потерять его результат.
 * Без `cancelLabel` окно информационное: одна кнопка.
 */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  cancelLabel = 'Отмена',
  tone = 'primary',
  busy = false,
  error,
  onConfirm,
  onCancel,
}: {
  title: string
  children?: ReactNode
  confirmLabel: string
  cancelLabel?: string | null
  tone?: 'primary' | 'danger'
  busy?: boolean
  error?: string | null
  onConfirm: () => void
  onCancel: () => void
}) {
  const titleId = useId()
  const textId = useId()
  const cancelRef = useRef<HTMLButtonElement>(null)
  const confirmRef = useRef<HTMLButtonElement>(null)

  // Фокус на безопасную кнопку: случайный Enter не должен удалить черновик.
  useEffect(() => {
    ;(cancelRef.current ?? confirmRef.current)?.focus()
  }, [])

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape' && !busy) onCancel()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [busy, onCancel])

  return (
    <div className="confirmDialog" role="presentation">
      <button
        type="button"
        className="confirmDialog__backdrop"
        aria-label="Закрыть"
        tabIndex={-1}
        onClick={() => (busy ? undefined : onCancel())}
      />
      <div
        className="confirmDialog__panel"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={children ? textId : undefined}
      >
        <h2 id={titleId} className="confirmDialog__title">
          {title}
        </h2>
        {children ? (
          <div id={textId} className="confirmDialog__text">
            {children}
          </div>
        ) : null}
        {error ? <p className="confirmDialog__error">{error}</p> : null}

        <div className="confirmDialog__actions">
          <button
            ref={confirmRef}
            type="button"
            className={`screenButton ${tone === 'danger' ? 'confirmDialog__danger' : 'screenButton--primary'}`}
            disabled={busy}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
          {cancelLabel ? (
            <button
              ref={cancelRef}
              type="button"
              className="screenButton screenButton--outline"
              disabled={busy}
              onClick={onCancel}
            >
              {cancelLabel}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
}
