import asyncio

from alicat import AlicatDriver

PORT = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A9RK9TER-if00-port0"


async def main() -> None:
    client = AlicatDriver.serial(PORT)
    lines = await client.query_data_frame_format_lines()
    for line in lines:
        print(line)
    print(await client.poll())


if __name__ == "__main__":
    asyncio.run(main())
