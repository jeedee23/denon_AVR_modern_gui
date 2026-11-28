# Mini-PC handoff: Denon AVR controller

Updated: 2026-11-28. This is a working handoff, not a claim that the desktop
application is complete. Read the protocol evidence in [protocol.md](protocol.md)
and the outstanding work in [TODO.md](../TODO.md).

## Context and objective

The owner wants a native controller for a Denon AVR-X3400H. The existing
Android Denon AVR Remote is separate and can be improved later. The intended
desktop targets are Ubuntu and Windows; macOS was previously assumed as an
additional target and still needs owner confirmation.

The immediate request is to **perform a speaker test before further coding**:

- Set the receiver's main volume to 50 on its 0–98 scale.
- Temporarily set the channel adjustments shown in the Denon app to 0 dB.
- Play a 425 Hz tone for three seconds on each configured speaker channel.
- For the subwoofer, play a 100 Hz down to 50 Hz sweep over six seconds.
- Run the sequence once and restore the original receiver volume and channel
  adjustments afterward. The owner explicitly requested restoration.
- Ask for the owner's confirmation of the output mapping and safe test tone
  level before producing sound. Include an immediate stop method. Do not write
  persistent speaker setup, distances, crossovers, Audyssey calibration or EQ.

The mini-PC is connected by HDMI to the receiver's CBL/SAT input and runs Tidal.
It is visible from the current computer through RustDesk. Its OS, HDMI
multichannel format, channel mapping and audio libraries have **not** been
confirmed. Inspect those facts on the mini-PC before proposing playback. The
current Ubuntu computer cannot be assumed to provide that HDMI audio path:
its default PipeWire sink was its own laptop speakers, its HDMI sinks showed
stereo, and ALSA reported no connected HDMI monitor.

Playing a separate tone per speaker requires a verified multichannel PCM route
and known channel mapping; Telnet channel-trim controls alone do not generate or
route tones. In particular, do not claim independent Dolby speaker tests unless
the chosen route actually exposes those channels. Receiver upmixing, bass
management, the current sound mode, OS downmixing and channel layouts can all
change where a signal is played. Avoid interrupting Tidal or changing the
receiver's input without the owner's approval.

After the speaker test, the owner wants to test selection of listening modes
and perform an equalizer test. Exact modes, EQ controls, test sequence and
restoration need confirmation before changing them. The screenshots show Music
mode options including Stereo, Multi Ch In, Multi In + Dolby Surround,
Multi In + Neural:X, Multi Ch Stereo, Rock Arena, Jazz Club, Matrix and Virtual.
Availability depends on the receiver's current input signal.

## Actual receiver evidence

The owner verified prior HTTP power-on using
`/goform/formiPhoneAppDirect.xml?PWON` on port 8080. Discovery using SSDP/UPnP
found the AVR. A read-only GET to the app's candidate
`/goform/formMainZone_MainZoneXml.xml` endpoint on port 8080 returned **403
Forbidden** on 2026-11-28. The firmware version is unknown.

TCP port 23 works on this actual receiver. Read-only queries `PW?`, `ZM?`,
`MV?`, `MU?`, `SI?`, `MS?` and `CV?` received responses. The owner explicitly
authorized standby; a single `PWSTANDBY` produced `PWSTANDBY` and `ZMOFF`,
and the owner confirmed the receiver shut down. Power-on and absolute volume
changes were also tested. A three-cycle volume 40–65–40 test completed with
receiver readback and the owner confirmed it worked. The owner says 70 is very
loud and 80 is the maximum; the receiver separately reported `MVMAX 73`.

The user-authorized Dolby-channel test set main volume to 55 and alternated
the temporary channel adjustments. `CVSDL 38` / `CVSDR 62` and the reverse
were confirmed by the receiver. Both were restored to `545`, matching the
app's screenshot of **+4.5 dB**. `CV?` returned the following values at the
last read-only inspection (not a promise of current state):

| Channel | Telnet response | App screenshot |
|---|---|---|
| Front L / R | `CVFL 57`, `CVFR 57` | +7.0 dB each |
| Center | `CVC 50` | 0.0 dB |
| Subwoofer | `CVSW 56` | +6.0 dB |
| Surround L / R | `CVSL 56`, `CVSR 56` | +6.0 dB each |
| Surround Dolby L / R | `CVSDL 545`, `CVSDR 545` | +4.5 dB each |

At that inspection the receiver reported `PWON`, `ZMON`, `MV45`, `MUOFF`,
`SISAT/CBL` and `MSMCH STEREO`. Re-query before any action; the owner can change
state independently. Never assume that the displayed settings or IP address
are still current. Do not automatically power-cycle: shutting down the receiver
interrupts Tidal on the connected PC.

Existing reference implementations:

- [denonavr issue #438](https://github.com/ol-iver/denonavr/issues/438):
  another X3400H reports 403 on the Main Zone status endpoint while port 23
  and AppCommand work. This is not a substitute for testing the owner's unit.
- [denonavr PR #439](https://github.com/ol-iver/denonavr/pull/439): proposed
  Telnet/Deviceinfo fallback; it was open and unmerged when checked.
- [denonavr Telnet implementation](https://github.com/ol-iver/denonavr/blob/main/denonavr/api.py).
  Its README notes that receivers may support only one Telnet connection.
- [Community Telnet protocol notes](https://github.com/alsak0de/marantz-denon-mqtt/blob/main/docs/telnet/MARANTZ_DENON_TELNET_PROTOCOL.md)
  describe channel trim encoding; check actual receiver readback.

## Repository and transfer

The existing project is `denon_AVR_modern_gui`; do not create a nested Git
repository or overwrite existing work. The current GUI still uses the forbidden
HTTP status endpoint and does **not** implement the verified Telnet control.
Its simulation and unit tests do not demonstrate real AVR control.

At handoff, the worktree contains an edited README and many untracked project
files. They are **not automatically included in the remote repository**. Do
not assume cloning the remote transfers them. The owner should review and
explicitly decide how to transfer or commit these changes. Avoid publishing
private IP addresses, device identifiers, packet captures, the full chat
transcript, credentials or other sensitive material.

The conversation text export is a separate private session artifact on the
original machine. It includes recorded user and assistant messages and
interactive questions, but not the full tool-call log or embedded screenshots.
Transfer it only through a trusted channel, and review it before sharing.
Screenshots are described above; the original attachments are not bundled in
this repository.

## Next steps on the mini-PC

1. Establish authorized local or remote access and identify its OS, active
   HDMI sink, channel count, supported formats and actual speaker mapping.
2. Read receiver state over port 23; record every current channel trim, main
   volume, mute, input and sound mode without changing them.
3. Design a safe, low-amplitude test, verify routing, and explain any limitation
   (particularly Dolby height channels and subwoofer routing). Confirm the
   owner's desired setup and an emergency stop.
4. Run exactly the requested single test loop when routing is proven. Restore
   each captured setting on success, interruption and errors; report any
   restoration failure explicitly.
5. Only then clarify and perform the later mode and equalizer tests. Do not
   claim acoustic verification without the owner's observations.
