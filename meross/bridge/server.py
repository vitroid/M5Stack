#!/usr/bin/env python3
"""Thin HTTP bridge for Meross outlets (LAN preferred via meross-iot).

Wraps the same account/discovery path as toggle_outlet.py. ESP32 / Amica
sketches only need Wi‑Fi + HTTP GET/POST — no Meross credentials on the MCU.

Env: MEROSS_EMAIL, MEROSS_PASSWORD, optional MEROSS_API_BASE_URL.
Bind: MEROSS_BRIDGE_HOST (default 0.0.0.0), MEROSS_BRIDGE_PORT (default 8787).

Aliases for home remote:
  lamp / ランプ  → device name ランプ
  fan  / ファン  → device name ファン
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Allow `python bridge/server.py` from meross/ and `python -m bridge.server`.
_MEROSS_DIR = Path(__file__).resolve().parent.parent
if str(_MEROSS_DIR) not in sys.path:
    sys.path.insert(0, str(_MEROSS_DIR))

from aiohttp import web

import toggle_outlet as probe
from meross_iot.controller.device import BaseDevice
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager, TransportMode

ALIASES: Dict[str, str] = {
    "lamp": "ランプ",
    "ランプ": "ランプ",
    "fan": "ファン",
    "ファン": "ファン",
}


def _resolve_query(raw: str) -> str:
    key = raw.strip()
    return ALIASES.get(key, ALIASES.get(key.lower(), key))


def _channel0_on(dev: BaseDevice) -> Optional[bool]:
    if not hasattr(dev, "is_on"):
        return None
    try:
        return bool(dev.is_on(channel=0))
    except TypeError:
        return bool(dev.is_on())
    except Exception:  # noqa: BLE001
        return None


def _device_dict(dev: BaseDevice) -> Dict[str, Any]:
    dtype = getattr(dev, "type", None) or getattr(dev, "device_type", "?")
    return {
        "name": dev.name,
        "uuid": dev.uuid,
        "type": str(dtype),
        "online": probe._online(dev),
        "lan_ip": probe._lan_ip(dev),
        "channel0_on": _channel0_on(dev),
    }


class MerossBridge:
    """Long-lived manager so button presses do not re-login every time."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._http: Optional[MerossHttpClient] = None
        self._manager: Optional[MerossManager] = None
        self._ready = asyncio.Event()

    async def start(self) -> None:
        email, password, api_base = probe._require_credentials()
        self._http = await MerossHttpClient.async_from_user_password(
            email=email,
            password=password,
            api_base_url=api_base,
        )
        self._manager = MerossManager(http_client=self._http)
        self._manager.default_transport_mode = TransportMode.LAN_HTTP_FIRST
        await self._manager.async_init()
        await self._manager.async_device_discovery()
        self._ready.set()
        print(
            f"Meross bridge ready (transport=LAN_HTTP_FIRST, api={api_base})",
            flush=True,
        )

    async def stop(self) -> None:
        self._ready.clear()
        if self._manager is not None:
            self._manager.close()
            self._manager = None
        if self._http is not None:
            await self._http.async_logout()
            self._http = None

    async def _ensure(self) -> MerossManager:
        await self._ready.wait()
        assert self._manager is not None
        return self._manager

    async def list_devices(self) -> list[Dict[str, Any]]:
        async with self._lock:
            manager = await self._ensure()
            await manager.async_device_discovery()
            out = []
            for d in probe._collect_toggleables(manager):
                try:
                    await d.async_update()
                except Exception as exc:  # noqa: BLE001
                    print(f"warn: update {d.name!r}: {exc}", file=sys.stderr)
                out.append(_device_dict(d))
            return out

    async def _get_device(self, query: str) -> BaseDevice:
        manager = await self._ensure()
        # Light refresh so newly online plugs show up without full reconnect.
        await manager.async_device_discovery()
        return probe._match_device(
            probe._collect_toggleables(manager), _resolve_query(query)
        )

    async def _safe_update(self, dev: BaseDevice) -> None:
        """Best-effort refresh; LAN timeout must not 500 the HTTP API."""
        try:
            await dev.async_update()
        except Exception as exc:  # noqa: BLE001 — CommandTimeoutError etc.
            print(f"warn: async_update {dev.name!r}: {exc}", file=sys.stderr)

    async def status(self, query: str) -> Dict[str, Any]:
        async with self._lock:
            dev = await self._get_device(query)
            await self._safe_update(dev)
            return _device_dict(dev)

    async def power(self, query: str, action: str) -> Dict[str, Any]:
        async with self._lock:
            dev = await self._get_device(query)
            await self._safe_update(dev)
            before = _channel0_on(dev)
            try:
                if action == "on":
                    await dev.async_turn_on(channel=0)
                elif action == "off":
                    await dev.async_turn_off(channel=0)
                elif action == "toggle":
                    if hasattr(dev, "async_toggle"):
                        await dev.async_toggle(channel=0)
                    elif before:
                        await dev.async_turn_off(channel=0)
                    else:
                        await dev.async_turn_on(channel=0)
                else:
                    raise web.HTTPBadRequest(text=f"unknown action {action}")
            except web.HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001
                raise web.HTTPBadGateway(
                    text=json.dumps(
                        {
                            "error": str(exc),
                            "device": _resolve_query(query),
                            "action": action,
                        },
                        ensure_ascii=False,
                    ),
                    content_type="application/json",
                ) from exc
            await asyncio.sleep(0.35)
            await self._safe_update(dev)
            after = _channel0_on(dev)
            body = _device_dict(dev)
            body["action"] = action
            body["before"] = before
            body["after"] = after
            print(
                f"{action}: {dev.name!r} before={before} after={after} "
                f"lan_ip={probe._lan_ip(dev)}",
                flush=True,
            )
            return body


