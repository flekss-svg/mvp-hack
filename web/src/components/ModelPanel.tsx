import { api } from '../api/client'
import { useResource } from '../hooks/useResource'

/**
 * Качество модели из reports/metrics.json: переобучили — панель обновилась сама.
 * Все числа и подписи признаков приходят с сервера.
 */
export function ModelPanel() {
  const { data, error } = useResource((signal) => api.model(signal), [])

  if (error) return <section className="panel model"><p className="empty">{error.message}</p></section>
  if (!data) return <section className="panel model"><p className="empty">Загрузка метрик…</p></section>

  return (
    <section className="panel model">
      <h2>Качество модели</h2>
      <p>
        Среди машин, которые пока идут по графику, модель ловит {data.recall}% будущих
        опозданий при точности тревог <b>{data.precision}%</b>. Правило «смотреть на текущее
        опоздание» при той же полноте дает {data.baselinePrecision}%.
      </p>
      <p className="muted">
        PR-AUC {data.prAuc} против {data.baselinePrAuc} у базового правила. Проверено на
        отложенной неделе, движение смоделировано — цифры показывают работоспособность
        подхода, а не точность на реальных данных.
      </p>
      <h3>Главные признаки</h3>
      {data.features.map((f) => (
        <div key={f.key} className="feature">
          <div className="feature-label">
            <span>{f.label}</span>
            <span>{f.importance.toFixed(1)}</span>
          </div>
          <div className="feature-bar">
            <i style={{ width: `${Math.max(4, f.share * 100)}%` }} />
          </div>
        </div>
      ))}
    </section>
  )
}
