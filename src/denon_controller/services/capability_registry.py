from dataclasses import dataclass

from denon_controller.models import DeviceState, Evidence


@dataclass(frozen=True)
class Capability:
    name: str
    evidence: Evidence
    detail: str


def capabilities(state: DeviceState) -> list[Capability]:
    result = [
        Capability(
            "Power ON / HTTP", Evidence.VERIFIED, "Owner curl test; firmware/date not supplied"
        ),
    ]
    for name, available in (
        ("Main Zone power readback", state.main.power is not None),
        ("System power readback", state.system_power is not None),
        ("Volume readback", state.main.volume_db is not None),
        ("Mute readback", state.main.mute is not None),
        ("Input readback", state.main.source is not None),
        ("Reported input list", bool(state.sources)),
        ("Listening mode readback", state.surround is not None),
        ("Zone 2 readback", state.zone2.power is not None),
    ):
        result.append(
            Capability(
                name,
                Evidence.OBSERVED if available else Evidence.PROPOSED,
                "Simulation only"
                if state.protocol == "Simulation"
                else "Readback does not certify candidate write commands",
            )
        )
    for name in (
        "Standby / volume / mute / input writes",
        "Listening mode writes",
        "Audyssey / Dynamic EQ / Dynamic Volume",
        "Temporary channel trims",
        "Calibration / distances / crossovers",
        "HEOS / playback metadata",
    ):
        result.append(Capability(name, Evidence.PROPOSED, "Requires separate live validation"))
    return result
