"""Подписчик on_fix: история отметок для прогноза копится вне приемника, он хранит только последнюю."""
import asyncio

import pytest

from app.service.ndtp_server import NdtpServer
from tests.factories import ndtp_realtime

pytestmark = pytest.mark.integration


def test_on_fix_gets_every_fix_and_a_failing_subscriber_does_not_break_the_stream() -> None:
    seen = []

    def on_fix(fix) -> None:
        seen.append((fix.unit_id, round(fix.lat, 2)))
        if len(seen) == 1:
            raise RuntimeError("подписчик сломался")

    async def main() -> None:
        server = NdtpServer("127.0.0.1", 0, on_fix=on_fix)
        await server.start()
        assert server.listening, server.error
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", server.port)
            writer.write(ndtp_realtime(7, lat=55.70))
            writer.write(ndtp_realtime(7, lat=55.71))
            await writer.drain()
            async with asyncio.timeout(3):
                while len(seen) < 2:
                    await asyncio.sleep(0.01)
            assert seen == [(7, 55.70), (7, 55.71)]
            assert server.stats.fixes == 2
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()

    asyncio.run(main())
