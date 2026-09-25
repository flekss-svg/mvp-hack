"""Проверка приемника NDTP. Запуск из корня репозитория:
    python3 -m unittest tests.test_ndtp -v

Пакеты собираются здесь вручную по спецификации эмулятора, независимо от боевого кода
(CRC — побитово, без таблицы). Это сверка кода со спецификацией в моем прочтении, а не
проверка против настоящего эмулятора.
"""
import asyncio
import struct
import unittest

from app.data_sources.ndtp_protocol import FrameParser, crc16_modbus, fix_from_frame
from app.data_sources.ndtp_server import NdtpServer


def crc_reference(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def build_frame(unit_id: int, service_id: int, nph_type: int, body: bytes, request_id: int = 1,
                crc_delta: int = 0) -> bytes:
    payload = struct.pack("<HHHI", service_id, nph_type, 1, request_id) + body
    crc = (crc_reference(payload) + crc_delta) & 0xFFFF
    swapped = ((crc & 0xFF) << 8) | (crc >> 8)
    header = struct.pack("<HHHHBIH", 0x7E7E, len(payload), 0, swapped, 0x02, unit_id, 0)
    return header + payload


def conn_request(unit_id: int) -> bytes:
    body = struct.pack("<HHHIII", 6, 2, 0, unit_id, 65535, 0)
    return build_frame(unit_id, 0, 100, body)


def realtime(unit_id: int, lat: float = 55.7551234, lon: float = 37.617321, *, north=True, east=True,
             valid=True, speed=40, course=90, ts=1_780_000_000, **kw) -> bytes:
    dop = (north << 5) | (east << 6) | (valid << 7)
    nav = struct.pack("<IIIBBHHHHHBB", ts, round(abs(lon) * 1e7), round(abs(lat) * 1e7), dop, 200,
                      speed, speed + 5, course, 0, 150, 12, 10)
    # после навигации — ячейка ДУТ (type 8, 6 байт): парсер должен ее спокойно проигнорировать
    fuel = bytes([8, 0]) + struct.pack("<BHHB", 0, 300, 120, 20)
    return build_frame(unit_id, 1, 101, bytes([0, 0]) + nav + fuel, **kw)


class Crc(unittest.TestCase):
    def test_check_value(self):
        self.assertEqual(crc16_modbus(b"123456789"), 0x4B37)   # стандартный контрольный вектор
        self.assertEqual(crc_reference(b"123456789"), 0x4B37)

    def test_table_matches_bitwise(self):
        data = bytes(range(256)) * 3
        self.assertEqual(crc16_modbus(data), crc_reference(data))


class Parser(unittest.TestCase):
    def test_frame_fields(self):
        (frame,) = FrameParser().feed(conn_request(1166336))
        self.assertEqual((frame.peer_address, frame.service_id, frame.nph_type), (1166336, 0, 100))
        self.assertEqual(len(frame.body), 18)

    def test_byte_by_byte(self):
        stream = conn_request(7) + realtime(7)
        parser, frames = FrameParser(), []
        for b in stream:
            frames += parser.feed(bytes([b]))
        self.assertEqual([f.nph_type for f in frames], [100, 101])

    def test_several_frames_in_one_chunk(self):
        frames = FrameParser().feed(realtime(1) + realtime(2) + realtime(3))
        self.assertEqual([f.peer_address for f in frames], [1, 2, 3])

    def test_garbage_between_frames(self):
        parser = FrameParser()
        frames = parser.feed(b"\x00\x11\x7e" + realtime(1) + b"\xff\xff\x7e\x7e\x01" + realtime(2))
        self.assertEqual([f.peer_address for f in frames], [1, 2])
        self.assertEqual(parser.crc_errors, 0)

    def test_bad_crc_dropped_and_next_frame_survives(self):
        parser = FrameParser()
        frames = parser.feed(realtime(1, crc_delta=1) + realtime(2))
        self.assertEqual([f.peer_address for f in frames], [2])
        self.assertEqual(parser.crc_errors, 1)
        wire, computed = parser.last_crc_mismatch
        self.assertNotEqual(wire, computed)

    def test_crc_check_can_be_disabled(self):
        frames = FrameParser(verify_crc=False).feed(realtime(1, crc_delta=1))
        self.assertEqual(len(frames), 1)


class Nav(unittest.TestCase):
    def fix(self, **kw):
        (frame,) = FrameParser().feed(realtime(5, **kw))
        return fix_from_frame(frame, received_at=123.0)

    def test_example_from_spec(self):
        f = self.fix()
        self.assertAlmostEqual(f.lat, 55.7551234, places=7)
        self.assertAlmostEqual(f.lon, 37.617321, places=7)
        self.assertTrue(f.location_valid)
        self.assertEqual((f.unit_id, f.gps_time, f.speed, f.course, f.received_at),
                         (5, 1_780_000_000, 40, 90, 123.0))

    def test_hemispheres(self):
        f = self.fix(lat=33.9, lon=18.4, north=False, east=False)
        self.assertAlmostEqual(f.lat, -33.9, places=6)
        self.assertAlmostEqual(f.lon, -18.4, places=6)

    def test_invalid_flag(self):
        self.assertFalse(self.fix(valid=False).location_valid)

    def test_zero_coordinates_are_not_a_position(self):
        self.assertFalse(self.fix(lat=0.0, lon=0.0).location_valid)

    def test_handshake_is_not_a_fix(self):
        (frame,) = FrameParser().feed(conn_request(5))
        self.assertIsNone(fix_from_frame(frame, 0.0))


class Server(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = NdtpServer("127.0.0.1", 0)
        await self.server.start()
        self.assertTrue(self.server.listening, self.server.error)

    async def asyncTearDown(self):
        await self.server.stop()

    async def wait_for(self, predicate, timeout=3.0):
        async with asyncio.timeout(timeout):
            while not predicate():
                await asyncio.sleep(0.01)

    async def test_like_the_emulator(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.server.port)
        writer.write(conn_request(1166336))
        await writer.drain()
        await asyncio.sleep(0.2)   # пауза между handshake и данными, как у эмулятора
        writer.write(realtime(1166336, lat=55.70, lon=37.50, speed=33))
        await writer.drain()
        await self.wait_for(lambda: self.server.stats.fixes == 1)

        (unit,) = self.server.snapshot()["units"]
        self.assertTrue(unit["connected"])
        self.assertEqual(unit["unitId"], 1166336)
        self.assertEqual(unit["packets"], 1)
        self.assertAlmostEqual(unit["position"]["lat"], 55.70, places=6)
        self.assertEqual(unit["position"]["speed"], 33)

        writer.write(realtime(1166336, lat=55.71, lon=37.51))
        await writer.drain()
        await self.wait_for(lambda: self.server.stats.fixes == 2)
        self.assertAlmostEqual(self.server.snapshot()["units"][0]["position"]["lat"], 55.71, places=6)

        writer.close()
        await writer.wait_closed()
        await self.wait_for(lambda: not self.server.snapshot()["units"][0]["connected"])

    async def test_reconnect_keeps_unit_connected(self):
        _, w1 = await asyncio.open_connection("127.0.0.1", self.server.port)
        w1.write(realtime(9))
        await w1.drain()
        await self.wait_for(lambda: self.server.stats.fixes == 1)

        _, w2 = await asyncio.open_connection("127.0.0.1", self.server.port)
        w2.write(realtime(9))
        await w2.drain()
        await self.wait_for(lambda: self.server.stats.fixes == 2)

        w1.close()   # старое соединение закрылось уже после нового — машина все еще на связи
        await w1.wait_closed()
        await self.wait_for(lambda: self.server.stats.connections == 2 and len(self.server._conns) == 1)
        self.assertTrue(self.server.snapshot()["units"][0]["connected"])
        w2.close()
        await w2.wait_closed()

    async def test_bad_crc_is_counted_and_not_stored(self):
        _, writer = await asyncio.open_connection("127.0.0.1", self.server.port)
        writer.write(realtime(3, crc_delta=1))
        await writer.drain()
        await self.wait_for(lambda: self.server.stats.crc_errors == 1)
        self.assertEqual(self.server.stats.fixes, 0)
        writer.close()
        await writer.wait_closed()

    async def test_busy_port_does_not_crash(self):
        second = NdtpServer("127.0.0.1", self.server.port)
        await second.start()
        self.assertFalse(second.listening)
        self.assertIn("не удалось открыть", second.error)

    async def test_stop_with_connected_client(self):
        _, writer = await asyncio.open_connection("127.0.0.1", self.server.port)
        writer.write(realtime(4))
        await writer.drain()
        await self.wait_for(lambda: self.server.stats.fixes == 1)
        async with asyncio.timeout(3):
            await self.server.stop()   # не должен зависнуть на живом соединении
        self.assertFalse(self.server.listening)
        writer.close()


if __name__ == "__main__":
    unittest.main()
