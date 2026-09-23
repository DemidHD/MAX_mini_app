import { Spinner } from '@maxhub/max-ui'

/** Индикатор загрузки экрана — без пустого белого экрана (UX-карта, раздел 8). */
export function LoadingScreen() {
  return (
    <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }} role="status" aria-label="Загрузка">
      <Spinner size={32} />
    </div>
  )
}
