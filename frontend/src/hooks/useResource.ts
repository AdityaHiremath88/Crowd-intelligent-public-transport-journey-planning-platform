import { useEffect, useState } from 'react'

export function useResource<T>(load: () => Promise<T>, dependencies: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let current = true
    setLoading(true)
    load().then((value) => {
      if (current) { setData(value); setError(null) }
    }).catch((reason: unknown) => {
      if (current) setError(reason instanceof Error ? reason.message : 'Could not load this information.')
    }).finally(() => { if (current) setLoading(false) })
    return () => { current = false }
    // Callers supply stable loaders/dependencies for each view.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies)

  return { data, error, loading, reload: () => setLoading(true) }
}


