"""Общее отображение строкового tr_id в 32-битный unit_id протокола NDTP."""

import zlib


def unit_id_for_trip(trip_id: str) -> int:
    value = zlib.crc32(str(trip_id).encode("utf-8")) & 0xFFFFFFFF
    return value or 1
