"""Run all high-level Alicat query methods against a real serial device."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from alicat import AlicatDriver, AsyncSerialClient  # noqa: E402

PORT = "/dev/tty.usbserial-A9RK9TER"
UNIT_ID = "A"

QueryCall = Callable[[], Awaitable[Any]]


async def main() -> None:
    client = AsyncSerialClient(PORT)
    driver = AlicatDriver(client, unit_id=UNIT_ID)
    queries: tuple[tuple[str, QueryCall], ...] = (
        ("query_data_frame_format", driver.query_data_frame_format),
        ("poll", driver.poll),
        ("query_data_frame_with_units", driver.query_data_frame_with_units),
        ("request_data", lambda: driver.request_data(100, 4, 5)),
        ("query_streaming_interval", driver.query_streaming_interval),
        ("query_manufacturer_info", driver.query_manufacturer_info),
        ("query_firmware_version", driver.query_firmware_version),
        ("query_control_point", driver.query_control_point),
        ("query_control_mode", driver.query_control_mode),
        ("query_baud_rate", driver.query_baud_rate),
        ("query_setpoint", driver.query_setpoint),
        ("query_or_set_setpoint", driver.query_or_set_setpoint),
        ("query_available_gases", driver.query_available_gases),
        ("query_active_gas", driver.query_active_gas),
        ("query_valve_drive_state", driver.query_valve_drive_state),
    )

    try:
        for name, query in queries:
            try:
                result = await query()
            except Exception as exc:
                result = f"{type(exc).__name__}: {exc}"
            print(f"{name}: {result}")
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
