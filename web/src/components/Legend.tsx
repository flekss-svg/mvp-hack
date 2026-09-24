const DOTS = [
  { cls: 'low', text: 'Низкий риск' },
  { cls: 'mid', text: 'Средний риск' },
  { cls: 'high', text: 'Высокий риск' },
  { cls: 'muted', text: 'Рейс скоро завершится' },
]

export function Legend({ threshold }: { threshold: number }) {
  return (
    <div className="legend">
      {DOTS.map((d) => (
        <div key={d.cls}>
          <i className={`dot dot-${d.cls}`} />
          {d.text}
        </div>
      ))}
      <div>
        <i className="dot dot-ring" />
        Уже опаздывает ≥ {threshold} мин
      </div>
      <div>
        <i className="bar bar-slow" />
        Перегон медленнее плана
      </div>
      <div>
        <i className="bar bar-slow-strong" />
        …существенно медленнее
      </div>
    </div>
  )
}
