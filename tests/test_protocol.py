import unittest

from alicat.protocol import (
    CommandBuilder,
    ControlMode,
    ControlPoint,
    DeviceRejectedCommand,
    ParseError,
    StatusCode,
    control_mode_for_point,
    encode_command,
    normalize_control_point,
    parse_available_gases,
    parse_control_point_response,
    parse_data_frame,
    parse_data_frame_format,
    parse_firmware_response,
    parse_gas_option,
    parse_setpoint_response,
)
from alicat.units import (
    PressureUnit,
    TemperatureUnit,
    pressure_unit_label,
    temperature_unit_label,
)


DATA_FRAME_FORMAT_LINES = (
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
    "A D10 701 *Error                     string          3 ADC",
    "A D11 702 *Status                    string          3 OPL",
    "A D12 702 *Status                    string          3 POV",
    "A D13 702 *Status                    string          3 P2O",
    "A D14 702 *Status                    string          3 TOV",
    "A D15 702 *Status                    string          3 VOV",
    "A D16 702 *Status                    string          3 MOV",
    "A D17 702 *Status                    string          3 TMF",
    "A D18 702 *Status                    string          3 OVR",
    "A D19 702 *Status                    string          3 HLD",
    "A D20 702 *Status                    string          3 EXH",
    "A D21 702 *Status                    string          3 LCK",
)


class CommandBuilderTests(unittest.TestCase):
    def test_builds_common_commands(self) -> None:
        builder = CommandBuilder("a")

        self.assertEqual(builder.poll(), "A")
        self.assertEqual(builder.query_data_frame_format(), "A??D*")
        self.assertEqual(builder.query_firmware_version(), "AVE")
        self.assertEqual(builder.query_control_point(), "AR122")
        self.assertEqual(
            builder.set_control_point(ControlPoint.MASS_FLOW),
            "AW122=37",
        )
        self.assertEqual(builder.set_control_point("gauge pressure"), "AW122=38")
        self.assertEqual(builder.set_setpoint(12.5), "AS12.5")
        self.assertEqual(builder.query_or_set_setpoint(12.5, 7), "ALS 12.5 7")
        self.assertEqual(builder.set_gas(8), "AG8")
        self.assertEqual(builder.start_streaming(), "A@=@")
        self.assertEqual(builder.stop_streaming("b"), "@@=B")
        self.assertEqual(builder.set_streaming_interval(250), "ANCS 250")
        self.assertEqual(builder.set_legacy_streaming_interval(250), "AW91=250")

    def test_encodes_carriage_return_terminated_ascii(self) -> None:
        self.assertEqual(encode_command("A\r\n"), b"A\r")


