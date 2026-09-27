# Примеры запросов и ответов

Ответы получены на текущем коде: Live — на треках validate, поданных через NDTP (идентификаторы машин, адреса остановок и координаты в Live-примерах заменены условными); Симуляция — на записанном дне 3 сентября 2026 года. Длинные массивы сокращены. Полная схема — [openapi.json](openapi.json), описание полей — раздел 5 технической документации.

## Готовность

```http
GET /api/health
```

```json
{
  "ok": true,
  "sources": {
    "replay": {"ready": true, "error": null},
    "live": {"ready": true, "error": null},
    "ndtp": {"ready": true, "error": null},
    "forecast": {"ready": true, "error": null}
  },
  "tripsInSchedule": 28537
}
```

`ndtp` — приемник NDTP слушает порт; `forecast` — загружены модели и данные хакатона для прогноза по потоку; `replay` — есть записанный день; `live` — модель событий `POST /api/events`. При неготовом источнике ответ остается 200: в `error` — причина.

## Live-срез

```http
GET /api/live/snapshot
```

```json
{
  "clock": "08:28",
  "tracked": 14,
  "kpi": [
    {"key": "onLine", "label": "ТС на связи (NDTP)", "value": "14"},
    {"key": "high", "label": "высокий риск через 10–15 мин", "tone": "high", "value": "2"},
    {"key": "late", "label": "уже опаздывают", "value": "0"},
    {"key": "unmatched", "label": "не сопоставлено с расписанием", "value": "2",
     "hint": "Машины из потока без расписания: видны на карте, прогноз по ним не строится"}
  ],
  "alerts": [
    {
      "tripId": 100001, "route": "tr-001", "mode": "unknown", "dest": "",
      "stop": "ул. Примерная, д.1", "delay": 1.8, "risk": 77,
      "currentTime": "08:28", "forecastStop": "ул. Примерная, д.1",
      "scheduledArrival": "08:39", "expectedArrival": "08:41",
      "expectedDelay": 2.4, "forecastDelay": 2.4, "forecastMinutes": 13,
      "averageSpeed": 13.0,
      "forecastReason": "Много остановок до цели (8); уже отстаёт от графика на 105 с"
    }
  ],
  "vehicles": [
    {"vehicleId": 100002, "tripId": 100002, "route": "tr-002", "mode": null,
     "lat": 55.750000, "lon": 37.600000, "speed": 13, "course": 317,
     "risk": 51, "level": 1, "delay": 1.3, "updatedAt": 1767702597000},
    {"vehicleId": 100003, "tripId": 100003, "route": "tr-003", "mode": null,
     "lat": 55.760000, "lon": 37.610000, "speed": 0, "course": 24,
     "risk": null, "level": null, "delay": null, "updatedAt": 1767702588000}
  ],
  "trips": {
    "100002": {
      "found": true, "onLine": true, "tripId": 100002,
      "route": "tr-002", "routeName": "ТС tr-002", "mode": "unknown",
      "currentTime": "12:29", "stop": "просп. Условный, д.2",
      "forecastStop": "просп. Условный, д.2",
      "scheduledArrival": "12:42", "expectedArrival": "12:43",
      "expectedDelay": 2.0, "forecastDelay": 2.0, "forecastMinutes": 14,
      "averageSpeed": 13.0, "risk": 51, "level": 1, "delay": 1.3,
      "forecastReason": "Много остановок до цели (9); уже отстаёт от графика на 80 с"
    },
    "100003": {
      "found": true, "onLine": true, "tripId": 100003,
      "route": "tr-003", "routeName": "ТС tr-003", "mode": "unknown",
      "currentTime": "12:29", "averageSpeed": 0.0, "risk": null,
      "forecastReason": "Через 10–15 мин по расписанию нет остановки: рейс заканчивается или перерыв"
    }
  }
}
```

Тревога и карточки взяты из двух моментов потока (08:28 и 12:29). `vehicleId` и `tripId` — `unit_id` терминала, `route` — `tr_id` из данных хакатона. `delay` — текущее отставание в минутах (оценка `cur_dev_s`), `forecastDelay` — прогноз отклонения на остановке `forecastStop`, `risk` — вероятность опоздания больше 2 минут, %. `level`: 0 — низкий, 1 — средний, 2 — высокий, `null` — прогноза нет; причина — в `forecastReason` карточки.

## Приемник NDTP

```http
GET /api/live/units
```

```json
{
  "listening": true, "host": "0.0.0.0", "port": 9201, "error": null,
  "stats": {"connections": 1, "frames": 6, "fixes": 5, "ignored": 1, "crc_errors": 0},
  "units": [
    {"unitId": 100002, "connected": true, "remote": "127.0.0.1:63866", "packets": 5,
     "lastSeenSec": 0.5,
     "position": {"lon": 37.600000, "lat": 55.750000, "valid": true,
                  "gpsTime": 1767702657, "speed": 13, "course": 317}}
  ]
}
```

