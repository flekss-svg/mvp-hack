"""Клиент выделенного ML-сервиса и готовый live-срез для дашборда."""

import logging
from datetime import datetime

import httpx

from app.config import LIVE_UNIT_TTL_S, ML_TIMEOUT_S, RISK_LEVELS
from app.data_sources.ndtp_protocol import Fix

log = logging.getLogger(__name__)


class ForecastClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.enabled = bool(self.base_url)
        self.ready = False
        self.error: str | None = None
        self._client: httpx.AsyncClient | None = None
        self._predictions: dict[int, dict] = {}

    async def start(self) -> None:
        if not self.enabled:
            return
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=ML_TIMEOUT_S)
        await self.health()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health(self) -> dict:
        if not self.enabled:
            return {"ready": False, "mode": "disabled", "error": "ML_URL не задан"}
        try:
            client = self._require_client()
            response = await client.get("/health")
            response.raise_for_status()
            payload = response.json()
            self.ready = bool(payload.get("ready"))
            self.error = payload.get("error")
            return {
                "ready": self.ready,
                "mode": "service",
                "dataReady": bool(payload.get("dataReady")),
                "error": self.error,
            }
        except (httpx.HTTPError, ValueError) as exc:
            self.ready = False
            self.error = f"{type(exc).__name__}: {exc}"
            return {"ready": False, "mode": "service", "error": self.error}

    async def submit_fix(self, fix: Fix) -> None:
        if not self.enabled or not fix.location_valid:
            return
        try:
            response = await self._require_client().post(
                "/predict",
                json={
                    "unit_id": fix.unit_id,
                    "event_time": fix.gps_time,
                    "lon": fix.lon,
                    "lat": fix.lat,
                    "speed": fix.speed,
                    "location_valid": fix.location_valid,
                },
            )
            response.raise_for_status()
            prediction = response.json()
            self._predictions[fix.unit_id] = prediction
            self.ready = True
            self.error = None
        except (httpx.HTTPError, ValueError) as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            log.warning("ML service request failed: %s", self.error)

    def snapshot(self, ndtp: dict) -> dict:
        active = [
            unit
            for unit in ndtp.get("units", [])
            if unit.get("position")
            and unit["position"].get("valid")
            and unit.get("lastSeenSec") is not None
            and unit["lastSeenSec"] <= LIVE_UNIT_TTL_S
        ]
        vehicles = {"id": [], "lon": [], "lat": [], "level": [], "risk": [], "late": []}
        alerts = []
        high = late = predicted = 0
        for unit in active:
            unit_id = unit["unitId"]
            position = unit["position"]
            forecast = self._predictions.get(unit_id, {})
            prediction_ready = bool(forecast.get("predictionReady"))
            risk = float(forecast.get("risk", -1)) if prediction_ready else -1.0
            delay_s = float(forecast.get("currentDelaySec", 0.0))
            level = 3 if risk < 0 else int(risk >= RISK_LEVELS[0]) + int(risk >= RISK_LEVELS[1])
            predicted += int(prediction_ready)
            high += int(level == 2)
            late += int(delay_s >= 180)
            vehicles["id"].append(unit_id)
            vehicles["lon"].append(position["lon"])
            vehicles["lat"].append(position["lat"])
            vehicles["level"].append(level)
            vehicles["risk"].append(-1 if risk < 0 else round(risk * 100))
            vehicles["late"].append(int(delay_s >= 180))
            if level == 2:
                alerts.append({
                    "tripId": unit_id,
                    "route": str(forecast.get("tripId", unit_id))[-6:],
                    "mode": "other",
                    "dest": str(forecast.get("targetStopId", "")),
                    "stop": "телеметрия NDTP",
                    "delay": round(delay_s / 60, 1),
                    "risk": round(risk * 100),
                })
        return {
            "clock": datetime.now().strftime("%H:%M"),
            "tracked": len(active),
            "kpi": [
                {"key": "onLine", "label": "машин в потоке", "value": str(len(active))},
                {"key": "high", "label": "высокий риск через 10–15 мин", "tone": "high", "value": str(high)},
                {"key": "late", "label": "уже опаздывают", "value": str(late)},
                {"key": "hit", "label": "прогноз готов", "value": f"{predicted}/{len(active)}"},
            ],
            "vehicles": vehicles,
            "alerts": sorted(alerts, key=lambda item: -item["risk"]),
        }

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("ForecastClient.start() не вызван")
        return self._client
