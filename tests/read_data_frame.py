import asyncio
from typing import Any, Awaitable, Callable
from alicat import AlicatDriver, AsyncSerialClient  # noqa: E402

PORT = "/dev/tty.usbserial-A9RK9TER"
UNIT_ID = "A"

QueryCall = Callable[[], Awaitable[Any]]


async def main() -> None:
    client = AsyncSerialClient(PORT)
    driver = AlicatDriver(client, unit_id=UNIT_ID)
    try:
        response = await driver.query_data_frame_format()
        for value in response.fields:
            print(value)
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
