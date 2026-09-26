"""Live-срез для дашборда: позиции машин из потока NDTP + прогнозы RiskService.

Позиции и прогнозы — независимые источники. Машина видна на карте, как только от нее пришел
пакет, даже если модель еще не загружена или машина не сопоставлена с расписанием.

В пакете NDTP нет ни рейса, ни маршрута, ни остановки — только unitId, координаты, скорость и
курс. Пока привязки к расписанию (map matching) нет, каждая машина из потока — «контекстная»:
она показывается серой, без прогноза. Организаторы прямо предупреждают, что в телеметрии
будут ТС без расписания, и сервис не должен на них падать.
"""
from datetime import datetime

from app.data_sources.ndtp_protocol import Fix

UNMATCHED_REASON = "Прогноз строится только для ТС, сопоставленных с расписанием"


def _hhmm(unix_s: float) -> str:
    return datetime.fromtimestamp(unix_s).strftime("%H:%M")


def _vehicle(f: Fix) -> dict:
    return {
        "vehicleId": f.unit_id,
        "lat": f.lat, "lon": f.lon,
        "speed": f.speed, "course": f.course,
        # Нет привязки к рейсу — нет ни маршрута, ни риска. level=None карта рисует как «нет прогноза».
        "route": None, "mode": None, "risk": None, "level": None, "delay": None,
        "updatedAt": int(f.received_at * 1000),
    }


def _card(f: Fix) -> dict:
    # level не задается: у TripPanel level=3 означает «рейс скоро завершится», здесь это неправда.
    return {
        "found": True, "onLine": True, "tripId": f.unit_id,
        "route": "—", "routeName": "Не сопоставлено с расписанием", "mode": "unknown",
        "risk": None, "currentTime": _hhmm(f.gps_time),
        "averageSpeed": f.speed, "forecastReason": UNMATCHED_REASON,
    }


def _kpi_value(risk: dict | None, key: str) -> str:
    return next((k["value"] for k in (risk or {}).get("kpi", []) if k["key"] == key), "0")


def live_snapshot(fixes: list[Fix], risk: dict | None) -> dict:
    """fixes — свежие отметки из NDTP; risk — RiskService.snapshot() или None, если модель
    недоступна. Формат совпадает с тем, что фронтенд уже умеет рисовать (LiveSnapshot)."""
    return {
        "clock": datetime.now().strftime("%H:%M"),
        "tracked": len(fixes),
        "kpi": [
            {"key": "onLine", "label": "ТС на связи (NDTP)", "value": str(len(fixes))},
            {"key": "high", "label": "высокий риск через 10–15 мин", "tone": "high",
             "value": _kpi_value(risk, "high")},
            {"key": "late", "label": "уже опаздывают", "value": _kpi_value(risk, "late")},
            {"key": "unmatched", "label": "не сопоставлено с расписанием", "value": str(len(fixes)),
             "hint": "Машины из потока без привязки к рейсу: видны на карте, прогноз по ним не строится"},
        ],
        "alerts": (risk or {}).get("alerts", []),
        "vehicles": [_vehicle(f) for f in fixes],
        "trips": {f.unit_id: _card(f) for f in fixes},
    }
