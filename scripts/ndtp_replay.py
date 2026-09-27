"""Воспроизводит traffic.csv организаторов в TCP-приёмник NDTP.

Команда из Docker-чеклиста:
python scripts/ndtp_replay.py --host backend --wait 120 --start 06:00 --minutes 1080 --speed 10
"""

import argparse
import math
import socket
import struct
import time
from pathlib import Path

import pandas as pd

from app.data_sources.ndtp_protocol import crc16_modbus
from ml_service.ids import unit_id_for_trip
from scripts.telemetry_features import to_ts

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "hackathon"


def _wire_crc(payload: bytes) -> int:
    crc = crc16_modbus(payload)
    return ((crc & 0xFF) << 8) | (crc >> 8)


def _frame(unit_id: int, service_id: int, nph_type: int, body: bytes) -> bytes:
    payload = struct.pack("<HHHI", service_id, nph_type, 1, 1) + body
    return struct.pack("<HHHHBIH", 0x7E7E, len(payload), 0, _wire_crc(payload), 0x02, unit_id, 0) + payload


def handshake(unit_id: int) -> bytes:
    body = struct.pack("<HHHIII", 6, 2, 0, unit_id, 65535, 0)
    return _frame(unit_id, 0, 100, body)


def realtime(unit_id: int, timestamp: int, lon: float, lat: float, speed: float, valid: bool) -> bytes:
    dop = (int(lat >= 0) << 5) | (int(lon >= 0) << 6) | (int(valid) << 7)
    nav = struct.pack(
        "<IIIBBHHHHHBB",
        int(timestamp),
        round(abs(lon) * 1e7),
        round(abs(lat) * 1e7),
        dop,
        200,
        max(0, min(65535, round(speed))),
        max(0, min(65535, round(speed))),
        0,
        0,
        150,
        12,
        10,
    )
    return _frame(unit_id, 1, 101, bytes([0, 0]) + nav)


def parse_clock(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("время должно иметь формат HH:MM")
    return hour * 3600 + minute * 60


def find_traffic(data_root: Path, part: str | None) -> Path:
    parts = [part] if part else ["validate", "test", "train"]
    for candidate in parts:
        path = data_root / str(candidate) / "traffic.csv"
        if path.exists():
            return path
    expected = ", ".join(str(data_root / str(candidate) / "traffic.csv") for candidate in parts)
    raise FileNotFoundError(f"traffic.csv не найден; проверены: {expected}")


def load_window(path: Path, start_s: int, duration_s: int, tz_offset_s: int) -> pd.DataFrame:
    columns = ["tr_id", "event_time", "location_valid", "lon", "lat", "speed"]
    frame = pd.read_csv(path, usecols=columns, dtype={"tr_id": str})
    frame["timestamp"] = to_ts(frame["event_time"])
    local = frame["timestamp"] + tz_offset_s
    frame["service_day"] = local // 86400
    frame["second_of_day"] = local % 86400
    valid_days = frame.loc[
        (frame["second_of_day"] >= start_s) & (frame["second_of_day"] < start_s + duration_s),
        "service_day",
    ]
    if valid_days.empty:
        raise ValueError(f"в {path} нет телеметрии в выбранном окне")
    day = int(valid_days.iloc[0])
    selected = frame[
        (frame["service_day"] == day)
        & (frame["second_of_day"] >= start_s)
        & (frame["second_of_day"] < start_s + duration_s)
    ].copy()
    selected["location_valid"] = selected["location_valid"].astype(str).str.lower().eq("true")
    return selected.sort_values("timestamp", kind="stable")


def connect(host: str, port: int, wait_s: int) -> socket.socket:
    deadline = time.monotonic() + wait_s
    while True:
        try:
            return socket.create_connection((host, port), timeout=5)
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)


def play(frame: pd.DataFrame, host: str, port: int, speed: float, wait_s: int) -> None:
    sent_units: set[int] = set()
    first_timestamp: int | None = None
    started = time.monotonic()
    with connect(host, port, wait_s) as connection:
        for row in frame.itertuples(index=False):
            timestamp = int(row.timestamp)
            if first_timestamp is None:
                first_timestamp = timestamp
            due = (timestamp - first_timestamp) / speed
            delay = due - (time.monotonic() - started)
            if delay > 0:
                time.sleep(delay)
            unit_id = unit_id_for_trip(row.tr_id)
            if unit_id not in sent_units:
                connection.sendall(handshake(unit_id))
                sent_units.add(unit_id)
            lon = 0.0 if math.isnan(float(row.lon)) else float(row.lon)
            lat = 0.0 if math.isnan(float(row.lat)) else float(row.lat)
            speed_kmh = 0.0 if math.isnan(float(row.speed)) else float(row.speed)
            connection.sendall(realtime(unit_id, timestamp, lon, lat, speed_kmh, bool(row.location_valid)))
    print(f"NDTP replay завершён: {len(frame):,} пакетов, {len(sent_units):,} машин")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay traffic.csv через NDTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9201)
    parser.add_argument("--wait", type=int, default=120, help="сколько секунд ждать backend")
    parser.add_argument("--start", default="06:00")
    parser.add_argument("--minutes", type=int, default=1080)
    parser.add_argument("--speed", type=float, default=10.0)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--part", choices=["validate", "test", "train"])
    parser.add_argument("--tz-offset", type=int, default=int(__import__("os").environ.get("NDTP_PLAN_TZ_OFFSET_S", "0")))
    args = parser.parse_args()
    if args.speed <= 0 or args.minutes <= 0:
        parser.error("--speed и --minutes должны быть больше нуля")
    traffic = find_traffic(args.data_root, args.part)
    rows = load_window(traffic, parse_clock(args.start), args.minutes * 60, args.tz_offset)
    print(f"NDTP replay: {traffic}, строк {len(rows):,}, ускорение x{args.speed:g}")
    play(rows, args.host, args.port, args.speed, args.wait)


if __name__ == "__main__":
    main()
