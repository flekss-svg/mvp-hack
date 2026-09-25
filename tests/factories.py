from __future__ import annotations

import struct

import numpy as np

from app.service.replay_service import KEY_SPAN, ReplayDay


def make_replay_day() -> ReplayDay:
    """Small deterministic day shared by unit, API and browser tests."""
    ev_trip = np.array([0, 0], dtype=np.int32)
    ev_fact = np.array([480.0, 490.0], dtype=np.float64)
    return ReplayDay(
        date="2026-09-03",
        dow=3,
        rain={"level": 0.0, "start": 0.0, "end": 0.0},
        threshold=3.0,
        t_min=480.0,
        t_max=490.0,
        stop_lon=np.array([37.61, 37.62], dtype=np.float32),
        stop_lat=np.array([55.75, 55.76], dtype=np.float32),
        stop_names=["Начальная", "Конечная"],
        seg_a=np.array([0], dtype=np.int32),
        seg_b=np.array([1], dtype=np.int32),
        ev_stop=np.array([0, 1], dtype=np.int32),
        ev_plan=np.array([480.0, 487.0], dtype=np.float64),
        ev_fact=ev_fact,
        ev_risk=np.array([0.8, -1.0], dtype=np.float32),
        ev_target=np.array([1, -1], dtype=np.int64),
        ev_trip=ev_trip,
        ev_key=ev_trip * KEY_SPAN + ev_fact,
        trip_off=np.array([0, 2], dtype=np.int64),
        trip_route=np.array([0], dtype=np.int32),
        trip_mode=np.array([0], dtype=np.int32),
        route_short=["42"],
        route_long=["Тестовый маршрут"],
        modes=["bus", "tram", "trolley", "other"],
        trav_t=np.array([490.0], dtype=np.float64),
        trav_seg=np.array([0], dtype=np.int32),
        trav_excess=np.array([3.0], dtype=np.float32),
    )


class FakeLiveService:
    schedule_size = 1

    def __init__(self) -> None:
        self.context = {"rain": 0.0, "holiday": 0}

    def snapshot(self) -> dict:
        return {"clock": "08:05", "tracked": 1, "kpi": [], "alerts": []}

    def ingest_events(self, events: list[dict]) -> int:
        return len(events)

    def set_context(self, rain: float, holiday: int) -> None:
        self.context = {"rain": rain, "holiday": holiday}

    def current_risk(self, limit: int, min_risk: float) -> list[dict]:
        if not limit or min_risk > 0.8:
            return []
        return [{"trip_id": "trip-1", "risk": 0.8}]


# ---------- NDTP: пакеты собираются по спецификации эмулятора, независимо от боевого кода ----------

def crc16_reference(data: bytes) -> int:
    """CRC-16/Modbus побитово, без таблицы — сверка с табличной реализацией в ndtp_protocol."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def ndtp_frame(unit_id: int, service_id: int, nph_type: int, body: bytes, crc_delta: int = 0) -> bytes:
    payload = struct.pack("<HHHI", service_id, nph_type, 1, 1) + body
    crc = (crc16_reference(payload) + crc_delta) & 0xFFFF
    swapped = ((crc & 0xFF) << 8) | (crc >> 8)
    return struct.pack("<HHHHBIH", 0x7E7E, len(payload), 0, swapped, 0x02, unit_id, 0) + payload


def ndtp_handshake(unit_id: int) -> bytes:
    return ndtp_frame(unit_id, 0, 100, struct.pack("<HHHIII", 6, 2, 0, unit_id, 65535, 0))


def ndtp_realtime(unit_id: int, lat: float = 55.7551234, lon: float = 37.617321, *, north=True,
                  east=True, valid=True, speed=40, course=90, ts=1_780_000_000, crc_delta=0) -> bytes:
    dop = (north << 5) | (east << 6) | (valid << 7)
    nav = struct.pack("<IIIBBHHHHHBB", ts, round(abs(lon) * 1e7), round(abs(lat) * 1e7), dop, 200,
                      speed, speed + 5, course, 0, 150, 12, 10)
    # после навигации — ячейка ДУТ (type 8): приемник должен ее проигнорировать
    fuel = bytes([8, 0]) + struct.pack("<BHHB", 0, 300, 120, 20)
    return ndtp_frame(unit_id, 1, 101, bytes([0, 0]) + nav + fuel, crc_delta)
