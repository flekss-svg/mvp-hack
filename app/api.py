"""HTTP-слой: тонкий FastAPI поверх бизнес-логики в service/.

Весь дашборд собирается здесь, а не в браузере. Фронтенд (web/) запрашивает готовые
кадры, KPI и тревоги и только рисует их — в нем нет ни порогов риска, ни интерполяции
положения машин, ни распаковки данных.

Запуск (из корня репозитория):
    uvicorn app.api:app --reload

    GET  /api/health              — что доступно сервису прямо сейчас
    GET  /api/model               — качество модели (из reports/metrics.json)
    GET  /api/replay/day          — метаданные записанного дня + геометрия сети
    GET  /api/replay/frame        — кадр на момент t: машины, KPI, тревоги, медленные перегоны
    GET  /api/replay/timeline     — шкала времени: сколько машин с высоким риском по часам
    GET  /api/live/snapshot       — то же по форме, но из живого потока событий
    POST /api/events              — пачка событий «машина прошла остановку»
    POST /api/context             — погода/праздник на сегодня

Собранный фронтенд (web/dist) отдается статикой в корне — сервис и дашборд поднимаются
одной командой.
"""
import json
import logging
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import HORIZON_MIN, LATE_THRESHOLD_MIN, ML_URL, REPORTS, WEB_DIST
from app.engine.feature_definitions import FEATURE_DESCRIPTIONS
from app.model.artifacts import ModelArtifacts
from app.service.forecast_client import ForecastClient
from app.service.ndtp_server import NdtpServer
from app.service.replay_service import ReplayService
from app.service.risk_service import RiskService

_ndtp_log = logging.getLogger("ndtp")
_ndtp_log.setLevel(logging.INFO)
_ndtp_log.handlers = logging.getLogger("uvicorn").handlers
_ndtp_log.propagate = False

_forecast = ForecastClient(ML_URL)
_ndtp = NdtpServer(on_fix=_forecast.submit_fix if _forecast.enabled else None)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await _forecast.start()
    await _ndtp.start()
    yield
    await _ndtp.stop()
    await _forecast.close()


app = FastAPI(title="Предиктор задержек наземного транспорта", lifespan=lifespan)

# Дашборд в разработке живет на порту Vite и стучится сюда кросс-доменно.
# Для прода сузить allow_origins до конкретного адреса.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
# Кадры — это массивы координат; без сжатия они занимают в разы больше.
app.add_middleware(GZipMiddleware, minimum_size=1024)


class Lazy:
    """Артефакты грузятся при первом обращении, а не при импорте: сервис должен подниматься
    и тогда, когда данные еще не сгенерированы, — и внятно об этом сообщать."""

    def __init__(self, name: str, load: Callable, hint: str):
        self._name, self._load, self._hint = name, load, hint
        self._value = None
        self._error: str | None = None

    def get(self):
        if self._value is None:
            try:
                self._value = self._load()
                self._error = None
            except Exception as e:  # noqa: BLE001 — причину показываем диспетчеру как есть
                # не запоминаем неудачу навсегда: данные могут появиться, пока сервис работает
                self._error = f"{type(e).__name__}: {e}"
                raise HTTPException(503, detail={"what": self._name, "error": self._error,
                                                 "hint": self._hint})
        return self._value

    @property
    def ready(self) -> bool:
        try:
            self.get()
            return True
        except HTTPException:
            return False

    @property
    def error(self) -> str | None:
        return self._error


_live = Lazy("live", lambda: RiskService(ModelArtifacts.load()),
             "Нет обработанных данных или модели. Запустите ./run_all.sh")
_replay = Lazy("replay", ReplayService.load,
               "Нет кэша записанного дня. Запустите python -m app.replay_build")


def _mode_index(mode: str | None) -> int | None:
    if not mode or mode == "all":
        return None
    modes = _replay.get().day.modes
    if mode not in modes:
        raise HTTPException(400, detail=f"Неизвестный вид транспорта: {mode}")
    return modes.index(mode)


class Event(BaseModel):
    trip_id: str
    route_id: str
    direction_id: str
    k: int
    stop_id: str
    plan: float
    fact: float


class Context(BaseModel):
    rain: float = 0.0
    holiday: int = 0


@app.get("/api/health")
async def health():
    forecast = await _forecast.health()
    return {
        "ok": True,
        "sources": {
            "replay": {"ready": _replay.ready, "error": _replay.error},
            "live": {"ready": _live.ready, "error": _live.error},
            "ndtp": {"ready": _ndtp.listening, "error": _ndtp.error},
            "forecast": forecast,
        },
        "tripsInSchedule": _live.get().schedule_size if _live.ready else 0,
    }


@app.get("/api/model")
def model_quality():
    """Панель «Качество модели» — из reports/metrics.json, чтобы после переобучения дашборд
    обновлялся сам. Подписи признаков тоже приходят с сервера: у фронтенда своей копии нет."""
    path = REPORTS / "metrics.json"
    if not path.exists():
        raise HTTPException(503, detail={"what": "model", "error": "нет reports/metrics.json",
                                         "hint": "Запустите python -m app.model.training"})
    m = json.loads(path.read_text(encoding="utf-8"))
    early, base = m["early_warning"][0], m["early_warning"][1]
    fi = m.get("feature_importance", {})
    labels = {**FEATURE_DESCRIPTIONS, **m.get("feature_descriptions", {})}
    top = sorted(fi.items(), key=lambda kv: -kv[1])[:5]
    peak = top[0][1] if top else 1.0
    return {
        "horizon": f"{HORIZON_MIN[0]}–{HORIZON_MIN[1]} мин",
        "threshold": LATE_THRESHOLD_MIN,
        "recall": 70,
        "precision": round(early["precision_at_recall70"] * 100),
        "baselinePrecision": round(base["precision_at_recall70"] * 100),
        "prAuc": early["pr_auc"],
        "baselinePrAuc": base["pr_auc"],
        "testSize": m.get("n_test_early"),
        "features": [{"key": k, "label": labels.get(k, k), "importance": v,
                      "share": round(v / peak, 3) if peak else 0} for k, v in top],
    }


@app.get("/api/replay/day")
def replay_day():
    return _replay.get().day_info()


@app.get("/api/replay/frame")
def replay_frame(t: float, mode: str | None = None, min_level: int = 0, trip: int | None = None):
    """Все, что дашборд показывает на момент t. Если передан trip — вместе с его карточкой."""
    return _replay.get().frame(t, mode=_mode_index(mode), min_level=min_level, trip_id=trip)


@app.get("/api/replay/timeline")
def replay_timeline(mode: str | None = None):
    return _replay.get().timeline(mode=_mode_index(mode))


@app.get("/api/live/snapshot")
def live_snapshot():
    if _forecast.enabled:
        return _forecast.snapshot(_ndtp.snapshot())
    return _live.get().snapshot()


@app.get("/api/live/units")
def live_units():
    return _ndtp.snapshot()


@app.post("/api/events")
def events(batch: list[Event]):
    scored = _live.get().ingest_events([e.model_dump() for e in batch])
    return {"accepted": len(batch), "scored": scored}


@app.post("/api/context")
def set_context(c: Context):
    _live.get().set_context(rain=c.rain, holiday=c.holiday)
    return {"ok": True}


@app.get("/api/risk")
def risk(limit: int = 50, min_risk: float = 0.0):
    """Сырой срез прогнозов — для интеграций; дашборд берет готовый /api/live/snapshot."""
    return _live.get().current_risk(limit=limit, min_risk=min_risk)


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
