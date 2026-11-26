# Troubleshooting and live QA

## Development checks (2026-11-26)

Validated with Python 3.12 in the Linux sandbox: offline pytest suite, Ruff
lint/format, editable installation and console entrypoint, source/wheel builds
with included fixtures, simulated diagnostic export, and native xcb Qt under
Xvfb. The GUI exercised all seven tabs, resizing, theme changes and a 200%
scale factor. A screenshot of this application's simulation is in README.
These are software-only checks, not physical Ubuntu laptop, Windows or AVR
certification. Socket-pair tests cover trickling HTTP and total deadlines,
TCP fragmentation, cancellation and offline errors without accessing a LAN.

## Connection or unknown status

- Use the receiver's current private hostname/IP, HTTP port 8080 and TCP port
  23 unless you deliberately configured otherwise. A UPnP description port is
  not proof of the control port. No network inventory is stored.
- A closed/occupied Telnet port is normal on some setups. Close competing TCP
  clients or use HTTP fallback. Do not change router/firewall settings blindly.
- Check network standby/network control settings in the AVR's own manual.
  A sleeping receiver may not answer. There are no automatic power writes.
- HTTP 200 without recognized XML is not Connected. Run a read-only diagnostic
  and record the missing endpoint/firmware. Do not enable more commands to
  compensate for unavailable readback.
- Public/loopback/CGNAT endpoints are intentionally rejected. Mixed
  public/private DNS answers are also rejected. Use a private LAN address.
- Reconnects use read-only queries with exponential offline backoff. Press
  Refresh for an explicit probe; do not repeat write commands after a timeout.
  Readback might take longer during startup.

## GUI or packaging

- Confirm Python 3.12+ and the active virtual environment. Install editable
  package and dev extra from the repository root, not from `src`.
- Missing xcb dependencies: install the Ubuntu packages listed in README.
  Wayland users can try `QT_QPA_PLATFORM=xcb` under XWayland if necessary.
  Do not use root to work around display permissions.
- Headless testing: `QT_QPA_PLATFORM=offscreen python -m pytest tests/test_gui.py`.
- Qt high-DPI scaling is automatic. Check a normal desktop at 100%, 150% and
  200%; `QT_SCALE_FACTOR=2 python -m denon_controller --simulate` is a useful
  visual check, not a substitute for real 4K QA.
- On Windows use Python 3.12+, `py -3.12 -m venv .venv`,
  `.venv\Scripts\python -m pip install -e ".[dev]"`, then the PowerShell launcher.
  Windows has not been tested in this session.
- Invalid TOML fails clearly rather than silently loading unsafe defaults.
  Back up/repair the per-user config or point `--config` at a valid file.

## Safety and diagnostics

- Only Power ON is owner-verified. To test candidate controls deliberately,
  enable the per-session warning checkbox with the AVR at a quiet level.
- If measured volume is above the configured ceiling, `−` can still reduce it.
  The slider is clamped to the ceiling and only writes on an explicit mouse
  release; receiving status, focusing it or pressing arrow keys sends nothing.
- A pending write blocks further non-safety-reducing writes. Muting or reducing
  volume remains possible, without forgetting unresolved quieter volume targets.
  A timed-out send is indeterminate, never retried.
- Freshness is per field, at most ten seconds (or twice the poll interval if
  shorter). A Zone 2 or source event does not refresh volume. Use Refresh before
  changing controls if standby polling or backoff makes their readback stale.
- Unmute requires measured volume at or below the safe ceiling. System standby can affect
  Zone 2 and is guarded. Persistent calibration is never written.
- Logs contain safe categories and parsed numeric state, not raw XML, MAC
  inventory, packet captures, track titles or authentication material.
  Configured host/IPs and IP/MAC/URL patterns are masked. No sanitizer can
  guarantee arbitrary free text is safe: review every export before sharing.

## Owner hardware checklist (not completed)

Record UTC time, firmware/version and sanitized evidence for each step:

1. Set a conservative volume on the physical AVR. Run **read-only** diagnostics
   first; note endpoints and power fields available. Keep Zone 2 separate.
2. Try deliberate HTTP Power ON once from standby. Observe the actual AVR and
   matching readback; pending/indeterminate is acceptable when no status API
   has yet been confirmed.
3. Change volume, mute, source and listening mode with the original remote and
   phone. Confirm GUI events or polling follow those changes.
4. Only with opt-in, test one basic candidate write at a time, checking before/
   after state. Input selection requires a genuine reported source list.
5. Unplug Ethernet, power-cycle, allow standby, and change Wi-Fi networks.
   Confirm a responsive window, offline indication, no write retries, bounded
   polling and read-only recovery. Test closing while an operation times out.
6. Check Zone 2 remains unchanged; do not test calibration or advanced writes.
7. Test Ubuntu laptop/4K scaling and accessibility, then Windows if available.

Do not mark a hardware milestone complete based on simulator screenshots,
unit tests or successful socket/HTTP delivery.
