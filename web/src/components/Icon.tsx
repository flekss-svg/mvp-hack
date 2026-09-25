export function Icon({ name, size = 16 }: { name: 'search' | 'settings' | 'pin' | 'signal' | 'warning'; size?: number }) {
  const paths = {
    search: <><circle cx="10" cy="10" r="6" /><path d="m15 15 5 5" /></>,
    settings: <><path d="M4 6h16M4 12h16M4 18h16" /><path d="M8 3v6m8 0v6m-6 0v6" /></>,
    pin: <><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z" /><circle cx="12" cy="10" r="2" /></>,
    signal: <><path d="M5 19v-4m7 4V9m7 10V3" /></>,
    warning: <><path d="m12 3 10 17H2L12 3Z" /><path d="M12 9v4m0 3v.5" /></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}
