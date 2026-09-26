import { useEffect, useRef, useState } from 'react'

export function ChangedValue({ value, className = '' }: { value: string; className?: string }) {
  const previous = useRef(value)
  const [changed, setChanged] = useState(false)
  useEffect(() => {
    if (previous.current === value) return
    previous.current = value
    setChanged(true)
    const timer = window.setTimeout(() => setChanged(false), 1600)
    return () => window.clearTimeout(timer)
  }, [value])
  return <span className={`changed-value ${className}${changed ? ' value-updated' : ''}`}>{value}</span>
}
