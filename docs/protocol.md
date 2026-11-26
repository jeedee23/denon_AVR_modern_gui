# Protocol and evidence ledger

No receiver was accessible in the development sandbox. Automated tests use
synthetic examples, not packet recordings. The owner's power-on test predates
this implementation; its date and firmware were not supplied.

| Capability | Transport/example | Evidence/source | Status | Test time / firmware |
|---|---|---|---|---|
| Power ON | HTTP :8080 `/goform/formiPhoneAppDirect.xml?PWON` | Owner's successful curl, HANDOFF | VERIFIED by owner | Not supplied / unknown |
| System standby | HTTP `PWSTANDBY` | General Denon references below | PROPOSED; opt-in plus PW readback required | Not hardware tested / unknown |
| System/Main power readback | TCP `PW?`, `ZM?` | General protocol references | PROPOSED; separate fields, never conflated | Not hardware tested / unknown |
| Volume/status | TCP `MV?`; HTTP `MVxx` / `MVxx5` | General protocol references, synthetic unit tests | PROPOSED; guarded candidate writes | Not hardware tested / unknown |
| Mute, input | `MU?`, `SI?`, candidate HTTP `MUON/OFF`, `SI…` | General references | PROPOSED; opt-in and readback required | Not hardware tested / unknown |
| Listening mode readback/events | TCP `MS?`, `MS…` events | General references | PROPOSED; no mode writes | Not hardware tested / unknown |
| Live state events | TCP 23, CR-delimited | denonavr monitoring documentation | PROPOSED; HTTP polling fallback | Not hardware tested / unknown |
| Main HTTP status | `/goform/formMainZone_MainZoneXmlStatus.xml`, `/goform/formMainZone_MainZoneXml.xml` | denonavr/common Denon endpoint candidates | UNVERIFIED; recognized parsed fields required | Not hardware tested / unknown |
| Zone 2 readback | TCP `Z2?`, `Z2ON/OFF`, `Z2MU…`, `Z2xx`; HTTP `/goform/formZone2_Zone2XmlStatus.xml` | General references / library endpoint candidates | PROPOSED; no Zone 2 writes | Not hardware tested / unknown |
| Input labels/list | HTTP `/goform/Deviceinfo.xml`, `InputSource/FuncName`, `Rename` | Conservative candidate XML parser | UNVERIFIED; absent/unknown schema disables input writes | Not hardware tested / unknown |
| Audyssey, Dynamic EQ, trims | Candidate PS / CV command families | Older model-dependent documentation | UNVERIFIED; no commands sent | Not hardware tested / unknown |
| Calibration, distances, crossovers | Persistent setup | Not authorized | OUT OF SCOPE; no writes | Not tested |
| HEOS / DLNA / AVTransport | Separate protocols | Ecosystem references | NOT CORE AVR CONTROL | Not tested |

Development date: 2026-11-26. Update this ledger after each deliberate owner
test with UTC timestamp, firmware, command/query, before/after state and a
reviewed sanitized log file reference. Never promote a write command solely
because a read query exists, a library supports a related family, HTTP returns
200, or a socket accepts bytes.

## Wire behavior and limitations

- HTTP control uses the proven path with a single quoted allowlisted command
  after `?`, no implicit form key. Empty bodies are legal and do not confirm
  state. No redirects, proxies, broad URL access, or retries of writes.
- HTTP/TCP share one pinned private destination resolved from the configured
  hostname. All DNS answers must be LAN-private; loopback, public, documentation,
  multicast and carrier-grade NAT addresses are refused. No Tailscale access
  is enabled. OS DNS resolution itself follows the host resolver's timeout.
- XML is bounded to 64 KiB and rejects DTDs/entities and NUL-encoded documents.
  Only known fields produce state. Main XML `Power` is Main Zone, not system PW.
- Denon `MV00` means −80 dB, `MV50` means −30 dB and `MV505` means −29.5 dB.
  The absolute range is −80 through +18 dB in half-steps; GUI safety ceilings
  are stricter. `MVUP`/`MVDOWN` are not used by the GUI: bounded absolute
  half-step writes avoid ambiguous relative retry outcomes.
- The worker serializes all requests. At most one non-safety-reducing write
  awaits readback; rate limit is 400 ms. Identical absolute-volume requests
  are suppressed. Pending expires after ten seconds as **Indeterminate**.
  New polls/events can confirm target state but are not proof of causation.
- TCP sends only fixed read queries on connect and each poll. Unsolicited
  CR-delimited events are drained between polls; TCP retry is capped at once
  per 30 seconds. Some firmware permits only one TCP client; failure falls
  back to polling. A closed TCP stream is shown offline until refresh recovers.
- Polling backs off up to 60 seconds offline, and at least 30 seconds in
  standby. A pending action temporarily requests faster readback. Individual
  HTTP/TCP operations have short timeouts, though a full multi-endpoint probe
  can take several timeouts. Closing the window remains asynchronous.
- Source lists, XML schemas and half-step support still need X3400H firmware
  validation. Source metadata refreshes at most once per minute.
  Unknown fields/modes and unreported metadata remain Not available.

## Reference evaluation

- Official **similar-family**, not X3400H certification:
  <https://assets.denon.com/DocumentMaster/UK/AVRX3000_PROTOCOL_1020__V03.pdf>.
  Not independently retrieved/verified in this session.
- Maintained Python library: <https://pypi.org/project/denonavr/> and
  <https://github.com/ol-iver/denonavr>. Evaluated 2026-11-26 as an MIT-licensed
  reference. Its generic post-2016 HTTP/TCP support is not hardware evidence.
  Not vendored, copied or added as a dependency; the small core here keeps
  protocol safety and evidence gating explicit. Reconsider an adapter as
  real response coverage grows instead of duplicating advanced functionality.
- Community reference, not certification:
  <https://github.com/alsak0de/marantz-denon-mqtt/blob/main/docs/telnet/MARANTZ_DENON_TELNET_PROTOCOL.md>.
- Dashboard inspiration only:
  <https://github.com/OxygenLack/Denon-Marantz-AVR-Dashboard>.
- Owner's Android app:
  <https://play.google.com/store/apps/details?id=com.dmholdings.DenonAVRRemote>.
  No artwork/assets or implementation copied.

## Optional future capture workflow

Capture import is deliberately not implemented without an explicit request.
If requested, capture only user-authorized traffic to/from the owned receiver
using an owner-controlled endpoint or authorized switch mirror. Never silently
intercept a phone, manipulate a router, or rely on passive Wi-Fi sniffing.
Keep original pcap/pcapng outside Git (ignored), manually remove all personal
data, and derive minimal synthetic fixtures. Attribute commands to one
deliberate action, compare readback, and record firmware/time before updating
the ledger. Diagnostic JSON exports are not packet captures.
