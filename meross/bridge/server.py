#!/usr/bin/env python3
"""Thin HTTP bridge for Meross outlets (LAN preferred via meross-iot).

Persistent MerossManager (login/discovery once at startup). Power actions are
fast: no per-request rediscovery / async_update (those cost ~10–20s when LAN
HTTP fails and MQTT times out). MCU-facing toggle/on/off default to HTTP 202
+ background queue so ESP8266 is not blocked.

Env: MEROSS_EMAIL, MEROSS_PASSWORD, optional MEROSS_API_BASE_URL.
Bind: MEROSS_BRIDGE_HOST (default 0.0.0.0), MEROSS_BRIDGE_PORT (default 8787).

Aliases: lamp/ランプ, fan/ファン.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

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

# Rediscover at most this often (seconds). Per-request discovery was a major stall.
REDISCOVER_INTERVAL_S = 300.0


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
    """Long-lived manager + serial job queue for snappy MCU UX."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._http: Optional[MerossHttpClient] = None
        self._manager: Optional[MerossManager] = None
        self._ready = asyncio.Event()
        self._last_discovery = 0.0
        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._worker_task: Optional[asyncio.Task] = None
        # Optimistic channel-0 state; avoid meross-iot async_update (slow/timeout).
        self._on_guess: Dict[str, Optional[bool]] = {}

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
        self._last_discovery = time.monotonic()
        self._ready.set()
        self._worker_task = asyncio.create_task(self._worker(), name="meross-job-worker")
        print(
            f"Meross bridge ready (transport=LAN_HTTP_FIRST, api={api_base})",
            flush=True,
        )

    async def stop(self) -> None:
        self._ready.clear()
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
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

    async def _maybe_discover(self, force: bool = False) -> MerossManager:
        manager = await self._ensure()
        now = time.monotonic()
        if force or (now - self._last_discovery) >= REDISCOVER_INTERVAL_S:
            await manager.async_device_discovery()
            self._last_discovery = now
        return manager

    async def _resolve_device(self, query: str) -> BaseDevice:
        """Resolve from cache; rediscover only on miss or interval."""
        manager = await self._maybe_discover(force=False)
        try:
            return probe._match_device(
                probe._collect_toggleables(manager), _resolve_query(query)
            )
        except SystemExit:
            manager = await self._maybe_discover(force=True)
            return probe._match_device(
                probe._collect_toggleables(manager), _resolve_query(query)
            )

    async def list_devices(self) -> list[Dict[str, Any]]:
        async with self._lock:
            manager = await self._maybe_discover(force=True)
            # Cached state only — no per-device async_update (slow when LAN fails).
            return [_device_dict(d) for d in probe._collect_toggleables(manager)]

    async def status(self, query: str) -> Dict[str, Any]:
        # Cached view; optional light command omitted for speed.
        async with self._lock:
            return _device_dict(await self._resolve_device(query))

    async def power_fast(self, query: str, action: str) -> Dict[str, Any]:
        """Issue on/off/toggle without rediscovery or async_update round-trips."""
        t0 = time.monotonic()
        async with self._lock:
            dev = await self._resolve_device(query)
            before = self._on_guess.get(dev.uuid)
            if action == "on":
                await dev.async_turn_on(channel=0)
                after: Optional[bool] = True
            elif action == "off":
                await dev.async_turn_off(channel=0)
                after = False
            elif action == "toggle":
                # Prefer explicit on/off from our guess; async_toggle needs prior update.
                if before is True:
                    await dev.async_turn_off(channel=0)
                    after = False
                elif before is False:
                    await dev.async_turn_on(channel=0)
                    after = True
                elif hasattr(dev, "async_toggle"):
                    await dev.async_toggle(channel=0)
                    after = None
                else:
                    await dev.async_turn_on(channel=0)
                    after = True
            else:
                raise web.HTTPBadRequest(text=f"unknown action {action}")
            self._on_guess[dev.uuid] = after
            body = _device_dict(dev)
            body["channel0_on"] = after
            body["action"] = action
            body["before"] = before
            body["after"] = after
            body["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
            print(
                f"{action}: {dev.name!r} before={before} after≈{after} "
                f"lan_ip={probe._lan_ip(dev)} elapsed_ms={body['elapsed_ms']}",
                flush=True,
            )
            return body

    async def enqueue_power(self, query: str, action: str) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        resolved = _resolve_query(query)
        job = {
            "id": job_id,
            "device": resolved,
            "action": action,
            "status": "queued",
            "result": None,
            "error": None,
            "queued_ms": int(time.time() * 1000),
        }
        self._jobs[job_id] = job
        await self._queue.put({"job_id": job_id, "query": query, "action": action})
        return {
            "accepted": True,
            "job_id": job_id,
            "device": resolved,
            "action": action,
            "status": "queued",
        }

    def job_status(self, job_id: str) -> Dict[str, Any]:
        job = self._jobs.get(job_id)
        if not job:
            raise web.HTTPNotFound(
                text=json.dumps({"error": "unknown job"}, ensure_ascii=False),
                content_type="application/json",
            )
        return dict(job)

    async def _worker(self) -> None:
        while True:
            item = await self._queue.get()
            job_id = item["job_id"]
            job = self._jobs.get(job_id)
            if job is None:
                self._queue.task_done()
                continue
            job["status"] = "running"
            try:
                result = await self.power_fast(item["query"], item["action"])
                job["status"] = "done"
                job["result"] = result
            except Exception as exc:  # noqa: BLE001
                job["status"] = "error"
                job["error"] = str(exc) or exc.__class__.__name__
                print(f"job {job_id} error: {job['error']}", file=sys.stderr, flush=True)
            finally:
                self._queue.task_done()


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


def _want_wait(request: web.Request) -> bool:
    # Default async (202) for MCU. ?wait=1 for sync / curl debugging.
    q = request.rel_url.query.get("wait", "").lower()
    return q in ("1", "true", "yes", "sync")


def create_app(bridge: MerossBridge) -> web.Application:
    app = web.Application()

    async def health(_request: web.Request) -> web.Response:
        return _json(
            {
                "ok": True,
                "service": "meross-bridge",
                "queue_size": bridge._queue.qsize(),
            }
        )

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
                text=json.dumps(
                    {"error": str(exc) or exc.__class__.__name__},
                    ensure_ascii=False,
                ),
                content_type="application/json",
            ) from exc

    async def devices(_request: web.Request) -> web.Response:
        return _json({"devices": await _run(bridge.list_devices())})

    async def status(request: web.Request) -> web.Response:
        return _json(await _run(bridge.status(_device_from_match(request))))

    async def do_action(request: web.Request, action: str) -> web.Response:
        device = _device_from_match(request)
        if _want_wait(request):
            return _json(await _run(bridge.power_fast(device, action)))
        accepted = await bridge.enqueue_power(device, action)
        return _json(accepted, status=202)

    async def toggle(request: web.Request) -> web.Response:
        return await do_action(request, "toggle")

    async def on(request: web.Request) -> web.Response:
        return await do_action(request, "on")

    async def off(request: web.Request) -> web.Response:
        return await do_action(request, "off")

    async def job(request: web.Request) -> web.Response:
        return _json(bridge.job_status(request.match_info["job_id"]))

    app.router.add_get("/health", health)
    app.router.add_get("/devices", devices)
    app.router.add_get("/status/{device}", status)
    app.router.add_get("/status", status)
    app.router.add_get("/jobs/{job_id}", job)
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
