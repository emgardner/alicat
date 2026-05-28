import asyncio
from typing import Any, Awaitable, Callable
from alicat import AlicatDriver, AsyncSerialClient  # noqa: E402
from alicat.units import GasNumber

PORT = "/dev/tty.usbserial-A9RK9TER"
UNIT_ID = "A"

QueryCall = Callable[[], Awaitable[Any]]


async def run_hold(driver: AlicatDriver) -> None:
    await driver.cancel_valve_hold()
    await asyncio.sleep(5)
    print(await driver.query_data_frame_with_units())
    await driver.exhaust()
    await asyncio.sleep(5)
    print(await driver.query_data_frame_with_units())
    await driver.hold_valves_closed()
    await asyncio.sleep(5)
    print(await driver.query_data_frame_with_units())
    await driver.cancel_valve_hold()
    await asyncio.sleep(5)
    print(await driver.query_data_frame_with_units())


async def main() -> None:
    client = AsyncSerialClient(PORT)
    driver = AlicatDriver(client, unit_id=UNIT_ID)
    try:
        # print(await driver.query_active_gas())
        # print(await driver.query_available_gases())
        #frame_format = await driver.query_data_frame_format()
        # print(await driver.query_data_frame_with_units())
        #data = await driver.poll()
        # print(data)
        # print(data.measurements)
        # print(await driver.query_control_point())
        # print(await driver.unlock_display())
        # await run_hold(driver)
        #await driver.stop_streaming(UNIT_ID)
        #data = await driver.query_data_frame_format()
        #for field in data.fields:
        #    print(field)
        for i in range(0, 10):
            await driver.set_pressure(i)
            data = await driver.query_data_frame_with_units()
            print(data)
            #print(data.control_setpoint, data.control_setpoint_name, data.ga_press_setpt)
        for i in range(0, 10):
            await driver.set_flowrate(i)
            data = await driver.query_data_frame_with_units()
            print(data)
            #print(data.control_setpoint, data.control_setpoint_name, data.ga_press_setpt)
        # await asyncio.sleep(5)
        # print(await driver.exhaust())
        # print(await driver.cancel_valve_hold())
        # print(await driver.hold_valves_closed())
        # await asyncio.sleep(5)

        # print(await driver.query_setpoint())
        # print(data.)

        # print(await driver.set_active_gas(GasNumber.OXYGEN))
        # print(await driver.query_active_gas())
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
