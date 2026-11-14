#!/usr/bin/env python3
"""
Build complete 2-layer PCB (rear-core.kicad_pcb) from rear-core.kicad_sch.

Phases (BUILD_PHASE):
  topology — wide board; search component orientations/positions, then route
  shrink   — pack a known-good topology toward smaller outline (later)

Freerouting only draws wires for a fixed placement; placement recipes vary
U1/L1/D1 rotations and relative offsets so topology is not locked blindly.

Run with KiCad bundled Python:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 scripts/build_pcb.py
"""

import csv
import math
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

import pcbnew

SHARE = "/Applications/KiCad/KiCad.app/Contents/SharedSupport"
KCLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
HW_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(HW_DIR, "out")
FAB_DIR = os.path.join(HW_DIR, "fab")
PCB_PATH = os.path.join(HW_DIR, "rear-core.kicad_pcb")
SCH_PATH = os.path.join(HW_DIR, "rear-core.kicad_sch")
NETLIST_PATH = os.path.join(OUT_DIR, "netlist.xml")
FREEROUTING_JAR = os.path.expanduser("~/.cache/freerouting/freerouting-1.9.0.jar")
# Freerouting 1.9 needs Java 17+ (class file 61)
for _j in (
    "/opt/homebrew/opt/openjdk@17/bin/java",
    "/opt/homebrew/opt/openjdk/bin/java",
    "/opt/homebrew/opt/openjdk@18/bin/java",
    "java",
):
    if _j == "java" or os.path.isfile(_j):
        JAVA_BIN = _j
        break

OX, OY = 100.0, 80.0
EDGE_MARGIN = 0.55
GAP = 0.18
MM = pcbnew.FromMM

# ---------------------------------------------------------------------------
# Build phases
#   topology : wide board; try component positions/orientations + route
#   shrink   : (later) take a known-good topology and pack toward target size
# ---------------------------------------------------------------------------
BUILD_PHASE = "shrink"

# Room for topology search — connectors stay on the bottom edge; interior is loose.
TOPOLOGY_SIZE = (85.0, 52.0)
# Used only when BUILD_PHASE == "shrink"
# Largest-first: lock a clean route, then try tighter outlines.
# 75x46 is the current known-clean shrink target after topology.
# Known clean fit: 66x42 (right margin cropped; deferred H1/H2).
SHRINK_SIZES = [(66.0, 42.0), (64.0, 42.0), (64.0, 40.0)]

# Freerouting passes: modest; placement search matters more than long rip-up.
FREEROUTING_PASSES = 28
ROUTE_ATTEMPTS = 3  # per size/recipe (Freerouting is stochastic)

# Mounting holes are deferred during topology/shrink — park them in free space
# only after routing succeeds (they must not steal clearance or block packing).
DEFER_MOUNTING_HOLES = True
MOUNTING_HOLE_REFS = ("H1", "H2")

# Buck-cluster recipes: try orientations AND relative positions (not just wires).
# L1 is the anchor near J3; U1/D1/F1 are placed relative to it.
# u1_rot=180 → SW column faces L1; d1_rot=90 → +12V faces toward U1 (down).
BUCK_RECIPES = [
    # name, u1_rot, l1_rot, d1_rot, u1_dx, u1_dy, d1_dx, d1_dy  (rel. to L1 center)
    ("sw_right_d1_down", 180.0, 90.0, 90.0, -5.0, 6.5, -9.5, 4.5),
    ("sw_right_d1_down_b", 180.0, 90.0, 90.0, -5.5, 7.5, -10.0, 5.0),
    ("sw_right_d1_up", 180.0, 90.0, -90.0, -5.0, 6.5, -9.5, 3.0),
    ("sw_left_d1_down", 0.0, 90.0, 90.0, -5.0, 6.5, -9.5, 4.5),
    ("sw_right_l1_flip", 180.0, 270.0, 90.0, -5.0, 6.0, -9.5, 4.0),
    ("sw_right_tight", 180.0, 90.0, 90.0, -4.2, 5.8, -8.8, 4.0),
]

# Zones: LEFT=J2/WS2812+C7, TOP=MCU(antenna up) between USB/RJ45,
#         RIGHT=RJ45/12V/J3/RS-485/Buck. Power lane lower-right, signals mid.
ANCHORS = {
    # Buck + 12V protection (right / lower power lane) — absolute XY filled after connectors
    "F1": (38.0, 24.0),
    "D1": (38.0, 16.0),
    "D6": ("D1", "1"),
    "U1": (52.0, 20.0),
    "C1": ("U1", "3"),
    "C2": ("U1", "3"),
    "C3": ("U1", "3"),
    "C4": ("U1", "6"),
    "L1": (55.0, 16.5),
    "R1": ("U1", "4"),
    "R2": ("U1", "4"),
    "C5": ("L1", "2"),
    "C6": ("L1", "2"),
    # WS2812 support (C7/U6 are fix-placed next to J2)
    "C17": ("U6", "5"),
    "R14": ("U6", "4"),
    # LDO near MCU
    "U2": ("U4", "3"),
    "D2": ("U2", "1"),
    "D3": ("U2", "1"),
    "C8": ("U2", "1"),
    "C9": ("U2", "5"),
    "C10": ("U2", "5"),
    # USB ESD with J4
    "U7": ("J4", "A6"),
    "R3": ("J4", "A5"),
    "R4": ("J4", "B5"),
    # MCU decoupling / boot / status (absolute XY filled after U4)
    "C11": ("U4", "3"),
    "C12": ("U4", "3"),
    "R5": ("U4", "8"),
    "C13": ("U4", "8"),
    "SW1": (20.0, 21.0),
    "SW2": (40.0, 21.0),
    "R6": ("SW2", "2"),
    "R7": ("U4", "5"),
    "D7": (36.0, 16.0),
    "R8": ("D7", "2"),
    "R19": ("U4", "22"),
    "TP1": ("U4", "12"),
    # RS-485 near RJ45 (signal lane, mid-right)
    "U3": ("J1", "1"),
    "C14": ("U3", "8"),
    "R9": ("U3", "1"),
    "R10": ("U3", "3"),
    "JP1": ("U3", "6"),
    "R11": ("JP1", "2"),
    "D8": ("J1", "1"),
    # IMU near MCU (absolute XY filled after U4)
    "U5": (34.0, 20.0),
    "C15": ("U5", "14"),
    "C16": ("U5", "1"),
    "R12": ("U5", "6"),
    "R13": ("U5", "4"),
    "R20": ("U5", "7"),
}

KEEP_SILK_REFS = {
    "J1", "J2", "J3", "J4", "U1", "U2", "U3", "U4", "U5", "U6", "U7",
    "SW1", "SW2", "JP1", "TP1", "D7", "F1", "L1", "H1", "H2",
}

