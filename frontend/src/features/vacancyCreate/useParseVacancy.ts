import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import { parseVacancy } from '@/api/ai'
import { DESCRIPTION_MAX_LENGTH, draftFromParsed } from '@/features/vacancyCreate/draft'
import { useVacancyDraft } from '@/features/vacancyCreate/useVacancyDraft'

/**
 * Общий путь разбора текста вакансии для E11 (текст) и E13 (голос → текст):
 * `POST /ai/parse-vacancy` → черновик формы → экран подтверждения E12.
 *
 * Ветки раздела 57: ИИ недоступен — ручная форма E02 с текстом в описании;
 * запрещённая деятельность — причина показывается на месте, E12 не
 * открывается; сетевая ошибка — текст остаётся, можно повторить.
 */
export function useParseVacancy() {
  const { draft, setDraft, updateDraft } = useVacancyDraft()
  const navigate = useNavigate()
  const [parsing, setParsing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function parse(text: string): Promise<void> {
    const trimmed = text.trim()
    if (!trimmed || parsing) return
    setParsing(true)
    setError(null)
    try {
      const result = await parseVacancy(trimmed)
      if (result.rejected) {
        setError(result.rejection_reason ?? 'Такую вакансию опубликовать нельзя.')
        return
      }
      if (!result.ai_available) {
        updateDraft({ sourceText: trimmed, description: trimmed.slice(0, DESCRIPTION_MAX_LENGTH) })
        navigate(routes.employerVacancyCreate)
        return
      }
      setDraft(draftFromParsed(draft, result.parsed, trimmed))
      navigate(routes.employerVacancyAiCheck)
    } catch {
      setError('Не удалось разобрать текст. Он на месте — попробуйте еще раз или заполните вручную.')
    } finally {
      setParsing(false)
    }
  }

  return { parse, parsing, error, setError }
}
