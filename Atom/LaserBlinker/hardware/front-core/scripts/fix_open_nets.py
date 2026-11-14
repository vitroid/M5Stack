#!/usr/bin/env python3
"""Close front-core DRC unconnected nets for JLCPCB fab readiness.

Strategy (CH224K-dense board — do NOT park R21/R22 on the /VBUS_PD spine):
  1. Keep R21 east of U0 (MCU VBUS stubs already work).
  2. Move R22 west of F1; feed /VBUS_PD and Net-(U0-VDD) on B.Cu.
  3. Move R3 west of J3 (R4-style mirror); CC1 via B.Cu north of J3 VBUS.
  4. Export fab/ only when DRC unconnected == 0 and shorts == 0.

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 \
      scripts/fix_open_nets.py
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


def xy(obj):
    p = obj.GetPosition()
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def find_pad(board, ref, num):
    return bp._find_pad(board, ref, num)


def delete_net_tracks(board, netname: str) -> int:
    dead = [tr for tr in board.GetTracks() if (tr.GetNetname() or "") == netname]
    for tr in dead:
        board.Delete(tr)
    return len(dead)


def delete_tracks_touching(board, ref, num, tol=0.15) -> int:
    pad = find_pad(board, ref, num)
    if not pad:
        return 0
    px, py = xy(pad)
    dead = []
    for tr in board.GetTracks():
        if tr.GetClass() == "PCB_VIA":
            pos = tr.GetPosition()
            if abs(pcbnew.ToMM(pos.x) - px) < tol and abs(pcbnew.ToMM(pos.y) - py) < tol:
                dead.append(tr)
            continue
        for end in (tr.GetStart(), tr.GetEnd()):
            if abs(pcbnew.ToMM(end.x) - px) < tol and abs(pcbnew.ToMM(end.y) - py) < tol:
                dead.append(tr)
                break
    for tr in dead:
        board.Delete(tr)
    return len(dead)


def add_track(board, a, b, width, layer, net):
    tr = pcbnew.PCB_TRACK(board)
    tr.SetStart(pcbnew.VECTOR2I_MM(a[0], a[1]))
    tr.SetEnd(pcbnew.VECTOR2I_MM(b[0], b[1]))
    tr.SetWidth(pcbnew.FromMM(width))
    tr.SetLayer(layer)
    tr.SetNet(net)
    board.Add(tr)


def poly(board, pts, width, layer, net):
    for a, b in zip(pts, pts[1:]):
        add_track(board, a, b, width, layer, net)


def via(board, x, y, net):
    return bp._add_via(board, pcbnew.VECTOR2I_MM(x, y), net)


def main() -> None:
    board = pcbnew.LoadBoard(bp.PCB_PATH)
    board.BuildConnectivity()
    before = board.GetConnectivity().GetUnconnectedCount(False)
    print(f"Unconnected before: {before}")

    for ref in ("R21", "R22", "R3"):
        for n in ("1", "2"):
            delete_tracks_touching(board, ref, n)
    print(
        "Cleared U0-VDD tracks=",
        delete_net_tracks(board, "Net-(U0-VDD)"),
        "CC1 tracks=",
        delete_net_tracks(board, "Net-(J3-CC1)"),
    )

    # R21 stays — pad2→U0.8 already routed on baseline
    r21 = board.FindFootprintByReference("R21")
    # R22: west of F1, clear of USB-DP / J2 GND via
    r22 = board.FindFootprintByReference("R22")
    r22.SetPosition(pcbnew.VECTOR2I_MM(101.40, 188.55))
    r22.SetOrientationDegrees(180)
    # R3: west of J3, same y as CC1 (R4 mirror)
    r3 = board.FindFootprintByReference("R3")
    r3.SetPosition(pcbnew.VECTOR2I_MM(101.70, 120.13))
    r3.SetOrientationDegrees(180)

    print("Moved:")
    print(f"  R21 stay {xy(r21)} rot={r21.GetOrientationDegrees()}")
    print("  R22 -> (101.40, 188.55) rot=180")
    print("  R3  -> (101.70, 120.13) rot=180")
    board.BuildConnectivity()
    for ref in ("R21", "R22", "R3"):
        fp = board.FindFootprintByReference(ref)
        pads = [(p.GetNumber(), xy(p), p.GetNetname()) for p in fp.Pads() if p.GetNumber()]
        print(f"  {ref} pads: {pads}")

    f1 = find_pad(board, "F1", "1")
    net_v = f1.GetNet()
    r21_1 = find_pad(board, "R21", "1")
    r22_1 = find_pad(board, "R22", "1")
    r22_2 = find_pad(board, "R22", "2")
    u0_1 = find_pad(board, "U0", "1")
    c18 = find_pad(board, "C18", "1")
    j3 = find_pad(board, "J3", "A5")
    r3_1 = find_pad(board, "R3", "1")
    r3_2 = find_pad(board, "R3", "2")

    # --- /VBUS_PD: R21 via B.Cu @ y=184.9; R22 via B.Cu south of pad ---
    ax, ay = xy(r21_1)
    v_r21 = (113.25, 184.90)
    v_f1 = (104.20, 188.50)
    poly(board, [(ax, ay), (ax, v_r21[1]), v_r21], 0.25, pcbnew.F_Cu, net_v)
    via(board, *v_r21, net_v)
    via(board, *v_f1, net_v)
    poly(board, [xy(f1), (xy(f1)[0], v_f1[1]), v_f1], 0.35, pcbnew.F_Cu, net_v)
    poly(board, [v_r21, (v_f1[0], v_r21[1]), v_f1], 0.30, pcbnew.B_Cu, net_v)

    rx, ry = xy(r22_1)
    v_r22 = (rx, 189.40)
    poly(board, [(rx, ry), v_r22], 0.25, pcbnew.F_Cu, net_v)
    via(board, *v_r22, net_v)
    poly(board, [v_r22, (v_f1[0], v_r22[1]), v_f1], 0.30, pcbnew.B_Cu, net_v)

    # --- Net-(U0-VDD): west-edge B.Cu ---
    px, py = xy(r22_2)
    net_d = r22_2.GetNet()
    ux, uy = xy(u0_1)
    v_a = (100.05, py)
    v_c = (ux - 1.15, uy)
    poly(board, [(px, py), v_a], 0.20, pcbnew.F_Cu, net_d)
    via(board, *v_a, net_d)
    poly(board, [v_a, (100.05, uy), v_c], 0.20, pcbnew.B_Cu, net_d)
    via(board, *v_c, net_d)
    poly(board, [v_c, (ux, uy)], 0.20, pcbnew.F_Cu, net_d)
    if c18:
        poly(board, [(ux, uy), xy(c18)], 0.20, pcbnew.F_Cu, net_d)

    # --- CC1: stub east of +3V3, B.Cu north of J3 VBUS back-tie ---
    net_c = j3.GetNet()
    jx, jy = xy(j3)
    r3x, r3y = xy(r3_1)
    v_j = (107.40, jy)
    y_bus = 118.40
    poly(board, [(jx, jy), v_j], 0.20, pcbnew.F_Cu, net_c)
    via(board, *v_j, net_c)
    via(board, r3x, r3y, net_c)
    poly(board, [v_j, (v_j[0], y_bus), (r3x, y_bus), (r3x, r3y)], 0.20, pcbnew.B_Cu, net_c)
    # R3 GND via-in-pad
    via(board, *xy(r3_2), r3_2.GetNet())

    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    board.BuildConnectivity()
    print(f"Unconnected final (connectivity): {board.GetConnectivity().GetUnconnectedCount(False)}")
    pcbnew.SaveBoard(bp.PCB_PATH, board)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        drc_path = tf.name
    subprocess.run(
        [bp.KCLI, "pcb", "drc", "--format", "json", "-o", drc_path, bp.PCB_PATH],
        check=True,
    )
    drc = json.load(open(drc_path))
    un = drc.get("unconnected_items", [])
    shorts = [v for v in drc.get("violations", []) if "short" in v.get("type", "")]
    print(f"DRC unconnected: {len(un)}")
    for u in un:
        print(" ", [i.get("description") for i in u.get("items", [])])
    print(f"DRC shorts: {len(shorts)}")
    for s in shorts[:10]:
        print(" ", s.get("description", "")[:100])

    if un or shorts:
        print("FAIL: not exporting fab")
        sys.exit(1)

    print("Exporting JLCPCB fab…")
    bp.export_jlcpcb_and_renders()
    print("OK:", os.path.join(bp.FAB_DIR, "front-core-gerber.zip"))


if __name__ == "__main__":
    main()
