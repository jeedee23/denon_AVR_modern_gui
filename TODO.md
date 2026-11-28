# Implementation milestones

- [x] Bootstrap package metadata, settings template, and ignore rules.
- [x] Add typed state, HTTP client, owner-verified power-on action, and offline simulation.
- [x] Add a native Qt window with non-blocking network operations and periodic status polling.
- [x] Add a diagnostic CLI and protocol/capability documentation.
- [x] Add offline tests for protocol construction, state parsing, settings, and safety.
- [ ] Confirm the candidate Main Zone status endpoint against the X3400H and record firmware/date/evidence.
- [ ] Add robust input/volume/mute controls only after command support and safe bounds are verified.
- [ ] Add Telnet status/event synchronization and HTTP fallback if confirmed available.
- [x] Add local SSDP discovery and manual receiver selection; scan verified against the owner's X3400H.
- [ ] Add Zone 2, advanced audio features, and sanitized diagnostics only as capabilities are verified.
- [ ] Complete Ubuntu/Windows usability checks, screenshots of this UI, and end-user setup documentation.
- [ ] Validate macOS startup and per-user settings path.
- [ ] Plan separate follow-up work to optimize the existing Android app; do not add Android UI to this desktop repository.
