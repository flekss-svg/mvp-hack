"""NDTP-приемник по настоящему TCP на свободном порту — так же, как к нему подключается эмулятор."""
import asyncio

import pytest

from app.service.ndtp_server import NdtpServer
from tests.factories import ndtp_handshake, ndtp_realtime

pytestmark = pytest.mark.integration


async def wait_for(predicate, timeout: float = 3.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


async def connect(server: NdtpServer) -> asyncio.StreamWriter:
    _, writer = await asyncio.open_connection("127.0.0.1", server.port)
    return writer


async def send(writer: asyncio.StreamWriter, data: bytes) -> None:
    writer.write(data)
    await writer.drain()


async def close(writer: asyncio.StreamWriter) -> None:
    writer.close()
    await writer.wait_closed()


def run(scenario) -> None:
    async def main():
        server = NdtpServer("127.0.0.1", 0)
        await server.start()
        assert server.listening, server.error
        try:
            await scenario(server)
        finally:
            await server.stop()
    asyncio.run(main())


def test_session_like_the_emulator() -> None:
    async def scenario(server: NdtpServer) -> None:
        w = await connect(server)
        await send(w, ndtp_handshake(1166336))
        await asyncio.sleep(0.2)   # пауза между handshake и данными, как у эмулятора
        await send(w, ndtp_realtime(1166336, lat=55.70, lon=37.50, speed=33))
        await wait_for(lambda: server.stats.fixes == 1)

        (unit,) = server.snapshot()["units"]
        assert (unit["unitId"], unit["connected"], unit["packets"]) == (1166336, True, 1)
        assert unit["position"]["lat"] == pytest.approx(55.70)
        assert unit["position"]["speed"] == 33

        await send(w, ndtp_realtime(1166336, lat=55.71, lon=37.51))
        await wait_for(lambda: server.stats.fixes == 2)
        assert server.snapshot()["units"][0]["position"]["lat"] == pytest.approx(55.71)

        await close(w)
        await wait_for(lambda: not server.snapshot()["units"][0]["connected"])
    run(scenario)


def test_reconnect_keeps_unit_connected() -> None:
    async def scenario(server: NdtpServer) -> None:
        old = await connect(server)
        await send(old, ndtp_realtime(9))
        await wait_for(lambda: server.stats.fixes == 1)
        new = await connect(server)
        await send(new, ndtp_realtime(9))
        await wait_for(lambda: server.stats.fixes == 2)

        await close(old)   # старое соединение закрылось уже после нового — машина все еще на связи
        await wait_for(lambda: len(server._conns) == 1)
        assert server.snapshot()["units"][0]["connected"]
        await close(new)
    run(scenario)


def test_bad_crc_is_counted_and_not_stored() -> None:
    async def scenario(server: NdtpServer) -> None:
        w = await connect(server)
        await send(w, ndtp_realtime(3, crc_delta=1))
        await wait_for(lambda: server.stats.crc_errors == 1)
        assert server.stats.fixes == 0
        await close(w)
    run(scenario)


def test_busy_port_is_reported_instead_of_crashing() -> None:
    async def scenario(server: NdtpServer) -> None:
        second = NdtpServer("127.0.0.1", server.port)
        await second.start()
        assert not second.listening
        assert "не удалось открыть" in second.error
    run(scenario)


def test_stop_does_not_hang_on_a_connected_terminal() -> None:
    async def scenario(server: NdtpServer) -> None:
        w = await connect(server)
        await send(w, ndtp_realtime(4))
        await wait_for(lambda: server.stats.fixes == 1)
        async with asyncio.timeout(3):
            await server.stop()
        assert not server.listening
        w.close()
    run(scenario)
