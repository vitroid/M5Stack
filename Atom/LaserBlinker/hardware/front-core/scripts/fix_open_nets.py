#!/usr/bin/env python3
"""Attempt to close front-core DRC unconnected nets (JLCPCB fab readiness).

Targets (schematic nets already defined; copper missing after U0/CH224K move):
  1. /VBUS_PD → R21.1 → U0.8 (VBUS sense, 10k)
  2. /VBUS_PD → R22.1 → U0.1 (VDD series, 1k)
  3. J3.A5 (CC1) → R3.1 → GND (5.1k)

Current board placement is too dense for Freerouting and for safe hand
tracks without shorts. Reposition R21/R22/R3 (see docs/pcb-layout-policy.md)
before expecting this script to succeed, then:

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
    scripts/fix_open_nets.py

Exits 0 only when DRC unconnected_items == 0; then re-exports fab/.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_pcb as bp  # noqa: E402


def main() -> None:
    board = pcbnew.LoadBoard(bp.PCB_PATH)
    board.BuildConnectivity()
    n = board.GetConnectivity().GetUnconnectedCount(False)
    print(f"Unconnected (connectivity): {n}")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        drc_path = tf.name
    subprocess.run(
        [bp.KCLI, "pcb", "drc", "--format", "json", "-o", drc_path, bp.PCB_PATH],
        check=True,
    )
    drc = json.load(open(drc_path))
    un = drc.get("unconnected_items", [])
    print(f"DRC unconnected_items: {len(un)}")
    for u in un:
        print(" ", [i.get("description") for i in u.get("items", [])])

    if un:
        print(
            "BLOCKED: reposition R21/R22/R3 (or free a routing channel), "
            "then extend this script / route_critical. Not exporting fab."
        )
        sys.exit(1)

    print("All clear — exporting JLCPCB fab…")
    bp.export_jlcpcb_and_renders()


if __name__ == "__main__":
    main()
