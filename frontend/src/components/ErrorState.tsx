import { Button, Flex, Typography } from '@maxhub/max-ui'

export function ErrorState({
  title = 'Что-то пошло не так',
  description,
  onRetry,
}: {
  title?: string
  description?: string
  onRetry?: () => void
}) {
  return (
    <Flex
      direction="column"
      align="center"
      justify="center"
      gap={12}
      style={{ minHeight: '60vh', padding: 16, textAlign: 'center' }}
    >
      <Typography.Title>{title}</Typography.Title>
      {description ? <Typography.Body>{description}</Typography.Body> : null}
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          Повторить
        </Button>
      ) : null}
    </Flex>
  )
}
