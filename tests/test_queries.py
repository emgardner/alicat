from dataclasses import dataclass
import unittest

from alicat.client import AsyncSerialClient
from alicat.protocol import CommandBuilder


class ScriptedSerial:
    def __init__(self, responses: dict[str, bytes], **kwargs: object) -> None:
        self.responses = responses
        self.kwargs = kwargs
        self.is_open = True
        self.writes: list[bytes] = []
        self.last_command: str | None = None

    def read(self, size: int) -> bytes:
        return b""

    def read_until(self, expected: bytes) -> bytes:
        if self.last_command is None:
            raise AssertionError("read_until called before write")
        return self.responses[self.last_command]

    def write(self, payload: bytes) -> int:
        self.writes.append(payload)
        self.last_command = payload.rstrip(b"\r").decode("ascii")
        return len(payload)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.is_open = False


@dataclass(frozen=True)
class QueryCase:
    name: str
    command: str
    response: str


class QueryCommandTests(unittest.IsolatedAsyncioTestCase):
    def test_query_inventory_is_complete(self) -> None:
        query_methods = {
            name
            for name in dir(CommandBuilder)
            if name.startswith("query_") and callable(getattr(CommandBuilder, name))
        }
        self.assertEqual(
            query_methods | {"poll", "request_data"},
            {
                "poll",
                "query_active_gas",
                "query_available_gases",
                "query_baud_rate",
                "query_control_point",
                "query_data_frame_format",
                "query_firmware_version",
                "query_manufacturer_info",
                "query_or_set_setpoint",
                "query_setpoint",
                "query_streaming_interval",
                "query_valve_drive_state",
                "request_data",
            },
        )

    async def test_runs_all_query_commands(self) -> None:
        builder = CommandBuilder("A")
        cases = (
            QueryCase(
                "poll",
                builder.poll(),
                "A +087.59 +025.00 +164.7 +981.6 985.0 022741.4 Air",
            ),
            QueryCase("request_data", builder.request_data(100, 4, 5), "164.7 981.6"),
            QueryCase(
                "streaming_interval",
                builder.query_streaming_interval(),
                "A 250",
            ),
            QueryCase(
                "data_frame_format",
                builder.query_data_frame_format(),
                "A ABS_PRESSURE TEMP VOLUMETRIC_FLOW MASS_FLOW SETPOINT GAS",
            ),
            QueryCase(
                "manufacturer_info",
                builder.query_manufacturer_info(),
                "Alicat Scientific",
            ),
            QueryCase(
                "firmware_version",
                builder.query_firmware_version(),
                "A 10v05 2023-02-01",
            ),
            QueryCase("control_point", builder.query_control_point(), "A R122=37"),
            QueryCase("baud_rate", builder.query_baud_rate(), "A 19200"),
            QueryCase("setpoint", builder.query_setpoint(), "A 1.0 1.0 7 SLPM"),
            QueryCase(
                "setpoint_via_query_or_set",
                builder.query_or_set_setpoint(),
                "A 1.0 1.0 7 SLPM",
            ),
            QueryCase(
                "available_gases",
                builder.query_available_gases(),
                "A 0 Air 1 Ar 8 N2",
            ),
            QueryCase("active_gas", builder.query_active_gas(), "A 0 Air"),
            QueryCase("valve_drive_state", builder.query_valve_drive_state(), "A 0.0"),
        )
        fake = ScriptedSerial(
            {case.command: f"{case.response}\r".encode("ascii") for case in cases}
        )
        client = AsyncSerialClient(
            "/dev/ttyFAKE",
            timeout=0.1,
            serial_factory=lambda **kwargs: fake,
        )

        for case in cases:
            with self.subTest(case=case.name):
                self.assertEqual(await client.request(case.command), case.response)

        self.assertEqual(
            fake.writes,
            [f"{case.command}\r".encode("ascii") for case in cases],
        )


if __name__ == "__main__":
    unittest.main()
