"""Pure Alicat ASCII protocol helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Mapping, Sequence

from alicat.units import (
    PressureUnit,
    TemperatureUnit,
    pressure_unit_label,
    temperature_unit_label,
)

COMMAND_TERMINATOR = b"\r"

_UNIT_ID_RE = re.compile(r"^[A-Z@]$")
_NUMBER_RE = re.compile(r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[Ee][+-]?\d+)?$")
_DATA_FRAME_FORMAT_RE = re.compile(
    r"^(?P<unit_id>\S+)\s+(?P<row_id>D\d+)\s+"
    r"(?P<statistic>\S+)\s+(?P<rest>.*)$"
)
_GAS_RE = re.compile(r"^(?P<unit_id>\S+)\s+G(?P<number>\d+)\s+(?P<name>.+)$")
_SNAKE_CASE_RE = re.compile(r"[^0-9A-Za-z]+")


class AlicatProtocolError(ValueError):
    """Base exception for Alicat command/response protocol errors."""


class CommandValidationError(AlicatProtocolError):
    """Raised when a command cannot be represented as valid Alicat ASCII."""


class ParseError(AlicatProtocolError):
    """Raised when an Alicat response cannot be parsed."""


class DeviceRejectedCommand(ParseError):
    """Raised when a device responds with the standard rejection marker."""


class StatusCode(str, Enum):
    """Known Alicat data-frame status/error codes."""

    ADC = "ADC"
    EXH = "EXH"
    HLD = "HLD"
    LCK = "LCK"
    MOV = "MOV"
    OPL = "OPL"
    OVR = "OVR"
    P2O = "P2O"
    POV = "POV"
    TMF = "TMF"
    TOV = "TOV"
    VOV = "VOV"


STATUS_CODES = frozenset(code.value for code in StatusCode)


class ControlMode(str, Enum):
    """High-level control mode selected by the Alicat loop variable."""

    FLOW = "flow"
    PRESSURE = "pressure"


class ControlPoint(str, Enum):
    """Known Alicat loop control variables."""

    MASS_FLOW = "mass_flow"
    VOLUMETRIC_FLOW = "volumetric_flow"
    ABSOLUTE_PRESSURE = "absolute_pressure"
    GAUGE_PRESSURE = "gauge_pressure"
    DIFFERENTIAL_PRESSURE = "differential_pressure"


CONTROL_POINT_REGISTER_VALUES: Mapping[ControlPoint, int] = {
    ControlPoint.MASS_FLOW: 0b00100101,
    ControlPoint.VOLUMETRIC_FLOW: 0b00100100,
    ControlPoint.ABSOLUTE_PRESSURE: 0b00100010,
    ControlPoint.GAUGE_PRESSURE: 0b00100110,
    ControlPoint.DIFFERENTIAL_PRESSURE: 0b00100111,
}
CONTROL_POINTS_BY_REGISTER: Mapping[int, ControlPoint] = {
    register_value: control_point
    for control_point, register_value in CONTROL_POINT_REGISTER_VALUES.items()
}
_CONTROL_POINT_MODES: Mapping[ControlPoint, ControlMode] = {
    ControlPoint.MASS_FLOW: ControlMode.FLOW,
    ControlPoint.VOLUMETRIC_FLOW: ControlMode.FLOW,
    ControlPoint.ABSOLUTE_PRESSURE: ControlMode.PRESSURE,
    ControlPoint.GAUGE_PRESSURE: ControlMode.PRESSURE,
    ControlPoint.DIFFERENTIAL_PRESSURE: ControlMode.PRESSURE,
}
_CONTROL_POINT_ALIASES: Mapping[str, ControlPoint] = {
    "mass": ControlPoint.MASS_FLOW,
    "mass_flow": ControlPoint.MASS_FLOW,
    "flow": ControlPoint.MASS_FLOW,
    "vol_flow": ControlPoint.VOLUMETRIC_FLOW,
    "volu_flow": ControlPoint.VOLUMETRIC_FLOW,
    "volume_flow": ControlPoint.VOLUMETRIC_FLOW,
    "volumetric": ControlPoint.VOLUMETRIC_FLOW,
    "volumetric_flow": ControlPoint.VOLUMETRIC_FLOW,
    "abs_pressure": ControlPoint.ABSOLUTE_PRESSURE,
    "abs_press": ControlPoint.ABSOLUTE_PRESSURE,
    "absolute_pressure": ControlPoint.ABSOLUTE_PRESSURE,
    "pressure": ControlPoint.ABSOLUTE_PRESSURE,
    "gauge_pressure": ControlPoint.GAUGE_PRESSURE,
    "gauge_press": ControlPoint.GAUGE_PRESSURE,
    "ga_pressure": ControlPoint.GAUGE_PRESSURE,
    "ga_press": ControlPoint.GAUGE_PRESSURE,
    "diff_pressure": ControlPoint.DIFFERENTIAL_PRESSURE,
    "differential_pressure": ControlPoint.DIFFERENTIAL_PRESSURE,
    "pressure_differential": ControlPoint.DIFFERENTIAL_PRESSURE,
}

_MASS_FLOW_METER_FIELDS = (
    "absolute_pressure",
    "temperature",
    "volumetric_flow",
    "mass_flow",
)
_MASS_FLOW_CONTROLLER_FIELDS = _MASS_FLOW_METER_FIELDS + ("setpoint",)
_MASS_FLOW_CONTROLLER_TOTALIZER_FIELDS = _MASS_FLOW_CONTROLLER_FIELDS + (
    "totalized_flow",
)
_LIQUID_FLOW_METER_FIELDS = ("pressure", "temperature", "volumetric_flow")
_DIFFERENTIAL_PRESSURE_FIELDS = ("differential_pressure",)


@dataclass(frozen=True)
class DataFrame:
    """Parsed Alicat data frame.

    Alicat data frames are device- and configuration-dependent. ``values`` always
    preserves the numeric payload in frame order, while ``measurements`` contains
    inferred or caller-provided names for those numeric values.
    """

    unit_id: str
    values: tuple[float, ...]
    gas: str | None = None
    statuses: tuple[StatusCode, ...] = ()
    measurements: Mapping[str, float] = field(default_factory=dict)
    measurement_units: Mapping[str, str] = field(default_factory=dict)
    raw: str = ""
    tokens: tuple[str, ...] = ()

    def __getitem__(self, name: str) -> float:
        return self.measurements[name]

    def units(self, name: str) -> str | None:
        return self.measurement_units.get(name)


@dataclass(frozen=True)
class SetpointResponse:
    """Response from the 9v00+ query/change setpoint command."""

    unit_id: str
    current: float
    requested: float
    unit_value: int
    unit_label: str
    raw: str = ""


@dataclass(frozen=True)
class FirmwareResponse:
    """Response from the firmware-version command."""

    unit_id: str
    version: str
    date: str | None = None
    raw: str = ""


@dataclass(frozen=True)
class ControlPointResponse:
    """Parsed loop control variable response."""

    unit_id: str | None
    control_point: ControlPoint
    mode: ControlMode
    register_value: int
    raw: str = ""

    @property
    def is_flow_control(self) -> bool:
        return self.mode == ControlMode.FLOW

    @property
    def is_pressure_control(self) -> bool:
        return self.mode == ControlMode.PRESSURE


@dataclass(frozen=True)
class DataFrameFormatField:
    """One row from an Alicat ``??D*`` data-frame format response."""

    unit_id: str
    row_id: str
    index: int
    statistic: int
    name: str
    key: str
    data_type: str
    width: str
    notes: str = ""
    note_tokens: tuple[str, ...] = ()
    raw: str = ""

    @property
    def is_numeric(self) -> bool:
        return "decimal" in self.data_type.lower()

    @property
    def is_gas(self) -> bool:
        return self.statistic == 703

    @property
    def is_error(self) -> bool:
        return self.statistic == 701

    @property
    def is_status(self) -> bool:
        return self.statistic == 702

    @property
    def is_pressure(self) -> bool:
        name = f"{self.name} {self.key}".lower()
        return "press" in name or "pressure" in name

    @property
    def is_temperature(self) -> bool:
        name = f"{self.name} {self.key}".lower()
        return "temp" in name or "temperature" in name

    @property
    def unit_code(self) -> int | None:
        if not self.note_tokens or not self.note_tokens[0].isdigit():
            return None
        return int(self.note_tokens[0])

    @property
    def pressure_unit(self) -> PressureUnit | None:
        unit_code = self.unit_code
        if not self.is_pressure or unit_code is None:
            return None
        try:
            return PressureUnit(unit_code)
        except ValueError:
            return None

    @property
    def temperature_unit(self) -> TemperatureUnit | None:
        unit_code = self.unit_code
        if not self.is_temperature or unit_code is None:
            return None
        try:
            return TemperatureUnit(unit_code)
        except ValueError:
            return None

    @property
    def units(self) -> str | None:
        if not self.is_numeric or not self.note_tokens:
            return None
        pressure_unit = self.pressure_unit
        if pressure_unit is not None:
            return pressure_unit_label(pressure_unit)
        temperature_unit = self.temperature_unit
        if temperature_unit is not None:
            return temperature_unit_label(temperature_unit)
        return self.note_tokens[-1]


@dataclass(frozen=True)
class DataFrameFormat:
    """Structured Alicat ``??D*`` data-frame format response."""

    unit_id: str
    header: str | None
    fields: tuple[DataFrameFormatField, ...]
    raw_lines: tuple[str, ...]

    @property
    def measurement_field_names(self) -> tuple[str, ...]:
        """Names suitable for :func:`parse_data_frame` ``field_names``."""

        return tuple(field.key for field in self.fields if field.is_numeric)

    @property
    def measurement_units(self) -> Mapping[str, str]:
        return {
            field.key: field.units
            for field in self.fields
            if field.is_numeric and field.units is not None
        }

    @property
    def gas_field(self) -> DataFrameFormatField | None:
        return next((field for field in self.fields if field.is_gas), None)

    @property
    def status_fields(self) -> tuple[DataFrameFormatField, ...]:
        return tuple(field for field in self.fields if field.is_status)

    @property
    def error_fields(self) -> tuple[DataFrameFormatField, ...]:
        return tuple(field for field in self.fields if field.is_error)


@dataclass(frozen=True)
class GasOption:
    """One gas row from an Alicat gas-list response."""

    unit_id: str
    number: int
    code: str
    name: str
    raw: str = ""


@dataclass(frozen=True)
class AvailableGases:
    """Structured Alicat ``??G*`` available-gases response."""

    unit_id: str
    gases: tuple[GasOption, ...]
    raw_lines: tuple[str, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(gas.name for gas in self.gases)

    @property
    def numbers(self) -> tuple[int, ...]:
        return tuple(gas.number for gas in self.gases)

    @property
    def by_number(self) -> Mapping[int, GasOption]:
        return {gas.number: gas for gas in self.gases}

    @property
    def by_name(self) -> Mapping[str, GasOption]:
        return {gas.name.upper(): gas for gas in self.gases}

    def get(self, gas: int | str) -> GasOption | None:
        if isinstance(gas, int):
            return self.by_number.get(gas)
        return self.by_name.get(gas.upper())

    def __iter__(self) -> Iterator[GasOption]:
        return iter(self.gases)

    def __len__(self) -> int:
        return len(self.gases)


def normalize_unit_id(unit_id: str) -> str:
    """Validate and normalize an Alicat unit ID."""

    normalized = unit_id.strip().upper()
    if not _UNIT_ID_RE.match(normalized):
        raise CommandValidationError(
            "unit_id must be one letter A-Z, or '@' for streaming mode"
        )
    return normalized


def normalize_control_point(control_point: ControlPoint | str) -> ControlPoint:
    """Validate and normalize an Alicat loop control variable."""

    if isinstance(control_point, ControlPoint):
        return control_point
    key = _SNAKE_CASE_RE.sub("_", control_point.strip().lower()).strip("_")
    try:
        return _CONTROL_POINT_ALIASES[key]
    except KeyError as exc:
        raise CommandValidationError(
            f"unknown control point: {control_point!r}"
        ) from exc


def control_mode_for_point(control_point: ControlPoint | str) -> ControlMode:
    """Return whether a loop control variable is flow or pressure control."""

    return _CONTROL_POINT_MODES[normalize_control_point(control_point)]


def format_argument(value: object) -> str:
    """Serialize a command argument without adding protocol syntax."""

    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def encode_command(command: str, terminator: bytes = COMMAND_TERMINATOR) -> bytes:
    """Return a CR-terminated ASCII command payload."""

    if not terminator:
        raise CommandValidationError("terminator must not be empty")
    command = command.rstrip("\r\n")
    try:
        return command.encode("ascii") + terminator
    except UnicodeEncodeError as exc:
        raise CommandValidationError("Alicat commands must be ASCII") from exc


@dataclass(frozen=True)
class CommandBuilder:
    """Pure builder for common Alicat ASCII commands.

    Returned commands do not include the terminating carriage return. Use
    :func:`encode_command` at the transport boundary.
    """

    unit_id: str = "A"

    def __post_init__(self) -> None:
        object.__setattr__(self, "unit_id", normalize_unit_id(self.unit_id))

    def with_unit_id(self, unit_id: str) -> "CommandBuilder":
        return type(self)(unit_id=unit_id)

    def raw(self, body: str = "", *, unit_id: str | None = None) -> str:
        return f"{normalize_unit_id(unit_id or self.unit_id)}{body}"

    def command(
        self,
        mnemonic: str = "",
        *arguments: object,
        unit_id: str | None = None,
        compact_first_argument: bool = False,
    ) -> str:
        prefix = self.raw(mnemonic, unit_id=unit_id)
        serialized = tuple(format_argument(argument) for argument in arguments)
        if not serialized:
            return prefix
        if compact_first_argument:
            first, *rest = serialized
            suffix = first if not rest else f"{first} {' '.join(rest)}"
            return f"{prefix}{suffix}"
        return f"{prefix} {' '.join(serialized)}"

    def poll(self) -> str:
        return self.raw()

    def request_data(self, milliseconds: int, *statistics: int) -> str:
        if not statistics:
            raise CommandValidationError("request_data requires at least one statistic")
        if len(statistics) > 13:
            raise CommandValidationError("request_data accepts at most 13 statistics")
        return self.command("DV", milliseconds, *statistics)

    def start_streaming(self) -> str:
        return f"{self.unit_id}@=@"

    def stop_streaming(self, new_unit_id: str) -> str:
        return f"@@={normalize_unit_id(new_unit_id)}"

    def query_streaming_interval(self) -> str:
        return self.command("NCS")

    def set_streaming_interval(self, milliseconds: int) -> str:
        if milliseconds < 0:
            raise CommandValidationError("streaming interval must be non-negative")
        return self.command("NCS", milliseconds)

    def set_legacy_streaming_interval(self, milliseconds: int) -> str:
        if milliseconds < 0:
            raise CommandValidationError("streaming interval must be non-negative")
        return f"{self.unit_id}W91={milliseconds}"

    def query_data_frame_format(self) -> str:
        return self.raw("??D*")

    def configure_data_frame_format(self, format_id: int) -> str:
        if format_id not in {0, 1, 2}:
            raise CommandValidationError("data frame format must be 0, 1, or 2")
        return self.command("FDF", format_id)

    def query_manufacturer_info(self) -> str:
        return self.raw("??M*")

    def query_firmware_version(self) -> str:
        return self.raw("VE")

    def query_control_point(self) -> str:
        return self.raw("R122")

    def set_control_point(self, control_point: ControlPoint | str) -> str:
        normalized = normalize_control_point(control_point)
        register_value = CONTROL_POINT_REGISTER_VALUES[normalized]
        return self.raw(f"W122={register_value}")

    def change_unit_id(self, new_unit_id: str) -> str:
        return f"{self.unit_id}@={normalize_unit_id(new_unit_id)}"

    def query_baud_rate(self) -> str:
        return self.command("NCB")

    def set_baud_rate(self, baud_rate: int) -> str:
        if baud_rate not in {2400, 9600, 19200, 38400, 57600, 115200}:
            raise CommandValidationError("unsupported Alicat baud rate")
        return self.command("NCB", baud_rate)

    def set_setpoint(self, value: float) -> str:
        return self.command("S", value, compact_first_argument=True)

    def query_setpoint(self) -> str:
        return self.command("LS")

    def query_or_set_setpoint(
        self,
        value: float | None = None,
        units_value: int | None = None,
    ) -> str:
        if value is None:
            if units_value is not None:
                raise CommandValidationError("units_value requires a setpoint value")
            return self.query_setpoint()
        if units_value is None:
            return self.command("LS", value)
        return self.command("LS", value, units_value)

    def query_available_gases(self) -> str:
        return self.raw("??G*")

    def set_gas(self, gas_number: int) -> str:
        if gas_number < 0:
            raise CommandValidationError("gas_number must be non-negative")
        return self.command("G", gas_number, compact_first_argument=True)

    def query_active_gas(self) -> str:
        return self.command("GS")

    def set_active_gas(self, gas_number: int, *, save: bool | None = None) -> str:
        if gas_number < 0:
            raise CommandValidationError("gas_number must be non-negative")
        if save is None:
            return self.command("GS", gas_number)
        return self.command("GS", gas_number, save)

    def tare_flow(self) -> str:
        return self.raw("V")

    def tare_gauge_pressure(self) -> str:
        return self.raw("P")

    def tare_absolute_pressure(self) -> str:
        return self.raw("PC")

    def reset_totalizer(self, totalizer: int | None = None) -> str:
        if totalizer is None:
            return self.raw("T")
        if totalizer not in {1, 2}:
            raise CommandValidationError("totalizer must be 1 or 2")
        return self.command("T", totalizer)

    def cancel_valve_hold(self) -> str:
        return self.raw("C")

    def exhaust(self) -> str:
        return self.raw("E")

    def hold_valves(self) -> str:
        return self.raw("HP")

    def hold_valves_closed(self) -> str:
        return self.raw("HC")

    def query_valve_drive_state(self) -> str:
        return self.raw("VD")

    def lock_display(self) -> str:
        return self.raw("L")

    def unlock_display(self) -> str:
        return self.raw("U")


def parse_data_frame(
    line: str,
    *,
    field_names: Sequence[str] | None = None,
    field_units: Mapping[str, str] | None = None,
) -> DataFrame:
    """Parse a data-frame response from an Alicat device."""

    raw = _clean_line(line)
    if raw == "?":
        raise DeviceRejectedCommand("device rejected command with '?' response")
    tokens = tuple(raw.split())
    if len(tokens) < 2:
        raise ParseError("data frame must include a unit ID and at least one value")

    unit_id = normalize_unit_id(tokens[0])
    payload = list(tokens[1:])
    statuses = _pop_status_codes(payload)

    numeric_tokens: list[str] = []
    text_tokens: list[str] = []
    for token in payload:
        if _is_number(token) and not text_tokens:
            numeric_tokens.append(token)
        else:
            text_tokens.append(token)

    values = tuple(float(token) for token in numeric_tokens)
    gas = text_tokens[0] if text_tokens else None
    if len(text_tokens) > 1:
        raise ParseError(f"unexpected non-status tokens in data frame: {text_tokens!r}")

    names = _resolve_field_names(len(values), bool(gas), field_names)
    measurements = dict(zip(names, values, strict=True))
    measurement_units = (
        {name: field_units[name] for name in names if name in field_units}
        if field_units is not None
        else {}
    )
    return DataFrame(
        unit_id=unit_id,
        values=values,
        gas=gas,
        statuses=statuses,
        measurements=measurements,
        measurement_units=measurement_units,
        raw=raw,
        tokens=tokens,
    )


def parse_setpoint_response(line: str) -> SetpointResponse:
    """Parse the response to ``unit_idLS`` query/change setpoint."""

    raw = _clean_line(line)
    if raw == "?":
        raise DeviceRejectedCommand("device rejected command with '?' response")
    tokens = raw.split()
    if len(tokens) != 5:
        raise ParseError(f"setpoint response must contain 5 fields: {raw!r}")
    unit_id, current, requested, unit_value, unit_label = tokens
    if not (_is_number(current) and _is_number(requested)):
        raise ParseError(
            f"setpoint response contains non-numeric setpoint fields: {raw!r}"
        )
    if not unit_value.isdigit():
        raise ParseError(f"setpoint response contains non-integer unit value: {raw!r}")
    return SetpointResponse(
        unit_id=normalize_unit_id(unit_id),
        current=float(current),
        requested=float(requested),
        unit_value=int(unit_value),
        unit_label=unit_label,
        raw=raw,
    )


def parse_firmware_response(line: str) -> FirmwareResponse:
    """Parse the response to the firmware-version command."""

    raw = _clean_line(line)
    if raw == "?":
        raise DeviceRejectedCommand("device rejected command with '?' response")
    tokens = raw.split()
    if len(tokens) < 2:
        raise ParseError("firmware response must contain at least unit ID and version")
    return FirmwareResponse(
        unit_id=normalize_unit_id(tokens[0]),
        version=tokens[1],
        date=" ".join(tokens[2:]) or None,
        raw=raw,
    )


def parse_control_point_response(line: str) -> ControlPointResponse:
    """Parse a loop control variable response.

    The public command is ``unit_idLV`` on newer firmware, but older firmware
    can interpret that as the display-lock command. ``unit_idR122`` reads the
    same setting on older devices, so register-shaped responses are accepted.
    """

    raw = _clean_line(line)
    if raw == "?":
        raise DeviceRejectedCommand("device rejected command with '?' response")

    unit_id, payload = _split_optional_unit_id(raw)
    value_text = _last_register_value(payload)
    try:
        register_value = int(value_text, 0)
    except ValueError as exc:
        raise ParseError(
            f"control-point response contains a non-integer value: {raw!r}"
        ) from exc

    control_point = CONTROL_POINTS_BY_REGISTER.get(register_value)
    if control_point is None:
        raise ParseError(
            f"unexpected control-point register value {register_value}: {raw!r}"
        )
    return ControlPointResponse(
        unit_id=unit_id,
        control_point=control_point,
        mode=_CONTROL_POINT_MODES[control_point],
        register_value=register_value,
        raw=raw,
    )


def parse_data_frame_format(lines: Sequence[str]) -> DataFrameFormat:
    """Parse the multi-line response from the ``unit_id??D*`` command."""

    raw_lines = tuple(_clean_line(line) for line in lines if line.strip())
    if not raw_lines:
        raise ParseError("data frame format response is empty")

    header: str | None = None
    fields: list[DataFrameFormatField] = []
    unit_id: str | None = None
    for line in raw_lines:
        match = _DATA_FRAME_FORMAT_RE.match(line)
        if match is None:
            raise ParseError(f"invalid data frame format row: {line!r}")

        row_unit_id = normalize_unit_id(match.group("unit_id"))
        unit_id = row_unit_id if unit_id is None else unit_id
        if row_unit_id != unit_id:
            raise ParseError("data frame format response contains multiple unit IDs")

        row_id = match.group("row_id")
        statistic_text = match.group("statistic")
        if row_id == "D00":
            header = line
            continue
        if not statistic_text.isdigit():
            raise ParseError(f"invalid statistic in data frame format row: {line!r}")

        fields.append(
            _parse_data_frame_format_field(
                unit_id=row_unit_id,
                row_id=row_id,
                statistic=int(statistic_text),
                rest=match.group("rest"),
                raw=line,
            )
        )

    if unit_id is None:
        raise ParseError("data frame format response does not include a unit ID")
    return DataFrameFormat(
        unit_id=unit_id,
        header=header,
        fields=tuple(fields),
        raw_lines=raw_lines,
    )


def parse_gas_option(line: str) -> GasOption:
    """Parse one gas row such as ``A G00      Air``."""

    raw = _clean_line(line)
    if raw == "?":
        raise DeviceRejectedCommand("device rejected command with '?' response")
    match = _GAS_RE.match(raw)
    if match is None:
        raise ParseError(f"invalid gas row: {raw!r}")
    number_text = match.group("number")
    return GasOption(
        unit_id=normalize_unit_id(match.group("unit_id")),
        number=int(number_text),
        code=f"G{number_text}",
        name=match.group("name").strip(),
        raw=raw,
    )


def parse_available_gases(lines: Sequence[str]) -> AvailableGases:
    """Parse the multi-line response from the ``unit_id??G*`` command."""

    raw_lines = tuple(_clean_line(line) for line in lines if line.strip())
    if not raw_lines:
        raise ParseError("available gases response is empty")

    gases = tuple(parse_gas_option(line) for line in raw_lines)
    unit_id = gases[0].unit_id
    if any(gas.unit_id != unit_id for gas in gases):
        raise ParseError("available gases response contains multiple unit IDs")
    return AvailableGases(unit_id=unit_id, gases=gases, raw_lines=raw_lines)


def _clean_line(line: str) -> str:
    cleaned = line.replace("\x00", "").strip()
    if not cleaned:
        raise ParseError("response line is empty")
    return cleaned


def _split_optional_unit_id(raw: str) -> tuple[str | None, str]:
    parts = raw.split(maxsplit=1)
    if parts and len(parts[0]) == 1:
        try:
            return (
                normalize_unit_id(parts[0]),
                parts[1] if len(parts) > 1 else "",
            )
        except CommandValidationError:
            pass

    if len(raw) > 1:
        rest = raw[1:].lstrip()
        if rest.startswith("$$"):
            rest = rest[2:].lstrip()
        if rest.upper().startswith(("R122", "W122", "122")):
            try:
                return normalize_unit_id(raw[0]), rest
            except CommandValidationError:
                pass

    return None, raw


def _last_register_value(payload: str) -> str:
    if "=" in payload:
        return payload.rsplit("=", 1)[-1].strip()
    tokens = payload.split()
    if not tokens:
        raise ParseError("control-point response does not contain a register value")
    return tokens[-1]


def _parse_data_frame_format_field(
    *,
    unit_id: str,
    row_id: str,
    statistic: int,
    rest: str,
    raw: str,
) -> DataFrameFormatField:
    columns = re.split(r"\s{2,}", rest.strip(), maxsplit=2)
    if len(columns) < 3:
        raise ParseError(f"invalid data frame format row: {raw!r}")
    name, data_type, width_and_notes = columns
    width, _, notes = width_and_notes.strip().partition(" ")
    index = int(row_id[1:])
    return DataFrameFormatField(
        unit_id=unit_id,
        row_id=row_id,
        index=index,
        statistic=statistic,
        name=name.strip(),
        key=_normalize_field_name(name),
        data_type=data_type.strip(),
        width=width.strip(),
        notes=notes.strip(),
        note_tokens=tuple(notes.split()),
        raw=raw,
    )


def _normalize_field_name(name: str) -> str:
    normalized = _SNAKE_CASE_RE.sub("_", name.strip().lstrip("*").lower())
    return normalized.strip("_")


def _is_number(token: str) -> bool:
    return bool(_NUMBER_RE.match(token))


def _pop_status_codes(tokens: list[str]) -> tuple[StatusCode, ...]:
    statuses: list[StatusCode] = []
    while tokens and tokens[-1].upper() in STATUS_CODES:
        statuses.append(StatusCode(tokens.pop().upper()))
    statuses.reverse()
    return tuple(statuses)


def _resolve_field_names(
    value_count: int,
    has_gas: bool,
    field_names: Sequence[str] | None,
) -> tuple[str, ...]:
    if field_names is not None:
        names = tuple(field_names)
        if len(names) != value_count:
            raise ParseError(
                "field_names length must match the number of numeric values"
            )
        return names

    if has_gas and value_count == 6:
        return _MASS_FLOW_CONTROLLER_TOTALIZER_FIELDS
    if has_gas and value_count == 5:
        return _MASS_FLOW_CONTROLLER_FIELDS
    if has_gas and value_count == 4:
        return _MASS_FLOW_METER_FIELDS
    if not has_gas and value_count == 3:
        return _LIQUID_FLOW_METER_FIELDS
    if not has_gas and value_count == 1:
        return _DIFFERENTIAL_PRESSURE_FIELDS
    return tuple(f"value_{index}" for index in range(1, value_count + 1))
