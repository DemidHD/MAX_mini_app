import { Link } from 'react-router-dom'
import { Typography } from '@maxhub/max-ui'

import { routes } from '@/app/routes'
import { EmptyState } from '@/components/EmptyState'

/**
 * Экраны следующих этапов (профиль кандидата, лента, вакансии — см.
 * распределение задач, Этапы 2-3) в этой задаче не реализуются: дизайна ещё
 * нет, а маршрутизация уже должна корректно доводить пользователя до места,
 * куда backend направляет его через `current_step`.
 */
export function StubPage({ title }: { title: string }) {
  return (
    <EmptyState
      title={title}
      description="Экран появится на следующем этапе разработки."
      action={
        <Link to={routes.profile}>
          <Typography.Action>Открыть профиль</Typography.Action>
        </Link>
      }
    />
  )
}
