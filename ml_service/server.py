"""ML-модуль как отдельный HTTP-сервис: прием отметок потока и выдача прогнозов.

Backend (app/) пересылает сюда навигационные отметки NDTP пачками и забирает прогнозы по машинам.
Внутри — тот же LiveForecaster (ml_service/live.py): буфер отметок, map matching, признаки, модели,
причины. Сервис не зависит от app/ и может масштабироваться и переобучаться отдельно от backend.

Запуск: uvicorn ml_service.server:app --port 8100
    POST /fixes       пачка отметок -> сколько принято в буферы машин с рейсом
    GET  /forecasts   unit_id -> прогноз (как LiveForecaster.forecasts)
    GET  /health      загружены ли модели и данные
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .live import LiveForecaster, load_forecaster

log = logging.getLogger("uvicorn.error")
_forecaster: LiveForecaster | None = None
_error: str | None = None


class Fix(BaseModel):
    """Навигационная отметка; поля совпадают с app.data_sources.ndtp_protocol.Fix."""
    unit_id: int
    gps_time: int
    received_at: float = 0.0
    lon: float
    lat: float
    location_valid: bool
    speed: int = 0
    course: int = 0


def _load() -> None:
    global _forecaster, _error
    try:
        _forecaster = load_forecaster(tz_offset_s=int(os.environ.get("NDTP_PLAN_TZ_OFFSET_S", "0")))
        _error = None
    except Exception as e:  # noqa: BLE001 — причина уходит в /health
        _forecaster, _error = None, f"{type(e).__name__}: {e}"
        log.warning("модели не загружены: %s", _error)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(_load)
    yield


app = FastAPI(title="ML-модуль: прогноз задержек по потоку NDTP", lifespan=lifespan)


def _ready() -> LiveForecaster:
    if _forecaster is None:
        raise HTTPException(503, detail={"what": "forecast", "error": _error,
                                         "hint": "Положите data/hackathon и проверьте models/hackathon_v2_online*.cbm"})
    return _forecaster


@app.get("/health")
def health():
    return {"ready": _forecaster is not None, "error": _error,
            "units": len(_forecaster.units) if _forecaster else 0}


@app.post("/fixes")
def fixes(batch: list[Fix]):
    fc = _ready()
    return {"received": len(batch), "accepted": sum(fc.ingest(f) for f in batch)}


@app.get("/forecasts")
def forecasts():
    return {str(unit): fc for unit, fc in _ready().forecasts().items()}