# Post-route power track floors (mm) — reinforce Freerouting widths
POWER_TRACK_WIDTH_MM = {
    "V12_RAW": 0.80,
    "V12_FUSED": 0.80,
    # Leave BUCK_SW at Freerouting width — thickening pushed it into BOOT/FB.
    "+12V": 0.60,
    "+5V": 0.50,
    "VBUS": 0.50,
    "V5_OR": 0.50,
    # Do NOT thicken +3V3: Freerouting leaves ~0.15mm gaps; forcing 0.30mm
    # creates dozens of clearance violations against nearby signal vias/pads.
}


def V(x: float, y: float):
    return pcbnew.VECTOR2I_MM(OX + x, OY + y)


def to_mm(vec):
    return pcbnew.ToMM(vec.x) - OX, pcbnew.ToMM(vec.y) - OY


def parse_netlist():
    root = ET.parse(NETLIST_PATH).getroot()
    comps = {}
    for c in root.iter("comp"):
        ref = c.get("ref")
        val = c.findtext("value") or ""
        fp_spec = c.findtext("footprint") or ""
        tstamp = (c.findtext("tstamps") or "").strip("/")
        fields = {f.get("name"): (f.text or "") for f in c.iter("field")}
        props = {p.get("name"): (p.get("value") or "") for p in c.iter("property")}
        dnp = any(p.get("name") == "dnp" for p in c.iter("property"))
        comps[ref] = {
            "ref": ref,
            "value": val,
            "fp": fp_spec,
            "uuid": tstamp,
            "lcsc": fields.get("LCSC", props.get("LCSC", "")),
            "mpn": fields.get("MPN", props.get("MPN", "")),
            "dnp": dnp,
            "pins": {},
        }

    nets = {}
    for n in root.iter("net"):
        name = n.get("name")
        nodes = [(nd.get("ref"), nd.get("pin")) for nd in n.iter("node")]
        nets[name] = nodes
        for r, p in nodes:
            if r in comps:
                comps[r]["pins"][p] = name
    return comps, nets


def load_footprint(fp_spec: str):
    lib, mod = fp_spec.split(":", 1)
    if lib == "RearCore":
        lib_path = os.path.join(HW_DIR, "footprints.pretty")
    else:
        lib_path = os.path.join(SHARE, "footprints", f"{lib}.pretty")
    fp = pcbnew.FootprintLoad(lib_path, mod)
    if fp is None:
        raise RuntimeError(f"Footprint not found: {fp_spec} in {lib_path}")
    fp.SetFPID(pcbnew.LIB_ID(lib, mod))
    return fp


def get_courtyard(fp):
    xs, ys = [], []
    boxes = [
        it.GetBoundingBox()
        for it in fp.GraphicalItems()
        if it.GetLayer() == pcbnew.F_CrtYd
    ]
    if not boxes:
        boxes = [fp.GetBoundingBox(False)]
    for b in boxes:
        for pt in (b.GetOrigin(), b.GetEnd()):
            x, y = to_mm(pt)
            xs.append(x)
            ys.append(y)
    return [min(xs), min(ys), max(xs), max(ys)]


def pad_xy(fp, pad_num: str):
    for p in fp.Pads():
        if p.GetNumber() == pad_num:
            return to_mm(p.GetPosition())
    # Fallback to footprint center
    return to_mm(fp.GetPosition())


def boxes_overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def add_silk_label(board, text: str, x: float, y: float, size: float = 0.9, rot: float = 0.0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetPosition(V(x, y))
    t.SetTextAngleDegrees(rot)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(0.15))
    board.Add(t)


