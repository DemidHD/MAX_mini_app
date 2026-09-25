import { useState } from 'react'

import { ApiError } from '@/api/client'
import { deleteVacancy } from '@/api/vacancies'
import { ConfirmDialog } from '@/components/ConfirmDialog'

/**
 * Подтверждение удаления черновика (`DELETE /vacancies/{id}`). Удалить можно
 * только черновик: опубликованную вакансию закрывают, чтобы не потерять отклики.
 */
export function DeleteDraftDialog({
  vacancyId,
  title,
  onDeleted,
  onClose,
}: {
  vacancyId: number
  title: string
  onDeleted: () => void
  onClose: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleDelete() {
    setBusy(true)
    setError(null)
    try {
      await deleteVacancy(vacancyId)
      onDeleted()
    } catch (cause) {
      // Черновика уже нет (удалён с другого устройства) — цель достигнута.
      if (cause instanceof ApiError && cause.status === 404) {
        onDeleted()
        return
      }
      setError(
        cause instanceof ApiError && cause.code === 'vacancy_not_draft'
          ? 'Вакансия уже опубликована — удалить её нельзя, только закрыть.'
          : 'Не удалось удалить черновик. Попробуйте еще раз.',
      )
      setBusy(false)
    }
  }

  return (
    <ConfirmDialog
      title="Удалить черновик?"
      confirmLabel={busy ? 'Удаляем…' : 'Удалить'}
      tone="danger"
      busy={busy}
      error={error}
      onConfirm={() => void handleDelete()}
      onCancel={onClose}
    >
      «{title.trim() || 'Без названия'}» удалится без возможности восстановления.
    </ConfirmDialog>
  )
}

/** Сообщение о лимите черновиков — на главной и при ошибке сохранения. */
export function DraftLimitDialog({ limit, onClose }: { limit: number; onClose: () => void }) {
  return (
    <ConfirmDialog title="Слишком много черновиков" confirmLabel="Понятно" cancelLabel={null} onConfirm={onClose} onCancel={onClose}>
      Можно держать до {limit} незаконченных вакансий. Опубликуйте или удалите один из черновиков, чтобы начать
      новую.
    </ConfirmDialog>
  )
}
