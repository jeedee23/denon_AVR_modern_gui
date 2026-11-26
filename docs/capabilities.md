# Capability matrix

| Feature | Implemented behavior | Receiver evidence |
|---|---|---|
| Native desktop | Resizable Qt window, scrollable tabs, keyboard focus, light/dark/system themes | Offscreen simulator QA; desktop/4K pending |
| Connect/disconnect | Read-only startup; worker thread; bounded network operations and backoff | Mocked offline/fallback tests |
| System / Main / Zone 2 | Distinct typed state and visible unknowns | Candidate parsing only |
| Power ON | Explicit click, one HTTP PWON, readback or pending/error | Owner-verified command; app-to-hardware pending |
| Standby | Guarded whole-system candidate, requires PW readback and session opt-in | Not hardware tested |
| Volume | Measured dB, ceiling, half-step mapping, +/- and release-only slider | Synthetic mapping/safety tests, live validation pending |
| Mute | Explicit on/off, never blind toggle | Candidate; opt-in and readback |
| Input selection | Reported tokens and renamed labels only, no static universal list | Candidate Deviceinfo schema; disabled if unavailable |
| Listening modes | Read current reported mode | Writes disabled; signal-dependent support unknown |
| Audyssey/tone/dialogue | Explained as unverified, disabled | No writes or claimed readback |
| Channels | Honest Not available; no invented speaker layout | No temporary trim or calibration writes |
| Zone 2 | Recognized status fields only | Writes disabled; sources may be unavailable |
| Signal/track metadata | Not available | No validated API |
| Discovery | Optional, explicit one-shot LAN SSDP; manual host entry always available | Descriptor is not a control endpoint |
| Diagnostics | Fixed read-only probes, bounded sanitized memory log, explicit JSON export | Synthetic tests |
| Capture import, HEOS, presets | Deferred, not placeholder working features | Requires explicit future scope/validation |

The capability registry differentiates **owner-verified command**, **readback
observed** and **unverified/proposed**. Simulation is visibly labeled and never
promotes a hardware capability. No list of Dolby/DTS or input capabilities is
assumed from another AVR model. Input-specific and firmware restrictions may
prevent a candidate action even after readback appears.

The original requested directory layout is used at the existing repository
root. `transport/simulation.py`, package `__init__.py` files and additional
settings/diagnostic/GUI tests are intentional additions. No separate web UI,
HMS integration, copied app branding or cloud control is involved.