def _json(data: Any, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        status=status,
        content_type="application/json",
        charset="utf-8",
    )


def _device_from_match(match: web.Request) -> str:
    name = match.match_info.get("device") or match.rel_url.query.get("device")
    if not name:
        raise web.HTTPBadRequest(text="missing device (path or ?device=)")
    return name


def create_app(bridge: MerossBridge) -> web.Application:
    app = web.Application()

    async def health(_request: web.Request) -> web.Response:
        return _json({"ok": True, "service": "meross-bridge"})

    async def _run(coro):
        try:
            return await coro
        except web.HTTPException:
            raise
        except SystemExit as exc:
            raise web.HTTPNotFound(
                text=json.dumps({"error": str(exc)}, ensure_ascii=False),
                content_type="application/json",
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise web.HTTPBadGateway(
                text=json.dumps({"error": str(exc)}, ensure_ascii=False),
                content_type="application/json",
            ) from exc

    async def devices(_request: web.Request) -> web.Response:
        return _json({"devices": await _run(bridge.list_devices())})

    async def status(request: web.Request) -> web.Response:
        return _json(await _run(bridge.status(_device_from_match(request))))

    async def do_action(request: web.Request, action: str) -> web.Response:
        return _json(
            await _run(bridge.power(_device_from_match(request), action))
        )

    async def toggle(request: web.Request) -> web.Response:
        return await do_action(request, "toggle")

    async def on(request: web.Request) -> web.Response:
        return await do_action(request, "on")

    async def off(request: web.Request) -> web.Response:
        return await do_action(request, "off")

    app.router.add_get("/health", health)
    app.router.add_get("/devices", devices)
    app.router.add_get("/status/{device}", status)
    app.router.add_get("/status", status)
    for method in ("GET", "POST"):
        app.router.add_route(method, "/toggle/{device}", toggle)
        app.router.add_route(method, "/toggle", toggle)
        app.router.add_route(method, "/on/{device}", on)
        app.router.add_route(method, "/on", on)
        app.router.add_route(method, "/off/{device}", off)
        app.router.add_route(method, "/off", off)

    async def on_startup(_app: web.Application) -> None:
        await bridge.start()

    async def on_cleanup(_app: web.Application) -> None:
        await bridge.stop()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main() -> None:
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    host = probe._env("MEROSS_BRIDGE_HOST", "0.0.0.0") or "0.0.0.0"
    port_s = probe._env("MEROSS_BRIDGE_PORT", "8787") or "8787"
    port = int(port_s)
    bridge = MerossBridge()
    app = create_app(bridge)
    print(f"Listening on http://{host}:{port}", flush=True)
    web.run_app(app, host=host, port=port, print=None)


if __name__ == "__main__":
    main()
