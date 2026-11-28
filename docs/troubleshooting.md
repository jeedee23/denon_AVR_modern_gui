# Troubleshooting

- **Scan finds no receiver:** verify that the AVR and computer are on the same
  local network, that network discovery is enabled on the receiver, and that
  the firewall/router allows SSDP multicast (UDP 1900) and replies. Standby,
  guest-network isolation, and multicast filtering can prevent discovery.
  Use the receiver's IP or hostname manually if necessary. A discovered UPnP
  device does not guarantee its control or status endpoints are supported.
- **Cannot connect:** verify the receiver address and that the computer can reach it on the local network. The app rejects public destinations and uses a short configurable timeout.
- **Connected but fields say “Not available”:** the candidate status endpoint may not be supported by this firmware, or the XML field names may differ. Do not treat the candidate as verified until a sanitized response is recorded.
- **Status is not immediate:** the UI polls at the configured interval (default 3 seconds). Telnet event listening is not yet implemented.
- **Qt is missing:** install `python3-pyside6.qtwidgets` from Ubuntu packages or install the project with `python -m pip install -e '.[dev]'` in a virtual environment.
- **Safe test without an AVR:** run `python -m denon_controller --simulate`.
