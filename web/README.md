# Контроль движения — frontend

React + TypeScript + Vite. Backend endpoints не меняются; все HTTP-запросы находятся в `src/api/client.ts`.

## Запуск

```sh
cd web
npm install
cp .env.example .env
npm run dev
```

В `web/.env`:

```dotenv
VITE_YANDEX_MAPS_API_KEY=ваш_ключ_JavaScript_API
VITE_USE_MOCKS=true
```

Перезапустите Vite после изменения `.env`. Параметры Vite подставляются при сборке. Для production настройте их **до** `npm run build`. `.env` исключён из Git. Ключ JavaScript API используется в браузере и виден посетителю; ограничения доменов задаются в кабинете Yandex Maps.

- `VITE_USE_MOCKS=true`: полностью синтетические 24 ТС, 6 маршрутов, риски, прогнозы, метрики и Live-поток. Backend не нужен. На экране всегда есть `DEMO DATA`.
- `VITE_USE_MOCKS=false`: существующий backend; Vite проксирует `/api` на `http://127.0.0.1:8000`. При необходимости адрес можно переопределить через `VITE_API_BASE`.
- Без ключа или при ошибке загрузки Yandex Maps работает резервная Canvas-схема, если есть координаты. Ошибка карты не блокирует панель и воспроизведение.

## Карта и данные

Yandex Maps API v3 подключается один раз через `src/maps/yandex.ts`. `TransportMap` использует `YMapDefaultSchemeLayer` для географической подложки, `YMapFeature` для маршрутной сети и проблемных участков, `YMapMarker` для ТС. Маркеры обновляются по ID без пересоздания карты. Существующий `MapCanvas` сохранён как самостоятельная резервная схема; у него собственная проекция, поэтому он не накладывается на Yandex Maps.

Официальная документация: [YMap](https://yandex.com/maps-api/docs/js-api/map/YMap.html), [YMapMarker](https://yandex.com/maps-api/docs/js-api/object/markers/YMapMarker.html).

Replay: старт/пауза, скорости ×15/×60/×300, перемотка мышью и клавиатурой, фильтры транспорта и высокого риска. Выбор ТС ставит Replay на паузу для просмотра подробностей. Запросы кадров выполняются последовательно, даже при медленном backend.

Текущий production `/api/live/snapshot` не содержит координат и подробного прогноза. Интерфейс честно показывает доступные KPI и alerts, а для карты — объяснение отсутствия координат. Неизвестные горизонт/будущее отклонение не подменяются синтетическими значениями. В Demo Live есть синтетические координаты и полные карточки.

## Проверки

```sh
npm run build
node --experimental-strip-types --test tests/demo.test.mjs
```

Для тестов нужен Node.js 22.6+. Проверяются целостность синтетической сети, соответствие тревог маркерам и карточкам, фильтры, движение, изменение риска и согласованность Timeline.
