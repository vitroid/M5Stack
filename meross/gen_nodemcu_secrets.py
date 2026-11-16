#!/usr/bin/env python3
"""Emit NodeMCU secrets.h LAN macros from devices.local.json (stdout).

Does not overwrite Wi‑Fi lines — paste the printed block into include/secrets.h.
Never commit the result.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "devices.local.json"


def main() -> int:
    if not DOC.is_file():
        print(f"Missing {DOC}. Run export_lan_devices.py first.", file=sys.stderr)
        return 2
    data = json.loads(DOC.read_text(encoding="utf-8"))
    by_alias = {d.get("alias"): d for d in data["devices"]}
    lamp = by_alias.get("lamp") or next(d for d in data["devices"] if d.get("name") == "ランプ")
    fan = by_alias.get("fan") or next(d for d in data["devices"] if d.get("name") == "ファン")
    print("// --- LAN direct (from devices.local.json; do not commit) ---")
    print(f'#define MEROSS_KEY    "{data["key"]}"')
    print("#define MEROSS_CHANNEL 0")
    print(f'#define LAMP_IP       "{lamp["lan_ip"]}"')
    print(f'#define LAMP_UUID     "{lamp["uuid"]}"')
    print(f'#define FAN_IP        "{fan["lan_ip"]}"')
    print(f'#define FAN_UUID      "{fan["uuid"]}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
