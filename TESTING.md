# Проверки проекта

## Быстрый старт на новом компьютере

Windows:

```powershell
.\scripts\setup-tests.ps1
.\scripts\test-all.ps1
```

Linux/macOS/Git Bash:

```bash
./scripts/setup-tests.sh
./scripts/test-all.sh
```

Setup-скрипт создаёт `venv`, устанавливает Python/npm-зависимости и Chromium для
Playwright, затем включает `.githooks/pre-push` только для текущего clone.

## Структура

```text
tests/
├── factories.py              маленькие общие фикстуры
├── unit/                     функции, адаптеры, engine и services без HTTP
├── integration/              FastAPI через TestClient
└── e2e/server.py             детерминированный full-stack сервер для Playwright

web/
├── src/**/*.test.ts(x)       Vitest-тесты рядом с компонентами и логикой
├── e2e/*.spec.ts             Playwright smoke/E2E
├── vitest.config.ts          frontend coverage gate
└── playwright.config.ts      запуск production build + FastAPI

scripts/
├── setup-tests.ps1/.sh       первичная настройка окружения
└── test-all.ps1/.sh          единая локальная проверка

.githooks/pre-push            локальная защита перед push
.github/workflows/tests.yml   независимая проверка в GitHub Actions
```

## Что проверяется перед каждым push

1. Backend unit-тесты: метрики, признаки, replay/live services, адаптеры GPS и
   data.mos.ru. Coverage накапливается в `.coverage`.
2. Backend integration: реальные `/api/...` endpoints, успешные ответы, `400`, `422`,
   POST-запросы. После этого проверяется общий backend coverage не ниже 80%.
3. Frontend unit/component tests: HTTP-клиент, hooks, состояния приложения и панелей;
   Vitest применяет отдельные thresholds.
4. Production build: строгий TypeScript и сборка Vite.
5. Smoke/E2E: настоящий FastAPI отдаёт production build; Chromium открывает страницу,
   проверяет основные endpoints, UI и отсутствие ошибок console/page.

E2E использует маленькую детерминированную replay-фикстуру. Поэтому тест работает на
чистом clone без `data/`, больших моделей и 15-минутного обучения.

## Отдельные команды

```powershell
python -m pytest tests/unit -m unit
python -m pytest tests/integration -m integration
npm.cmd --prefix web run test:run
npm.cmd --prefix web run build
npm.cmd --prefix web run test:e2e
```

Все Python warnings настроены как ошибки. `npm audit` должен возвращать ноль известных
уязвимостей. Сгенерированные `__pycache__`, coverage, build и Playwright artifacts
игнорируются Git и не должны попадать в commit.

## Перед отправкой в GitHub

```powershell
git status --short
.\scripts\test-all.ps1
git add .
git status --short
git commit -m "Add automated test pipeline"
git push
```

Перед `git add .` проверьте отдельно бинарные файлы в `models/`: они могли измениться после
локального обучения и не относятся к тестовой инфраструктуре.

## Следующие улучшения

- включить branch protection и требовать успешный workflow `tests` перед merge;
- добавить nightly workflow для `run_all.sh` и порогов качества ML-модели;
- добавить accessibility (`axe`) и visual regression для canvas-компонентов;
- добавить проверку обратной совместимости OpenAPI/JSON-контрактов.
