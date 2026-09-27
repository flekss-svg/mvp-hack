from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_compose_matches_required_service_contract() -> None:
    compose = read("compose.yaml")
    for service in ("ml:", "backend:", "web:", "player:"):
        assert service in compose
    assert "ml_service.server:app" in compose
    assert "app.api:app" in compose
    assert "ML_URL: http://ml:8100" in compose
    assert "NDTP_HOST: 0.0.0.0" in compose
    assert '"9201:9201"' in compose
    assert '"8000:80"' in compose
    assert "./data/hackathon:/app/data/hackathon:ro" in compose
    assert "--start 06:00" in compose
    assert "--minutes 1080" in compose
    assert "--speed 10" in compose


def test_images_and_nginx_match_required_contract() -> None:
    python_image = read("Dockerfile")
    web_image = read("Dockerfile.web")
    nginx = read("docker/nginx.conf")
    assert python_image.startswith("FROM python:3.12-slim")
    for directory in ("app/", "ml_service/", "scripts/", "models/", "reports/", "data/processed/"):
        assert directory in python_image
    assert "FROM node:20-alpine AS build" in web_image
    assert "npm ci" in web_image and "npm run build" in web_image
    assert "ARG VITE_YANDEX_MAPS_API_KEY" in web_image
    assert "try_files $uri $uri/ /index.html" in nginx
    for path in ("/api/", "/docs", "/openapi.json"):
        assert path in nginx


def test_dockerignore_and_secret_rules() -> None:
    ignored = set(read(".dockerignore").splitlines())
    required = {
        "venv/", "web/node_modules/", "web/dist/", "data/raw/", "data/hackathon/",
        "data/processed/features*", "data/processed/fact/", "catboost_info/", "submissions/",
        ".git/", "web/test-results/",
    }
    assert required <= ignored
    assert ".env" in read(".gitignore").splitlines()
    assert "VITE_YANDEX_MAPS_API_KEY=" in read(".env.example")
