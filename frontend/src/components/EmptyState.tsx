import { Flex, Typography } from '@maxhub/max-ui'
import type { ReactNode } from 'react'

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <Flex
      direction="column"
      align="center"
      justify="center"
      gap={12}
      style={{ minHeight: '50vh', padding: 16, textAlign: 'center' }}
    >
      <Typography.Title>{title}</Typography.Title>
      {description ? <Typography.Body>{description}</Typography.Body> : null}
      {action}
    </Flex>
  )
}
