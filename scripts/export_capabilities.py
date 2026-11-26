"""Export the evidence registry without connecting to any receiver."""

import json
from dataclasses import asdict

from denon_controller.models import DeviceState
from denon_controller.services.capability_registry import capabilities

print(json.dumps([asdict(capability) for capability in capabilities(DeviceState())], indent=2))
