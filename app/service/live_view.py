"""Live-срез для дашборда: позиции машин из потока NDTP + прогнозы.

Позиции и прогнозы — независимые источники. Машина видна на карте, как только от нее пришел
пакет, даже если модель еще не загружена или машина не сопоставлена с расписанием.

В пакете NDTP нет ни рейса, ни маршрута, ни остановки — только unitId, координаты, скорость и
курс. Машины, у которых есть расписание (unit_id -> tr_id, см. ml_service/live.py), получают прогноз
задержки на модели хакатона; остальные — «контекстные»: серые, без прогноза. Организаторы прямо
предупреждают, что в телеметрии будут ТС без расписания, и сервис не должен на них падать.

forecasts=None или пуст — прогнозов нет (прогнозист не загрузился или поток еще не пришел): все машины
контекстные, а тревоги и KPI берутся из RiskService, как раньше.
"""
import math
from datetime import datetime, timezone

from app.config import LATE_THRESHOLD_MIN, PLAN_TZ_OFFSET_S, RISK_LEVELS
from app.data_sources.ndtp_protocol import Fix

UNMATCHED_REASON = "Прогноз строится только для ТС, сопоставленных с расписанием"
STATUS_REASON = {
    "few_pings": "Мало отметок для прогноза: машина только вышла на связь",
    "no_target": "Через 10–15 мин по расписанию нет остановки: рейс заканчивается или перерыв",
    "no_signal": "Давно нет отметок от машины: прогноз не выдается",
}
ALERT_LIMIT = 30


def _hhmm_plan(t: float) -> str:
    """Время в шкале расписания: там секунды от эпохи означают показания часов в файле, без пояса."""
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%H:%M")


def _num(x, ndigits: int | None = None):
    """Число для JSON: NaN и inf в ответ API попадать не должны (сериализация падает)."""
    if x is None or not math.isfinite(x):
        return None
    return round(x, ndigits) if ndigits is not None else x


def _level(p_late: float) -> int:
    return 2 if p_late >= RISK_LEVELS[1] else 1 if p_late >= RISK_LEVELS[0] else 0


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
        # та же шкала времени, что у машин с прогнозом и у часов потока (время расписания, без пояса ПК)
        "risk": None, "currentTime": _hhmm_plan(f.gps_time + PLAN_TZ_OFFSET_S),
        "averageSpeed": f.speed, "forecastReason": UNMATCHED_REASON,
    }


def _forecast_fields(fc: dict) -> dict:
    """Поля прогноза в формате записанного дня (ForecastContext): задержки в минутах со знаком."""
    delay_min = fc["delay_s"] / 60
    arrival = fc["target_plan"] + fc["delay_s"]
    reasons = "; ".join(fc["reasons"])
    out = {
        "currentTime": _hhmm_plan(fc["T"]),
        "forecastStop": fc["target_stop"] or fc["target_stop_id"],
        "scheduledArrival": _hhmm_plan(fc["target_plan"]),
        "expectedArrival": _hhmm_plan(arrival),
        "expectedDelay": round(delay_min, 1), "forecastDelay": round(delay_min, 1),
        "forecastMinutes": max(1, round((arrival - fc["T"]) / 60)),
        "averageSpeed": _num(fc["speed"]),
    }
    if reasons:
        out["forecastReason"] = reasons[0].upper() + reasons[1:]
    return out


def _route_card(fc: dict) -> dict:
    """Номер и название маршрута. В данных хакатона их нет — ML восстанавливает по остановкам
    расписания (ml_service/routes.py); не опознан — так и пишем, tr_id за маршрут не выдаем."""
    track = " · рейс определен по треку" if fc.get("matched_by") == "track" else ""
    name = fc.get("route_name") or "Номер маршрута не определен"
    return {"route": fc.get("route") or "—", "routeName": f"{name} · tr_id {fc['tr_id']}{track}",
            "mode": fc.get("mode") or "unknown"}


