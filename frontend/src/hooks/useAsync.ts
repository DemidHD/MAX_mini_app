import { useCallback, useEffect, useState } from 'react'
import type { DependencyList } from 'react'

export type AsyncState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: Error }
  | { status: 'success'; data: T }

/**
 * Загрузка данных экрана с состояниями loading / error / success и повтором
 * (UX-карта, раздел 8: у каждого P0-экрана есть загрузка и ошибка с «Повторить»).
 */
export function useAsync<T>(load: (signal: AbortSignal) => Promise<T>, deps: DependencyList) {
  const [state, setState] = useState<AsyncState<T>>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stableLoad = useCallback(load, deps)

  useEffect(() => {
    const controller = new AbortController()
    setState({ status: 'loading' })
    stableLoad(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ status: 'success', data })
      },
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setState({ status: 'error', error: error instanceof Error ? error : new Error(String(error)) })
        }
      },
    )
    return () => controller.abort()
  }, [stableLoad, attempt])

  const reload = useCallback(() => setAttempt((value) => value + 1), [])

  return { state, reload, setState }
}
