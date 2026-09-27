"""Разбор бинарного протокола NDTP, используемого эмулятором организаторов."""

import struct
from dataclasses import dataclass

SIGNATURE = b"\x7e\x7e"
NPL_SIZE = 15
NPH_SIZE = 10
NPL_TYPE_NPH = 0x02
SERVICE_GENERIC_CONTROLS = 0
SERVICE_NAVDATA = 1
NPH_CONN_REQUEST = 100
NPH_REALTIME = 101
CELL_NAV = 0
NAV_SIZE = 26

_NAV = struct.Struct("<IIIBBHHHHHBB")
_NPL = struct.Struct("<HHHHBIH")
_NPH = struct.Struct("<HHHI")
_CONN = struct.Struct("<HHHIII")
_BIT_NORTH, _BIT_EAST, _BIT_VALID = 1 << 5, 1 << 6, 1 << 7


def _make_crc_table() -> list[int]:
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        table.append(crc)
    return table


_CRC_TABLE = _make_crc_table()


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc = (crc >> 8) ^ _CRC_TABLE[(crc ^ byte) & 0xFF]
    return crc


@dataclass(frozen=True)
class Frame:
    peer_address: int
    service_id: int
    nph_type: int
    body: bytes


@dataclass(frozen=True)
class Fix:
    unit_id: int
    gps_time: int
    received_at: float
    lon: float
    lat: float
    location_valid: bool
    speed: int
    course: int


class FrameParser:
    """Собирает NDTP-кадры из TCP-потока и отбрасывает кадры с плохой CRC."""

    def __init__(self, verify_crc: bool = True):
        self._buf = bytearray()
        self.verify_crc = verify_crc
        self.crc_errors = 0
        self.last_crc_mismatch: tuple[int, int] | None = None
        self.skipped_bytes = 0

    def feed(self, data: bytes) -> list[Frame]:
        self._buf += data
        frames = []
        while (frame := self._next()) is not None:
            frames.append(frame)
        return frames

    def _next(self) -> Frame | None:
        buf = self._buf
        while True:
            start = buf.find(SIGNATURE)
            if start < 0:
                self.skipped_bytes += max(len(buf) - 1, 0)
                del buf[:-1]
                return None
            if start:
                self.skipped_bytes += start
                del buf[:start]
            if len(buf) < NPL_SIZE:
                return None

            data_size = struct.unpack_from("<H", buf, 2)[0]
            if data_size < NPH_SIZE or buf[8] != NPL_TYPE_NPH:
                self.skipped_bytes += 1
                del buf[:1]
                continue

            total = NPL_SIZE + data_size
            if len(buf) < total:
                return None
            raw = bytes(buf[:total])
            payload = raw[NPL_SIZE:]
            if self.verify_crc:
                wire = struct.unpack_from(">H", raw, 6)[0]
                computed = crc16_modbus(payload)
                if wire != computed:
                    self.crc_errors += 1
                    self.last_crc_mismatch = (wire, computed)
                    self.skipped_bytes += 1
                    del buf[:1]
                    continue

            del buf[:total]
            peer = _NPL.unpack_from(raw, 0)[5]
            service_id, nph_type, _, _ = _NPH.unpack_from(raw, NPL_SIZE)
            return Frame(peer, service_id, nph_type, raw[NPL_SIZE + NPH_SIZE:])


def parse_conn_request(body: bytes) -> tuple[int, int] | None:
    if len(body) < _CONN.size:
        return None
    high, low, *_ = _CONN.unpack_from(body)
    return high, low


def fix_from_frame(frame: Frame, received_at: float) -> Fix | None:
    if frame.service_id != SERVICE_NAVDATA or frame.nph_type != NPH_REALTIME:
        return None
    body = frame.body
    if len(body) < 2 + NAV_SIZE or body[0] != CELL_NAV:
        return None
    ts, lon_raw, lat_raw, dop, _bat, speed, _speed_max, course, *_ = _NAV.unpack_from(body, 2)
    lon = lon_raw / 1e7 * (1 if dop & _BIT_EAST else -1)
    lat = lat_raw / 1e7 * (1 if dop & _BIT_NORTH else -1)
    valid = bool(dop & _BIT_VALID) and (lon_raw, lat_raw) != (0, 0)
    return Fix(frame.peer_address, ts, received_at, lon, lat, valid, speed, course)
