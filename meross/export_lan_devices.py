#!/usr/bin/env python3
"""One-shot: cloud login → export key + device LAN IPs to a gitignored local file.

Usage:
  set -a && source .env && set +a
  python export_lan_devices.py

Writes meross/devices.local.json (gitignored). Never commit that file.
Cloud is used only for this export; day-to-day toggles use lan_http / NodeMCU.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set

from meross_iot.controller.device import BaseDevice
from meross_iot.controller.mixins.toggle import ToggleMixin, ToggleXMixin
from meross_iot.http_api import MerossHttpClient
from meross_iot.manager import MerossManager, TransportMode

DEFAULT_API_BASE = "https://iotx-ap.meross.com"
OUT_PATH = Path(__file__).resolve().parent / "devices.local.json"
ALIASES = {
    "ランプ": "lamp",
    "ファン": "fan",
}


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _collect(manager: MerossManager) -> List[BaseDevice]:
    seen: Set[str] = set()
    out: List[BaseDevice] = []
    for cls in (ToggleXMixin, ToggleMixin):
        for dev in manager.find_devices(device_class=cls):
            if dev.uuid in seen:
                continue
            seen.add(dev.uuid)
            out.append(dev)
    for dev in manager.find_devices():
        if dev.uuid in seen:
            continue
        if isinstance(dev, (ToggleXMixin, ToggleMixin)):
            seen.add(dev.uuid)
            out.append(dev)
    return out


async def main() -> int:
    email = _env("MEROSS_EMAIL")
    password = _env("MEROSS_PASSWORD")
    api_base = _env("MEROSS_API_BASE_URL", DEFAULT_API_BASE) or DEFAULT_API_BASE
    if not email or not password:
        print("Set MEROSS_EMAIL and MEROSS_PASSWORD (see env.example).", file=sys.stderr)
        return 2

    t0 = time.monotonic()
    http = await MerossHttpClient.async_from_user_password(
        email=email, password=password, api_base_url=api_base
    )
    creds = http.cloud_credentials
    manager = MerossManager(http_client=http)
    manager.default_transport_mode = TransportMode.LAN_HTTP_FIRST
    try:
        await manager.async_init()
        await manager.async_device_discovery()
        devices = _collect(manager)
        exported: List[Dict[str, Any]] = []
        for d in devices:
            try:
                await d.async_update()
            except Exception as exc:  # noqa: BLE001
                print(f"warn: async_update failed for {d.name!r}: {exc}", file=sys.stderr)
            on = None
            if hasattr(d, "is_on"):
                try:
                    on = bool(d.is_on(channel=0))
                except Exception:  # noqa: BLE001
                    on = None
            name = d.name or ""
            exported.append(
                {
                    "name": name,
                    "alias": ALIASES.get(name),
                    "uuid": d.uuid,
                    "type": getattr(d, "type", None) or getattr(d, "device_type", "?"),
                    "lan_ip": getattr(d, "lan_ip", None),
                    "mac": getattr(d, "mac_address", None),
                    "channel": 0,
                    "channel0_on": on,
                    "encryption": bool(d.support_encryption()),
                }
            )
    finally:
        manager.close()
        await http.async_logout()

    doc = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "api_base_url": api_base,
        "user_id": creds.user_id,
        "user_email": creds.user_email,
        "key": creds.key,
        "note": "Gitignored. key signs LAN /config messages. Re-run this script if key rotates or IPs change.",
        "devices": exported,
        "elapsed_ms": int((time.monotonic() - t0) * 1000),
    }
    OUT_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(exported)} devices, {doc['elapsed_ms']}ms)")
    for d in exported:
        print(
            f"  {d.get('alias') or '-':<6} {d['name']!r:<12} "
            f"ip={d['lan_ip']} uuid={d['uuid'][:12]}… on={d['channel0_on']} enc={d['encryption']}"
        )
    print("key length:", len(creds.key), "(value not printed)")
    return 0


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(main()))
