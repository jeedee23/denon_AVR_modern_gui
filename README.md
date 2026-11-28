# Denon AVR Controller

A native PySide6 desktop app for Ubuntu, Windows, and macOS, for monitoring a
Denon AVR over the local network. The existing Android app is a separate
project; optimizing it is a later task.
The current UI supports automatic Main Zone status polling and the owner-verified
power-on request. The Main Zone status endpoint is still a candidate and must be
confirmed against the X3400H before its fields are treated as verified.

## Quick start

Requires Python 3.12 or newer. Run the commands for your desktop OS from the
directory where you cloned this repository.

### Ubuntu

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
cd ~/github/repos/denon_AVR_modern_gui
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m denon_controller
```

### Windows PowerShell

Install Python 3.12 or newer, open PowerShell in the cloned repository
directory, then run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m denon_controller
```

### macOS

Install Python 3.12 or newer, open Terminal in the cloned repository
directory, then run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m denon_controller
```

macOS support is a target but has not yet been validated on a macOS machine.

If PowerShell blocks activation, allow it for the current process with
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate the
environment again.

If you already created `.venv` in another directory, activate this project's
environment instead: `cd ~/github/repos/denon_AVR_modern_gui` followed by
`source .venv/bin/activate`. Then rerun `python -m pip install -e '.[dev]'`
from the project directory. On Windows, use
`.\.venv\Scripts\Activate.ps1` instead.

On launch the app scans the local network for Denon devices using UPnP
discovery. If one device is found, it fills in its IP address and connects
automatically when no address is saved and auto-connect is enabled. A saved
address is never replaced automatically; if auto-connect is enabled, the app
connects to it after scanning. If several devices are found, select yours and
click **Connect / refresh**. Use **Scan for Denon** to scan again, or enter
the receiver's private LAN IP/hostname manually if discovery fails.
Once connected, it polls automatically at the configured interval
(default: 3 seconds), including after a refresh error, so changes from the
physical remote show up when the receiver status endpoint exposes them. The
network operations run outside the GUI thread. Simulation mode is
available without a receiver:

```bash
python -m denon_controller --simulate
```

The auto-connect preference is enabled by default. After a successful
connection, the host and polling preference are saved in the per-user config,
so the app reconnects and resumes syncing on later launches. The user config is
stored at `~/.config/denon-avr-controller/config.toml` on
Linux (or the equivalent per-user roaming directory on Windows). Start from
[config.example.toml](config.example.toml). The app only sends the verified
`PWON` control when the user clicks **Power on**; a successful HTTP response is
shown as pending until refreshed status can confirm it. Other controls are not
implemented rather than being presented as tested.

Check connectivity without changing receiver state:

```bash
denon-diagnose --host 192.168.1.100
```

Run offline checks:

```bash
pytest
ruff check .
```

See [protocol evidence](docs/protocol.md), the [capability matrix](docs/capabilities.md),
and [troubleshooting](docs/troubleshooting.md). The original handoff and
implementation brief is preserved in [HANDOFF.md](HANDOFF.md).

## Original implementation brief

Audience: GitHub Copilot Agent in VS Code
Goal: Create a complete, maintainable Git repository with a working native Linux GUI to control and monitor a Denon AVR-X3400H over the home LAN.
Status: Requirements and implementation assignment; NOT a claim that all AVR commands have been validated.
1. Known facts from the owner (do not rediscover or second-guess)
- AVR: Denon AVR-X3400H; UPnP identity 9f290714-7ad0-dbfb-2e05-29fd9110fec4.
- AVR LAN IP during testing: 192.168.10.192. Make configurable; never assume it stays fixed.
- UPnP device description observed: http://192.168.10.192:60006/upnp/desc/aios_device/aios_device.xml; Aios 4.025 was reported. This is a discovery descriptor, not proof that port 60006 is the primary control API.
- Confirmed functional command: curl --max-time 5 'http://192.168.10.192:8080/goform/formiPhoneAppDirect.xml?PWON' powered the AVR on from Ubuntu. Treat this as the only owner-verified control command at handoff.
- Desktop targets: Ubuntu, Windows, and macOS; Python and VS Code/Copilot. The existing Android app is separate and can be optimized in a later task; do not replace it with a new Android implementation in this desktop repository.
- User wants a complete GUI and full repository, not a one-command demonstration. Priorities are direct AVR control, accurate live status and discoverability of advanced functions. A future network-capture workflow may help document commands used by the Android app.
- Do not rely on Home Media Server for AVR control. HMS can remain a separate DLNA/HEOS media tool.
2. Assignment / deliverables
Create the repository denon-avr-controller in the current VS Code workspace (ask only if the target folder genuinely cannot be determined). Implement code, tests, scripts, docs and usable UI. Do not stop after scaffolding. Do not claim any untested advanced command works.

Required repository layout (adapt if justified, document deviations):
denon-avr-controller/
  README.md
  HANDOFF.md                     # copy of this briefing
  pyproject.toml
  .gitignore
  .env.example                   # optional, no secrets
  config.example.toml
  docs/
    protocol.md                  # tested/untested commands, evidence and limitations
    capabilities.md              # feature matrix and receiver constraints
    troubleshooting.md
    screenshots/                 # screenshots of OUR GUI only
  src/denon_controller/
    __init__.py
    __main__.py                  # python -m denon_controller
    app.py
    settings.py
    models.py                   # typed DeviceState, ZoneState, capabilities
    transport/
      http.py
      telnet.py
      discovery.py
    services/
      receiver.py               # high-level actions, state synchronization
      capability_registry.py
      diagnostics.py
    ui/
      main_window.py
      overview.py
      sources.py
      sound.py
      channels.py
      zones.py
      diagnostics.py
      settings.py
  tests/
    test_protocol.py
    test_state_parsing.py
    test_volume.py
    test_safety.py
    test_offline.py
    fixtures/                   # sanitized responses, no private IPs/secrets
  scripts/
    diagnose_avr.py
    export_capabilities.py
    run_linux.sh
    run_windows.ps1
3. Technology and UX
- Use Python 3.12+, type hints, pytest, ruff, packaging via pyproject.toml and a virtual environment.
- Preferred native GUI: PySide6 / Qt Widgets (single desktop window, responsive resizing, readable on high-DPI 4K screens, native keyboard focus). Do not use a heavyweight web front-end unless there is a compelling reason.
- Keep network I/O off the GUI thread (Qt signals + worker thread or a deliberate Qt/async integration). No freezes on unplugged Ethernet, sleeping AVR or timeouts.
- Accessible, reasonably large buttons and text; light/dark theme support; visible focus outlines; tooltips. Keyboard shortcuts only where safe.
- Clear labels for Connected, Connecting, Offline, Standby, Unsupported, Unverified, Error. Never show a command as successful solely because HTTP returned status 200 or socket.send succeeded; read back AVR state or show Sent, awaiting confirmation.
- Display Main Zone first. Keep Zone 2 distinct (do not mistake system power PW for main-zone power ZM).
- Settings: hostname/IP, HTTP port default 8080, Telnet port default 23, poll interval, auto-connect, volume ceiling, optional diagnostics verbosity, UDP discovery on/off.
- Store user configuration using an appropriate per-user config directory. Never store credentials, secrets, or private packet captures in Git. Allow hostname discovery and manual IP entry.
- Prefer UI status that reflects physical remote changes, not just clicks in our app.
4. Proposed GUI sections
Overview / Always-visible header
- AVR name, connection indicator, actual power and Main Zone power, current input, listening/surround mode, mute, measured volume in dB and readable volume controls.
- Big Power ON / Standby button with state readback; guarded shutdown if needed. Volume +/- and bounded slider; avoid an accidental jump when the slider first receives state.
- Signal/status information when available: input audio format, active output channels, sampling info, artist/track for network playback. If no reliable API, show Not available rather than invent values.
Inputs
- Show only inputs detected/supported on this receiver. Include TV Audio, CBL/SAT, Blu-ray, Game, Media Player, HEOS etc. only if reported or verified. Handle renamed/reassigned inputs and dynamic source lists.
Sound / Audio
- Listening modes (Stereo, Direct, Pure Direct, Dolby/DTS modes, etc.) by capability, not one hard-coded universal list.
- Audyssey MultEQ XT32, Dynamic EQ, reference level offset, Dynamic Volume, tone, bass/treble, dialogue and related sound controls only when verified. Indicate modes that the receiver temporarily disallows depending on source/input signal.
Channels / Speakers
- Visual input/output speaker layout if status data exists.
- Per-channel temporary level trims where exposed, with safe bounds, plus readback. Do not confuse temporary channel trims with calibration levels/distance/crossover or write into saved Audyssey calibration settings.
- Treat persistent speaker setup, distances, crossovers and equalizer calibration as read-only or out of scope until separately supported and authorized.
Zones
- Main and Zone 2 status, power, source, mute, volume where actually supported.
Diagnostics
- Display protocol, connected ports, roundtrip timings, last error and supported capabilities.
- Event log with timestamp, command category and parsed response (mask private and sensitive data).
- Optional explicit Capture diagnostic session/export of sanitized logs; do not silently intercept network traffic or manipulate the router/network.
- Read-only command probe area; optional Advanced manual raw-command terminal hidden behind a clear warning and allowlist/confirmation. No uncontrolled scanning or discovery beyond the user's LAN.
5. Protocol strategy and verified facts
Use a clean abstraction (ReceiverTransport) so HTTP and TCP can coexist and the high-level UI never constructs raw URLs or port-23 strings.
1. HTTP API (confirmed for power-on on this unit):
   GET http://192.168.10.192:8080/goform/formiPhoneAppDirect.xml?PWON
   Use proper URL construction and fixed allowlisted parameters; set short timeouts and handle XML/text/empty responses.
2. Denon Telnet/IP control is widely documented on port 23, with commands typically terminated by carriage return \r. It is generally bidirectional: some models send unsolicited state changes. First probe connection and read-only status, and gracefully fall back to HTTP polling if Telnet is closed, occupied, filtered or unsupported on this firmware.
3. HTTP status endpoints: discover and confirm which ones return data on the X3400H (possibly goform/formMainZone_MainZoneXml.xml, goform/formZone2_Zone2Xml.xml and other Denon endpoints; their presence is not verified yet). Do not assume an endpoint works because a different Denon model has it.
4. UPnP/SSDP may discover receiver details; avoid conflating AVTransport, DLNA media playback, HEOS, and AVR amp/control protocols.
5. Consider using the maintained Python denonavr library as a reference or adapter for base control/status; evaluate supported model behavior and licensing. Avoid redundant code if robust, but keep own abstraction so advanced features and diagnostics can evolve independently.
6. Serial/IP Denon protocol examples such as PWON, PWSTANDBY, PW?, MV?, MVUP, MVDOWN, MU?, SI?, ZM? occur in published documentation. These are candidate commands; validate their support and exact semantics on this receiver before exposing them as confirmed.
7. Listening modes, channel-level commands, Audyssey settings and HEOS control may vary by firmware and source. Mark candidates as PROPOSED until verified by read-only queries or safe, opt-in action tests.
Initial protocol evidence ledger
Capability	Transport / example	Evidence	Status
Power ON	HTTP :8080/goform/formiPhoneAppDirect.xml?PWON	Owner ran curl and confirmed it works	VERIFIED
Power standby	HTTP ...?...PWSTANDBY; IP PWSTANDBY\r	General Denon protocol references	PROPOSED; verify
Receiver power query	Telnet PW?\r	General protocol refs	PROPOSED; verify
Volume up/down/status	MVUP, MVDOWN, MV?	General protocol refs	PROPOSED; verify
Mute, input, surround modes	MU..., SI..., MS...	General protocol refs	PROPOSED; verify
Live state events	TCP 23	denonavr documentation and community references	PROPOSED; verify
Audyssey / dynamic EQ / channel trims	Various PS... / CV...	Older model-dependent Denon docs	UNVERIFIED on X3400H
HEOS	Separate protocol, depending on receiver	HMS and ecosystem docs	NOT PART OF CORE AVR CONTROL until tested


Keep this ledger updated with a test timestamp, receiver firmware/version and source (log/file or URL). Never misrepresent an older protocol reference as an X3400H-specific certification.
6. Safety and correctness requirements
- No automation that sends commands on application start except read-only queries. Startup must not turn on the AVR, change a source, start loud playback or alter a surround setting.
- Add a configurable safe maximum volume (initial default conservatively low, e.g. -30 dB for direct absolute setting); always allow softer and mute operations. Relative volume operations should be rate-limited and users must see current state. Direct-volume mapping must be unit-tested: Denon uses protocol-specific integer/half-step encoding; do not equate UI dB directly to raw protocol numbers.
- Do not automatically toggle Zone 2 or write calibration/EQ settings.
- Rate-limit commands, suppress duplicate slider writes and serialize responses as needed. Reconnect on network interruption; do not spam requests while in standby.
- Timeouts and retry behavior must not cause repeated toggle or relative volume commands. Mark indeterminate outcomes and refresh state.
- Validate that the destination address is the user's configured receiver; no remote cloud control, credential sharing, or access outside authorized private network.
- Avoid persistence of full local MAC/IP inventory in public logs or version control; mask IPs in bug reports by default.
- Unit tests must run without an AVR or internet; use mocked HTTP/TCP transports and fixture recordings.
7. Implementation milestones (complete these in order)
1. Bootstrap project: repo, README, modern Python packaging, environment setup, licensing decision, formatting/lint/test tasks, runnable blank Qt window and sample config.
2. Protocol diagnostic CLI: non-destructive python -m denon_controller ... or scripts/diagnose_avr.py for HTTP connectivity and optional Telnet read-only query; save sanitized results. Explicit opt-in --power-on for the already-verified command.
3. Receiver state model and transport: typed zones, parsing, timeouts, Telnet event listener and HTTP fallback, state change signals, simulated/offline transport.
4. Minimum usable GUI: connect/disconnect, confirmed power on, power status, volume, mute, input; use Unverified/disabled for functions until capability checks pass.
5. Advanced sections: zones, listening modes, sound/Audyssey, channel trims with real readback; device capabilities dynamically gate controls.
6. Diagnostics and capture analysis: import .pcap/pcapng only when requested, document traffic attributed to user-owned receiver; write tests from sanitized captures; avoid relying on passive Wi-Fi sniffing.
7. QA & documentation: test offline errors, power cycling, Wi-Fi roaming, AVR standby, physical remote changes, 4K scaling, Ubuntu and Windows startup. README includes screenshots of own app, explicit installation, launch commands and limitations.
8. Optional extras after core is stable: configurable presets, quick select, Tailscale access only with user approval, installable desktop launcher (.desktop), optional Windows packaging and read-only HEOS metadata.
8. Acceptance criteria
- python -m denon_controller opens a useful window on Ubuntu and can connect to a manually configured receiver.
- pytest and ruff check . pass locally; no known secrets, BitLocker recovery keys, account tokens or personal identifiers committed.
- It can power on the actual X3400H using the proven HTTP command when user clicks the button, with observable confirmation (or an accurate pending/error state).
- Further controls are actually tested, not mere UI decoration. Unsupported functions appear disabled or absent with an explanation.
- The displayed status follows changes made by the physical remote when an appropriate status channel exists (and falls back to polling).
- The GUI does not freeze when the receiver is unplugged/offline; failure/reconnection is clear.
- Setup is reproducible by another developer from README, and the owner can identify what is working and what remains to be verified.
9. Example end-user setup commands (adjust to created package)
# Ubuntu
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
cd denon-avr-controller
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m denon_controller
Implement the dev extra and entrypoint for real. If Qt libraries are missing on a target Ubuntu install, document exact apt packages needed; do not instruct users to run the GUI as root.
10. Research references (not an assurance of model-specific command support)
- Official Denon protocol example for similar AVR families: https://assets.denon.com/DocumentMaster/UK/AVRX3000_PROTOCOL_1020__V03.pdf
- Python Denon AVR library: https://pypi.org/project/denonavr/
- Python library source: https://github.com/ol-iver/denonavr (verify current repository/maintainer before relying on it)
- Community Denon Telnet/IP implementation reference: https://github.com/alsak0de/marantz-denon-mqtt/blob/main/docs/telnet/MARANTZ_DENON_TELNET_PROTOCOL.md
- Example community dashboard: https://github.com/OxygenLack/Denon-Marantz-AVR-Dashboard
11. Instructions to Copilot: begin now
1. Inspect the current workspace first. If this is already an existing repository, preserve its code and adopt a migration plan instead of overwriting files.
2. Create the implementation milestones as TODO.md with checkboxes and update it while coding.
3. Build the core runnable version in this session: repository, packaging, state model, HTTP client, simulation transport, GUI and automated tests.
4. Do not invent successful hardware tests. Mark live X3400H checks for the owner to execute only after code is ready.
5. Report exact run/test commands, what is implemented, what is mocked, what is unverified and the next safe test.
6. Ask the owner only for essential missing decisions; use the defaults above otherwise.