def build_board(W: float, H: float, comps: dict, net_map: dict, place_opts: dict = None):
    """
    place_opts (optional) overrides fixed-cluster orientations/positions, e.g.:
      {
        "recipe": "sw_right_d1_down",
        "u1_rot": 180, "l1_rot": 90, "d1_rot": 90,
        "u1_dx": -5.0, "u1_dy": 6.5, "d1_dx": -9.5, "d1_dy": 4.5,
      }
    """
    place_opts = place_opts or {}
    board = pcbnew.NewBoard(PCB_PATH)
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)

    # Register all nets
    net_items = {}
    for net_name in net_map:
        ni = pcbnew.NETINFO_ITEM(board, net_name)
        board.Add(ni)
        net_items[net_name] = ni

    fps = {}
    for ref, c in comps.items():
        if DEFER_MOUNTING_HOLES and ref in MOUNTING_HOLE_REFS:
            continue  # add later into free space after route
        fp = load_footprint(c["fp"])
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + c["uuid"]))
        if c["lcsc"]:
            fp.SetField("LCSC", c["lcsc"])
            fld = fp.GetField("LCSC")
            fld.SetVisible(False)
            fld.SetLayer(pcbnew.F_Fab)
        if c["mpn"]:
            fp.SetField("MPN", c["mpn"])
            fld = fp.GetField("MPN")
            fld.SetVisible(False)
            fld.SetLayer(pcbnew.F_Fab)
        # Configure Reference text: keep visible on F.SilkS for key parts, F.Fab for tiny passives
        ref_txt = fp.Reference()
        if ref in KEEP_SILK_REFS:
            ref_txt.SetLayer(pcbnew.F_SilkS)
            ref_txt.SetVisible(True)
            ref_txt.SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))
            ref_txt.SetTextThickness(MM(0.15))
        else:
            ref_txt.SetLayer(pcbnew.F_Fab)
            ref_txt.SetVisible(False)
            ref_txt.SetTextSize(pcbnew.VECTOR2I(MM(0.6), MM(0.6)))
            ref_txt.SetTextThickness(MM(0.1))

        val_txt = fp.Value()
        val_txt.SetLayer(pcbnew.F_Fab)
        val_txt.SetVisible(False)

        if ref in ("U5", "J4"):
            fp.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

        board.Add(fp)
        for pad in fp.Pads():
            pnum = pad.GetNumber()
            nname = c["pins"].get(pnum)
            if nname and nname in net_items:
                pad.SetNet(net_items[nname])
        fps[ref] = fp

    # Board outline (Edge.Cuts rectangle W x H)
    corners = [(0, 0), (W, 0), (W, H), (0, H)]
    for i in range(4):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(V(*corners[i]))
        seg.SetEnd(V(*corners[(i + 1) % 4]))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(MM(0.15))
        board.Add(seg)

    obstacles = []  # list of (name, [xmin,ymin,xmax,ymax])
    placed = set()

    def expand_box(b, m: float):
        return [b[0] - m, b[1] - m, b[2] + m, b[3] + m]

    def fix_place(ref: str, x: float, y: float, rot: float = 0.0, custom_obs=None, keepout_margin=0.0):
        fp = fps[ref]
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(V(x, y))
        obs = custom_obs if custom_obs else get_courtyard(fp)
        if keepout_margin:
            obs = expand_box(obs, keepout_margin)
        obstacles.append((ref, obs))
        placed.add(ref)
        return obs

    def courtyard_at_origin(ref: str, rot: float):
        fp = fps[ref]
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(V(0, 0))
        return get_courtyard(fp)

    def place_align_edge(ref: str, rot: float, cy: float = None, cx: float = None,
                         left=None, right=None, top=None, bottom=None):
        """Place by courtyard-center on free axis, and align one courtyard edge."""
        b = courtyard_at_origin(ref, rot)
        if left is not None:
            px = left - b[0]
        elif right is not None:
            px = right - b[2]
        else:
            px = cx - (b[0] + b[2]) / 2.0
        if top is not None:
            py = top - b[1]
        elif bottom is not None:
            py = bottom - b[3]
        else:
            py = cy - (b[1] + b[3]) / 2.0
        return fix_place(ref, px, py, rot=rot)

    # 1. Fixed strategic edge placements
    # Bottom L→R: J2(WS2812) | J4(USB) | J1(RJ45) | J3(12V exp)
    # Top: MCU antenna UP between USB and RJ45 (shorten EXP_CMD / balance rails)
    # Left column: C7+U6 glued above J2; H2 top-left; H1 top-right
    j4_fp = fps["J4"]
    best_j4 = None
    for rot in (0.0, 90.0, 180.0, 270.0):
        j4_fp.SetOrientationDegrees(rot)
        j4_fp.SetPosition(V(0, 0))
        sig_ys = [to_mm(p.GetPosition())[1] for p in j4_fp.Pads() if p.GetNumber().startswith(("A", "B"))]
        avg_y = sum(sig_ys) / len(sig_ys)
        if best_j4 is None or avg_y < best_j4[0]:
            best_j4 = (avg_y, rot)

    conn_order = [("J2", 0.0), ("J4", best_j4[1]), ("J1", 180.0), ("J3", 0.0)]
    widths = {}
    for ref, rot in conn_order:
        b = courtyard_at_origin(ref, rot)
        widths[ref] = b[2] - b[0]
    gap = 2.0
    edge_clear = 2.0
    row_w = sum(widths[r] for r, _ in conn_order) + gap * (len(conn_order) - 1)
    need_w = row_w + 2 * edge_clear
    if need_w > W + 0.01:
        raise RuntimeError(f"Bottom connector row needs {need_w:.1f}mm width, board is {W}mm")
    x = edge_clear
    centers = {}
    for ref, _ in conn_order:
        centers[ref] = x + widths[ref] / 2.0
        x += widths[ref] + gap

    for ref, rot in conn_order:
        bottom = H + (0.3 if ref in ("J1", "J4") else 0.15)
        place_align_edge(ref, rot, cx=centers[ref], bottom=bottom)

    j1b = get_courtyard(fps["J1"])
    j2b = get_courtyard(fps["J2"])
    j4b = get_courtyard(fps["J4"])

    # MCU: between USB and RJ45, antenna up. Shift ~3mm left vs prior bias to
    # free the J1→J3 corridor for a short 12V trunk (F1/D1).
    u4_half_w, u4_body_bottom = 7.0, 17.3
    u4_cy = 11.45
    u4_cx = 0.55 * centers["J4"] + 0.45 * centers["J1"] - 1.0  # left of previous right-bias
    u4_cx = max(u4_cx, centers["J4"] + 2.0)
    u4_cx = min(u4_cx, centers["J1"] - 2.0)

    def u4_box(cx):
        return [cx - u4_half_w, 0.0, cx + u4_half_w, u4_body_bottom]

    # Nudge until the module body clears connector courtyards in 2D
    for _ in range(24):
        body = u4_box(u4_cx)
        hit = None
        for ref, box in (("J1", j1b), ("J2", j2b), ("J4", j4b)):
            if boxes_overlap(body, expand_box(box, 0.4)):
                hit = ref
                break
        if hit is None:
            break
        u4_cx -= 0.5 if hit == "J1" else -0.5
    else:
        raise RuntimeError(f"MCU body still collides near x={u4_cx:.1f} on {W}x{H}mm")

    u4_body = u4_box(u4_cx)
    fix_place("U4", u4_cx, u4_cy, rot=0.0, custom_obs=u4_body)
    obstacles.append(("ANT", [-1.0, -1.0, W + 1.0, 5.85]))

    # Retarget MCU-local parts now that U4 is known
    ANCHORS["SW1"] = (u4_cx - 9.0, 21.0)
    ANCHORS["SW2"] = (u4_cx + 9.0, 21.0)
    ANCHORS["U5"] = (u4_cx + 3.5, 20.0)
    ANCHORS["D7"] = (u4_cx + 7.0, 16.0)
    # 12V trunk + Buck cluster — orientations/offsets come from place_opts (recipe search).
    j3b = get_courtyard(fps["J3"])
    u1_rot = float(place_opts.get("u1_rot", 180.0))
    l1_rot = float(place_opts.get("l1_rot", 90.0))
    d1_rot = float(place_opts.get("d1_rot", 90.0))
    u1_dx = float(place_opts.get("u1_dx", -5.0))
    u1_dy = float(place_opts.get("u1_dy", 6.5))
    d1_dx = float(place_opts.get("d1_dx", -9.5))
    d1_dy = float(place_opts.get("d1_dy", 4.5))

    # On a tall topology board, park the cluster mid-right with air above J1.
    l1_cx = centers["J3"] - 2.0
    l1_cy = min(16.0, j1b[1] * 0.45)
    u1_cx = l1_cx + u1_dx
    u1_cy = l1_cy + u1_dy
    d1_cx = l1_cx + d1_dx
    d1_cy = l1_cy + d1_dy

    if "L1" in fps:
        fix_place("L1", l1_cx, l1_cy, rot=l1_rot)
    if "U1" in fps:
        fix_place("U1", u1_cx, u1_cy, rot=u1_rot)
        ANCHORS["C1"] = ("U1", "3")
        ANCHORS["C2"] = ("U1", "3")
        ANCHORS["C3"] = ("U1", "3")
        ANCHORS["C4"] = ("U1", "6")
        ANCHORS["R1"] = ("U1", "4")
        ANCHORS["R2"] = ("U1", "4")
        ANCHORS["C5"] = ("L1", "2")
        ANCHORS["C6"] = ("L1", "2")
    if "D1" in fps:
        d1_box = fix_place("D1", d1_cx, d1_cy, rot=d1_rot)
        f1_b0 = courtyard_at_origin("F1", 90.0) if "F1" in fps else [0, 0, 4, 6]
        f1_half_w = (f1_b0[2] - f1_b0[0]) / 2.0
        f1_half_h = (f1_b0[3] - f1_b0[1]) / 2.0
        f1_cx = d1_box[0] - 0.6 - f1_half_w
        f1_cy = min(d1_cy, d1_box[1] - 0.5 - f1_half_h)
        f1_cy = max(f1_cy, 8.0)
    else:
        f1_cx = 0.55 * centers["J1"] + 0.45 * centers["J3"]
        f1_cy = min(j1b[1], j3b[1]) - 4.0
    if "F1" in fps:
        fix_place("F1", f1_cx, f1_cy, rot=90.0)
    if "D6" in fps:
        ANCHORS["D6"] = (d1_cx + 3.0, max(8.5, d1_cy - 5.5))
    print(
        f"  Buck recipe={place_opts.get('recipe', '?')}: "
        f"U1@{u1_rot:.0f} L1@{l1_rot:.0f} D1@{d1_rot:.0f} "
        f"L1=({l1_cx:.1f},{l1_cy:.1f}) U1=({u1_cx:.1f},{u1_cy:.1f}) D1=({d1_cx:.1f},{d1_cy:.1f})"
    )

    # U3 RS-485 (SOIC-8): near J1 A/B. On 40mm-tall boards there is no vertical
    # gap under the MCU, so shift U3 to the right of the ESP32 body instead.
    if "U3" in fps:
        u3_b0 = courtyard_at_origin("U3", -90.0)
        u3_half_w = (u3_b0[2] - u3_b0[0]) / 2.0
        u3_half_h = (u3_b0[3] - u3_b0[1]) / 2.0
        u4_right = u4_cx + u4_half_w
        u3_cx = max(centers["J1"] - 1.5, u4_right + 0.50 + u3_half_w)
        u3_cy = j1b[1] - 0.50 - u3_half_h
        # Prefer sitting below MCU body when height allows
        below = u4_body_bottom + 0.40 + u3_half_h
        if below + u3_half_h <= j1b[1] - 0.30:
            u3_cy = below
            u3_cx = centers["J1"] - 1.5
        fix_place("U3", u3_cx, u3_cy, rot=-90.0)
        ANCHORS["JP1"] = (u3_cx + 4.5, u3_cy)
        ANCHORS["D8"] = (centers["J1"] + 0.5, j1b[1] - 2.8)

    # C7: electrolytic bulk cap glued just above J2 (left-aligned to free data-pin side)
    if "C7" in fps:
        place_align_edge("C7", 90.0, left=EDGE_MARGIN + 0.15, bottom=j2b[1] - 0.30)
        c7b = get_courtyard(fps["C7"])
    else:
        c7b = None

    # U6: raise above J2 so R14 (330Ω LED damp) fits on the short data path
    # without courtyard/pad overlap (previous mid-point placement shorted GND↔LED_DATA).
    if "U6" in fps:
        u6_cx = centers["J2"] + 2.8
        if c7b is not None:
            u6_cx = max(u6_cx, c7b[2] + 1.6)
        u6_cy = j2b[1] - 6.8
        u6_box = fix_place("U6", u6_cx, u6_cy, rot=0.0)
        # R14 between U6-Y and J2-2, forced below U6 courtyard
        if "R14" in fps:
            r14_b = courtyard_at_origin("R14", 90.0)
            r14_half_h = (r14_b[3] - r14_b[1]) / 2.0
            r14_cx = (pad_xy(fps["U6"], "4")[0] + centers["J2"] + 1.2) / 2.0
            r14_cy = max(
                (u6_cy + j2b[1]) / 2.0,
                u6_box[3] + 0.35 + r14_half_h,
            )
            # Stay above J2 courtyard
            r14_cy = min(r14_cy, j2b[1] - 0.35 - r14_half_h)
            if r14_cy - r14_half_h < u6_box[3] + 0.20:
                raise RuntimeError(
                    f"No gap for R14 between U6 and J2 on {W}x{H}mm "
                    f"(U6 bottom={u6_box[3]:.2f}, J2 top={j2b[1]:.2f})"
                )
            fix_place("R14", r14_cx, r14_cy, rot=90.0)

    # Mounting holes (H1/H2) intentionally omitted here — placed into free
    # space after a clean route (see place_mounting_holes_in_gaps).

    raw = {"U4": u4_body}
    for ref in ("J1", "J2", "J3", "J4"):
        raw[ref] = get_courtyard(fps[ref])
    for href in ("C7", "U6", "R14", "U3", "U1", "L1", "D1", "F1"):
        if href in fps and href in placed:
            raw[href] = get_courtyard(fps[href])
    check_pairs = [
        ("J1", "J2"), ("J1", "J3"), ("J1", "J4"),
        ("J2", "J3"), ("J2", "J4"), ("J3", "J4"),
        ("U4", "J4"), ("U4", "J2"), ("U4", "J1"), ("U4", "J3"),
        ("U4", "U3"), ("U6", "R14"),
        ("U1", "L1"), ("U1", "D1"), ("L1", "D1"), ("D1", "F1"), ("U1", "J3"), ("L1", "J3"),
    ]
    for href in ("C7", "U6", "R14", "U3", "U1", "L1", "D1", "F1"):
        if href in raw:
            check_pairs += [(href, "U4"), (href, "J2"), (href, "J1"), (href, "J3"), (href, "J4")]
    if "C7" in raw and "U6" in raw:
        check_pairs.append(("C7", "U6"))
    if "C7" in raw and "R14" in raw:
        check_pairs.append(("C7", "R14"))
    for a, b in check_pairs:
        if a in raw and b in raw and boxes_overlap(raw[a], raw[b]):
            raise RuntimeError(
                f"Fixed overlap {a}{raw[a]} x {b}{raw[b]} on {W}x{H}mm board"
            )

    print("  Fixed placement courtyards:")
    for name, b in obstacles:
        print(f"    {name:4s} [{b[0]:6.2f},{b[1]:6.2f},{b[2]:6.2f},{b[3]:6.2f}]")
    extra = f" | U4@{u4_cx:.1f}"
    if DEFER_MOUNTING_HOLES:
        extra += " | H1/H2=deferred"
    if "C7" in placed:
        c7p = to_mm(fps["C7"].GetPosition())
        extra += f" | C7@{c7p[0]:.1f},{c7p[1]:.1f}"
    print(
        f"  Bottom row centers: "
        + ", ".join(f"{r}@{centers[r]:.1f}" for r, _ in conn_order)
        + extra
    )

    obstacles = [b for _, b in obstacles]

    # 2. Search-grid placement for remaining SMD components sorted by importance
    offsets = []
    step = 0.25
    max_r = 32.0
    steps = int(max_r / step)
    for ix in range(-steps, steps + 1):
        for iy in range(-steps, steps + 1):
            d = math.hypot(ix * step, iy * step)
            if d <= max_r:
                offsets.append((d, ix * step, iy * step))
    offsets.sort()

    def fp_area(ref):
        fp = fps[ref]
        fp.SetOrientationDegrees(0)
        b = get_courtyard(fp)
        return (b[2] - b[0]) * (b[3] - b[1])

    remaining = [
        r for r in comps
        if r not in placed and not (DEFER_MOUNTING_HOLES and r in MOUNTING_HOLE_REFS)
    ]
    ics_fets = [r for r in remaining if r.startswith(("U", "Q", "SW"))]
    power_big = sorted(
        [r for r in remaining if r not in ics_fets and fp_area(r) > 10.0],
        key=fp_area,
        reverse=True,
    )
    decoupling = [
        r for r in remaining
        if r not in ics_fets and r not in power_big and r.startswith("C")
    ]
    others = [
        r for r in remaining
        if r not in ics_fets and r not in power_big and r not in decoupling
    ]
    order = ics_fets + power_big + decoupling + others

    while order:
        progressed = False
        for ref in list(order):
            anc = ANCHORS.get(ref, (W / 2.0, H / 2.0))
            if isinstance(anc[0], str):
                if anc[0] not in placed:
                    continue
                tx, ty = pad_xy(fps[anc[0]], anc[1])
                target_net = comps[anc[0]]["pins"].get(anc[1])
                matching_pins = [k for k, v in comps[ref]["pins"].items() if v == target_net]
            else:
                tx, ty = anc
                matching_pins = []

            fp = fps[ref]
            best = None
            for rot in (0.0, 90.0, 180.0, 270.0):
                fp.SetOrientationDegrees(rot)
                fp.SetPosition(V(0, 0))
                b = get_courtyard(fp)
                kx, ky = pad_xy(fp, matching_pins[0]) if matching_pins else (0.0, 0.0)
                for d, ox, oy in offsets:
                    if best and d >= best[0]:
                        break
                    px, py = tx - kx + ox, ty - ky + oy
                    bb = [b[0] + px - GAP, b[1] + py - GAP, b[2] + px + GAP, b[3] + py + GAP]
                    if (
                        bb[0] < EDGE_MARGIN
                        or bb[1] < EDGE_MARGIN
                        or bb[2] > W - EDGE_MARGIN
                        or bb[3] > H - EDGE_MARGIN
                    ):
                        continue
                    if any(boxes_overlap(bb, o) for o in obstacles):
                        continue
                    best = (d, rot, px, py)
                    break

            if best is None:
                raise RuntimeError(f"Could not place {ref} on {W}x{H}mm board")

            fp.SetOrientationDegrees(best[1])
            fp.SetPosition(V(best[2], best[3]))
            # Place visible silkscreen reference centered inside/near body on F.SilkS so it won't hit pads
            if ref in KEEP_SILK_REFS and ref not in ("U4", "J1", "J2", "J3", "J4"):
                fp.Reference().SetPosition(V(best[2], best[3]))
            obstacles.append(get_courtyard(fp))
            placed.add(ref)
            order.remove(ref)
            progressed = True

        if not progressed:
            raise RuntimeError(f"Unresolved anchor dependencies: {order}")

    # Silkscreen callouts just above the bottom connector row
    add_silk_label(board, "J2:5V D G", centers["J2"], H - 13.8, size=0.8)
    add_silk_label(board, "J3:12V 5V G CMD", centers["J3"], H - 13.8, size=0.8)
    add_silk_label(board, "J1 RJ45", centers["J1"], H - 17.8, size=0.85)
    add_silk_label(board, "A B 12V G", centers["J1"], H - 16.6, size=0.8)
    add_silk_label(board, "J4 USB", centers["J4"], H - 11.8, size=0.8)

    fps["U4"].Reference().SetPosition(V(u4_cx - 8.5, 7.5))
    fps["J1"].Reference().SetVisible(False)
    fps["J2"].Reference().SetVisible(False)
    fps["J3"].Reference().SetVisible(False)
    fps["J4"].Reference().SetVisible(False)

    # Back silkscreen title
    bt = pcbnew.PCB_TEXT(board)
    bt.SetText("LaserBlinker Rear Core v2.0")
    bt.SetLayer(pcbnew.B_SilkS)
    bt.SetPosition(V(W / 2.0, H / 2.0))
    bt.SetMirrored(True)
    bt.SetTextSize(pcbnew.VECTOR2I(MM(1.1), MM(1.1)))
    bt.SetTextThickness(MM(0.15))
    board.Add(bt)

    return board, net_items, fps


