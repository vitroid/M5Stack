#!/usr/bin/env python3
"""Prove mss110 toggle via pure LAN HTTP (no MQTT/cloud on command path).

Reads meross/devices.local.json from export_lan_devices.py.
Minimizes toggles; restores both devices to ON.

Usage:
  python export_lan_devices.py   # once, needs cloud creds
  python prove_lan_toggle.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from lan_http import channel0_on_from_all, lan_get_all, lan_set_onoff

OUT_PATH = Path(__file__).resolve().parent / "devices.local.json"


def _load() -> Dict[str, Any]:
    if not OUT_PATH.is_file():
        raise SystemExit(f"Missing {OUT_PATH}. Run export_lan_devices.py first.")
    return json.loads(OUT_PATH.read_text(encoding="utf-8"))


def _pick(devices: List[Dict[str, Any]], *names: str) -> Dict[str, Any]:
    lower = {n.lower() for n in names}
    for d in devices:
        if (d.get("name") or "").lower() in lower:
            return d
        if (d.get("alias") or "").lower() in lower:
            return d
    raise SystemExit(f"Device not found for names={names}. Have: {[d.get('name') for d in devices]}")


def main() -> int:
    doc = _load()
    key = doc["key"]
    results: List[Dict[str, Any]] = []

    targets = [
        _pick(doc["devices"], "ランプ", "lamp"),
        _pick(doc["devices"], "ファン", "fan"),
    ]

    print("=== Pure LAN prove (no MQTT) ===")
    print(f"key loaded (len={len(key)}); user_id={doc.get('user_id')}")

    # 1) GET status both
    states: Dict[str, bool | None] = {}
    for d in targets:
        name = d["name"]
        ip = d["lan_ip"]
        uuid = d["uuid"]
        if not ip:
            raise SystemExit(f"{name}: no lan_ip in export")
        parsed, ms = lan_get_all(ip, key, uuid)
        on = channel0_on_from_all(parsed)
        states[name] = on
        method = (parsed.get("header") or {}).get("method")
        print(f"GET  {name} @{ip} on={on} method={method} {ms:.0f}ms")
        results.append({"op": "GET", "name": name, "ip": ip, "on": on, "ms": round(ms, 1)})

    # 2) Minimal toggle proof on ランプ only: OFF then ON (restore)
    lamp = targets[0]
    print("--- toggle proof on ランプ (off→on) ---")
    for want in (0, 1):
        parsed, ms = lan_set_onoff(lamp["lan_ip"], key, lamp["uuid"], want)
        method = (parsed.get("header") or {}).get("method")
        print(f"SET  ランプ onoff={want} method={method} {ms:.0f}ms")
        results.append(
            {
                "op": "SET",
                "name": "ランプ",
                "onoff": want,
                "method": method,
                "ms": round(ms, 1),
            }
        )
        time.sleep(0.25)

    # 3) Ensure ファン ON (was off in last discovery); one SET if needed
    fan = targets[1]
    fan_on = states.get(fan["name"])
    if fan_on is not True:
        parsed, ms = lan_set_onoff(fan["lan_ip"], key, fan["uuid"], 1)
        method = (parsed.get("header") or {}).get("method")
        print(f"SET  ファン onoff=1 (restore) method={method} {ms:.0f}ms")
        results.append(
            {"op": "SET", "name": "ファン", "onoff": 1, "method": method, "ms": round(ms, 1)}
        )
        time.sleep(0.25)
    else:
        print("ファン already ON — skip extra toggle")

    # 4) Final GET both — expect ON
    print("--- final ---")
    all_ok = True
    for d in targets:
        parsed, ms = lan_get_all(d["lan_ip"], key, d["uuid"])
        on = channel0_on_from_all(parsed)
        ok = on is True
        all_ok = all_ok and ok
        print(f"GET  {d['name']} on={on} ok={ok} {ms:.0f}ms")
        results.append({"op": "FINAL", "name": d["name"], "on": on, "ms": round(ms, 1)})

    set_ms = [r["ms"] for r in results if r["op"] == "SET"]
    get_ms = [r["ms"] for r in results if r["op"] in ("GET", "FINAL")]
    print(
        f"latency: SET n={len(set_ms)} "
        f"min={min(set_ms):.0f} med≈{sorted(set_ms)[len(set_ms)//2]:.0f} max={max(set_ms):.0f} ms; "
        f"GET n={len(get_ms)} "
        f"min={min(get_ms):.0f} med≈{sorted(get_ms)[len(get_ms)//2]:.0f} max={max(get_ms):.0f} ms"
    )
    print("pure_lan_ok" if all_ok else "pure_lan_PARTIAL", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
