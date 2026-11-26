from typing import Protocol


class ReceiverTransport(Protocol):
    def send(self, command: str) -> None: ...

    def close(self) -> None: ...