class ParserTests(unittest.TestCase):
    def test_parses_mass_flow_controller_frame_with_totalizer(self) -> None:
        frame = parse_data_frame(
            "A +087.59 +025.00 +164.7 +981.6 985.0 022741.4 Air HLD MOV"
        )

        self.assertEqual(frame.unit_id, "A")
        self.assertEqual(frame.gas, "Air")
        self.assertEqual(frame.statuses, (StatusCode.HLD, StatusCode.MOV))
        self.assertEqual(frame["absolute_pressure"], 87.59)
        self.assertEqual(frame["mass_flow"], 981.6)
        self.assertEqual(frame["totalized_flow"], 22741.4)

    def test_parses_mass_flow_meter_frame(self) -> None:
        frame = parse_data_frame("B +010.02 +025.00 +128.0 +87.2 He")

        self.assertEqual(frame.measurements["absolute_pressure"], 10.02)
        self.assertEqual(frame.measurements["volumetric_flow"], 128.0)
        self.assertEqual(frame.gas, "He")

    def test_parses_custom_field_names(self) -> None:
        frame = parse_data_frame(
            "D -05.62",
            field_names=("delta_pressure",),
        )

        self.assertEqual(frame["delta_pressure"], -5.62)

    def test_rejected_command_raises(self) -> None:
        with self.assertRaises(DeviceRejectedCommand):
            parse_data_frame("?")

    def test_parses_setpoint_response(self) -> None:
        response = parse_setpoint_response("A 1.0 2.0 7 SLPM")

        self.assertEqual(response.unit_id, "A")
        self.assertEqual(response.current, 1.0)
        self.assertEqual(response.requested, 2.0)
        self.assertEqual(response.unit_value, 7)
        self.assertEqual(response.unit_label, "SLPM")

    def test_setpoint_parse_error_includes_raw_response(self) -> None:
        with self.assertRaisesRegex(ParseError, "A G01"):
            parse_setpoint_response("A G01       Ar")

    def test_parses_firmware_response(self) -> None:
        response = parse_firmware_response("A 10v05 2023-02-01")

        self.assertEqual(response.unit_id, "A")
        self.assertEqual(response.version, "10v05")
        self.assertEqual(response.date, "2023-02-01")

    def test_parses_control_point_response(self) -> None:
        response = parse_control_point_response("A 37")

        self.assertEqual(response.unit_id, "A")
        self.assertEqual(response.register_value, 37)
        self.assertEqual(response.control_point, ControlPoint.MASS_FLOW)
        self.assertEqual(response.mode, ControlMode.FLOW)
        self.assertTrue(response.is_flow_control)
        self.assertFalse(response.is_pressure_control)

    def test_parses_legacy_control_point_register_response(self) -> None:
        response = parse_control_point_response("A R122=37")

        self.assertEqual(response.unit_id, "A")
        self.assertEqual(response.control_point, ControlPoint.MASS_FLOW)
        self.assertEqual(response.mode, ControlMode.FLOW)

    def test_parses_legacy_control_point_write_response(self) -> None:
        response = parse_control_point_response("A W122=38")

        self.assertEqual(response.unit_id, "A")
        self.assertEqual(response.register_value, 38)
        self.assertEqual(response.control_point, ControlPoint.GAUGE_PRESSURE)
        self.assertEqual(response.mode, ControlMode.PRESSURE)

    def test_normalizes_control_point_aliases(self) -> None:
        self.assertEqual(
            normalize_control_point("vol flow"),
            ControlPoint.VOLUMETRIC_FLOW,
        )
        self.assertEqual(
            normalize_control_point("ga press"), ControlPoint.GAUGE_PRESSURE
        )
        self.assertEqual(
            control_mode_for_point("diff pressure"),
            ControlMode.PRESSURE,
        )

    def test_parses_pressure_control_point_response(self) -> None:
        response = parse_control_point_response("AW122=38")

        self.assertEqual(response.unit_id, "A")
        self.assertEqual(response.control_point, ControlPoint.GAUGE_PRESSURE)
        self.assertEqual(response.mode, ControlMode.PRESSURE)
        self.assertTrue(response.is_pressure_control)

    def test_rejects_unknown_control_point_register(self) -> None:
        with self.assertRaisesRegex(ParseError, "unexpected control-point"):
            parse_control_point_response("A R122=99")

    def test_parses_query_data_frame_format_response(self) -> None:
        response = parse_data_frame_format(DATA_FRAME_FORMAT_LINES)

        self.assertEqual(response.unit_id, "A")
        self.assertEqual(len(response.fields), 21)
        self.assertEqual(response.fields[1].statistic, 2)
        self.assertEqual(response.fields[1].name, "Abs Press")
        self.assertEqual(response.fields[1].key, "abs_press")
        self.assertEqual(response.fields[1].data_type, "s decimal")
        self.assertEqual(response.fields[1].width, "7/2")
        self.assertEqual(response.fields[1].note_tokens, ("010", "02", "PSIA"))
        self.assertEqual(response.fields[1].unit_code, PressureUnit.PSI)
        self.assertEqual(response.fields[1].pressure_unit, PressureUnit.PSI)
        self.assertEqual(response.fields[1].units, "PSI")
        self.assertEqual(response.fields[2].unit_code, TemperatureUnit.CELSIUS)
        self.assertEqual(response.fields[2].temperature_unit, TemperatureUnit.CELSIUS)
        self.assertEqual(response.fields[2].units, "C")
        self.assertEqual(response.fields[5].unit_code, PressureUnit.PSI)
        self.assertEqual(response.fields[5].pressure_unit, PressureUnit.PSI)
        self.assertEqual(response.fields[5].units, "PSI")
        self.assertIsNotNone(response.gas_field)
        assert response.gas_field is not None
        self.assertEqual(response.gas_field.name, "Gas")
        self.assertEqual(response.status_fields[2].note_tokens, ("P2O",))
        self.assertEqual(
            response.measurement_field_names,
            (
                "abs_press",
                "flow_temp",
                "volu_flow",
                "mass_flow",
                "ga_press_setpt",
                "valve_drive",
                "mass_total",
            ),
        )
        self.assertEqual(
            response.measurement_units,
            {
                "abs_press": "PSI",
                "flow_temp": "C",
                "volu_flow": "CCM",
                "mass_flow": "SCCM",
                "ga_press_setpt": "PSI",
                "valve_drive": "%",
                "mass_total": "Scm3",
            },
        )

    def test_pressure_units_are_resolved_from_unit_code(self) -> None:
        response = parse_data_frame_format(
            (
                "A D00 ID_ NAME______________________ TYPE_______ WIDTH NOTES___________________",
                "A D01 002 Abs Press                  s decimal     7/2 010 02",
                "A D02 038 Ga Press Setpt             s decimal     7/2 010 02",
            )
        )

        self.assertEqual(response.fields[0].pressure_unit, PressureUnit.PSI)
        self.assertEqual(response.fields[0].units, "PSI")
        self.assertEqual(response.fields[1].pressure_unit, PressureUnit.PSI)
        self.assertEqual(response.fields[1].units, "PSI")
        self.assertEqual(
            response.measurement_units,
            {"abs_press": "PSI", "ga_press_setpt": "PSI"},
        )

    def test_pressure_unit_labels(self) -> None:
        self.assertEqual(pressure_unit_label(PressureUnit.PSI), "PSI")
        self.assertEqual(pressure_unit_label(PressureUnit.KPA), "kPa")

    def test_temperature_units_are_resolved_from_unit_code(self) -> None:
        response = parse_data_frame_format(
            (
                "A D00 ID_ NAME______________________ TYPE_______ WIDTH NOTES___________________",
                "A D01 003 Flow Temp                  s decimal     7/2 002 02 `C",
            )
        )

        self.assertEqual(response.fields[0].temperature_unit, TemperatureUnit.CELSIUS)
        self.assertEqual(response.fields[0].units, "C")
        self.assertEqual(response.measurement_units, {"flow_temp": "C"})

    def test_temperature_unit_labels(self) -> None:
        self.assertEqual(temperature_unit_label(TemperatureUnit.CELSIUS), "C")
        self.assertEqual(temperature_unit_label(TemperatureUnit.KELVIN), "K")

    def test_parses_p2o_status_in_data_frames(self) -> None:
        data_frame_format = parse_data_frame_format(DATA_FRAME_FORMAT_LINES)
        frame = parse_data_frame(
            "A +087.59 +025.00 +164.7 +981.6 +012.34 +056.78 00012345 N2 P2O HLD",
            field_names=data_frame_format.measurement_field_names,
            field_units=data_frame_format.measurement_units,
        )

        self.assertEqual(frame["ga_press_setpt"], 12.34)
        self.assertEqual(frame["valve_drive"], 56.78)
        self.assertEqual(frame["mass_total"], 12345.0)
        self.assertEqual(frame.units("abs_press"), "PSI")
        self.assertEqual(frame.units("flow_temp"), "C")
        self.assertEqual(frame.units("volu_flow"), "CCM")
        self.assertEqual(frame.units("mass_flow"), "SCCM")
        self.assertEqual(frame.units("valve_drive"), "%")
        self.assertEqual(frame.units("mass_total"), "Scm3")
        self.assertEqual(frame.gas, "N2")
        self.assertEqual(frame.statuses, (StatusCode.P2O, StatusCode.HLD))

    def test_parses_gas_rows(self) -> None:
        gas = parse_gas_option("A G08       N2")

        self.assertEqual(gas.unit_id, "A")
        self.assertEqual(gas.number, 8)
        self.assertEqual(gas.code, "G08")
        self.assertEqual(gas.name, "N2")

    def test_parses_available_gases(self) -> None:
        gases = parse_available_gases(
            (
                "A G00      Air",
                "A G01       Ar",
                "A G08       N2",
                "A G164   EAN32",
            )
        )

        self.assertEqual(gases.unit_id, "A")
        self.assertEqual(len(gases), 4)
        self.assertEqual(gases.numbers, (0, 1, 8, 164))
        self.assertEqual(gases.names, ("Air", "Ar", "N2", "EAN32"))
        self.assertEqual(gases.by_number[8].name, "N2")
        self.assertEqual(gases.by_name["AIR"].number, 0)
        ean32 = gases.get(164)
        argon = gases.get("ar")
        self.assertIsNotNone(ean32)
        self.assertIsNotNone(argon)
        assert ean32 is not None
        assert argon is not None
        self.assertEqual(ean32.name, "EAN32")
        self.assertEqual(argon.number, 1)
        self.assertIsNone(gases.get("not-a-gas"))


if __name__ == "__main__":
    unittest.main()
