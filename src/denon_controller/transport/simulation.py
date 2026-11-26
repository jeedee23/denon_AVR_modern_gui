from denon_controller.models import DeviceState, apply_event, decode_volume


class SimulationTransport:
    def __init__(self) -> None:
        self.lines = ["PWSTANDBY", "ZMOFF", "MV35", "MUOFF", "SITV", "MSSTEREO", "Z2OFF"]
        self.sent: list[str] = []

    def query(self) -> list[str]:
        return list(self.lines)

    def send(self, command: str) -> None:
        self.sent.append(command)
        if command == "PWON":
            updates = ["PWON", "ZMON"]
        elif command == "PWSTANDBY":
            updates = ["PWSTANDBY", "ZMOFF"]
        elif command in ("MVUP", "MVDOWN"):
            current = next(line for line in self.lines if line.startswith("MV"))
            from denon_controller.models import encode_volume

            db = decode_volume(current[2:]) + (0.5 if command == "MVUP" else -0.5)
            updates = ["MV" + encode_volume(max(-80, min(18, db)))]
        else:
            updates = [command]
        for update in updates:
            prefix = update[:2]
            self.lines = [line for line in self.lines if line[:2] != prefix] + [update]

    def populate(self, state: DeviceState) -> None:
        for line in self.query():
            apply_event(state, line)
        state.sources = {"TV": "TV Audio", "BD": "Blu-ray (simulated)", "GAME": "Game (simulated)"}

    def close(self) -> None:
        pass
