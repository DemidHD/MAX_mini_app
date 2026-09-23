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
      {/*
       * Panel — flex-контейнер, поэтому классический трюк `margin: 0 auto`
       * здесь не работает: auto-отступы по кросс-оси перебивают stretch, и
       * блок сжимается до ширины контента вместо 100%. Центрируем через
       * alignSelf, а ширину задаём явно и ограничиваем maxWidth.
       */}
      <div style={{ width: '100%', maxWidth: 480, alignSelf: 'center', minHeight: '100vh' }}>
        <Outlet />
      </div>
    </Panel>
  )
}
