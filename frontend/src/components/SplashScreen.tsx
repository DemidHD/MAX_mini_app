import { Spinner, Typography } from '@maxhub/max-ui'

import heroImage from '@/assets/splash-hero.webp'
import './SplashScreen.css'

/**
 * Экран G01 «Загрузка и авторизация» (UX-карта). Обязательные элементы по
 * карте — логотип, индикатор загрузки и скрытая проверка авторизации;
 * иллюстрация — готовый макет от дизайнера, название поверх нее — текстом.
 */
export function SplashScreen({
  statusLabel = 'Входим в MAX…',
  caption = 'Восстанавливаем ваш сценарий',
}: {
  statusLabel?: string
  caption?: string
}) {
  return (
    <div className="splash" style={{ backgroundImage: `url(${heroImage})` }}>
      <h1 className="splash__brand">МЭТЧ</h1>
      <div className="splash__status">
        <div className="splash__pill">
          <Spinner size={24} appearance="primary" />
          <Typography.Body>{statusLabel}</Typography.Body>
        </div>
        <Typography.Body className="splash__caption">{caption}</Typography.Body>
      </div>
    </div>
  )
}
