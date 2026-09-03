"""Async client for the Chrome DevTools Protocol exposed by Hisense VIDAA TVs.

The TV runs the VIDAA UI as a Chromium WebView with port 9223 open, no auth.
That WebView is Chromium 48, which accepts only ONE WebSocket debugger client
per page. We therefore hold a single connection open and reuse it for every
call, rather than opening one per poll: a connect/close cycle every few seconds
eventually leaves a session attached, and the next upgrade is then refused with
"500 Invalid response status" until the TV is power cycled at the mains.

The page UUID changes on UI restart, so discovery via /json runs on every
(re)connect, not on every call. Any failure drops the socket and the next call
reconnects.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Bound every network phase explicitly. aiohttp's ClientWSTimeout only covers
# the close handshake, so connect and receive are wrapped in wait_for instead.
DISCOVERY_TIMEOUT = 5.0
CONNECT_TIMEOUT = 10.0
# No WebSocket heartbeat. This Chromium build never answers a ping, so aiohttp
# tears down a perfectly healthy socket about 83 s into any idle period, which
# is the connect/close churn this client exists to avoid. Measured against the
# TV: with heartbeat=55 the connection closed between t+80 s and t+90 s every
# time. The poll traffic is the liveness check instead, and a socket the TV has
# dropped surfaces on the next call and is reconnected transparently.

NAME_ALIASES = {
    "tv": ["tv"],
    "av": ["av"],
    "component": ["component"],
    "scart": ["scart"],
    "hdmi1": ["hdmi1", "hdmi 1"],
    "hdmi2": ["hdmi2", "hdmi 2"],
    "hdmi3": ["hdmi3", "hdmi 3"],
    "hdmi4": ["hdmi4", "hdmi 4"],
}


class HisenseCDPError(Exception):
    """Raised when CDP discovery or evaluation fails."""


class HisenseCDP:
    """Thin wrapper around the TV's CDP endpoint."""

    def __init__(self, host: str, port: int, session: aiohttp.ClientSession) -> None:
        self._host = host
        self._port = port
        self._session = session
        self._msg_id = 0
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def base(self) -> str:
        return f"http://{self._host}:{self._port}"

    async def _ws_url(self) -> str:
        try:
            async with self._session.get(
                f"{self.base}/json", timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                resp.raise_for_status()
                pages = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HisenseCDPError(f"discovery failed: {err}") from err
        # Prefer the index.html page; fall back to any page in the hisenseUI tree;
        # last resort the first listed page. The launcher reloads the WebView during
        # transitions, briefly producing different URLs.
        candidates = [
            p for p in pages
            if p.get("type") == "page" and p.get("webSocketDebuggerUrl")
        ]
        for p in candidates:
            if p.get("url", "").endswith("index.html"):
                return p["webSocketDebuggerUrl"]
        for p in candidates:
            if "hisenseUI" in p.get("url", ""):
                return p["webSocketDebuggerUrl"]
        if candidates:
            return candidates[0]["webSocketDebuggerUrl"]
        raise HisenseCDPError("no debuggable page in /json")

    async def _ensure_ws(self) -> aiohttp.ClientWebSocketResponse:
        """Return the live connection, opening one if we do not have it."""
        if self._ws is not None and not self._ws.closed:
            return self._ws
        self._ws = None
        ws_url = await self._ws_url()
        try:
            self._ws = await asyncio.wait_for(
                self._session.ws_connect(ws_url),
                timeout=CONNECT_TIMEOUT,
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            self._ws = None
            raise HisenseCDPError(f"connect failed: {err}") from err
        _LOGGER.debug("CDP websocket opened to %s", ws_url)
        return self._ws

    async def _drop_ws(self) -> None:
        """Close and forget the connection so the next call reconnects.

        Always closes explicitly: leaving it to garbage collection is what
        strands a debugger session on the TV.
        """
        ws, self._ws = self._ws, None
        if ws is None or ws.closed:
            return
        try:
            await ws.close()
        except Exception:  # noqa: BLE001 - closing must never mask the real error
            _LOGGER.debug("ignoring error while closing CDP websocket", exc_info=True)

    async def async_close(self) -> None:
        """Release the connection. Called when the config entry unloads."""
        async with self._lock:
            await self._drop_ws()

    async def _read_reply(
        self, ws: aiohttp.ClientWebSocketResponse, msg_id: int, timeout: float
    ) -> dict:
        """Read until the reply carrying our id arrives, ignoring CDP events."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise HisenseCDPError(f"timed out waiting for reply to id={msg_id}")
            msg = await asyncio.wait_for(ws.receive(), timeout=remaining)
            if msg.type is aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("id") == msg_id:
                    return data
                continue  # an unsolicited event, or a reply we already gave up on
            if msg.type is aiohttp.WSMsgType.ERROR:
                raise HisenseCDPError(f"websocket error: {ws.exception()}")
            if msg.type in (
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.CLOSED,
            ):
                raise HisenseCDPError("websocket closed by the TV")

    async def _ws_call(self, method: str, params: dict, timeout: float = 10.0) -> dict:
        """Send one CDP command on the held connection and return its reply.

        One call at a time, because replies are matched by id on a shared
        socket. A failed attempt drops the connection and is retried once, so a
        socket the TV closed while idle does not surface as an error.
        """
        async with self._lock:
            last: Exception | None = None
            for attempt in (1, 2):
                try:
                    ws = await self._ensure_ws()
                    self._msg_id += 1
                    msg_id = self._msg_id
                    await ws.send_json(
                        {"id": msg_id, "method": method, "params": params}
                    )
                    return await self._read_reply(ws, msg_id, timeout)
                except (
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    HisenseCDPError,
                ) as err:
                    last = err
                    await self._drop_ws()
                    if attempt == 1:
                        _LOGGER.debug("CDP %s failed, reconnecting: %s", method, err)
            raise HisenseCDPError(f"CDP {method} failed: {last}") from last

    async def evaluate(self, expression: str, timeout: float = 10.0) -> Any:
        data = await self._ws_call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout,
        )
        result = data.get("result", {})
        inner = result.get("result", {})
        if inner.get("subtype") == "error" or result.get("wasThrown"):
            raise HisenseCDPError(inner.get("description", str(data)))
        if "error" in data:
            raise HisenseCDPError(data["error"].get("message", str(data)))
        return inner.get("value")

    async def dispatch_key(self, code: int) -> None:
        """Send a synthetic key press via CDP Input domain — needed to dismiss
        the VIDAA launcher fully (DOM keyboard events alone don't reach it)."""
        for ev_type in ("keyDown", "keyUp"):
            await self._ws_call(
                "Input.dispatchKeyEvent",
                {"type": ev_type, "windowsVirtualKeyCode": code, "nativeVirtualKeyCode": code},
            )

    async def fetch_state(self) -> dict[str, Any]:
        """Single round-trip read of everything we expose as entities."""
        expr = """JSON.stringify({
            source_uid: model.source.getCurrentSource(),
            inputs: model.source.getInputName(),
            volume: model.sound.getMainVolume(),
            mute: model.sound.getMainMute(),
            sound_mode: model.sound.getSoundMode(),
            on: model.system.getOn(),
            screen: model.system.getEnumScreenState(),
            picture_mode: model.video.getEnumPictureMode(),
            picture_modes: model.video.getEnumPictureModeList(),
            zoom: model.video.getEnumZoom(),
            zoom_list: model.video.getZoom_list(),
            three_d_supported: model.video.get3dSupported(),
            three_d_exists: model.video.get3dExist(),
            three_d_mode: model.video.getEnum3dMode(),
            three_d_2dto3d_exists: model.video.get3d2dto3dExist(),
            three_d_2dto3d: model.video.get3d2dto3d(),
            hdr_supported: model.video.getHDRSupport(),
            hdr_mode: model.video.getHDRMode(),
            backlight: model.video.getBacklight(),
            brightness: model.video.getBrightness(),
            contrast: model.video.getContrast(),
            colour_intensity: model.video.getColourIntensity(),
            sharpness: model.video.getSharpness(),
            color_temperature: model.video.getEnumColourTemperature(),
            color_gamut: model.video.getColorGamut(),
            local_dimming: model.video.getEnumLocalDimming(),
            smooth_motion: model.video.getEnumSmoothMotion(),
            noise_reduction: model.video.getEnumNoiseReduction(),
            dynamic_backlight: model.video.getDynamicBacklight(),
            eco_sensor: model.video.getEcoSensor(),
            freeze: model.video.getFreeze(),
            headphone_mute_tv: model.sound.getHeadphoneInsertTvMute()
        })"""
        raw = await self.evaluate(expr)
        return json.loads(raw)

    # Setters --------------------------------------------------------------

    async def set_source(self, uid: int) -> None:
        await self.evaluate(f'changeSourceTo("{int(uid)}")')

    async def set_volume(self, volume: int) -> None:
        v = max(0, min(100, int(volume)))
        await self.evaluate(f"model.sound.setMainVolume({v})")

    async def set_mute(self, mute: bool) -> None:
        await self.evaluate(f"model.sound.setMainMute({1 if mute else 0})")

    async def set_picture_mode(self, mode: int) -> None:
        await self.evaluate(f"model.video.setEnumPictureMode({int(mode)})")

    async def set_sound_mode(self, mode: int) -> None:
        await self.evaluate(f"model.sound.setSoundMode({int(mode)})")

    async def set_zoom(self, mode: int) -> None:
        await self.evaluate(f"model.video.setEnumZoom({int(mode)})")

    async def set_3d_mode(self, mode: int) -> None:
        """Force-write the 3D mode.

        On this firmware the panel gates 3D mode writes on its own
        get3dExist() detection — without a 3D signal on the current input
        the write is silently a no-op. We flip every existence flag we can
        first so the moment a real 3D source connects (or you switch to a
        side-by-side stream), the chosen mode engages.
        """
        m = int(mode)
        # Best-effort prime of all the gating flags; safe even if they're already 1.
        await self.evaluate(
            "model.video.set3dSupported(1);"
            "model.video.set3dExist(1);"
            "model.video.set3dModeExist(1);"
            "model.video.set3dDepthExist(1);"
            "model.video.set3dViewPointExist(1);"
            "model.video.set3dLrswitchExist(1);"
            "model.video.set3d2dto3dExist(1);"
            f"model.video.setEnum3dMode({m});"
            f"changeSourceTo(String(model.source.getCurrentSource()));"
        )

    async def set_3d_2dto3d(self, on: bool) -> None:
        """Force-enable the 2D→3D conversion path. Same gating caveat as
        set_3d_mode."""
        v = 1 if on else 0
        await self.evaluate(
            "model.video.set3d2dto3dExist(1);"
            f"model.video.set3d2dto3d({v});"
        )

    async def set_hdr_mode(self, mode: int) -> None:
        await self.evaluate(f"model.video.setHDRMode({int(mode)})")

    async def set_backlight(self, value: int) -> None:
        await self.evaluate(f"model.video.setBacklight({max(0, min(100, int(value)))})")

    async def set_brightness(self, value: int) -> None:
        await self.evaluate(f"model.video.setBrightness({max(0, min(100, int(value)))})")

    async def set_contrast(self, value: int) -> None:
        await self.evaluate(f"model.video.setContrast({max(0, min(100, int(value)))})")

    async def set_colour_intensity(self, value: int) -> None:
        await self.evaluate(f"model.video.setColourIntensity({max(0, min(100, int(value)))})")

    async def set_sharpness(self, value: int) -> None:
        await self.evaluate(f"model.video.setSharpness({max(0, min(100, int(value)))})")

    async def set_color_temperature(self, mode: int) -> None:
        await self.evaluate(f"model.video.setEnumColourTemperature({int(mode)})")

    async def set_color_gamut(self, mode: int) -> None:
        await self.evaluate(f"model.video.setColorGamut({int(mode)})")

    async def set_local_dimming(self, mode: int) -> None:
        await self.evaluate(f"model.video.setEnumLocalDimming({int(mode)})")

    async def set_smooth_motion(self, mode: int) -> None:
        await self.evaluate(f"model.video.setEnumSmoothMotion({int(mode)})")

    async def set_noise_reduction(self, mode: int) -> None:
        await self.evaluate(f"model.video.setEnumNoiseReduction({int(mode)})")

    async def set_dynamic_backlight(self, mode: int) -> None:
        await self.evaluate(f"model.video.setDynamicBacklight({int(mode)})")

    async def set_eco_sensor(self, on: bool) -> None:
        await self.evaluate(f"model.video.setEcoSensor({1 if on else 0})")

    async def set_freeze(self, freeze: bool) -> None:
        await self.evaluate(f"model.video.setFreeze({1 if freeze else 0})")

    async def set_headphone_mute_tv(self, on: bool) -> None:
        await self.evaluate(f"model.sound.setHeadphoneInsertTvMute({1 if on else 0})")

    async def set_power(self, on: bool) -> None:
        await self.evaluate(f"model.system.setOn({1 if on else 0})")

    async def cec_rediscover(self) -> None:
        await self.evaluate("model.cec.setHdmiDevicesSearch(1)")

    async def show_message(self, message: str, seconds: float = 3.0) -> None:
        """Display a message on the TV by hijacking the input picker.

        Because the VIDAA WebView isn't composited over HDMI on this firmware,
        we can't draw arbitrary text on top of an HDMI feed. The reliable
        workaround is:
          1. Rename the current input to the message via InputRename
          2. Pop the input picker (oneKeyOpenVIDAALauncherInput) — overlays
             the screen for `seconds`, with the renamed tile highlighted
          3. Dismiss the picker via tryToCloseAllApps + close VIDAALiteNavPage
             + a few synthetic BACK keys (CDP Input.dispatchKeyEvent)
          4. Restore the original input name

        This is DISRUPTIVE: it interrupts whatever is showing for ~`seconds`
        plus ~1s of dismissal animation. Best for doorbell/alarm-grade events.
        """
        msg = str(message)[:25]  # Hisense input names cap around here
        secs = max(1.0, min(15.0, float(seconds)))

        uid = await self.evaluate("model.source.getCurrentSource()")
        raw = await self.evaluate("model.source.getInputName()")
        parsed = parse_inputs(raw or [])
        current = next((e for e in parsed if e["uid"] == uid), None)
        if current is None:
            raise HisenseCDPError(f"no entry for current source uid {uid}")
        original = current.get("custom_name") or ""

        msg_json = json.dumps(msg)
        await self.evaluate(f'model.source.InputRename(String({int(uid)}), {msg_json})')
        try:
            await self.evaluate("oneKeyOpenVIDAALauncherInput()")
            await asyncio.sleep(secs)
        finally:
            # Best-effort dismissal sequence
            await self.evaluate(
                "(()=>{try{tryToCloseAllApps()}catch(e){}"
                "try{if(hiWebOsFrame.VIDAALiteNavPage){hiWebOsFrame.VIDAALiteNavPage.close()}}catch(e){}"
                "})()"
            )
            for code in (8, 27, 461, 4):  # BACK / ESC / Android-back / various
                try:
                    await self.dispatch_key(code)
                except HisenseCDPError:
                    pass
                await asyncio.sleep(0.15)
            # Restore original name
            original_json = json.dumps(original)
            try:
                await self.evaluate(
                    f'model.source.InputRename(String({int(uid)}), {original_json})'
                )
            except HisenseCDPError:
                pass

    async def reset_picture_defaults(self) -> None:
        await self.evaluate("model.video.ResetDefaultPictureSettings()")


def _norm(s: str | None) -> str:
    """Normalise an input label for matching: lowercase, strip every kind of
    whitespace (Hisense uses U+00A0 NBSP in custom names), drop _UHD suffix."""
    if not s:
        return ""
    out = s.lower().replace("_uhd", "")
    return "".join(ch for ch in out if not ch.isspace())


def parse_inputs(raw: list[str]) -> list[dict[str, Any]]:
    """Parse the flat 6-tuple array from model.source.getInputName()."""
    return [
        {
            "uid": int(raw[i]),
            "name": raw[i + 1],
            "available": raw[i + 2] == "1",
            "uhd": raw[i + 3] == "1",
            "custom_name": raw[i + 4],
        }
        for i in range(0, len(raw), 6)
    ]


def resolve_uid(target: str | int, table: list[dict[str, Any]]) -> int:
    """Resolve a target to a uid. Accepts uid, alias, or friendly label."""
    if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
        return int(target)
    key = _norm(str(target))
    aliases = NAME_ALIASES.get(key, [key])
    for entry in table:
        n = _norm(entry.get("name"))
        cn = _norm(entry.get("custom_name"))
        if cn == "wrong":
            cn = ""
        for alias in aliases:
            a = _norm(alias)
            if a and (a == n or a == cn or a in n or (cn and a in cn)):
                return entry["uid"]
    raise HisenseCDPError(f"no input matches {target!r}")
