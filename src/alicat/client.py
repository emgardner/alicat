"""Async Alicat transport clients."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

import serial

from alicat.protocol import COMMAND_TERMINATOR, encode_command

logger = logging.getLogger("alicat")

SerialFactory = Callable[..., Any]


class AbstractClient(ABC):
    """Abstract async transport for Alicat ASCII commands."""

    def __init__(
        self,
        *,
        timeout: float = 0.75,
        terminator: bytes = COMMAND_TERMINATOR,
        encoding: str = "ascii",
    ) -> None:
        self.timeout = timeout
        self.terminator = terminator
        self.encoding = encoding
        self._lock = asyncio.Lock()

    @property
    @abstractmethod
    def is_open(self) -> bool:
        """Whether the underlying transport is open."""

    @abstractmethod
    async def connect(self) -> None:
        """Open the underlying transport if needed."""

    @abstractmethod
    async def close(self) -> None:
        """Close the underlying transport."""

    @abstractmethod
    async def read(self, size: int) -> bytes:
        """Read up to ``size`` bytes."""

    @abstractmethod
    async def readline(self) -> str:
        """Read one CR-terminated Alicat response line."""

    @abstractmethod
    async def write(self, command: str | bytes) -> None:
        """Write a command or raw payload."""

    async def send(self, command: str | bytes) -> None:
        """Write a command without reading a response."""

        await self.connect()
        async with self._lock:
            await self.write(command)

    async def request(self, command: str | bytes) -> str:
        """Write one command and return one response line."""

        await self.connect()
        async with self._lock:
            await self.write(command)
            return await asyncio.wait_for(self.readline(), timeout=self.timeout)

    async def __aenter__(self) -> "AbstractClient":
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    def _decode_line(self, payload: bytes) -> str:
        return payload.decode(self.encoding).replace("\x00", "").strip()


class AsyncSerialClient(AbstractClient):
    """Async pyserial-backed transport for directly connected Alicat devices.

    Pyserial exposes blocking file operations. This client keeps the public API
    async by running those blocking reads/writes in worker threads, which avoids
    blocking the event loop without adding another runtime dependency.
    """

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 19200,
        timeout: float = 0.75,
        connect_timeout: float | None = None,
        bytesize: int = serial.EIGHTBITS,
        stopbits: float | int = serial.STOPBITS_ONE,
        parity: str = serial.PARITY_NONE,
        terminator: bytes = COMMAND_TERMINATOR,
        encoding: str = "ascii",
        serial_factory: SerialFactory | None = None,
    ) -> None:
        super().__init__(timeout=timeout, terminator=terminator, encoding=encoding)
        self.port = port
        self.connect_timeout = (
            connect_timeout
            if connect_timeout is not None
            else max(
                timeout,
                1.0,
            )
        )
        self.serial_settings: dict[str, Any] = {
            "baudrate": baudrate,
            "bytesize": bytesize,
            "stopbits": stopbits,
            "parity": parity,
            "timeout": timeout,
            "write_timeout": timeout,
        }
        self._serial_factory = serial_factory or serial.Serial
        self._serial: Any | None = None

    @property
    def is_open(self) -> bool:
        return bool(self._serial is not None and self._serial.is_open)

    async def connect(self) -> None:
        if self.is_open:
            return
        self._serial = await asyncio.wait_for(
            asyncio.to_thread(self._open_serial),
            timeout=self.connect_timeout,
        )

    async def close(self) -> None:
        if self._serial is None:
            return
        serial_port = self._serial
        self._serial = None
        if getattr(serial_port, "is_open", False):
            await asyncio.to_thread(serial_port.close)

    async def read(self, size: int) -> bytes:
        if size < 0:
            raise ValueError("size must be non-negative")
        await self.connect()
        serial_port = self._require_serial()
        return await asyncio.to_thread(serial_port.read, size)

    async def readline(self) -> str:
        await self.connect()
        serial_port = self._require_serial()
        payload = await asyncio.to_thread(serial_port.read_until, self.terminator)
        if not payload or not payload.endswith(self.terminator):
            raise asyncio.TimeoutError("timed out waiting for Alicat response")
        return self._decode_line(payload)

    async def write(self, command: str | bytes) -> None:
        await self.connect()
        payload = (
            encode_command(command, self.terminator)
            if isinstance(command, str)
            else command
        )
        serial_port = self._require_serial()
        bytes_written = await asyncio.to_thread(serial_port.write, payload)
        if bytes_written != len(payload):
            raise OSError(
                f"incomplete serial write: wrote {bytes_written} of {len(payload)} bytes"
            )
        await asyncio.to_thread(serial_port.flush)

    async def reset_input_buffer(self) -> None:
        await self.connect()
        serial_port = self._require_serial()
        if hasattr(serial_port, "reset_input_buffer"):
            await asyncio.to_thread(serial_port.reset_input_buffer)

    def _open_serial(self) -> Any:
        return self._serial_factory(port=self.port, **self.serial_settings)

    def _require_serial(self) -> Any:
        if self._serial is None:
            raise RuntimeError("serial transport is not connected")
        return self._serial


class AsyncTcpClient(AbstractClient):
    """Async TCP transport for serial-over-TCP gateways."""

    def __init__(
        self,
        address: str,
        *,
        timeout: float = 0.75,
        terminator: bytes = COMMAND_TERMINATOR,
        encoding: str = "ascii",
    ) -> None:
        super().__init__(timeout=timeout, terminator=terminator, encoding=encoding)
        try:
            host, port = address.rsplit(":", 1)
        except ValueError as exc:
            raise ValueError("address must be formatted as host:port") from exc
        self.host = host
        self.port = int(port)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    @property
    def is_open(self) -> bool:
        return bool(self._writer is not None and not self._writer.is_closing())

    async def connect(self) -> None:
        if self.is_open:
            return
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port),
            timeout=self.timeout,
        )

    async def close(self) -> None:
        if self._writer is None:
            return
        writer = self._writer
        self._reader = None
        self._writer = None
        writer.close()
        await writer.wait_closed()

    async def read(self, size: int) -> bytes:
        await self.connect()
        reader = self._require_reader()
        return await asyncio.wait_for(reader.read(size), timeout=self.timeout)

    async def readline(self) -> str:
        await self.connect()
        reader = self._require_reader()
        payload = await asyncio.wait_for(
            reader.readuntil(self.terminator),
            timeout=self.timeout,
        )
        return self._decode_line(payload)

    async def write(self, command: str | bytes) -> None:
        await self.connect()
        writer = self._require_writer()
        payload = (
            encode_command(command, self.terminator)
            if isinstance(command, str)
            else command
        )
        writer.write(payload)
        await asyncio.wait_for(writer.drain(), timeout=self.timeout)

    def _require_reader(self) -> asyncio.StreamReader:
        if self._reader is None:
            raise RuntimeError("TCP transport is not connected")
        return self._reader

    def _require_writer(self) -> asyncio.StreamWriter:
        if self._writer is None:
            raise RuntimeError("TCP transport is not connected")
        return self._writer


Client = AbstractClient
SerialClient = AsyncSerialClient
TcpClient = AsyncTcpClient
