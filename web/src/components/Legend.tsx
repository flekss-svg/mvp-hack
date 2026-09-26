export function Legend({ threshold }: { threshold: number }) {
  return (
    <details className="legend" open>
      <summary>Уровни риска</summary>
      <div className="legend-items"><span><i className="dot dot-low" />Низкий</span><span><i className="dot dot-mid" />Средний</span><span><i className="dot dot-high">!</i>Высокий</span><span><i className="dot dot-muted" />Нет прогноза</span></div>
      <div className="legend-secondary"><span><i className="dot dot-ring" />Опоздание ≥ {threshold} мин</span><span><i className="bar bar-slow" />Замедление</span><span><i className="bar bar-slow-strong" />Сильное</span></div>
    </details>
  )
}
