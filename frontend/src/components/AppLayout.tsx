import { Panel } from '@maxhub/max-ui'
import { Outlet } from 'react-router-dom'

/**
 * Общий каркас Mini App. Дизайн экранов ещё не утверждён (см. задачу),
 * поэтому layout ограничивается тем, что нужно для работы на мобильном
 * экране внутри MAX: фон темы и ограничение ширины контента.
 */
export function AppLayout() {
  return (
    <Panel mode="secondary" style={{ minHeight: '100vh' }}>
      <div style={{ maxWidth: 480, margin: '0 auto', minHeight: '100vh' }}>
        <Outlet />
      </div>
    </Panel>
  )
}
