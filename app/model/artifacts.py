"""Загрузка всего, что нужно для инференса: модель, исторический профиль перегонов,
справочники маршрутов и индекс расписания.

Единая точка, которой пользуются и API (service/risk_service.py), и пакетный экспорт
дашборда (dashboard_export.py) — без дублирования кода загрузки моделей и справочников.
"""
import pickle
from dataclasses import dataclass
from pathlib import Path

from app.config import MODELS
from app.data_sources import processed_repository as repo
from app.engine.stream_state import load_schedule_index
from app.model.predictor import DelayPredictor


@dataclass
class ModelArtifacts:
    predictor: DelayPredictor
    hist_profile: dict
    schedule: dict
    route_mode: dict
    route_name: dict
    stop_name: dict

    @classmethod
    def load(cls, models_dir: Path = MODELS) -> "ModelArtifacts":
        predictor = DelayPredictor.load(models_dir / "delay_catboost.cbm")
        with open(models_dir / "hist_profile.pkl", "rb") as fh:
            hist_profile = pickle.load(fh)
        routes = repo.read_routes()
        stops = repo.read_stops()
        return cls(
            predictor=predictor,
            hist_profile=hist_profile,
            schedule=load_schedule_index(repo.read_stop_times()),
            route_mode=repo.route_mode_map(routes),
            route_name=repo.route_name_map(routes),
            stop_name=dict(zip(stops.stop_id, stops.stop_name)),
        )