def place_mounting_holes_in_gaps(board, W: float, H: float, comps: dict, net_map: dict) -> int:
    """
    Drop H1/H2 into free space after routing.
    Preferred layout (uses empty board real estate):
      H2 — top-left (below antenna keepout)
      H1 — directly above J3, around mid-board height
    """
    if not DEFER_MOUNTING_HOLES:
        return 0

    # Obstacles = pad boxes (not U4 antenna courtyard, which spans half the board).
    obstacles = []
    j3 = None
    stale = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in MOUNTING_HOLE_REFS:
            stale.append(fp)
            continue
        if ref == "J3":
            j3 = to_mm(fp.GetPosition())
        if ref == "U4":
            cx, cy = to_mm(fp.GetPosition())
            obstacles.append([cx - 7.2, cy - 6.0, cx + 7.2, cy + 6.2])  # module body
            continue
        for pad in fp.Pads():
            px, py = to_mm(pad.GetPosition())
            sx = max(pcbnew.ToMM(pad.GetSizeX()), 1.0) * 0.5 + 0.35
            sy = max(pcbnew.ToMM(pad.GetSizeY()), 1.0) * 0.5 + 0.35
            obstacles.append([px - sx, py - sy, px + sx, py + sy])
    for fp in stale:
        board.Delete(fp)
    obstacles.append([-1.0, -1.0, W + 1.0, 5.85])  # antenna copper keepout

    # Also keep clear of existing copper tracks (hole pads are plated GND).
    tracks = []
    for tr in board.GetTracks():
        if tr.GetClass() not in ("PCB_TRACK", "PCB_ARC"):
            continue
        tracks.append(tr)

    def track_clear(cx: float, cy: float, radius: float = 2.8) -> bool:
        c = pcbnew.VECTOR2I(MM(cx), MM(cy))
        for tr in tracks:
            # Distance from point to segment in board units
            try:
                d = tr.GetDistance(c, radius * 1e6)  # may not exist
            except Exception:
                d = None
            if d is None:
                sx, sy = pcbnew.ToMM(tr.GetStart().x) - OX, pcbnew.ToMM(tr.GetStart().y) - OY
                ex, ey = pcbnew.ToMM(tr.GetEnd().x) - OX, pcbnew.ToMM(tr.GetEnd().y) - OY
                # point-line distance
                vx, vy = ex - sx, ey - sy
                L2 = vx * vx + vy * vy
                if L2 < 1e-9:
                    dist = math.hypot(cx - sx, cy - sy)
                else:
                    t = max(0.0, min(1.0, ((cx - sx) * vx + (cy - sy) * vy) / L2))
                    dist = math.hypot(cx - (sx + t * vx), cy - (sy + t * vy))
                w = pcbnew.ToMM(tr.GetWidth()) * 0.5
                if dist < radius + w + 0.25:
                    return False
            elif d < MM(0.25):
                return False
        return True

    gnd = board.FindNet("GND")
    placed_xy = []
    j3_x = j3[0] if j3 else (W - 10.0)
    j3_y = j3[1] if j3 else (H - 10.0)
    above_j3_y = min(H * 0.50, j3_y - 8.0)
    above_j3_y = max(above_j3_y, 8.5)

    def try_spot(ref: str, cx: float, cy: float) -> bool:
        c = comps[ref]
        fp = load_footprint(c["fp"])
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + c["uuid"]))
        fp.SetOrientationDegrees(0.0)
        fp.SetPosition(V(cx, cy))
        for pad in fp.Pads():
            if gnd is not None:
                pad.SetNet(gnd)
        b = get_courtyard(fp)
        bb = [b[0] - GAP, b[1] - GAP, b[2] + GAP, b[3] + GAP]
        if bb[0] < EDGE_MARGIN or bb[1] < 6.2 or bb[2] > W - EDGE_MARGIN or bb[3] > H - EDGE_MARGIN:
            return False
        if any(boxes_overlap(bb, o) for o in obstacles):
            return False
        if not track_clear(cx, cy):
            return False
        for px, py in placed_xy:
            if math.hypot(cx - px, cy - py) < 10.0:
                return False
        ref_txt = fp.Reference()
        ref_txt.SetLayer(pcbnew.F_SilkS)
        ref_txt.SetVisible(True)
        ref_txt.SetPosition(V(cx, cy))
        board.Add(fp)
        obstacles.append(bb)
        placed_xy.append((cx, cy))
        print(f"  Mounting hole {ref} @ ({cx:.1f},{cy:.1f})")
        return True

    def neighborhood(cx: float, cy: float, step: float = 0.5, rings: int = 12):
        yield (cx, cy)
        for r in range(1, rings + 1):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    yield (cx + dx * step, cy + dy * step)

    targets = {
        "H2": list(neighborhood(4.0, 9.0)),            # top-left
        "H1": list(neighborhood(j3_x, above_j3_y)),    # above J3 / mid-board
    }

    n = 0
    for ref in ("H2", "H1"):
        if ref not in comps:
            continue
        for cx, cy in targets[ref]:
            if try_spot(ref, cx, cy):
                n += 1
                break
        else:
            print(f"  WARNING: could not place mounting hole {ref} near preferred spot")
    return n


