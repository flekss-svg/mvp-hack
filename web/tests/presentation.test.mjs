import { test } from 'node:test'
import assert from 'node:assert/strict'
import { currentText, forecastText, stableIncidents, riskText, ageSeconds } from '../src/ui/presentation.ts'
import { DEFAULT_DISPLAY, parseDisplay, PALETTES } from '../src/ui/display.ts'

const alert = (tripId, risk) => ({ tripId, risk, delay: 2, route: '17', mode: 'bus', dest: 'Маяковская', stop: 'Тверская' })
test('signed deviations are explained without changing their meaning', () => {
  assert.equal(currentText(-3.5), 'На 3.5 мин раньше графика')
  assert.equal(currentText(2.1), 'Опаздывает на 2.1 мин')
  assert.equal(currentText(-0.04), 'По графику')
  assert.equal(forecastText(-3.5, 5.6), 'Ожидается опоздание на 5.6 мин')
  assert.equal(forecastText(2.1, 7.8), 'Опоздание вырастет до 7.8 мин')
  assert.equal(forecastText(5.4, 2.2), 'Опоздание сократится до 2.2 мин')
  assert.equal(forecastText(5.4, 0), 'Ожидается движение по графику')
  assert.equal(forecastText(2.2, -1.2), 'Ожидается прибытие на 1.2 мин раньше графика')
  assert.equal(forecastText(2.2, undefined), 'Прогноз опоздания не передан')
  assert.equal(currentText(NaN), 'Отклонение не передано')
  assert.equal(riskText(89.9), '90%')
  assert.equal(ageSeconds(1000, 19000), 18)
})
test('incident order is stable through small changes and changes only across severity bands', () => {
  const first = stableIncidents([], [alert(1, 91), alert(2, 89), alert(3, 85)])
  const small = stableIncidents(first, [alert(3, 86), alert(2, 91), alert(1, 89)])
  assert.deepEqual(small.map(v=>v.tripId), [1,2,3])
  assert.equal(small[0].critical,true)
  assert.equal(small[1].critical,false)
  const major = stableIncidents(small, [alert(1, 86), alert(2, 94), alert(3, 87)])
  assert.deepEqual(major.map(v=>v.tripId), [2,1,3])
  assert.equal(major[0].critical,true)
  assert.equal(major[1].critical,false)
  const removed = stableIncidents(major,[alert(1,86),alert(3,88)])
  assert.deepEqual(removed.map(v=>v.tripId),[1,3])
})
test('display preferences survive roundtrip and invalid storage falls back safely', () => {
  const custom = { ...DEFAULT_DISPLAY, palette:'custom', colors:{...DEFAULT_DISPLAY.colors, high:'#123456'}, lowRisk:false, density:'comfortable' }
  assert.deepEqual(parseDisplay(JSON.stringify(custom)),custom)
  assert.deepEqual(parseDisplay('broken'),DEFAULT_DISPLAY)
  assert.deepEqual(parseDisplay(null),DEFAULT_DISPLAY)
  assert.equal(parseDisplay(JSON.stringify({...custom,colors:{high:'url(bad)'}})).colors.high,DEFAULT_DISPLAY.colors.high)
  assert.deepEqual(parseDisplay(JSON.stringify({...DEFAULT_DISPLAY,palette:'colorblind'})).colors,PALETTES.colorblind)
})
