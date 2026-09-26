import { CloseIcon } from '@/components/icons'
import '@/pages/candidate/ProfileFieldSheet.css'

export interface SheetOption<T extends string | number> {
  id: T
  label: string
}

/**
 * Нижняя шторка с выбором одного варианта в оформлении P1 (`p1Sheet`):
 * выбор вакансии на доске найма (E15) и в аналитике (E18), периода в
 * аналитике.
 */
export function OptionSheet<T extends string | number>({
  title,
  options,
  selectedId,
  onSelect,
  onClose,
}: {
  title: string
  options: SheetOption<T>[]
  selectedId: T
  onSelect: (id: T) => void
  onClose: () => void
}) {
  return (
    <div className="fieldSheet p1Sheet" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" className="fieldSheet__backdrop" aria-label="Закрыть" onClick={onClose} />
      <div className="fieldSheet__panel">
        <span className="fieldSheet__handle" aria-hidden="true" />
        <div className="fieldSheet__head">
          <h2 className="fieldSheet__title">{title}</h2>
          <button type="button" className="fieldSheet__close" aria-label="Закрыть" onClick={onClose}>
            <CloseIcon size={18} />
          </button>
        </div>
        <div className="fieldSheet__options">
          {options.map((option) => (
            <button
              key={option.id}
              type="button"
              className={`fieldSheet__option${option.id === selectedId ? ' fieldSheet__option--active' : ''}`}
              onClick={() => onSelect(option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