def _matched_vehicle(f: Fix, fc: dict) -> dict:
    v = _vehicle(f)
    v["route"], v["mode"] = fc.get("route"), fc.get("mode")
    if fc["status"] == "ok":
        v.update(tripId=f.unit_id, risk=round(fc["p_late"] * 100), level=_level(fc["p_late"]),
                 delay=_num(fc["cur_dev_s"] / 60 if fc["cur_dev_s"] is not None else None, 1))
    else:
        v["tripId"] = f.unit_id
    return v


def _matched_card(f: Fix, fc: dict) -> dict:
    card = {"found": True, "onLine": True, "tripId": f.unit_id, **_route_card(fc),
            "averageSpeed": _num(fc["speed"]), "currentTime": _hhmm_plan(fc["T"])}
    if fc["status"] != "ok":
        return {**card, "risk": None, "forecastReason": STATUS_REASON[fc["status"]]}
    return {**card, **_forecast_fields(fc), "stop": fc["target_stop"] or fc["target_stop_id"],
            "risk": round(fc["p_late"] * 100), "level": _level(fc["p_late"]),
            "delay": _num(fc["cur_dev_s"] / 60 if fc["cur_dev_s"] is not None else None, 1)}


def _alert(f: Fix, fc: dict) -> dict:
    route = _route_card(fc)
    return {"tripId": f.unit_id, "route": route["route"], "mode": route["mode"], "dest": "",
            "stop": fc["target_stop"] or fc["target_stop_id"],
            "delay": _num(fc["cur_dev_s"] / 60 if fc["cur_dev_s"] is not None else 0.0, 1),
            "risk": round(fc["p_late"] * 100), **_forecast_fields(fc)}


def _kpi_value(risk: dict | None, key: str) -> str:
    return next((k["value"] for k in (risk or {}).get("kpi", []) if k["key"] == key), "0")


def live_snapshot(fixes: list[Fix], risk: dict | None, forecasts: dict | None = None) -> dict:
    """fixes — свежие отметки из NDTP; risk — RiskService.snapshot() или None, если модель
    недоступна; forecasts — unit_id -> прогноз (ml_service.live) или None, если прогнозиста нет.
    Формат совпадает с тем, что фронтенд уже умеет рисовать (LiveSnapshot)."""
    if not forecasts:      # прогнозиста нет или потока от машин с расписанием еще нет: тревоги — от RiskService
        return _context_only(fixes, risk)

    matched = [(f, forecasts[f.unit_id]) for f in fixes if f.unit_id in forecasts]
    context = [f for f in fixes if f.unit_id not in forecasts]
    ok = [(f, fc) for f, fc in matched if fc["status"] == "ok"]
    high = [(f, fc) for f, fc in ok if _level(fc["p_late"]) == 2]
    already_late = [(f, fc) for f, fc in ok if fc["cur_dev_s"] is not None and fc["cur_dev_s"] / 60 >= LATE_THRESHOLD_MIN]
    warn = sorted((p for p in high if p not in already_late), key=lambda p: -p[1]["p_late"])[:ALERT_LIMIT]
    # Часы дашборда — время потока: расписание привязано к дню данных, а не к «сейчас».
    clock = _hhmm_plan(max(fc["T"] for _, fc in matched)) if matched else datetime.now().strftime("%H:%M")
    return {
        "clock": clock,
        "tracked": len(fixes),
        "kpi": [
            {"key": "onLine", "label": "ТС на связи (NDTP)", "value": str(len(fixes))},
            {"key": "high", "label": "высокий риск через 10–15 мин", "tone": "high", "value": str(len(high))},
            {"key": "late", "label": "уже опаздывают", "value": str(len(already_late))},
            {"key": "unmatched", "label": "не сопоставлено с расписанием", "value": str(len(context)),
             "hint": "Машины из потока без расписания: видны на карте, прогноз по ним не строится"},
        ],
        "alerts": [_alert(f, fc) for f, fc in warn],
        "vehicles": [_matched_vehicle(f, fc) for f, fc in matched] + [_vehicle(f) for f in context],
        "trips": {**{f.unit_id: _matched_card(f, fc) for f, fc in matched}, **{f.unit_id: _card(f) for f in context}},
    }


def _context_only(fixes: list[Fix], risk: dict | None) -> dict:
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
