import { Flex, Spinner, Typography } from '@maxhub/max-ui'

export function LoadingState({ label = 'Загрузка…' }: { label?: string }) {
  return (
    <Flex direction="column" align="center" justify="center" gap={12} style={{ minHeight: '60vh' }}>
      <Spinner size={24} />
      <Typography.Body>{label}</Typography.Body>
    </Flex>
  )
}
