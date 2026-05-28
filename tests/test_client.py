import asyncio
import unittest

from alicat.client import AsyncSerialClient


class FakeSerial:
    def __init__(self, response: bytes = b"A +001.0\r", **kwargs: object) -> None:
        self.response = response
        self.kwargs = kwargs
        self.is_open = True
        self.writes: list[bytes] = []
        self.closed = False
        self.input_buffer_reset = False

    def read(self, size: int) -> bytes:
        return self.response[:size]

    def read_until(self, expected: bytes) -> bytes:
        return self.response

    def write(self, payload: bytes) -> int:
        self.writes.append(payload)
        return len(payload)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self.input_buffer_reset = True


class AsyncSerialClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_writes_cr_terminated_command_and_reads_line(self) -> None:
        fake = FakeSerial(response=b"A +001.0\r")
        client = AsyncSerialClient(
            "/dev/ttyFAKE",
            timeout=0.1,
            serial_factory=lambda **kwargs: fake,
        )

        response = await client.request("A")

        self.assertEqual(response, "A +001.0")
        self.assertEqual(fake.writes, [b"A\r"])

    async def test_timeout_when_response_has_no_terminator(self) -> None:
        fake = FakeSerial(response=b"A +001.0")
        client = AsyncSerialClient(
            "/dev/ttyFAKE",
            timeout=0.1,
            serial_factory=lambda **kwargs: fake,
        )

        with self.assertRaises(asyncio.TimeoutError):
            await client.request("A")

    async def test_close_releases_serial_port(self) -> None:
        fake = FakeSerial()
        client = AsyncSerialClient(
            "/dev/ttyFAKE",
            timeout=0.1,
            serial_factory=lambda **kwargs: fake,
        )

        await client.connect()
        await client.close()

        self.assertTrue(fake.closed)
        self.assertFalse(client.is_open)


if __name__ == "__main__":
    unittest.main()
