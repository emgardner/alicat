"""High-level Alicat device driver."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from alicat.client import AbstractClient, AsyncSerialClient, AsyncTcpClient
from alicat.protocol import (
    AlicatProtocolError,
    AvailableGases,
    CommandBuilder,
    ControlMode,
    ControlPoint,
    ControlPointResponse,
    DataFrame,
    DataFrameFormat,
    DeviceRejectedCommand,
    FirmwareResponse,
    ParseError,
    SetpointResponse,
    control_mode_for_point,
    normalize_control_point,
    normalize_unit_id,
    parse_available_gases,
    parse_control_point_response,
    parse_data_frame,
    parse_data_frame_format,
    parse_firmware_response,
    parse_setpoint_response,
)


@dataclass(frozen=True)
class TokenResponse:
    """Generic tokenized response for commands with device-specific layouts."""

    raw: str
    tokens: tuple[str, ...]
    unit_id: str | None = None


@dataclass(frozen=True)
class NumericResponse:
    """Generic numeric response for simple scalar/vector commands."""

    raw: str
    values: tuple[float, ...]
    tokens: tuple[str, ...]
    unit_id: str | None = None


@dataclass(frozen=True)
class Measurement:
    """A numeric measurement with its unit label."""

    value: float
    units: str | None = None


@dataclass(frozen=True)
class DataFrameWithUnits:
    """Common Alicat data-frame values paired with units."""

    unit_id: str
    abs_press: Measurement | None = None
    flow_temp: Measurement | None = None
    volu_flow: Measurement | None = None
    mass_flow: Measurement | None = None
    ga_press_setpt: Measurement | None = None
    control_setpoint: Measurement | None = None
    control_setpoint_name: str | None = None
    valve_drive: Measurement | None = None
    mass_total: Measurement | None = None
    gas: str | None = None
    status: str | None = None
    raw: str = ""
    data_frame: DataFrame | None = None

    @property
    def statuses(self) -> tuple[str, ...]:
        return (self.status,) if self.status is not None else ()


class AlicatDriver:
    """High-level async driver built on an Alicat transport client."""

    def __init__(
        self,
        client: AbstractClient,
        *,
        unit_id: str = "A",
        data_frame_fields: Sequence[str] | None = None,
        data_frame_units: Mapping[str, str] | None = None,
    ) -> None:
        self.client = client
        self.commands = CommandBuilder(unit_id)
        self.data_frame_fields = (
            tuple(data_frame_fields) if data_frame_fields is not None else None
        )
        self.data_frame_units = dict(data_frame_units or {})
        self.data_frame_format: DataFrameFormat | None = None
        self._data_frame_format_failed = False
        self.control_point: ControlPoint | None = None
        self._lock = asyncio.Lock()

    @classmethod
    def serial(
        cls,
        port: str,
        *,
        unit_id: str = "A",
        data_frame_fields: Sequence[str] | None = None,
        data_frame_units: Mapping[str, str] | None = None,
        **serial_options: Any,
    ) -> "AlicatDriver":
        """Create a driver using a directly connected serial device."""

        return cls(
            AsyncSerialClient(port, **serial_options),
            unit_id=unit_id,
            data_frame_fields=data_frame_fields,
            data_frame_units=data_frame_units,
        )

    @classmethod
    def tcp(
        cls,
        address: str,
        *,
        unit_id: str = "A",
        data_frame_fields: Sequence[str] | None = None,
        data_frame_units: Mapping[str, str] | None = None,
        **tcp_options: Any,
    ) -> "AlicatDriver":
        """Create a driver using a serial-over-TCP gateway."""

        return cls(
            AsyncTcpClient(address, **tcp_options),
            unit_id=unit_id,
            data_frame_fields=data_frame_fields,
            data_frame_units=data_frame_units,
        )

    @property
    def unit_id(self) -> str:
        return self.commands.unit_id

    async def close(self) -> None:
        await self.client.close()

    async def __aenter__(self) -> "AlicatDriver":
        await self.client.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def raw(self, command: str) -> str:
        """Run a raw command and return its raw single-line response."""

        return await self._request_raw(command)

    async def send_raw(self, command: str) -> None:
        """Send a raw command that is not expected to respond."""

        async with self._lock:
            await self.client.send(command)

    async def poll(self, field_names: Sequence[str] | None = None) -> DataFrame:
        """Poll the device and parse its data frame."""

        return await self._request_data_frame(self.commands.poll(), field_names)

    def invalidate_data_frame_format(self) -> None:
        """Clear cached frame metadata after layout/unit-affecting changes."""

        self.data_frame_format = None
        self.data_frame_fields = None
        self.data_frame_units = {}
        self._data_frame_format_failed = False

    async def query_data_frame_with_units(self) -> DataFrameWithUnits:
        """Query the current data frame as common measurements with units.

        If the data-frame format has not been read yet, this first queries
        ``??D*`` so the returned measurements include field names and units.
        """

        await self._ensure_data_frame_format()
        return _data_frame_with_units(await self.poll())

    async def request_data(
        self,
        milliseconds: int,
        *statistics: int,
    ) -> NumericResponse:
        """Request averaged values for explicit statistic IDs."""

        response = await self._request_raw(
            self.commands.request_data(milliseconds, *statistics)
        )
        return _parse_numeric_response(response)

    async def start_streaming(self) -> None:
        """Put the current device into streaming mode."""

        async with self._lock:
            await self.client.send(self.commands.start_streaming())
        self.commands = self.commands.with_unit_id("@")

    async def stop_streaming(self, new_unit_id: str) -> None:
        """Stop a streaming device and return it to polling mode."""

        normalized = normalize_unit_id(new_unit_id)
        async with self._lock:
            await self.client.send(self.commands.stop_streaming(normalized))
        self.commands = self.commands.with_unit_id(normalized)

    async def read_stream_frame(
        self,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        """Read one already-streaming data frame."""

        line = await self.client.readline()
        return self._parse_data_frame(line, field_names)

    async def query_streaming_interval(self) -> int:
        response = await self._request_raw(self.commands.query_streaming_interval())
        return _parse_single_int_response(response, "streaming interval")

    async def set_streaming_interval(self, milliseconds: int) -> int:
        response = await self._request_raw(
            self.commands.set_streaming_interval(milliseconds)
        )
        return _parse_single_int_response(response, "streaming interval")

    async def set_legacy_streaming_interval(self, milliseconds: int) -> TokenResponse:
        response = await self._request_raw(
            self.commands.set_legacy_streaming_interval(milliseconds)
        )
        return _parse_token_response(response)

    async def query_data_frame_format(
        self,
        line_count: int | None = None,
        *,
        max_lines: int = 64,
    ) -> DataFrameFormat:
        """Query the data-frame definition.

        Alicat returns a table whose length depends on the configured frame. The
        default reads until the transport times out after the final row. Pass
        ``line_count`` to read an exact number of rows when it is known.
        """

        if line_count is None:
            lines = await self._request_lines_until_timeout(
                self.commands.query_data_frame_format(),
                max_lines,
            )
        else:
            lines = await self._request_lines(
                self.commands.query_data_frame_format(),
                line_count,
            )
        data_frame_format = parse_data_frame_format(lines)
        self.data_frame_format = data_frame_format
        self.data_frame_fields = data_frame_format.measurement_field_names
        self.data_frame_units = dict(data_frame_format.measurement_units)
        self._data_frame_format_failed = False
        return data_frame_format

    async def query_data_frame_format_lines(
        self,
        line_count: int | None = None,
        *,
        max_lines: int = 64,
    ) -> tuple[str, ...]:
        """Return the raw ``??D*`` response lines and cache the parsed format."""

        if line_count is None:
            lines = await self._request_lines_until_timeout(
                self.commands.query_data_frame_format(),
                max_lines,
            )
        else:
            lines = await self._request_lines(
                self.commands.query_data_frame_format(),
                line_count,
            )
        try:
            data_frame_format = parse_data_frame_format(lines)
        except ParseError:
            return lines
        self.data_frame_format = data_frame_format
        self.data_frame_fields = data_frame_format.measurement_field_names
        self.data_frame_units = dict(data_frame_format.measurement_units)
        self._data_frame_format_failed = False
        return lines

    async def configure_data_frame_format(
        self,
        format_id: int,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        response = await self._request_raw(
            self.commands.configure_data_frame_format(format_id)
        )
        self.invalidate_data_frame_format()
        if field_names is None:
            await self._ensure_data_frame_format()
        return self._parse_data_frame(response, field_names)

    async def query_manufacturer_info(self, line_count: int = 10) -> tuple[str, ...]:
        return await self._request_lines(
            self.commands.query_manufacturer_info(),
            line_count,
        )

    async def query_firmware_version(self) -> FirmwareResponse:
        response = await self._request_raw(self.commands.query_firmware_version())
        return parse_firmware_response(response)

    async def query_control_point(self) -> ControlPointResponse:
        response = await self._request_raw(self.commands.query_control_point())
        parsed = parse_control_point_response(response)
        self.control_point = parsed.control_point
        return parsed

    async def query_control_mode(self) -> ControlMode:
        return (await self.query_control_point()).mode

    async def set_control_point(
        self,
        control_point: ControlPoint | str,
    ) -> ControlPointResponse:
        target = normalize_control_point(control_point)
        response = await self._request_raw(self.commands.set_control_point(target))
        parsed = parse_control_point_response(response)
        if parsed.control_point != target:
            raise ParseError(
                f"control point did not change to {target.value}: {parsed.raw!r}"
            )
        self.control_point = parsed.control_point
        self.invalidate_data_frame_format()
        return parsed

    async def set_flowrate(
        self,
        flowrate: float,
        *,
        control_point: ControlPoint | str = ControlPoint.MASS_FLOW,
    ) -> DataFrame:
        """Set a flow setpoint, switching from pressure control if needed."""

        target = normalize_control_point(control_point)
        if control_mode_for_point(target) != ControlMode.FLOW:
            raise ValueError("set_flowrate control_point must be a flow variable")

        current = await self.query_control_point()
        if current.mode != ControlMode.FLOW:
            await self.set_legacy_setpoint(0)
            await self.set_control_point(target)
            await self.query_data_frame_format()
        return await self.set_legacy_setpoint(flowrate)

    async def set_flow_rate(
        self,
        flowrate: float,
        *,
        control_point: ControlPoint | str = ControlPoint.MASS_FLOW,
    ) -> DataFrame:
        """Alias for :meth:`set_flowrate`."""

        return await self.set_flowrate(flowrate, control_point=control_point)

    async def set_pressure(
        self,
        pressure: float,
        *,
        control_point: ControlPoint | str = ControlPoint.ABSOLUTE_PRESSURE,
    ) -> DataFrame:
        """Set a pressure setpoint, switching from flow control if needed."""

        target = normalize_control_point(control_point)
        if control_mode_for_point(target) != ControlMode.PRESSURE:
            raise ValueError("set_pressure control_point must be a pressure variable")

        current = await self.query_control_point()
        if current.mode != ControlMode.PRESSURE:
            await self.set_legacy_setpoint(0)
            await self.set_control_point(target)
            await self.query_data_frame_format()
        return await self.set_legacy_setpoint(pressure)

    async def change_unit_id(self, new_unit_id: str) -> None:
        normalized = normalize_unit_id(new_unit_id)
        async with self._lock:
            await self.client.send(self.commands.change_unit_id(normalized))
        self.commands = self.commands.with_unit_id(normalized)

    async def query_baud_rate(self) -> int:
        response = await self._request_raw(self.commands.query_baud_rate())
        return _parse_single_int_response(response, "baud rate")

    async def set_baud_rate(self, baud_rate: int) -> int:
        response = await self._request_raw(self.commands.set_baud_rate(baud_rate))
        return _parse_single_int_response(response, "baud rate")

    async def query_setpoint(self) -> SetpointResponse | DataFrame:
        response = await self._request_raw(self.commands.query_setpoint())
        return self._parse_setpoint_or_data_frame(response)

    async def query_or_set_setpoint(
        self,
        value: float | None = None,
        units_value: int | None = None,
    ) -> SetpointResponse | DataFrame:
        response = await self._request_raw(
            self.commands.query_or_set_setpoint(value, units_value)
        )
        parsed = self._parse_setpoint_or_data_frame(response)
        if value is not None and units_value is not None:
            self.invalidate_data_frame_format()
        return parsed

    async def set_setpoint(
        self,
        value: float,
        units_value: int | None = None,
    ) -> SetpointResponse | DataFrame:
        """Set the controller setpoint using the 9v00+ command."""

        return await self.query_or_set_setpoint(value, units_value)

    async def set_legacy_setpoint(
        self,
        value: float,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        """Set the controller setpoint using the older compact command."""

        return await self._request_data_frame(
            self.commands.set_setpoint(value),
            field_names,
        )

    async def query_available_gases(
        self,
        line_count: int | None = None,
        *,
        max_lines: int = 256,
    ) -> AvailableGases:
        """Query all available gas rows.

        The device returns one row per gas and does not advertise the row count
        up front, so the default reads until the response stream times out.
        """

        if line_count is None:
            lines = await self._request_lines_until_timeout(
                self.commands.query_available_gases(),
                max_lines,
            )
        else:
            lines = await self._request_lines(
                self.commands.query_available_gases(),
                line_count,
            )
        return parse_available_gases(lines)

    async def query_available_gas_lines(
        self,
        line_count: int | None = None,
        *,
        max_lines: int = 256,
    ) -> tuple[str, ...]:
        """Return the raw ``??G*`` response lines."""

        if line_count is None:
            return await self._request_lines_until_timeout(
                self.commands.query_available_gases(),
                max_lines,
            )
        return await self._request_lines(
            self.commands.query_available_gases(),
            line_count,
        )

    async def query_active_gas(self) -> TokenResponse:
        response = await self._request_raw(self.commands.query_active_gas())
        return _parse_token_response(response)

    async def set_active_gas(
        self,
        gas_number: int,
        *,
        save: bool | None = None,
    ) -> TokenResponse:
        response = await self._request_raw(
            self.commands.set_active_gas(gas_number, save=save)
        )
        parsed = _parse_token_response(response)
        self.invalidate_data_frame_format()
        return parsed

    async def set_gas(
        self,
        gas_number: int,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        frame = await self._request_data_frame(
            self.commands.set_gas(gas_number),
            field_names,
        )
        self.invalidate_data_frame_format()
        return frame

    async def tare_flow(
        self,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        return await self._request_data_frame(self.commands.tare_flow(), field_names)

    async def tare_gauge_pressure(
        self,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        return await self._request_data_frame(
            self.commands.tare_gauge_pressure(),
            field_names,
        )

    async def tare_absolute_pressure(
        self,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        return await self._request_data_frame(
            self.commands.tare_absolute_pressure(),
            field_names,
        )

    async def reset_totalizer(
        self,
        totalizer: int | None = None,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        return await self._request_data_frame(
            self.commands.reset_totalizer(totalizer),
            field_names,
        )

    async def cancel_valve_hold(
        self,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame | None:
        return await self._request_optional_data_frame(
            self.commands.cancel_valve_hold(),
            field_names,
        )

    async def exhaust(
        self,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame | None:
        return await self._request_optional_data_frame(
            self.commands.exhaust(),
            field_names,
        )

    async def hold_valves(
        self,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame | None:
        return await self._request_optional_data_frame(
            self.commands.hold_valves(),
            field_names,
        )

    async def hold_valves_closed(
        self,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame | None:
        return await self._request_optional_data_frame(
            self.commands.hold_valves_closed(),
            field_names,
        )

    async def query_valve_drive_state(self) -> NumericResponse:
        response = await self._request_raw(self.commands.query_valve_drive_state())
        return _parse_numeric_response(response)

    async def lock_display(
        self,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        return await self._request_data_frame(
            self.commands.lock_display(),
            field_names,
        )

    async def unlock_display(
        self,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        return await self._request_data_frame(
            self.commands.unlock_display(),
            field_names,
        )

    async def _request_raw(self, command: str) -> str:
        async with self._lock:
            response = await self.client.request(command)
            return response

    async def _request_lines(self, command: str, line_count: int) -> tuple[str, ...]:
        if line_count < 1:
            raise ValueError("line_count must be at least 1")
        async with self._lock:
            await self.client.send(command)
            lines = [await self.client.readline() for _ in range(line_count)]
            return tuple(lines)

    async def _request_lines_until_timeout(
        self,
        command: str,
        max_lines: int,
    ) -> tuple[str, ...]:
        if max_lines < 1:
            raise ValueError("max_lines must be at least 1")
        async with self._lock:
            await self.client.send(command)
            lines: list[str] = []
            for _ in range(max_lines):
                try:
                    lines.append(await self.client.readline())
                except asyncio.TimeoutError:
                    break
            if not lines:
                raise ParseError("command did not return any response lines")
            return tuple(lines)

    async def _request_data_frame(
        self,
        command: str,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        response = await self._request_raw(command)
        return self._parse_data_frame(response, field_names)

    async def _request_optional_data_frame(
        self,
        command: str,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame | None:
        async with self._lock:
            await self.client.send(command)
            try:
                response = await self.client.readline()
            except TimeoutError:
                return None
        return self._parse_data_frame(response, field_names)

    async def _ensure_data_frame_format(self) -> None:
        """Lazily read ``??D*`` so data frames get real field names once."""

        if self.data_frame_fields is not None or self._data_frame_format_failed:
            return
        try:
            await self.query_data_frame_format()
        except (AlicatProtocolError, asyncio.TimeoutError):
            self._data_frame_format_failed = True

    def _parse_data_frame(
        self,
        response: str,
        field_names: Sequence[str] | None = None,
    ) -> DataFrame:
        names = field_names if field_names is not None else self.data_frame_fields
        return parse_data_frame(
            response,
            field_names=names,
            field_units=self.data_frame_units,
        )

    def _parse_setpoint_or_data_frame(
        self,
        response: str,
    ) -> SetpointResponse | DataFrame:
        try:
            return parse_setpoint_response(response)
        except ParseError as setpoint_error:
            try:
                return self._parse_data_frame(response)
            except ParseError:
                raise setpoint_error


def _parse_token_response(line: str) -> TokenResponse:
    raw = _clean_response(line)
    tokens = tuple(raw.split())
    unit_id = _maybe_unit_id(tokens)
    return TokenResponse(raw=raw, tokens=tokens, unit_id=unit_id)


def _data_frame_with_units(data_frame: DataFrame) -> DataFrameWithUnits:
    control_setpoint_name = _control_setpoint_name(data_frame)
    return DataFrameWithUnits(
        unit_id=data_frame.unit_id,
        abs_press=_measurement(data_frame, "abs_press"),
        flow_temp=_measurement(data_frame, "flow_temp"),
        volu_flow=_measurement(data_frame, "volu_flow"),
        mass_flow=_measurement(data_frame, "mass_flow"),
        ga_press_setpt=_measurement(data_frame, "ga_press_setpt"),
        control_setpoint=(
            _measurement(data_frame, control_setpoint_name)
            if control_setpoint_name is not None
            else None
        ),
        control_setpoint_name=control_setpoint_name,
        valve_drive=_measurement(data_frame, "valve_drive"),
        mass_total=_measurement(data_frame, "mass_total"),
        gas=data_frame.gas,
        status=data_frame.status,
        raw=data_frame.raw,
        data_frame=data_frame,
    )


def _measurement(data_frame: DataFrame, name: str) -> Measurement | None:
    value = data_frame.measurements.get(name)
    if value is None:
        return None
    return Measurement(value=value, units=data_frame.units(name))


def _control_setpoint_name(data_frame: DataFrame) -> str | None:
    for name in data_frame.measurements:
        if name.endswith("_setpt") or name.endswith("_setpoint"):
            return name
    if "setpoint" in data_frame.measurements:
        return "setpoint"
    return None


def _parse_numeric_response(line: str) -> NumericResponse:
    token_response = _parse_token_response(line)
    payload = token_response.tokens
    if token_response.unit_id is not None:
        payload = payload[1:]
    try:
        values = tuple(float(token) for token in payload)
    except ValueError as exc:
        raise ParseError(
            f"numeric response contains a non-numeric value: {token_response.raw!r}"
        ) from exc
    return NumericResponse(
        raw=token_response.raw,
        values=values,
        tokens=token_response.tokens,
        unit_id=token_response.unit_id,
    )


def _parse_single_int_response(line: str, description: str) -> int:
    response = _parse_numeric_response(line)
    if len(response.values) != 1:
        raise ParseError(f"{description} response must contain one numeric value")
    return int(response.values[0])


def _clean_response(line: str) -> str:
    raw = line.replace("\x00", "").strip()
    if not raw:
        raise ParseError("response line is empty")
    if raw == "?":
        raise DeviceRejectedCommand("device rejected command with '?' response")
    return raw


def _maybe_unit_id(tokens: tuple[str, ...]) -> str | None:
    if not tokens:
        return None
    try:
        return normalize_unit_id(tokens[0])
    except ValueError:
        return None
