# Implementation milestones

- [x] Bootstrap package metadata, settings template, and ignore rules.
- [x] Add typed state, HTTP client, owner-verified power-on action, and offline simulation.
- [x] Add a native Qt window with non-blocking network operations and periodic status polling.
- [x] Add a diagnostic CLI and protocol/capability documentation.
- [x] Add offline tests for protocol construction, state parsing, settings, and safety.
- [x] Confirmed the candidate HTTP Main Zone status endpoint is forbidden (403) on the X3400H; Telnet is the status channel.
- [x] Add volume control with a configurable safety limit; mute and input switching remain candidates pending verification.
- [x] Add Telnet status/event synchronization (realtime unsolicited events; no HTTP status fallback because the endpoint is forbidden).
- [x] Add local SSDP discovery and manual receiver selection; scan verified against the owner's X3400H.
- [ ] Add Zone 2, advanced audio features, and sanitized diagnostics only as capabilities are verified.
- [x] Add a speaker test tab (per-speaker tones over HDMI 7.1 PCM) with capture, restore, and readback verification.
- [x] Add a graphic EQ tab with realtime event sync and channel trim sliders (verified SSAEQLRS/CV commands).
- [ ] Complete Ubuntu/Windows usability checks, screenshots of this UI, and end-user setup documentation.
- [ ] Validate macOS startup and per-user settings path.
- [ ] Plan separate follow-up work to optimize the existing Android app; do not add Android UI to this desktop repository.
