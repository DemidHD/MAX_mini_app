import { Panel } from '@maxhub/max-ui'
import { Outlet, ScrollRestoration } from 'react-router-dom'

import { ApiError } from '@/api/client'
import { useAuth } from '@/auth/useAuth'
import { MaxBridgeUnavailableError } from '@/bridge/maxBridge'
import { ErrorScreen } from '@/components/ErrorScreen'
import { SplashScreen } from '@/components/SplashScreen'

/**
 * Общий каркас Mini App: фон темы, ширина контента и общий шлюз авторизации.
 *
 * Экраны монтируются только после успешного `POST /auth/max` (раздел 7):
 * иначе при открытии по прямой ссылке (например, из уведомления бота) их
 * запросы уходили бы раньше, чем появится серверная сессия, и падали с 401.
 * Пока идёт вход — G01, при ошибке — G03 с повтором (UX-карта).
 */
export function AppLayout() {
  const { state, refresh } = useAuth()

  let content
  if (state.status === 'loading') {
    content = <SplashScreen />
  } else if (state.status === 'error') {
    content = (
      <ErrorScreen error={state.error} description={authErrorText(state.error)} onRetry={() => void refresh()} />
    )
  } else {
    content = <Outlet />
  }

  return (
    <Panel mode="secondary" style={{ minHeight: '100vh' }}>
      {/*
       * Panel — flex-контейнер, поэтому классический трюк `margin: 0 auto`
       * здесь не работает: auto-отступы по кросс-оси перебивают stretch, и
       * блок сжимается до ширины контента вместо 100%. Центрируем через
       * alignSelf, а ширину задаём явно и ограничиваем maxWidth.
       */}
      <div style={{ width: '100%', maxWidth: 480, alignSelf: 'center', minHeight: '100vh' }}>{content}</div>
      {/* Новый экран открывается с начала, «назад» возвращает прежнюю прокрутку. */}
      <ScrollRestoration />
    </Panel>
  )
}

/**
 * Текст G03 без технического жаргона. Mini App, открытый вне MAX, — частый
 * случай для обычной https-ссылки; подсказку для разработчика показываем
 * только в dev-сборке. `invalid_init_data` — backend не подтвердил подпись
 * MAX (раздел 6): это не истёкшая сессия, общий текст для 401 тут вводит
 * в заблуждение.
 */
function authErrorText(error: Error): string | undefined {
  if (error instanceof MaxBridgeUnavailableError) {
    return import.meta.env.DEV ? error.message : 'Откройте МЭТЧ в приложении MAX и попробуйте еще раз'
  }
  if (error instanceof ApiError && error.code === 'invalid_init_data') {
    return 'Не удалось подтвердить вход через MAX. Закройте приложение и откройте его снова через бота'
  }
  return undefined
}