def add_gnd_zone(board, gnd_net, layer, W: float, H: float):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(gnd_net)
    z.SetMinThickness(MM(0.2))
    z.SetLocalClearance(MM(0.2))
    z.SetThermalReliefGap(MM(0.3))
    z.SetThermalReliefSpokeWidth(MM(0.4))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    ol = z.Outline()
    ol.NewOutline()
    # Top antenna strip copper-free (antenna faces +board top / -Y local on U4)
    for x, y in [(0.35, 5.9), (W - 0.35, 5.9), (W - 0.35, H - 0.35), (0.35, H - 0.35)]:
        ol.Append(V(x, y))
    board.Add(z)
    return z


def autoroute_headless_dialogfree(board):
    dsn = os.path.join(OUT_DIR, "route.dsn")
    ses = os.path.join(OUT_DIR, "route.ses")
    for p in (dsn, ses):
        if os.path.exists(p):
            os.remove(p)
    pcbnew.ExportSpecctraDSN(board, dsn)
    cmd = [
        JAVA_BIN,
        "-jar", FREEROUTING_JAR,
        "-de", dsn,
        "-do", ses,
        "-mp", str(FREEROUTING_PASSES),
        # Multi-thread opt is known-broken and creates clearance/shorts (Freerouting warning).
        "-mt", "1",
        "-dct", "0",
        "-da",
    ]
    print(f"Running Freerouting (-mp {FREEROUTING_PASSES} -mt 1 -dct 0 -da)...")
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if not os.path.exists(ses):
        print(res.stdout[-2000:], res.stderr[-2000:])
        raise RuntimeError("Freerouting failed to produce session file")
    pcbnew.ImportSpecctraSES(board, ses)


