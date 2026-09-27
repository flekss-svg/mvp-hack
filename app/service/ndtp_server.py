"""Асинхронный TCP-приёмник NDTP для телематики и Docker-player."""

import asyncio
import contextlib
import inspect
import logging
import socket
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field

from app.config import NDTP_HOST, NDTP_PORT, NDTP_VERIFY_CRC
from app.data_sources.ndtp_protocol import (
    NPH_CONN_REQUEST,
    SERVICE_GENERIC_CONTROLS,
    Fix,
    FrameParser,
    fix_from_frame,
    parse_conn_request,
)

log = logging.getLogger("ndtp")
FixHandler = Callable[[Fix], Awaitable[None] | None]


@dataclass
class UnitState:
    unit_id: int
    remote: str = ""
    connected: bool = False
    packets: int = 0
    last_seen: float | None = None
    fix: Fix | None = None
    conn: "_Conn | None" = None

    def to_json(self, now: float) -> dict:
        position = None
        if self.fix is not None:
            position = {
                "lon": self.fix.lon,
                "lat": self.fix.lat,
                "valid": self.fix.location_valid,
                "gpsTime": self.fix.gps_time,
                "speed": self.fix.speed,
                "course": self.fix.course,
            }
        return {
            "unitId": self.unit_id,
            "connected": self.connected,
            "remote": self.remote,
            "packets": self.packets,
            "lastSeenSec": round(now - self.last_seen, 1) if self.last_seen else None,
            "position": position,
        }


@dataclass
class Stats:
    connections: int = 0
    frames: int = 0
    fixes: int = 0
    ignored: int = 0
    crc_errors: int = 0


@dataclass(eq=False)
class _Conn:
    writer: asyncio.StreamWriter
    remote: str
    parser: FrameParser
    units: set[int] = field(default_factory=set)
    crc_reported: int = 0


class NdtpServer:
    def __init__(
        self,
        host: str = NDTP_HOST,
        port: int = NDTP_PORT,
        verify_crc: bool = NDTP_VERIFY_CRC,
        on_fix: FixHandler | None = None,
    ):
        self._host = host
        self._port = port
        self._verify_crc = verify_crc
        self._on_fix_handler = on_fix
        self._server: asyncio.Server | None = None
        self._conns: set[_Conn] = set()
        self._tasks: set[asyncio.Task] = set()
        self._units: dict[int, UnitState] = {}
        self.stats = Stats()
        self.error: str | None = None

    @property
    def listening(self) -> bool:
        return self._server is not None

    @property
    def port(self) -> int:
        return self._server.sockets[0].getsockname()[1] if self._server else self._port

    async def start(self) -> None:
        try:
            self._server = await asyncio.start_server(self._handle, self._host, self._port)
        except OSError as exc:
            self.error = f"не удалось открыть {self._host}:{self._port}: {exc}"
            log.error(self.error)
            return
        self.error = None
        log.info("NDTP-приёмник слушает %s:%d", self._host, self.port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            for conn in list(self._conns):
                conn.writer.close()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._server.wait_closed(), timeout=5)
            self._server = None
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def snapshot(self) -> dict:
        now = time.time()
        units = sorted(self._units.values(), key=lambda unit: unit.unit_id)
        return {
            "listening": self.listening,
            "host": self._host,
            "port": self.port,
            "error": self.error,
            "stats": asdict(self.stats),
            "units": [unit.to_json(now) for unit in units],
        }

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        remote = f"{peer[0]}:{peer[1]}" if peer else "?"
        conn = _Conn(writer, remote, FrameParser(self._verify_crc))
        sock = writer.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self._conns.add(conn)
        self.stats.connections += 1
        try:
            while data := await reader.read(65536):
                for frame in conn.parser.feed(data):
                    self._on_frame(conn, frame)
                self._report_crc(conn)
        except OSError:
            pass
        finally:
            self._conns.discard(conn)
            for unit_id in conn.units:
                unit = self._units[unit_id]
                if unit.conn is conn:
                    unit.connected = False
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    def _on_frame(self, conn: _Conn, frame) -> None:
        now = time.time()
        self.stats.frames += 1
        unit = self._units.setdefault(frame.peer_address, UnitState(frame.peer_address))
        unit.conn = conn
        unit.connected = True
        unit.remote = conn.remote
        unit.last_seen = now
        conn.units.add(unit.unit_id)

        if frame.service_id == SERVICE_GENERIC_CONTROLS and frame.nph_type == NPH_CONN_REQUEST:
            self.stats.ignored += 1
            version = parse_conn_request(frame.body)
            log.debug("NDTP handshake unit=%d version=%s", unit.unit_id, version)
            return

        fix = fix_from_frame(frame, now)
        if fix is None:
            self.stats.ignored += 1
            return
        unit.fix = fix
        unit.packets += 1
        self.stats.fixes += 1
        if self._on_fix_handler is not None:
            result = self._on_fix_handler(fix)
            if inspect.isawaitable(result):
                task = asyncio.create_task(result)
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    def _report_crc(self, conn: _Conn) -> None:
        errors = conn.parser.crc_errors
        if errors == conn.crc_reported:
            return
        self.stats.crc_errors += errors - conn.crc_reported
        if conn.crc_reported == 0:
            wire, computed = conn.parser.last_crc_mismatch or (0, 0)
            log.warning("%s: CRC mismatch: wire=0x%04X computed=0x%04X", conn.remote, wire, computed)
        conn.crc_reported = errors
