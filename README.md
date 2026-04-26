# Hisense VIDAA TV (CDP) — Home Assistant Custom Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Control older **Hisense VIDAA** smart TVs from Home Assistant via the unauthenticated **Chrome DevTools Protocol** the TV exposes on port `9223` — no MQTT broker, no PIN pairing, no client certs.

This works on TVs whose firmware ships a debuggable Chromium WebView for the VIDAA UI (verified on a 2016 Hisense `OPR/35.0.2070.0 OMI/4.7.0.0.Martell.111`). Newer firmware may have closed CDP — verify with `curl http://<tv>:9223/json/version` before installing.

## Why this exists

Most community Hisense integrations talk to the TV's internal MQTT broker on port 36669, which on this firmware is **closed**. CDP on 9223 is reachable, has no auth, and lets you read or write the TV's whole `model.*` state directly.

## What it gives you

A single **Hisense VIDAA TV** device with **23+ entities**:

### Media player
- `media_player.<host>` — power, source select, volume, mute, source list

### Selects (11)
- Picture mode, Sound mode, Aspect ratio
- 3D mode (force-write — see caveat below)
- HDR mode, Colour temperature, Colour gamut
- Local dimming, Smooth motion, Noise reduction, Dynamic backlight

### Numbers (5, sliders)
- Backlight, Brightness, Contrast, Colour intensity, Sharpness

### Switches (4)
- Picture freeze, Eco light sensor, 2D→3D conversion, Mute TV when headphones plug in

### Buttons (2)
- Re-scan CEC bus, Reset picture defaults

### Binary sensors (4)
- 3D signal present, 3D hardware supported, 2D→3D conversion available, HDR hardware supported

### Service: `hisense_vidaa.show_message`
Display a brief message on the TV by hijacking the input picker. **Disruptive** — interrupts video for ~3–5 s. Best for doorbell/alarm-grade events.

```yaml
action: hisense_vidaa.show_message
target:
  device: 01KQ4GAP54PNK6FK00EC43PWRG  # your TV's device id
data:
  message: "Doorbell ringing"
  seconds: 4
```

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → Custom repositories
2. Add `https://github.com/chrisns/hisense_vidaa`, category **Integration**
3. Install **Hisense VIDAA TV (CDP)**
4. Restart Home Assistant
5. Settings → Devices & Services → Add Integration → search **Hisense VIDAA**
6. Enter the TV's hostname or IP (e.g. `192.168.1.50`); leave port at `9223`

### Manual

Copy `custom_components/hisense_vidaa/` into your HA `/config/custom_components/`. Restart HA. Add the integration via the UI.

## Caveats

- **CDP only listens while the TV is powered on.** If the TV's off, the coordinator will fail every poll until you turn it back on.
- **No authentication on port 9223** — anyone on the same network as the TV can read or write its state. Treat your IoT VLAN accordingly.
- **3D mode is hardware-gated.** The TV refuses to apply `setEnum3dMode` writes unless `get3dExist == 1`, i.e. a real 3D source is on the wire. The select fires the full force chain (`set3dExist`, `set3dModeExist`, etc.) so the moment a 3D signal arrives your chosen mode engages.
- **Many enum labels are guesses.** Picture/sound/aspect modes are mapped to common Hisense names; an unknown int surfaces as `Mode N` — open an issue with what you see.
- **Older firmware only.** The 2016 Martell-Opera Chromium build exposes CDP. Newer Hisense firmware (post-2020) may have closed port 9223 entirely.
- **`show_message` is intrusive.** It opens the input picker overlay for the duration. Use sparingly.

## How it works

The VIDAA UI (`file:///3rd_rw/UI/hisenseUI/index.html`) is a Chromium WebView with debugging enabled. The integration:

1. Discovers the live page via `GET http://<tv>:9223/json` (page UUID changes on UI restart, so always rediscovered)
2. Opens a one-shot WebSocket per call, sends `Runtime.evaluate` against the page's `model.*` API:
   - Read: `model.source.getCurrentSource()`, `model.video.getEnumPictureMode()`, etc.
   - Write: `changeSourceTo(uid)`, `model.video.setBacklight(N)`, etc.
3. Closes the WebSocket immediately (the TV's CDP server is flaky if held open)
4. Bulk state read in one round-trip per coordinator poll (every 30 s)

For `show_message`, additional CDP `Input.dispatchKeyEvent` calls synthesise BACK keypresses to dismiss the launcher cleanly.

## Disclaimer

This integration drives the TV via an undocumented internal API. It works on the author's 2016 Hisense; YMMV. Hisense may close CDP in a future firmware update — there is no fallback in that case.

Not affiliated with Hisense.

## Licence

MIT — see [LICENSE](LICENSE).
