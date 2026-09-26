"""TCP-приемник NDTP: бортовые терминалы (или эмулятор) подключаются сюда сами.

На каждое соединение — свой разбор потока (FrameParser). Handshake и realtime-пакеты
приходят от терминала, ответов сервер не шлет: формата ответа в спецификации нет, а эмулятор
их не разбирает. Для реальных терминалов ответ, возможно, понадобится.

Сервер хранит только последнее положение каждой машины (unit_id -> Fix) и счетчики.
Дальше по конвейеру — отметки в события «прошла остановку» и в модель — он пока не передает.

Запуск отдельно, чтобы смотреть пакеты в консоли:
    python -m app.service.ndtp_server
Внутри API запускается автоматически (app/api.py), состояние — GET /api/live/units.
"""
import asyncio
import contextlib
import logging
import socket
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

from app.config import NDTP_HOST, NDTP_PORT, NDTP_VERIFY_CRC
from app.data_sources.ndtp_protocol import (NPH_CONN_REQUEST, SERVICE_GENERIC_CONTROLS, Fix,
                                            FrameParser, fix_from_frame, parse_conn_request)

log = logging.getLogger("ndtp")


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
        f = self.fix
        return {
            "unitId": self.unit_id,
            "connected": self.connected,
            "remote": self.remote,
            "packets": self.packets,
            "lastSeenSec": round(now - self.last_seen, 1) if self.last_seen else None,
            "position": None if f is None else {
                "lon": f.lon, "lat": f.lat, "valid": f.location_valid, "gpsTime": f.gps_time,
                "speed": f.speed, "course": f.course},
        }


@dataclass
class Stats:
    connections: int = 0
    frames: int = 0
    fixes: int = 0
    ignored: int = 0       # кадры без навигации: handshake и прочее
    crc_errors: int = 0


@dataclass(eq=False)   # сравнение по идентичности: соединения лежат в множестве
class _Conn:
    writer: asyncio.StreamWriter
    remote: str
    parser: FrameParser
    units: set = field(default_factory=set)
    crc_reported: int = 0


class NdtpServer:
    def __init__(self, host: str = NDTP_HOST, port: int = NDTP_PORT, verify_crc: bool = NDTP_VERIFY_CRC,
                 on_fix: Callable[[Fix], None] | None = None):
        self._host, self._port, self._verify_crc = host, port, verify_crc
        self._on_fix = on_fix
        self._server: asyncio.Server | None = None
        self._conns: set[_Conn] = set()
        self._units: dict[int, UnitState] = {}
        self.stats = Stats()
        self.error: str | None = None

    @property
    def listening(self) -> bool:
        return self._server is not None

    @property
    def port(self) -> int:
        """Настоящий порт: при port=0 его выбирает система."""
        return self._server.sockets[0].getsockname()[1] if self._server else self._port

    async def start(self) -> None:
        """Не падает, если порт занят: API должен подняться и сообщить причину в /api/health."""
        try:
            self._server = await asyncio.start_server(self._handle, self._host, self._port)
        except OSError as e:
            self.error = f"не удалось открыть {self._host}:{self._port}: {e}"
            log.error(self.error)
            return
        self.error = None
        log.info("NDTP-приемник слушает %s:%d (проверка CRC: %s)", self._host, self.port,
                 "вкл" if self._verify_crc else "выкл")

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        # с Python 3.12 wait_closed ждет завершения всех соединений — закрываем их сами
        for conn in list(self._conns):
            conn.writer.close()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._server.wait_closed(), timeout=5)
        self._server = None

    def snapshot(self) -> dict:
        now = time.time()
        units = sorted(self._units.values(), key=lambda u: u.unit_id)
        return {"listening": self.listening, "host": self._host, "port": self.port,
                "error": self.error, "stats": asdict(self.stats),
                "units": [u.to_json(now) for u in units]}

    def positions(self, max_age_s: float) -> list[Fix]:
        """Последние достоверные отметки машин, от которых были пакеты не позже max_age_s назад.
        Машина, пропавшая со связи, исчезает с карты, а не висит на последней точке вечно."""
        now = time.time()
        return [u.fix for u in sorted(self._units.values(), key=lambda u: u.unit_id)
                if u.fix is not None and u.fix.location_valid
                and u.last_seen is not None and now - u.last_seen <= max_age_s]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        conn = _Conn(writer, f"{peer[0]}:{peer[1]}" if peer else "?", FrameParser(self._verify_crc))
        sock = writer.get_extra_info("socket")
        if sock is not None:
            # терминал мог пропасть без закрытия соединения — пусть ОС это заметит
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self._conns.add(conn)
        self.stats.connections += 1
        log.info("подключение %s", conn.remote)
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
                if unit.conn is conn:   # машина могла уже переподключиться новым соединением
                    unit.connected = False
            log.info("отключение %s (машины: %s)", conn.remote, sorted(conn.units) or "—")
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    def _on_frame(self, conn: _Conn, frame) -> None:
        now = time.time()
        self.stats.frames += 1
        unit = self._units.setdefault(frame.peer_address, UnitState(frame.peer_address))
        unit.conn, unit.connected, unit.remote, unit.last_seen = conn, True, conn.remote, now
        conn.units.add(unit.unit_id)

        if frame.service_id == SERVICE_GENERIC_CONTROLS and frame.nph_type == NPH_CONN_REQUEST:
            self.stats.ignored += 1
            version = parse_conn_request(frame.body)
            log.info("handshake: машина %d, NDTP %s", unit.unit_id,
                     "%d.%d" % version if version else "? (тело handshake короче ожидаемого)")
            return

        fix = fix_from_frame(frame, now)
        if fix is None:
            self.stats.ignored += 1
            return
        unit.fix = fix
        unit.packets += 1
        self.stats.fixes += 1
        if self._on_fix is not None:
            try:
                self._on_fix(fix)
            except Exception:  # noqa: BLE001 — сбой подписчика не должен рвать соединение с терминалом
                log.exception("on_fix: ошибка обработки отметки машины %d", fix.unit_id)
        log.debug("машина %d: %.6f, %.6f  достоверно=%s  %d км/ч  курс %d°  gps_time=%d",
                  fix.unit_id, fix.lat, fix.lon, fix.location_valid, fix.speed, fix.course, fix.gps_time)

    def _report_crc(self, conn: _Conn) -> None:
        errors = conn.parser.crc_errors
        if errors == conn.crc_reported:
            return
        self.stats.crc_errors += errors - conn.crc_reported
        if conn.crc_reported == 0:
            # об остальных сообщаем только счетчиком: сбойный терминал не должен забивать лог
            wire, computed = conn.parser.last_crc_mismatch
            log.warning("%s: CRC не сошлась (в пакете 0x%04X, посчитано 0x%04X), пакет отброшен. "
                        "Если так со всеми пакетами — запустите с NDTP_VERIFY_CRC=0 и сверьте "
                        "расчет CRC со спецификацией", conn.remote, wire, computed)
        conn.crc_reported = errors


async def _serve_forever() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.setLevel(logging.DEBUG)
    server = NdtpServer()
    await server.start()
    if server.listening:
        await asyncio.Event().wait()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_serve_forever())
