import { api } from '../api/client'
import { useResource } from '../hooks/useResource'

export function ModelPanel({ demo }: { demo: boolean }) {
  const { data, error, refresh } = useResource((signal) => api.model(signal), [])
  return (
    <details className="model"><summary><span>Качество прогноза</span><span className="muted">{demo ? 'DEMO' : 'Метрики модели'} ↗</span></summary>
      <div className="model-content">{error ? <div className="empty">Сервис данных недоступен <button onClick={refresh}>Повторить</button></div> : !data ? <p className="empty">Загрузка метрик…</p> : <>
        {demo && <p className="demo-model-note">DEMO DATA · Все метрики ниже синтетические и не оценивают реальную модель.</p>}
        {data.hackathon && <>
          <h3>Данные хакатона · Live</h3>
          <div className="model-stats"><div><b>{Math.round(data.hackathon.mae)} с</b><span>Ошибка прогноза (MAE)</span></div><div><b>{Math.round(data.hackathon.baselineMae)} с</b><span>Базовое правило</span></div></div>
          <p>Отклонение от графика через 10–15 мин, {data.hackathon.testSize} точек test. Без прогноза (0) — {Math.round(data.hackathon.zeroMae)} с. В потоке NDTP без подсказки текущего отставания — {Math.round(data.hackathon.maeStream)} с. Классы early / ontime / late: точность {data.hackathon.accuracy}%, F1 {data.hackathon.f1}.</p>
          <h3>Режим «Симуляция»</h3>
        </>}
        <div className="model-stats"><div><b>{data.precision}%</b><span>Точность тревог</span></div><div><b>{data.recall}%</b><span>Полнота</span></div></div>
        <p>PR-AUC {data.prAuc} · базовое правило {data.baselinePrAuc}. Точность базового правила при той же полноте — {data.baselinePrecision}%.</p>
        {!demo && <p>Проверено на отложенной неделе со смоделированным движением.</p>}
        <h3>Вклад признаков</h3>{data.features.map((f) => <div key={f.key} className="feature"><div className="feature-label"><span>{f.label}</span><span>{f.importance.toFixed(1)}</span></div><div className="feature-bar"><i style={{ width: `${Math.min(100, Math.max(0, f.share * 100))}%` }} /></div></div>)}
      </>}</div>
    </details>
  )
}