def trim_render_margins(path: str, pad: int = 8) -> None:
    """Crop empty margins from kicad-cli renders (prefers alpha; else green-board bbox)."""
    try:
        from PIL import Image
    except ImportError:
        return
    im = Image.open(path).convert("RGBA")
    px = im.load()
    w, h = im.size

    def is_board(x, y):
        r, g, b, a = px[x, y]
        if a < 16:
            return False
        mx, mn = max(r, g, b), min(r, g, b)
        # Studio backdrop: low-sat mid/light gray (incl. blueish lavender)
        if mx - mn <= 30 and 90 <= mx <= 235:
            return False
        # Near-black floor / side padding under the board
        if mx - mn < 10 and mn < 55:
            return False
        return True

    step = 2
    cols = list(range(0, w, step))
    rows = list(range(0, h, step))
    top = next((y for y in rows if any(is_board(x, y) for x in cols)), 0)
    bottom = next((y for y in reversed(rows) if any(is_board(x, y) for x in cols)), h - 1)
    left = next((x for x in cols if any(is_board(x, y) for y in range(top, bottom + 1, step))), 0)
    right = next((x for x in reversed(cols) if any(is_board(x, y) for y in range(top, bottom + 1, step))), w - 1)
    box = (
        max(0, left - pad),
        max(0, top - pad),
        min(w, right + step + pad),
        min(h, bottom + step + pad),
    )
    bw, bh = box[2] - box[0], box[3] - box[1]
    if bw < 200 or bh < 120 or bw * bh > 0.98 * w * h:
        return
    im.crop(box).save(path)


def thicken_power_tracks(board) -> int:
    """Ensure power nets meet minimum copper width after autoroute."""
    widened = 0
    for tr in board.GetTracks():
        if tr.GetClass() != "PCB_TRACK":
            continue
        name = (tr.GetNetname() or "").lstrip("/")
        floor = POWER_TRACK_WIDTH_MM.get(name)
        if floor is None:
            continue
        want = MM(floor)
        if tr.GetWidth() < want:
            tr.SetWidth(want)
            widened += 1
    return widened


def try_bridge_short_rats(board, max_len_mm: float = 12.0) -> int:
    """Bridge remaining tiny same-net pad pairs that Freerouting left open."""
    board.BuildConnectivity()
    before = board.GetConnectivity().GetUnconnectedCount(False)
    if before == 0:
        return 0

    pads_by_net = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = pad.GetNetname()
            if not net or net.startswith("unconnected"):
                continue
            pads_by_net.setdefault(net, []).append(pad)

    added = 0
    for pads in pads_by_net.values():
        if len(pads) < 2:
            continue
        pairs = []
        for i in range(len(pads)):
            for j in range(i + 1, len(pads)):
                a, b = pads[i], pads[j]
                dx = pcbnew.ToMM(a.GetPosition().x - b.GetPosition().x)
                dy = pcbnew.ToMM(a.GetPosition().y - b.GetPosition().y)
                d = math.hypot(dx, dy)
                if d <= max_len_mm:
                    pairs.append((d, a, b))
        pairs.sort(key=lambda t: t[0])
        for d, a, b in pairs:
            board.BuildConnectivity()
            cur = board.GetConnectivity().GetUnconnectedCount(False)
            if cur == 0:
                return added
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(a.GetPosition())
            track.SetEnd(b.GetPosition())
            track.SetWidth(MM(0.2))
            track.SetLayer(pcbnew.F_Cu)
            track.SetNet(a.GetNet())
            board.Add(track)
            board.BuildConnectivity()
            nxt = board.GetConnectivity().GetUnconnectedCount(False)
            if nxt < cur:
                added += 1
            else:
                board.Delete(track)
    return added