Ответ снят с одним терминалом, приславшим handshake и пять отметок. `ignored` — кадры без навигации (handshake). Растущий `crc_errors` означает, что терминал считает контрольную сумму иначе.

## Кадр записанного дня

```http
GET /api/replay/frame?t=510&trip=7956
```

```json
{
  "t": 510.0, "clock": "08:30", "raining": false,
  "kpi": [
    {"key": "onLine", "label": "на линии", "value": "710"},
    {"key": "high", "label": "высокий риск через 10–15 мин", "tone": "high", "value": "403"},
    {"key": "late", "label": "уже опаздывают", "value": "417"},
    {"key": "hit", "label": "ранних тревог сбылось", "value": "93%",
     "hint": "Из 741 тревог, выданных 20–30 минут назад машинам без опоздания, сбылось 692"}
  ],
  "vehicles": {
    "id": [7956], "route": ["е41"], "mode": ["bus"],
    "lon": [37.20706], "lat": [56.00056], "level": [2], "risk": [81], "late": [0]
  },
  "slowSegments": [[5, 0, 1.5], [11, 0, 1.0], [418, 0, 1.5]],
  "alerts": [
    {
      "tripId": 7956, "route": "е41", "mode": "bus", "dest": "Метро «Ховрино»",
      "stop": "Северная", "delay": -0.5, "risk": 81, "currentTime": "08:30",
      "forecastStop": "Спортивная школа", "scheduledArrival": "08:37",
      "expectedArrival": "08:40", "forecastDelay": 3.9, "forecastMinutes": 11,
      "problemSegment": {"from": "Северная", "to": "М-н «Океан»", "index": 418, "excess": 1.5},
      "forecastReason": "Участок впереди обычно медленный в это время; замедление на участке впереди (по другим машинам)"
    }
  ],
  "trip": {
    "found": true, "onLine": true, "route": "е41", "routeName": "Северная - Метро «Ховрино»",
    "mode": "bus", "currentStopIndex": 0, "stop": "Северная", "delay": -0.5,
    "risk": 81, "level": 2, "outcome": null,
    "next": [{"stop": "М-н «Океан»", "plan": "08:30"}, {"stop": "М-н «Товары для дома»", "plan": "08:32"},
             {"stop": "Спортивная школа", "plan": "08:37"}, {"stop": "Московский просп.", "plan": "08:40"}],
    "forecastStop": "Спортивная школа", "forecastDelay": 3.9, "expectedArrival": "08:40",
    "forecastReason": "Участок впереди обычно медленный в это время; замедление на участке впереди (по другим машинам)"
  }
}
```

В ответе 710 машин и 103 медленных перегона; показаны одна машина и три перегона. Медленный перегон — `[индекс, ступень 0/1, превышение плана в минутах]`. `t` — минуты от начала служебных суток. Машины приходят колонками: `id[i]`, `lon[i]`, `level[i]` относятся к одной машине. Без `trip` поле `trip` равно `null`.

## Метаданные дня и шкала времени

```http
GET /api/replay/day
```

```json
{
  "date": "2026-09-03", "dow": 3,
  "rain": {"level": 0.0, "start": 0.0, "end": 0.0},
  "threshold": 3.0, "tMin": 250.7, "tMax": 1622.9,
  "horizonLabel": "10–15 мин",
  "riskLevels": {"mid": 0.3, "high": 0.6},
  "modes": [{"id": 0, "key": "bus"}, {"id": 1, "key": "tram"}, {"id": 2, "key": "trolley"}, {"id": 3, "key": "other"}],
  "trips": 15443,
  "network": {"stops": [[37.49794, 55.85306], "…"], "segments": [[0, 850], "…"]}
}
```

В сети 1 636 остановок и 1 691 перегон; координаты — `[долгота, широта]`.

```http
GET /api/replay/timeline?mode=bus
```

```json
{"tMin": 250.7, "tMax": 1622.9, "bins": [{"t": 480.0, "high": 240}, "…"], "ticks": [{"t": 300.0, "label": "05:00"}, {"t": 360.0, "label": "06:00"}, "…"], "rain": null}
```

## События и контекст

```http
POST /api/events
Content-Type: application/json

[{"trip_id": "<trip_id из расписания>", "route_id": "<route_id>", "direction_id": "0",
  "k": 0, "stop_id": "<stop_id>", "plan": 480.0, "fact": 481.2}]
```

```json
{"accepted": 1, "scored": 1}
```

`scored` — сколько событий получили прогноз: неизвестный рейс или рейс без цели прогноза дает 0. Без обязательного поля — 422.

```http
POST /api/context
Content-Type: application/json

{"rain": 0.7, "holiday": 1}
```

```json
{"ok": true}
```

## Ошибка неготового источника

```json
{
  "detail": {
    "what": "replay",
    "error": "FileNotFoundError: …",
    "hint": "Нет кэша записанного дня или он собран старой версией. Запустите python -m app.replay_build"
  }
}
```
