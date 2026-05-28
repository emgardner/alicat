import asyncio
import unittest

from alicat.client import AbstractClient
from alicat.driver import AlicatDriver
from alicat.protocol import ControlMode, ControlPoint, DataFrame, SetpointResponse


class ScriptedClient(AbstractClient):
    def __init__(self, responses: dict[str, list[str]]) -> None:
        super().__init__(timeout=0.1)
        self.responses = responses
        self.writes: list[str] = []
        self.last_command: str | None = None
        self.connected = False

    @property
    def is_open(self) -> bool:
        return self.connected

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.connected = False

    async def read(self, size: int) -> bytes:
        return b""

    async def readline(self) -> str:
        if self.last_command is None:
            raise AssertionError("readline called before write")
        if not self.responses[self.last_command]:
            raise asyncio.TimeoutError
        return self.responses[self.last_command].pop(0)

    async def write(self, command: str | bytes) -> None:
        if isinstance(command, bytes):
            command = command.rstrip(b"\r").decode("ascii")
        self.writes.append(command)
        self.last_command = command


class AlicatDriverTests(unittest.IsolatedAsyncioTestCase):
    async def test_polls_and_parses_data_frame(self) -> None:
        client = ScriptedClient(
            {"A": ["A +087.59 +025.00 +164.7 +981.6 985.0 022741.4 Air HLD"]}
        )
        driver = AlicatDriver(client)

        frame = await driver.poll()

        self.assertEqual(frame.unit_id, "A")
        self.assertEqual(frame["mass_flow"], 981.6)
        self.assertEqual(frame.gas, "Air")
        self.assertEqual(client.writes, ["A"])

    async def test_query_data_frame_format_names_later_polls(self) -> None:
        client = ScriptedClient(
            {
                "A??D*": [
                    "A D00 ID_ NAME______________________ TYPE_______ WIDTH NOTES___________________",
                    "A D01 700 Unit ID                    string          1",
                    "A D02 002 Abs Press                  s decimal     7/2 010 02 PSIA",
                    "A D03 003 Flow Temp                  s decimal     7/2 002 02 `C",
                    "A D04 004 Volu Flow                  s decimal     7/1 012 02 CCM",
                    "A D05 005 Mass Flow                  s decimal     7/1 012 02 SCCM",
                    "A D06 038 Ga Press Setpt             s decimal     7/2 010 02 PSIG",
                    "A D07 013 Valve Drive                s decimal     7/2 063 02 %",
                    "A D08 009 Mass Total                 s decimal     8/0 006 02 Scm3",
                    "A D09 703 Gas                        string          6",
                    "A D19 702 *Status                    string          3 HLD",
                ],
                "A": [
                    "A +014.64 +040.27 +0000.4 +0000.4 +015.00 +100.00 +0000000 O2 HLD"
                ],
            }
        )
        driver = AlicatDriver(client)

        await driver.query_data_frame_format()
        frame = await driver.poll()

        self.assertEqual(frame["abs_press"], 14.64)
        self.assertEqual(frame["flow_temp"], 40.27)
        self.assertEqual(frame["ga_press_setpt"], 15.0)
        self.assertEqual(frame["valve_drive"], 100.0)
        self.assertEqual(frame["mass_total"], 0.0)
        self.assertEqual(frame.units("abs_press"), "PSI")
        self.assertEqual(frame.units("flow_temp"), "C")
        self.assertEqual(frame.units("volu_flow"), "CCM")
        self.assertEqual(frame.units("mass_flow"), "SCCM")
        self.assertEqual(frame.units("valve_drive"), "%")
        self.assertEqual(frame.units("mass_total"), "Scm3")
        self.assertEqual(frame.gas, "O2")

    async def test_query_data_frame_with_units_loads_format_if_needed(self) -> None:
        client = ScriptedClient(
            {
                "A??D*": [
                    "A D00 ID_ NAME______________________ TYPE_______ WIDTH NOTES___________________",
                    "A D01 700 Unit ID                    string          1",
                    "A D02 002 Abs Press                  s decimal     7/2 010 02 PSIA",
                    "A D03 003 Flow Temp                  s decimal     7/2 002 02 `C",
                    "A D04 004 Volu Flow                  s decimal     7/1 012 02 CCM",
                    "A D05 005 Mass Flow                  s decimal     7/1 012 02 SCCM",
                    "A D06 038 Ga Press Setpt             s decimal     7/2 010 02 PSIG",
                    "A D07 013 Valve Drive                s decimal     7/2 063 02 %",
                    "A D08 009 Mass Total                 s decimal     8/0 006 02 Scm3",
                    "A D09 703 Gas                        string          6",
                    "A D19 702 *Status                    string          3 LCK",
                ],
                "A": [
                    "A +014.64 +040.27 +0000.4 +0000.4 +015.00 +100.00 +0000000 O2 LCK"
                ],
            }
        )
        driver = AlicatDriver(client)

        data = await driver.query_data_frame_with_units()

        self.assertEqual(client.writes, ["A??D*", "A"])
        self.assertIsNotNone(data.abs_press)
        self.assertIsNotNone(data.flow_temp)
        self.assertIsNotNone(data.volu_flow)
        self.assertIsNotNone(data.mass_flow)
        self.assertIsNotNone(data.valve_drive)
        self.assertIsNotNone(data.mass_total)
        assert data.abs_press is not None
        assert data.flow_temp is not None
        assert data.volu_flow is not None
        assert data.mass_flow is not None
        assert data.valve_drive is not None
        assert data.mass_total is not None
        self.assertEqual(data.abs_press.value, 14.64)
        self.assertEqual(data.abs_press.units, "PSI")
        self.assertEqual(data.flow_temp.units, "C")
        self.assertEqual(data.volu_flow.units, "CCM")
        self.assertEqual(data.mass_flow.units, "SCCM")
        self.assertIsNotNone(data.control_setpoint)
        assert data.control_setpoint is not None
        self.assertEqual(data.control_setpoint_name, "ga_press_setpt")
        self.assertEqual(data.control_setpoint.value, 15.0)
        self.assertEqual(data.control_setpoint.units, "PSI")
        self.assertEqual(data.valve_drive.value, 100.0)
        self.assertEqual(data.valve_drive.units, "%")
        self.assertEqual(data.mass_total.units, "Scm3")
        self.assertEqual(data.gas, "O2")
        self.assertEqual(data.status, "LCK")
        self.assertIsNotNone(data.data_frame)

    async def test_query_control_point_uses_legacy_register_directly(self) -> None:
        client = ScriptedClient({"AR122": ["A R122=37"]})
        driver = AlicatDriver(client)

        control_point = await driver.query_control_point()

        self.assertEqual(client.writes, ["AR122"])
        self.assertEqual(control_point.control_point, ControlPoint.MASS_FLOW)
        self.assertEqual(control_point.mode, ControlMode.FLOW)
        self.assertEqual(driver.control_point, ControlPoint.MASS_FLOW)

    async def test_set_control_point_writes_legacy_register(self) -> None:
        client = ScriptedClient({"AW122=38": ["A W122=38"]})
        driver = AlicatDriver(
            client,
            data_frame_fields=("abs_press", "ga_press_setpt"),
            data_frame_units={"abs_press": "PSI", "ga_press_setpt": "PSI"},
        )

        control_point = await driver.set_control_point(ControlPoint.GAUGE_PRESSURE)

        self.assertEqual(client.writes, ["AW122=38"])
        self.assertEqual(control_point.control_point, ControlPoint.GAUGE_PRESSURE)
        self.assertEqual(control_point.mode, ControlMode.PRESSURE)
        self.assertEqual(driver.control_point, ControlPoint.GAUGE_PRESSURE)
        self.assertIsNone(driver.data_frame_fields)
        self.assertEqual(driver.data_frame_units, {})

    async def test_set_flowrate_switches_from_pressure_control(self) -> None:
        client = ScriptedClient(
            {
                "AR122": ["A R122=34"],
                "AS0": ["A +000.0 +025.0 +000.0 +000.0 000.0 Air"],
                "AW122=37": ["A W122=37"],
                "A??D*": [
                    "A D00 ID_ NAME______________________ TYPE_______ WIDTH NOTES___________________",
                    "A D01 700 Unit ID                    string          1",
                    "A D02 002 Abs Press                  s decimal     7/2 010 02 PSIA",
                    "A D03 003 Flow Temp                  s decimal     7/2 002 02 `C",
                    "A D04 004 Volu Flow                  s decimal     7/1 012 02 CCM",
                    "A D05 005 Mass Flow                  s decimal     7/1 012 02 SCCM",
                    "A D06 005 Mass Flow Setpt            s decimal     7/1 012 02 SCCM",
                    "A D07 703 Gas                        string          6",
                ],
                "AS12.5": ["A +000.0 +025.0 +000.0 +000.0 012.5 Air"],
            }
        )
        driver = AlicatDriver(client)

        frame = await driver.set_flowrate(12.5)

        self.assertEqual(
            client.writes,
            ["AR122", "AS0", "AW122=37", "A??D*", "AS12.5"],
        )
        self.assertEqual(frame["mass_flow_setpt"], 12.5)
        self.assertEqual(frame.units("mass_flow_setpt"), "SCCM")

    async def test_set_flowrate_keeps_existing_flow_control_point(self) -> None:
        client = ScriptedClient(
            {
                "AR122": ["A R122=36"],
                "AS12.5": ["A +000.0 +025.0 +000.0 +000.0 012.5 Air"],
            }
        )
        driver = AlicatDriver(client)

        frame = await driver.set_flow_rate(12.5)

        self.assertEqual(client.writes, ["AR122", "AS12.5"])
        self.assertEqual(frame["setpoint"], 12.5)

    async def test_set_pressure_switches_from_flow_control(self) -> None:
        client = ScriptedClient(
            {
                "AR122": ["A R122=37"],
                "AS0": ["A +000.0 +025.0 +000.0 +000.0 000.0 Air"],
                "AW122=38": ["A W122=38"],
                "A??D*": [
                    "A D00 ID_ NAME______________________ TYPE_______ WIDTH NOTES___________________",
                    "A D01 700 Unit ID                    string          1",
                    "A D02 002 Abs Press                  s decimal     7/2 010 02 PSIA",
                    "A D03 003 Flow Temp                  s decimal     7/2 002 02 `C",
                    "A D04 004 Volu Flow                  s decimal     7/1 012 02 CCM",
                    "A D05 005 Mass Flow                  s decimal     7/1 012 02 SCCM",
                    "A D06 038 Ga Press Setpt             s decimal     7/2 010 02 PSIG",
                    "A D07 703 Gas                        string          6",
                ],
                "AS15": ["A +000.0 +025.0 +000.0 +000.0 015.0 Air"],
            }
        )
        driver = AlicatDriver(client)

        frame = await driver.set_pressure(15, control_point="gauge_pressure")

        self.assertEqual(
            client.writes,
            ["AR122", "AS0", "AW122=38", "A??D*", "AS15"],
        )
        self.assertEqual(frame["ga_press_setpt"], 15.0)
        self.assertEqual(frame.units("ga_press_setpt"), "PSI")

    async def test_set_pressure_keeps_existing_pressure_control_point(self) -> None:
        client = ScriptedClient(
            {
                "AR122": ["A R122=38"],
                "AS15": ["A +000.0 +025.0 +000.0 +000.0 015.0 Air"],
            }
        )
        driver = AlicatDriver(client)

        frame = await driver.set_pressure(15)

        self.assertEqual(client.writes, ["AR122", "AS15"])
        self.assertEqual(frame["setpoint"], 15.0)

    async def test_setpoint_commands_accept_data_frame_echoes(self) -> None:
        client = ScriptedClient(
            {
                "A??D*": [
                    "A D00 ID_ NAME______________________ TYPE_______ WIDTH NOTES___________________",
                    "A D01 700 Unit ID                    string          1",
                    "A D02 002 Abs Press                  s decimal     7/2 010 02 PSIA",
                    "A D03 003 Flow Temp                  s decimal     7/2 002 02 `C",
                    "A D04 004 Volu Flow                  s decimal     7/1 012 02 CCM",
                    "A D05 005 Mass Flow                  s decimal     7/1 012 02 SCCM",
                    "A D06 038 Ga Press Setpt             s decimal     7/2 010 02 PSI",
                    "A D07 013 Valve Drive                s decimal     7/2 063 02 %",
                    "A D08 009 Mass Total                 s decimal     8/0 006 02 Scm3",
                    "A D09 703 Gas                        string          6",
                    "A D19 702 *Status                    string          3 LCK",
                ],
                "ALS 1.76": [
                    "A +014.60 +040.13 +0000.0 +0000.0 +001.76 +000.00 +0000000 Air LCK"
                ],
            }
        )
        driver = AlicatDriver(client)
        await driver.query_data_frame_format()

        response = await driver.set_setpoint(1.76)

        self.assertIsInstance(response, DataFrame)
        assert isinstance(response, DataFrame)
        self.assertEqual(client.writes, ["A??D*", "ALS 1.76"])
        self.assertEqual(response["ga_press_setpt"], 1.76)
        self.assertEqual(response.status, "LCK")

    async def test_data_frame_with_units_reloads_after_control_point_change(
        self,
    ) -> None:
        client = ScriptedClient(
            {
                "AW122=37": ["A W122=37"],
                "A??D*": [
                    "A D00 ID_ NAME______________________ TYPE_______ WIDTH NOTES___________________",
                    "A D01 700 Unit ID                    string          1",
                    "A D02 002 Abs Press                  s decimal     7/2 010 02 PSIA",
                    "A D03 003 Flow Temp                  s decimal     7/2 002 02 `C",
                    "A D04 004 Volu Flow                  s decimal     7/1 012 02 CCM",
                    "A D05 005 Mass Flow                  s decimal     7/1 012 02 SCCM",
                    "A D06 005 Mass Flow Setpt            s decimal     7/1 012 02 SCCM",
                    "A D07 703 Gas                        string          6",
                ],
                "A": ["A +014.6 +040.0 +0000.5 +0000.5 +0012.5 Air"],
            }
        )
        driver = AlicatDriver(
            client,
            data_frame_fields=("abs_press", "ga_press_setpt"),
            data_frame_units={"abs_press": "PSI", "ga_press_setpt": "PSI"},
        )

        await driver.set_control_point(ControlPoint.MASS_FLOW)
        data = await driver.query_data_frame_with_units()

        self.assertEqual(client.writes, ["AW122=37", "A??D*", "A"])
        self.assertIsNone(data.ga_press_setpt)
        self.assertEqual(data.control_setpoint_name, "mass_flow_setpt")
        self.assertIsNotNone(data.control_setpoint)
        assert data.control_setpoint is not None
        self.assertEqual(data.control_setpoint.value, 12.5)
        self.assertEqual(data.control_setpoint.units, "SCCM")

    async def test_set_gas_invalidates_cached_frame_format(self) -> None:
        client = ScriptedClient(
            {"AG8": ["A +000.0 +025.0 +000.0 +000.0 000.0 N2"]}
        )
        driver = AlicatDriver(
            client,
            data_frame_fields=(
                "abs_press",
                "flow_temp",
                "volu_flow",
                "mass_flow",
                "ga_press_setpt",
            ),
            data_frame_units={"ga_press_setpt": "PSI"},
        )

        frame = await driver.set_gas(8)

        self.assertEqual(frame.gas, "N2")
        self.assertIsNone(driver.data_frame_fields)
        self.assertEqual(driver.data_frame_units, {})

    async def test_set_active_gas_invalidates_cached_frame_format(self) -> None:
        client = ScriptedClient({"AGS 8": ["A 8 N2"]})
        driver = AlicatDriver(
            client,
            data_frame_fields=("abs_press", "ga_press_setpt"),
            data_frame_units={"ga_press_setpt": "PSI"},
        )

        response = await driver.set_active_gas(8)

        self.assertEqual(response.tokens, ("A", "8", "N2"))
        self.assertIsNone(driver.data_frame_fields)
        self.assertEqual(driver.data_frame_units, {})

    async def test_setpoint_unit_change_invalidates_cached_frame_format(self) -> None:
        client = ScriptedClient({"ALS 1.5 7": ["A 0.0 1.5 7 SLPM"]})
        driver = AlicatDriver(
            client,
            data_frame_fields=("abs_press", "ga_press_setpt"),
            data_frame_units={"ga_press_setpt": "PSI"},
        )

        response = await driver.set_setpoint(1.5, units_value=7)

        self.assertIsInstance(response, SetpointResponse)
        assert isinstance(response, SetpointResponse)
        self.assertEqual(response.requested, 1.5)
        self.assertIsNone(driver.data_frame_fields)
        self.assertEqual(driver.data_frame_units, {})

    async def test_runs_query_methods_with_typed_responses(self) -> None:
        client = ScriptedClient(
            {
                "ADV 100 4 5": ["164.7 981.6"],
                "ANCS": ["A 250"],
                "AVE": ["A 10v05 2023-02-01"],
                "AR122": ["A R122=37", "A R122=37"],
                "ANCB": ["A 19200"],
                "ALS": ["A 1.0 1.0 7 SLPM"],
                "A??G*": ["A G00      Air", "A G01       Ar", "A G08       N2"],
                "AGS": ["A 0 Air"],
                "AVD": ["A 12.5 0.0"],
            }
        )
        driver = AlicatDriver(client)

        requested = await driver.request_data(100, 4, 5)
        streaming_interval = await driver.query_streaming_interval()
        firmware = await driver.query_firmware_version()
        control_point = await driver.query_control_point()
        control_mode = await driver.query_control_mode()
        baud_rate = await driver.query_baud_rate()
        setpoint = await driver.query_setpoint()
        gases = await driver.query_available_gases()
        active_gas = await driver.query_active_gas()
        valve_state = await driver.query_valve_drive_state()

        self.assertEqual(requested.values, (164.7, 981.6))
        self.assertEqual(streaming_interval, 250)
        self.assertEqual(firmware.version, "10v05")
        self.assertEqual(control_point.control_point, ControlPoint.MASS_FLOW)
        self.assertEqual(control_point.mode, ControlMode.FLOW)
        self.assertEqual(control_mode, ControlMode.FLOW)
        self.assertEqual(baud_rate, 19200)
        self.assertIsInstance(setpoint, SetpointResponse)
        assert isinstance(setpoint, SetpointResponse)
        self.assertEqual(setpoint.unit_label, "SLPM")
        self.assertEqual(gases.names, ("Air", "Ar", "N2"))
        self.assertEqual(gases.numbers, (0, 1, 8))
        self.assertEqual(gases.by_number[8].name, "N2")
        self.assertEqual(active_gas.tokens, ("A", "0", "Air"))
        self.assertEqual(valve_state.values, (12.5, 0.0))

    async def test_runs_mutating_commands(self) -> None:
        frame = "A +000.0 +025.0 +000.0 +000.0 000.0 Air"
        client = ScriptedClient(
            {
                "ALS 2.5 7": ["A 1.0 2.5 7 SLPM"],
                "AS2.5": [frame],
                "AG8": [frame.replace("Air", "N2")],
                "AV": [frame],
                "AP": [frame],
                "APC": [frame],
                "AT": [frame],
                "AC": [frame],
                "AE": [f"{frame} EXH"],
                "AHP": [f"{frame} HLD"],
                "AHC": [f"{frame} HLD"],
                "AL": [f"{frame} LCK"],
                "AU": [frame],
            }
        )
        driver = AlicatDriver(client)

        setpoint = await driver.set_setpoint(2.5, 7)
        legacy_setpoint = await driver.set_legacy_setpoint(2.5)
        gas_frame = await driver.set_gas(8)
        await driver.tare_flow()
        await driver.tare_gauge_pressure()
        await driver.tare_absolute_pressure()
        await driver.reset_totalizer()
        await driver.cancel_valve_hold()
        exhaust_frame = await driver.exhaust()
        hold_frame = await driver.hold_valves()
        await driver.hold_valves_closed()
        lock_frame = await driver.lock_display()
        await driver.unlock_display()

        self.assertIsInstance(setpoint, SetpointResponse)
        assert isinstance(setpoint, SetpointResponse)
        self.assertEqual(setpoint.requested, 2.5)
        self.assertEqual(legacy_setpoint["setpoint"], 0.0)
        self.assertEqual(gas_frame.gas, "N2")
        self.assertIsNotNone(exhaust_frame)
        self.assertIsNotNone(hold_frame)
        assert exhaust_frame is not None
        assert hold_frame is not None
        self.assertEqual(exhaust_frame.status, "EXH")
        self.assertEqual(hold_frame.status, "HLD")
        self.assertEqual(lock_frame.status, "LCK")

    async def test_valve_actions_allow_no_response(self) -> None:
        client = ScriptedClient(
            {
                "AC": [],
                "AE": [],
                "AHP": [],
                "AHC": [],
            }
        )
        driver = AlicatDriver(client)

        cancel_frame = await driver.cancel_valve_hold()
        exhaust_frame = await driver.exhaust()
        hold_frame = await driver.hold_valves()
        closed_frame = await driver.hold_valves_closed()

        self.assertEqual(client.writes, ["AC", "AE", "AHP", "AHC"])
        self.assertIsNone(cancel_frame)
        self.assertIsNone(exhaust_frame)
        self.assertIsNone(hold_frame)
        self.assertIsNone(closed_frame)

    async def test_reads_configured_multiline_responses(self) -> None:
        data_frame_format_lines = [
            "A D00 ID_ NAME______________________ TYPE_______ WIDTH NOTES___________________",
            "A D01 700 Unit ID                    string          1",
            "A D02 002 Abs Press                  s decimal     7/2 010 02 PSIA",
            "A D03 003 Flow Temp                  s decimal     7/2 002 02 `C",
            "A D09 703 Gas                        string          6",
            "A D11 702 *Status                    string          3 OPL",
        ]
        client = ScriptedClient(
            {
                "A??D*": data_frame_format_lines,
                "A??M*": [f"info {index}" for index in range(10)],
            }
        )
        driver = AlicatDriver(client)

        data_frame_format = await driver.query_data_frame_format()
        manufacturer_info = await driver.query_manufacturer_info()

        self.assertEqual(data_frame_format.unit_id, "A")
        self.assertEqual(
            data_frame_format.measurement_field_names, ("abs_press", "flow_temp")
        )
        self.assertIsNotNone(data_frame_format.gas_field)
        assert data_frame_format.gas_field is not None
        self.assertEqual(data_frame_format.gas_field.name, "Gas")
        self.assertEqual(data_frame_format.status_fields[0].note_tokens, ("OPL",))
        self.assertEqual(len(manufacturer_info), 10)

    async def test_updates_unit_id_for_no_response_commands(self) -> None:
        client = ScriptedClient({"A": ["A +001.0"]})
        driver = AlicatDriver(client)

        await driver.change_unit_id("b")
        await driver.start_streaming()
        await driver.stop_streaming("c")

        self.assertEqual(driver.unit_id, "C")
        self.assertEqual(client.writes, ["A@=B", "B@=@", "@@=C"])


if __name__ == "__main__":
    unittest.main()
