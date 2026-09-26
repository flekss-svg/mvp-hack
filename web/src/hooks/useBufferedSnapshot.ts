import { useEffect, useRef, useState } from 'react'

/** Sample the latest completed response, independent of map/replay render frequency. */
export function useBufferedSnapshot<T>(value: T | null, updatedAt: number | null, scope: string, instant = false) {
  const latest = useRef({ value, updatedAt })
  latest.current = { value, updatedAt }
  const [snapshot, setSnapshot] = useState({ value, updatedAt, scope })
  useEffect(() => {
    const commit = () => {
      const next = latest.current
      if (!next.value) return
      setSnapshot((previous) => previous.scope === scope && previous.updatedAt === next.updatedAt ? previous : { ...next, scope })
    }
    setSnapshot({ ...latest.current, scope })
    const timer = window.setInterval(commit, 4000)
    return () => window.clearInterval(timer)
  }, [scope])
  useEffect(() => {
    if (value) setSnapshot((previous) => (instant || !previous.value) && (previous.value !== value || previous.updatedAt !== updatedAt || previous.scope !== scope) ? { value, updatedAt, scope } : previous)
  }, [value, updatedAt, instant, scope])
  return snapshot.scope === scope ? snapshot : { value: null, updatedAt: null, scope }
}

export function useNow() {
  const [now, setNow] = useState(Date.now)
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [])
  return now
}
