import asyncio

import pytest

from app.service.ndtp_server import NdtpServer
from tests.factories import ndtp_handshake, ndtp_realtime

pytestmark = pytest.mark.integration


async def wait_for(predicate, timeout: float = 3.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


def test_ndtp_tcp_session_and_callback() -> None:
    received = []

    async def scenario() -> None:
        server = NdtpServer("127.0.0.1", 0, on_fix=lambda fix: received.append(fix))
        await server.start()
        assert server.listening
        _, writer = await asyncio.open_connection("127.0.0.1", server.port)
        writer.write(ndtp_handshake(42) + ndtp_realtime(42))
        await writer.drain()
        await wait_for(lambda: server.stats.fixes == 1)
        snapshot = server.snapshot()
        assert snapshot["units"][0]["unitId"] == 42
        assert snapshot["units"][0]["position"]["speed"] == 40
        assert received[0].unit_id == 42
        writer.close()
        await writer.wait_closed()
        await server.stop()

    asyncio.run(scenario())


def test_busy_ndtp_port_is_reported() -> None:
    async def scenario() -> None:
        first = NdtpServer("127.0.0.1", 0)
        await first.start()
        second = NdtpServer("127.0.0.1", first.port)
        await second.start()
        assert not second.listening
        assert second.error
        await first.stop()

    asyncio.run(scenario())
