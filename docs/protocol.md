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
| Mute, input, sound mode changes | Various HTTP or Telnet commands | No write tests performed | Unverified |

The app's startup and polling paths are read-only. The power-on action is the only control command exposed and is never sent automatically. An HTTP success response means only that the request returned; after power-on the UI refreshes status and labels the command as pending until status confirms it.

The firmware version was not recorded. No receiver hardware was contacted during
automated tests; the manual receiver checks above are separate from those tests.
