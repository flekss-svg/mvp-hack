import { ageSeconds, updatedText } from '../ui/presentation'
export function ConnectionStatus({ updatedAt, now, offline, paused }: { updatedAt: number | null; now: number; offline: boolean; paused: boolean }) {
  const stale = !paused && (ageSeconds(updatedAt, now) ?? 0) > 15
  return <div className={`connection-status ${offline ? 'connection-offline' : stale ? 'connection-stale' : 'connection-ok'}`} role="status">
    <span className="status-dot" /><strong>{offline ? 'Нет соединения' : paused && updatedAt ? 'Replay на паузе' : !updatedAt ? 'Подключение к данным' : stale ? 'Данные устарели' : 'Данные актуальны'}</strong>
    <span>{offline ? updatedAt === null ? 'Данные ещё не получены' : 'Показано последнее известное состояние' : stale ? `Последнее обновление ${ageSeconds(updatedAt, now)} сек назад` : updatedText(updatedAt, now)}</span>
  </div>
}
