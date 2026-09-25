import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { routes } from '@/app/routes'
import { VACANCY_TEXT_MAX_LENGTH } from '@/api/ai'
import { BackButton } from '@/components/BackButton'
import { MicIcon, PaperPlaneIcon } from '@/components/icons'
import { useParseVacancy } from '@/features/vacancyCreate/useParseVacancy'
import { useVacancyDraft } from '@/features/vacancyCreate/useVacancyDraft'
import './VacancyAiTextPage.css'

const EXAMPLE =
  'Например: нужен бариста на Белорусской. График 2/2, зарплата до 95 000 ₽. Опыт от полугода. Выйти желательно завтра.'

/**
 * E11 «Создание вакансии свободным текстом» (P1, функция 16 в UX-карте).
 * Текст разбирает `POST /ai/parse-vacancy`, результат открывается на E12 —
 * автоматически ничего не публикуется (раздел 57). Ветки ошибок — в
 * `useParseVacancy`: при недоступном ИИ текст уходит в описание формы E02.
 */
export function VacancyAiTextPage() {
  const { draft, updateDraft, startNew } = useVacancyDraft()
  const { parse, parsing, error } = useParseVacancy()
  const navigate = useNavigate()
  const location = useLocation()
  const text = draft.sourceText

  // «Создать вакансию» на главной приходит с `fresh`: открытый серверный
  // черновик не трогаем — начинаем новую вакансию (как на E02).
  const fresh = (location.state as { fresh?: boolean } | null)?.fresh === true
  useEffect(() => {
    if (!fresh) return
    if (draft.vacancyId !== null) startNew()
    navigate(location.pathname, { replace: true, state: null })
  }, [fresh, draft.vacancyId, startNew, navigate, location.pathname])

  const trimmed = text.trim()

  function handleParse() {
    void parse(text)
  }

  return (
    <div className="p1Screen aiText">
      <div className="p1Top">
        <BackButton onClick={() => navigate(routes.employerHome)} />
        <span className="p1Top__title">Новая вакансия</span>
      </div>

      <h1 className="p1Title aiText__title">
        Опишите,
        <br />
        кто вам нужен
      </h1>
      <p className="p1Subtitle aiText__subtitle">Можно написать как обычное сообщение</p>

      <div className="aiText__card">
        <textarea
          className="aiText__input"
          value={text}
          placeholder={EXAMPLE}
          maxLength={VACANCY_TEXT_MAX_LENGTH}
          aria-label="Описание вакансии"
          onChange={(event) => updateDraft({ sourceText: event.target.value })}
        />
        <div className="aiText__tools">
          <button
            type="button"
            className="aiText__mic"
            aria-label="Надиктовать голосом"
            onClick={() => navigate(routes.employerVacancyVoice)}
          >
            <MicIcon size={26} strokeWidth={1.7} />
          </button>
          <button
            type="button"
            className="aiText__send"
            aria-label="Разобрать"
            disabled={!trimmed || parsing}
            onClick={handleParse}
          >
            <PaperPlaneIcon size={25} />
          </button>
        </div>
      </div>

      <div className="aiText__spacer" />

      {error ? <p className="p1Error">{error}</p> : null}

      <p className="aiText__hint">Разберем текст на условия вакансии</p>
      <button type="button" className="p1Button" disabled={!trimmed || parsing} onClick={handleParse}>
        {parsing ? 'Разбираем…' : 'Разобрать'}
      </button>
      <button type="button" className="p1Link" onClick={() => navigate(routes.employerVacancyCreate)}>
        Заполнить вручную
      </button>
    </div>
  )
}
