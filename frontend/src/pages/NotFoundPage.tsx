import { Link } from 'react-router-dom'
import { Typography } from '@maxhub/max-ui'

import { routes } from '@/app/routes'
import { EmptyState } from '@/components/EmptyState'

export function NotFoundPage() {
  return (
    <EmptyState
      title="Страница не найдена"
      action={
        <Link to={routes.root}>
          <Typography.Action>На главную</Typography.Action>
        </Link>
      }
    />
  )
}
