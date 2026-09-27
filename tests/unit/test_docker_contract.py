"""Docker-обвязка соответствует чеклисту сборки: сервисы, команды, порты, тома, секреты."""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_compose_services_ports_and_volumes() -> None:
    compose = read("compose.yaml")
    for service in ("ml:", "backend:", "web:", "player:"):
        assert service in compose
    assert "ml_service.server:app --host 0.0.0.0 --port 8100" in compose
    assert "app.api:app --host 0.0.0.0 --port 8000 --workers 1" in compose
    assert "ML_URL: http://ml:8100" in compose
    assert "NDTP_HOST: 0.0.0.0" in compose
    assert '"9201:9201"' in compose and '"8000:80"' in compose
    assert compose.count("./data/hackathon:/app/data/hackathon:ro") == 2      # ml и player
    for arg in ("--host backend", "--wait 120", "--start 06:00", "--minutes 1080", "--speed 10"):
        assert arg in compose
    # эмулятор организаторов — только профилем: его образа нет в реестре, без профиля up не должен его трогать
    assert 'profiles: ["emulator"]' in compose and "pull_policy: never" in compose
    assert "--target backend:9201" in compose


def test_images_and_nginx() -> None:
    python_image, web_image, nginx = read("Dockerfile"), read("Dockerfile.web"), read("docker/nginx.conf")
    assert "FROM python:3.12-slim" in python_image
    for directory in ("app/", "ml_service/", "scripts/", "models/", "reports/", "data/processed/"):
        assert f"COPY --chown=app:app {directory}" in python_image
    assert "data/hackathon" not in python_image.split("COPY")[-1]   # данные организаторов — только томом
    assert "FROM node:20" in web_image and "npm ci" in web_image and "npm run build" in web_image
    assert "ARG VITE_YANDEX_MAPS_API_KEY" in web_image
    assert "try_files $uri $uri/ /index.html" in nginx
    for path in ("location /api/", "location = /docs", "location = /openapi.json"):
        assert path in nginx


def test_secrets_and_build_context() -> None:
    ignored = set(read(".dockerignore").splitlines())
    assert {"venv/", "web/node_modules/", "web/dist/", "data/raw/", "data/hackathon/",
            "data/processed/features*", "data/processed/fact/", "catboost_info/", "submissions/",
            ".git/", "web/test-results/"} <= ignored
    assert {".env", "web/.env"} <= ignored          # ключ попадает в сборку только build-arg'ом
    assert ".env" in read(".gitignore").splitlines()
    assert "VITE_YANDEX_MAPS_API_KEY=" in read(".env.example")


def test_organizers_data_is_never_committed() -> None:
    """Данные организаторов (data/hackathon/) и исходники data.mos.ru (data/raw/) в git не хранятся —
    даже через git add -f. Этот тест ловит такой коммит в pre-push и CI."""
    import shutil
    import subprocess
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("не git-репозиторий")
    tracked = subprocess.run(["git", "ls-files", "data/hackathon", "data/raw"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.split()
    assert tracked == [], f"в git попали данные организаторов: {tracked[:5]}"
