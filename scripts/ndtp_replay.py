"""Проигрыватель треков: отправляет телеметрию хакатона в приемник NDTP настоящими пакетами.

Эмулятор организаторов умеет только случайные или фиксированные точки, поэтому для демонстрации
live-режима с осмысленными прогнозами треки берутся из data/hackathon/<часть>/traffic.csv: те же
unit_id, координаты и время, что в выгрузке. Приемник (порт 9201) видит обычный поток NDTP.

Время потока — историческое (расписание привязано к дню данных), ускоренное в --speed раз.
Пакет NDTP хранит gps_time в секундах от эпохи. Выгрузка без часового пояса: если сервис запущен с
NDTP_PLAN_TZ_OFFSET_S=N, передайте тот же N в --tz-offset, тогда gps_time = время в файле − N.

Запуск (API должен уже работать):
    python scripts/ndtp_replay.py                       # validate, с 08:00, 2 часа, x30
    python scripts/ndtp_replay.py --start 12:30 --minutes 60 --speed 60 --units 10
    python scripts/ndtp_replay.py --hide-ids    # незнакомые терминалы: рейс определяется по треку
"""
import argparse
import asyncio
import struct
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.data_sources.ndtp_protocol import crc16_modbus
from ml_service.features import DATA, to_ts

SERVICE_GENERIC, SERVICE_NAV = 0, 1
NPH_CONN_REQUEST, NPH_REALTIME = 100, 101
HIDDEN_BASE = 900_000_000        # номера терминалов при --hide-ids: вне диапазона выгрузки


def frame(unit_id: int, service_id: int, nph_type: int, body: bytes) -> bytes:
    """Кадр NDTP: заголовок NPL + NPH + тело; CRC-16/Modbus по NPH и телу, байты в заголовке переставлены."""
    payload = struct.pack("<HHHI", service_id, nph_type, 1, 1) + body
    crc = crc16_modbus(payload)
    swapped = ((crc & 0xFF) << 8) | (crc >> 8)
    return struct.pack("<HHHHBIH", 0x7E7E, len(payload), 0, swapped, 0x02, unit_id, 0) + payload


def handshake(unit_id: int) -> bytes:
    return frame(unit_id, SERVICE_GENERIC, NPH_CONN_REQUEST, struct.pack("<HHHIII", 6, 2, 0, unit_id, 65535, 0))


def realtime(unit_id: int, ts: int, lat: float, lon: float, valid: bool, speed: int, course: int) -> bytes:
    """Realtime-пакет с ячейкой навигации G6CellNav00 (координаты в 1e-7 градуса, знак — в битах dop)."""
    lat, lon = (0.0, 0.0) if not (np.isfinite(lat) and np.isfinite(lon)) else (lat, lon)
    dop = ((lat >= 0) << 5) | ((lon >= 0) << 6) | (bool(valid) << 7)
    nav = struct.pack("<IIIBBHHHHHBB", ts, round(abs(lon) * 1e7), round(abs(lat) * 1e7), dop, 200,
                      speed, speed + 5, course, 0, 150, 12, 10)
    return frame(unit_id, SERVICE_NAV, NPH_REALTIME, bytes([0, 0]) + nav)


def load(part: str, start_s: int | None, minutes: int, max_units: int | None, tz_offset: int) -> pd.DataFrame:
    df = pd.read_csv(DATA / part / "traffic.csv", dtype={"tr_id": str},
                     usecols=["tr_id", "unit_id", "event_time", "location_valid", "lon", "lat", "speed", "heading"])
    df["t"] = to_ts(df["event_time"])
    df["unit"] = pd.to_numeric(df["unit_id"], errors="coerce")
    df["unit"] = df.groupby("tr_id")["unit"].transform(lambda s: s.ffill().bfill())
    df = df.dropna(subset=["unit"])
    df["unit"] = df["unit"].astype("int64")
    df["valid"] = df["location_valid"].astype(str).str.lower().eq("true")
    day0 = int(df["t"].min()) // 86400 * 86400
    t0 = day0 + start_s if start_s is not None else int(df["t"].min())
    df = df[(df["t"] >= t0) & (df["t"] < t0 + minutes * 60)]
    if max_units:
        keep = df.groupby("unit").size().sort_values(ascending=False).head(max_units).index
        df = df[df["unit"].isin(keep)]
    df = df.sort_values("t", kind="stable").reset_index(drop=True)
    df["gps"] = df["t"] - tz_offset
    return df


async def connect(host: str, port: int, wait_s: float):
    """Подключиться к приемнику; если он еще поднимается (например, в Docker), подождать до wait_s секунд."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_s
    while True:
        try:
            return await asyncio.open_connection(host, port)
        except OSError:
            if loop.time() >= deadline:
                raise
            await asyncio.sleep(2)


async def play(df: pd.DataFrame, host: str, port: int, speed: float, wait_s: float = 0) -> None:
    reader, writer = await connect(host, port, wait_s)
    for unit in df["unit"].unique():
        writer.write(handshake(int(unit)))
    await writer.drain()
    loop = asyncio.get_running_loop()
    wall0, t0 = loop.time(), int(df["t"].iloc[0])
    last_report = -1
    for row in df.itertuples(index=False):
        delay = wall0 + (row.t - t0) / speed - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        sp = int(row.speed) if np.isfinite(row.speed) else 0
        hd = int(row.heading) % 360 if np.isfinite(row.heading) else 0
        writer.write(realtime(int(row.unit), int(row.gps), float(row.lat), float(row.lon), bool(row.valid), sp, hd))
        minute = (int(row.t) - t0) // 60
        if minute != last_report:
            last_report = minute
            await writer.drain()
            print(f"\rвремя потока {pd.Timestamp(int(row.t), unit='s').strftime('%H:%M')}  (+{minute} мин)", end="", flush=True)
    await writer.drain()
    writer.close()
    print("\nготово")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", choices=["validate", "test"], default="validate")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9201)
    ap.add_argument("--speed", type=float, default=30.0, help="во сколько раз ускорить время потока")
    ap.add_argument("--start", default="08:00", help="с какого времени суток данных начинать, ЧЧ:ММ")
    ap.add_argument("--minutes", type=int, default=120, help="сколько минут потока проиграть")
    ap.add_argument("--units", type=int, default=None, help="ограничить число машин")
    ap.add_argument("--tz-offset", type=int, default=0, help="секунд вычесть из времени файла (см. описание)")
    ap.add_argument("--wait", type=float, default=0, help="сколько секунд ждать, пока приемник начнет принимать соединения")
    ap.add_argument("--hide-ids", action="store_true",
                    help="подменить номера терминалов: сервису они незнакомы, рейс определяется по треку")
    a = ap.parse_args()
    hh, mm = map(int, a.start.split(":"))
    df = load(a.part, hh * 3600 + mm * 60, a.minutes, a.units, a.tz_offset)
    if df.empty:
        sys.exit("в этом интервале нет данных: измените --start/--minutes")
    if a.hide_ids:
        df["unit"] = df["unit"].map({u: HIDDEN_BASE + i for i, u in enumerate(sorted(df["unit"].unique()))})
    print(f"{len(df)} отметок, {df['unit'].nunique()} машин, поток x{a.speed:g} -> {a.host}:{a.port}"
          + (", номера терминалов подменены" if a.hide_ids else ""))
    asyncio.run(play(df, a.host, a.port, a.speed, a.wait))


if __name__ == "__main__":
    main()