def stitch_gnd_vias(board, W: float, H: float, pitch: float = 3.0, clear_r: float = 0.65) -> int:
    gnd = board.FindNet("GND")
    zones = {
        z.GetLayer(): z
        for z in board.Zones()
        if z.GetNetCode() == gnd.GetNetCode()
    }
    ring_pts = [(0.0, 0.0)] + [
        (clear_r * math.cos(a * math.pi / 4.0), clear_r * math.sin(a * math.pi / 4.0))
        for a in range(8)
    ]
    count = 0
    y = 7.0  # stay clear of top antenna keepout
    while y < H - 1.5:
        x = 2.0
        while x < W - 2.0:
            if all(
                zones[lyr].GetFilledPolysList(lyr).Contains(V(x + dx, y + dy))
                for lyr in (pcbnew.F_Cu, pcbnew.B_Cu)
                for dx, dy in ring_pts
            ):
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(V(x, y))
                via.SetWidth(MM(0.6))
                via.SetDrill(MM(0.3))
                via.SetNet(gnd)
                board.Add(via)
                count += 1
            x += pitch
        y += pitch
    return count


def export_jlcpcb_and_renders():
    os.makedirs(FAB_DIR, exist_ok=True)
    gerber_dir = os.path.join(FAB_DIR, "gerber")
    if os.path.exists(gerber_dir):
        shutil.rmtree(gerber_dir)
    os.makedirs(gerber_dir, exist_ok=True)

    # 1. Gerbers & Drill
    subprocess.run([
        KCLI, "pcb", "export", "gerbers",
        "--layers", "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
        "--subtract-soldermask",
        "--output", gerber_dir + "/",
        PCB_PATH,
    ], check=True)
    subprocess.run([
        KCLI, "pcb", "export", "drill",
        "--format", "excellon",
        "--excellon-units", "mm",
        "--generate-map", "--map-format", "gerberx2",
        "--output", gerber_dir + "/",
        PCB_PATH,
    ], check=True)

    zip_path = os.path.join(FAB_DIR, "rear-core-gerber.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn in sorted(os.listdir(gerber_dir)):
            zf.write(os.path.join(gerber_dir, fn), arcname=fn)

    # 2. JLCPCB BOM (exclude DNP; no ref ranges — JLCPCB does not expand "R5-R7")
    bom_path = os.path.join(FAB_DIR, "jlcpcb-bom.csv")
    subprocess.run([
        KCLI, "sch", "export", "bom",
        "--fields", "Value,Reference,Footprint,LCSC",
        "--labels", "Comment,Designator,Footprint,JLCPCB Part #",
        "--group-by", "Value,Footprint,LCSC",
        "--exclude-dnp",
        "--ref-range-delimiter", "",
        "--output", bom_path,
        SCH_PATH,
    ], check=True)

    # 3. JLCPCB CPL (SMD + THT wave parts J1/J2/J3; skip jumpers/testpoints/holes)
    # Do NOT use --smd-only: BOM lists THT connectors for wave soldering, and
    # JLCPCB rejects BOM designators that are absent from the CPL.
    pos_raw = os.path.join(FAB_DIR, "pos-raw.csv")
    subprocess.run([
        KCLI, "pcb", "export", "pos",
        "--side", "front",
        "--format", "csv",
        "--units", "mm",
        "--exclude-dnp",
        "--output", pos_raw,
        PCB_PATH,
    ], check=True)

    cpl_path = os.path.join(FAB_DIR, "jlcpcb-cpl.csv")
    with open(pos_raw, newline="") as fin, open(cpl_path, "w", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.writer(fout)
        writer.writerow(["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"])
        for row in reader:
            ref = row["Ref"]
            if ref.startswith(("JP", "TP", "H")):
                continue
            writer.writerow([
                ref,
                row["Val"],
                row["Package"],
                f"{float(row['PosX']):.4f}mm",
                f"{float(row['PosY']):.4f}mm",
                row["Rot"],
                "Top",
            ])
    os.remove(pos_raw)

    # 4. 2D SVG/PNG & 3D Raytraced Renders
    subprocess.run([
        KCLI, "pcb", "export", "svg",
        "--layers", "F.Cu,B.Cu,F.SilkS,F.Mask,Edge.Cuts",
        "--page-size-mode", "2",
        "--output", os.path.join(OUT_DIR, "pcb-top.svg"),
        PCB_PATH,
    ], check=True)
    # Landscape (board is ~66x40). Old 1600x1800 was portrait and looked broken.
    top_png = os.path.join(OUT_DIR, "3d-top.png")
    subprocess.run([
        KCLI, "pcb", "render",
        "--side", "top",
        "--width", "1600", "--height", "980",
        "--background", "opaque",
        "--zoom", "1.05",
        "--quality", "high",
        "--output", top_png,
        PCB_PATH,
    ], check=True)
    trim_render_margins(top_png)
    subprocess.run([
        KCLI, "pcb", "render",
        "--rotate", "-45,0,35",
        "--width", "1600", "--height", "1400",
        "--quality", "high",
        "--output", os.path.join(OUT_DIR, "3d-iso.png"),
        PCB_PATH,
    ], check=True)


def export_netlist():
    os.makedirs(OUT_DIR, exist_ok=True)
    subprocess.run([
        KCLI, "sch", "export", "netlist",
        "--format", "kicadxml",
        "--output", NETLIST_PATH,
        SCH_PATH,
    ], check=True)


# Hard-fail DRC types: these are manufacturing / electrical blockers.
CRITICAL_DRC_TYPES = {
    "shorting_items",
    "tracks_crossing",
    "copper_edge_clearance",
    "hole_clearance",
    "drill_out_of_range",
}


def run_drc_report() -> dict:
    """Run kicad-cli DRC; return parsed JSON. Always writes out/drc.{json,rpt}."""
    os.makedirs(OUT_DIR, exist_ok=True)
    rpt = os.path.join(OUT_DIR, "drc.rpt")
    js = os.path.join(OUT_DIR, "drc.json")
    subprocess.run([
        KCLI, "pcb", "drc",
        "--format", "json",
        "--units", "mm",
        "--severity-error",
        "--refill-zones",
        "--output", js,
        PCB_PATH,
    ], check=True)
    subprocess.run([
        KCLI, "pcb", "drc",
        "--format", "report",
        "--units", "mm",
        "--severity-error",
        "--refill-zones",
        "--output", rpt,
        PCB_PATH,
    ], check=True)
    import json
    return json.loads(open(js, encoding="utf-8").read())


def summarize_drc(data: dict) -> tuple[int, list[str]]:
    viols = data.get("violations") or []
    critical = []
    for v in viols:
        typ = v.get("type") or ""
        if typ in CRITICAL_DRC_TYPES:
            critical.append(typ)
    return len(viols), critical


def _recipes_for_phase():
    """Yield (W, H, place_opts) candidates for the active build phase."""
    if BUILD_PHASE == "topology":
        W, H = TOPOLOGY_SIZE
        for name, u1_rot, l1_rot, d1_rot, u1_dx, u1_dy, d1_dx, d1_dy in BUCK_RECIPES:
            yield W, H, {
                "recipe": name,
                "u1_rot": u1_rot,
                "l1_rot": l1_rot,
                "d1_rot": d1_rot,
                "u1_dx": u1_dx,
                "u1_dy": u1_dy,
                "d1_dx": d1_dx,
                "d1_dy": d1_dy,
            }
    else:
        # Shrink phase: keep the topology-winning recipe; vary board size only.
        # Winner from topology search: sw_left_d1_down (U1@0 / L1@90 / D1@90).
        opts = {
            "recipe": "sw_left_d1_down",
            "u1_rot": 0.0,
            "l1_rot": 90.0,
            "d1_rot": 90.0,
            "u1_dx": -5.0,
            "u1_dy": 6.5,
            "d1_dx": -9.5,
            "d1_dy": 4.5,
        }
        for W, H in SHRINK_SIZES:
            yield W, H, dict(opts)


def main():
    export_netlist()
    comps, net_map = parse_netlist()
    best = None  # (critical, unrouted, soft_drc, area, recipe)
    best_meta = None
    print(f"BUILD_PHASE={BUILD_PHASE}")

    for W, H, place_opts in _recipes_for_phase():
        recipe = place_opts.get("recipe", "?")
        print(f"\n=== Placement '{recipe}' on {W}x{H} mm ===")
        try:
            board, net_items, fps = build_board(W, H, comps, net_map, place_opts)
        except RuntimeError as e:
            print(f"  Placement skipped: {e}")
            if BUILD_PHASE == "shrink" and best and best[0] == 0 and best[1] == 0:
                print("  Stopping shrink — previous size was the tightest clean fit.")
                break
            continue

        add_gnd_zone(board, net_items["GND"], pcbnew.B_Cu, W, H)
        place_path = os.path.join(OUT_DIR, f"place-{recipe}-{W:.0f}x{H:.0f}.kicad_pcb")
        pcbnew.SaveBoard(PCB_PATH, board)
        shutil.copy2(PCB_PATH, place_path)

        size_clean = False
        for attempt in range(1, ROUTE_ATTEMPTS + 1):
            print(f"  Route attempt {attempt}/{ROUTE_ATTEMPTS}...")
            shutil.copy2(place_path, PCB_PATH)
            board = pcbnew.LoadBoard(PCB_PATH)
            autoroute_headless_dialogfree(board)
            widened = thicken_power_tracks(board)
            if widened:
                print(f"    Widened {widened} power track segment(s)")
            add_gnd_zone(board, board.FindNet("GND"), pcbnew.F_Cu, W, H)
            pcbnew.SaveBoard(PCB_PATH, board)

            board = pcbnew.LoadBoard(PCB_PATH)
            filler = pcbnew.ZONE_FILLER(board)
            filler.Fill(board.Zones())
            board.BuildConnectivity()
            unrouted = board.GetConnectivity().GetUnconnectedCount(False)
            vias = stitch_gnd_vias(board, W, H) if unrouted == 0 else 0
            filler.Fill(board.Zones())
            pcbnew.SaveBoard(PCB_PATH, board)

            drc = run_drc_report()
            total, critical = summarize_drc(drc)
            print(
                f"    -> unrouted={unrouted}, drc={total}, "
                f"critical={len(critical)}, vias={vias}"
            )
            # Prefer clean + small area (shrink) / clean recipes (topology).
            score = (len(critical), unrouted, W * H, total, recipe)
            if best is None or score < best:
                best = score
                best_meta = (W, H, recipe, place_opts)
                shutil.copy2(PCB_PATH, os.path.join(OUT_DIR, "best-route.kicad_pcb"))
                with open(os.path.join(OUT_DIR, "best-recipe.txt"), "w") as f:
                    f.write(f"{recipe} on {W}x{H}\n{place_opts}\nscore={score}\n")
            if unrouted == 0 and not critical:
                print(f"SUCCESS: clean route ({recipe} on {W}x{H} mm)")
                size_clean = True
                break

        if BUILD_PHASE == "topology" and size_clean:
            break  # topology: lock first clean recipe
        if BUILD_PHASE == "shrink" and not size_clean:
            if best and best[0] == 0 and best[1] == 0:
                print("  Shrink stop — further sizes unlikely; keeping last clean board.")
                break

    if best is None:
        raise RuntimeError("All placement recipes failed")
    if best[0] != 0 or best[1] != 0:
        print(
            f"WARNING: no fully-clean result. "
            f"Best: critical={best[0]} unrouted={best[1]} soft_drc={best[3]} "
            f"recipe={best[4]} size={best_meta[0]}x{best_meta[1]}"
        )
    else:
        print(
            f"BEST CLEAN: {best_meta[2]} on {best_meta[0]}x{best_meta[1]} mm "
            f"(soft_drc={best[3]})"
        )

    best_path = os.path.join(OUT_DIR, "best-route.kicad_pcb")
    if os.path.exists(best_path):
        shutil.copy2(best_path, PCB_PATH)

    # Final step: drop mounting holes into leftover free space.
    board = pcbnew.LoadBoard(PCB_PATH)
    W_final, H_final = best_meta[0], best_meta[1]
    nh = place_mounting_holes_in_gaps(board, W_final, H_final, comps, net_map)
    if nh:
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
        pcbnew.SaveBoard(PCB_PATH, board)
        shutil.copy2(PCB_PATH, best_path)
        print(f"Placed {nh} mounting hole(s) into free space.")

    export_jlcpcb_and_renders()

    drc = run_drc_report()
    total, critical = summarize_drc(drc)
    print(f"DRC: {total} error(s); critical={critical or 'none'}")
    if BUILD_PHASE == "topology":
        print(
            "Topology phase done — size is intentionally large. "
            "Set BUILD_PHASE='shrink' after a clean topology."
        )
    else:
        print(f"Shrink phase done — kept {best_meta[0]}x{best_meta[1]} mm.")
    if critical:
        raise RuntimeError(
            f"Critical DRC remaining ({len(critical)}): {sorted(set(critical))}. "
            f"See {os.path.join(OUT_DIR, 'drc.rpt')}"
        )


if __name__ == "__main__":
    main()
