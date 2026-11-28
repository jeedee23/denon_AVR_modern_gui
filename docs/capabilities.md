# Capability matrix

## Platform targets

The four platform targets are Ubuntu, Windows, macOS, and the existing Android
app. This repository implements the native desktop controller for Ubuntu,
Windows, and macOS; Android remains a separate existing app to optimize later.
Automated validation in this repository has been performed in the available
Linux environment. Windows and macOS startup still need to be checked on their
respective systems.

| Feature | Availability | Notes |
|---|---|---|
| Local discovery | Verified on owner's X3400H | Read-only SSDP search and local UPnP device description; manual address entry remains available. |
| Receiver status polling | Candidate / unverified | Polls a likely Denon Main Zone XML endpoint; support must be confirmed on the X3400H. |
| Power on | Available | Explicit user action only; the owner verified the HTTP command on this receiver. |
| Standby, volume, mute, input selection | Unavailable | Not implemented because command behavior has not been verified. |
| Zone 2 | Unavailable | Kept distinct from Main Zone; no endpoint or command is assumed. |
| Listening / Audyssey / channel calibration | Unavailable | No unverified configuration writes are exposed. |
| Simulation | Available | `--simulate` runs without receiver hardware. |

Automatic synchronization currently means periodic Main Zone status polling. Unsolicited Telnet event synchronization is not implemented. Polling observes remote/app changes only if the receiver's status endpoint reports them; otherwise the UI reports the endpoint error instead of fabricating state.
