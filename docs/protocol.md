# Protocol status and evidence

| Capability | Transport / endpoint | Evidence | Status |
|---|---|---|---|
| Power on | HTTP `:8080/goform/formiPhoneAppDirect.xml?PWON` | Owner confirmed with `curl` on the X3400H | Verified by owner |
| Discovery | SSDP multicast and UPnP device description | Read-only scan on 2026-11-26 returned `Denon AVR-X3400H`; firmware version not recorded | Verified on owner's receiver |
| Main Zone status | HTTP `:8080/goform/formMainZone_MainZoneXml.xml` | X3400H returned HTTP 403 on 2026-11-28 | Forbidden on tested firmware |
| Read-only status queries | TCP port 23: `PW?`, `ZM?`, `MV?`, `MU?`, `SI?` | X3400H returned power, volume, mute and input responses on 2026-11-28 | Verified on receiver; not implemented in app |
| System standby | TCP port 23: `PWSTANDBY` | With owner authorization, one command sent on 2026-11-28; receiver replied `PWSTANDBY` and `ZMOFF`; owner confirmed shutdown | Verified on receiver; not implemented in app |
| Unsolicited state updates | TCP port 23 | Standby command produced power responses; external remote changes not tested | Partially observed; not implemented in app |
| Main volume | TCP port 23: `MVnn` | Owner-authorized changes and fades between 40 and 65 confirmed by receiver and owner on 2026-11-28 | Verified on receiver; not implemented in app |
| Dolby channel temporary trims | TCP port 23: `CVSDL`, `CVSDR` | Owner-authorized swaps between -12 and +12 dB were confirmed; both restored to +4.5 dB on 2026-11-28 | Verified on receiver; not implemented in app |
| All channel temporary trims | TCP port 23: `CVFL`, `CVFR`, `CVC`, `CVSW`, `CVSL`, `CVSR`, `CVSDL`, `CVSDR` | Owner-authorized speaker test on 2026-11-28 set all trims to 0 dB and restored originals; readback confirmed restoration | Verified on receiver; not implemented in app |
| Extended status queries | TCP port 23: `MS?`, `CV?` | X3400H returned sound mode and all channel trims on 2026-11-28; responses interleave unsolicited `SSSPC`/`OPSTS` status lines | Verified on receiver; not implemented in app |
| Multichannel PCM over HDMI | Windows WASAPI 7.1 PCM 48 kHz to CBL/SAT input | Owner-authorized speaker test on 2026-11-28 played 425 Hz per channel and an LFE sweep from a Windows 11 mini-PC; the owner confirmed the whole pass was correct, including audible back-channel probe tones; a later owner observation confirmed the BL/BR channels fold into the front speakers on this layout (7.1-capable amp configured 5.1.2 with a Surround Dolby pair mounted ~6 m back), so the Surround Dolby pair is not addressable via HDMI PCM. After HDMI EDID renegotiation Windows can fall back to a stereo endpoint; a receiver power cycle restored 7.1 on 2026-11-28 | Verified route; owner-confirmed pass |
| Graphic EQ on/off | TCP port 23: `PSGEQ ON` / `PSGEQ OFF`; query `PSGEQ ?` | Owner toggled GEQ in the Denon app on 2026-11-28; matching unsolicited events and query responses observed | Verified on receiver; not implemented in app |
| Graphic EQ band read | TCP port 23: `SSAEQLRS ?` | X3400H returned one line per speaker group (`FRO`, `CEN`, `SUR`, `SBK`, `FRH`, `TFR`, `TPM`, `FRD`, `SUD`) with nine `:`-separated band values (63 Hz-16 kHz) ending `SSAEQLRSEND` on 2026-11-28; changing a slider in the Denon app emits the same lines unsolicited | Verified on receiver; not implemented in app |
| Graphic EQ band write | TCP port 23: `SSAEQLRSFRO v1:...:v9` | Owner-authorized 1 kHz test on 2026-11-28 looped band 5 between 560 and 300 three times; every write confirmed by readback and the original values were restored. Encoding: 500 = 0 dB, half-dB steps x10, range 300 (-20 dB) to 560 (+6 dB). Owner observed the audible effect lags noticeably and the Denon app UI does not refresh until GEQ is toggled off/on | Verified on receiver; audible application lags; not implemented in app |
| Zone 2 power | TCP port 23: `Z2ON` / `Z2OFF` | Standard Denon protocol; status events `Z2ON`/`Z2OFF` parsed. The app sends `Z2ON` one second after `PWON` and `Z2OFF` before `PWSTANDBY` so both zones follow the power buttons | Candidate; not yet verified on this receiver |
| Sound mode for speaker test | TCP port 23: `MSDIRECT`; restore via `MS<reported mode>` | Standard Denon protocol. The speaker test session switches to Stream Direct (reported as `MULTI CH IN` with multichannel PCM input) so probe tones are not upmixed into the Dolby surround pair; the prior mode is restored and checked by readback when the session ends | Candidate; not yet verified on this receiver |
| Mute, input, sound mode changes | Various HTTP or Telnet commands | No write tests performed | Unverified |

The app's startup and polling paths are read-only. The power-on action is the only control command exposed and is never sent automatically. An HTTP success response means only that the request returned; after power-on the UI refreshes status and labels the command as pending until status confirms it.

The firmware version was not recorded. No receiver hardware was contacted during
automated tests; the manual receiver checks above are separate from those tests.
