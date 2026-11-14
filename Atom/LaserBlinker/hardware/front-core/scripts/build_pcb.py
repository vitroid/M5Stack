#!/usr/bin/env python3
"""
Build complete 2-layer PCB (front-core.kicad_pcb) from front-core.kicad_sch netlist,
route via Freerouting, pour GND planes + stitching vias, export JLCPCB + 3D renders.

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
PCB_PATH = os.path.join(HW_DIR, "front-core.kicad_pcb")
SCH_PATH = os.path.join(HW_DIR, "front-core.kicad_sch")
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

# Portrait for handlebar stem: width ≤~35mm, grow height until route succeeds.
CANDIDATE_SIZES = [
    (36.0, 120.0), (35.0, 115.0), (38.0, 125.0), (40.0, 130.0),
]

FREEROUTING_PASSES = 48

# Zones filled after connectors are placed (absolute XY / pad anchors).
ANCHORS = {
    # PD + 12V input near USB_PWR (J2)
    "U0": ("J2", "A5"),
    "F1": ("J2", "A4"),
    "D1": ("F1", "2"),
    "D6": ("D1", "1"),
    "D9": ("U0", "10"),
    "R21": ("U0", "8"),
    "R22": ("U0", "1"),
    "R23": ("U0", "9"),
    "R24": ("D9", "2"),
    "C18": ("U0", "1"),
    # Buck / LDO
    "U1": (40.0, 28.0),
    "C1": ("U1", "3"),
    "C2": ("U1", "3"),
    "C3": ("U1", "3"),
    "C4": ("U1", "6"),
    "L1": (48.0, 26.0),
    "R1": ("U1", "4"),
    "R2": ("U1", "4"),
    "C5": ("L1", "2"),
    "C6": ("L1", "2"),
    "C7": ("L1", "2"),
    "U2": ("U4", "3"),
    "D2": ("U2", "1"),
    "D3": ("U2", "1"),
    "C8": ("U2", "1"),
    "C9": ("U2", "5"),
    "C10": ("U2", "5"),
    # USB_DBG ESD (J3)
    "U7": ("J3", "A6"),
    "R3": ("J3", "A5"),
    "R4": ("J3", "B5"),
    # MCU local
    "C11": ("U4", "3"),
    "C12": ("U4", "3"),
    "C13": ("U4", "3"),
    "C14": ("U4", "45"),
    "C15": ("U4", "3"),
    "R5": ("U4", "45"),
    "SW1": (28.0, 32.0),
    "SW2": (44.0, 32.0),
    "R6": ("SW2", "2"),
    "D7": (50.0, 30.0),
    "R8": ("D7", "2"),
    "TP1": ("U4", "15"),
    # RS-485 near RJ45
    "U3": ("J1", "1"),
    "C16": ("U3", "8"),
    "R9": ("U3", "1"),
    "R10": ("U3", "3"),
    "JP1": ("U3", "6"),
    "R11": ("JP1", "2"),
    "D8": ("J1", "1"),
    "F3": ("J1", "4"),
    # Turn FETs near P2/P3
    "Q1": ("P2", "2"),
    "R15": ("Q1", "1"),
    "R16": ("Q1", "1"),
    "D4": ("P2", "2"),
    "Q2": ("P3", "2"),
    "R17": ("Q2", "1"),
    "R18": ("Q2", "1"),
    "D5": ("P3", "2"),
    # Status LED shifter near S4
    "U6": ("S4", "2"),
    "C17": ("U6", "5"),
    "R14": ("U6", "4"),
    # Buzzer
    "BZ1": (62.0, 30.0),
    "Q3": ("BZ1", "2"),
    "R35": ("BZ1", "1"),
    "R36": ("Q3", "1"),
    "R37": ("Q3", "1"),
    "D10": ("BZ1", "1"),
    # Navi 5V protect
    "F2": ("J4", "3"),
    "D11": ("F2", "1"),
    "JP2": ("J4", "3"),
    "R38": ("J4", "1"),
    "R39": ("J4", "2"),
    "R40": ("U4", "3"),
    # Switch RC networks (S1=TURN_L, S5=TURN_R)
    "R25": ("S5", "2"),
    "R26": ("S5", "2"),
    "R27": ("S1", "2"),
    "R28": ("S1", "2"),
    "R29": ("S2", "2"),
    "R30": ("S2", "2"),
    "R31": ("S3", "2"),
    "R32": ("S3", "2"),
    "C19": ("S5", "2"),
    "C20": ("S1", "2"),
    "C21": ("S2", "2"),
    "C22": ("S3", "2"),
    "R33": ("U4", "10"),
    "R34": ("U4", "10"),
    "C23": ("U4", "10"),
    "C24": ("U2", "1"),
}

KEEP_SILK_REFS = {
    "J1", "J2", "J3", "J4", "P2", "P3", "P4", "S1", "S2", "S3", "S4", "S5",
    "U0", "U1", "U2", "U3", "U4", "U6", "U7",
    "SW1", "SW2", "JP1", "JP2", "TP1", "F1", "F2", "F3", "L1", "BZ1",
    "Q1", "Q2", "Q3",
}

POWER_TRACK_WIDTH_MM = {
    "VBUS_PD": 1.00,
    "V12_FUSED": 1.00,
    "BUCK_SW": 0.80,
    "+12V": 1.00,
    "V12_TRUNK": 0.80,
    "+5V": 0.50,
    "VBUS": 0.50,
    "V5_LOGIC": 0.50,
    "+3V3": 0.25,
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


def _world_box(item):
    bb = item.GetBoundingBox()
    return [
        pcbnew.ToMM(bb.GetLeft()) - OX,
        pcbnew.ToMM(bb.GetTop()) - OY,
        pcbnew.ToMM(bb.GetRight()) - OX,
        pcbnew.ToMM(bb.GetBottom()) - OY,
    ]


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


def build_board(W: float, H: float, comps: dict, net_map: dict):
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

        if ref in ("J4", "U0"):
            fp.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

        # Skip mounting holes for now (portrait stem mount; H* deferred)
        if ref.startswith("H"):
            continue
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

    # 1. Portrait zoning (handlebar stem, width ≤~35mm)
    # Top: no connectors (waterproof).
    # Left upper: P2 + S1 (+ S2/P4). Right upper: P3 + S5 (+ S3/S4).
    # Mid-left: USB_DBG (J3) — short D+/D- to MCU.
    # Right edge: Grove/Navi (J4) horizontal, cable exits sideways (low profile).
    # Mid: MCU antenna overhanging left edge (below DBG). Bottom: USB_PWR | RJ45.

    def pack_col(order, edge_clear=1.2, gap=0.8):
        heights = {}
        for ref, rot in order:
            b = courtyard_at_origin(ref, rot)
            heights[ref] = b[3] - b[1]
        col_h = sum(heights[r] for r, _ in order) + gap * (len(order) - 1)
        # Keep a continuous mid band for MCU/buck between side TBs and bottom row
        need = col_h + edge_clear + 28.0
        if need > H + 0.01:
            raise RuntimeError(f"Side column needs {need:.1f}mm height, board is {H}mm")
        y = edge_clear
        centers = {}
        for ref, _ in order:
            centers[ref] = y + heights[ref] / 2.0
            y += heights[ref] + gap
        return centers

    def pack_row(order, edge_clear=1.2, gap=1.0):
        widths = {}
        for ref, rot in order:
            b = courtyard_at_origin(ref, rot)
            widths[ref] = b[2] - b[0]
        row_w = sum(widths[r] for r, _ in order) + gap * (len(order) - 1)
        need = row_w + 2 * edge_clear
        if need > W + 0.01:
            raise RuntimeError(f"Bottom row needs {need:.1f}mm, board is {W}mm")
        x = max(edge_clear, (W - row_w) / 2.0)
        centers = {}
        for ref, _ in order:
            centers[ref] = x + widths[ref] / 2.0
            x += widths[ref] + gap
        return centers

    # Terminal blocks face outward on left (rot=90) / right (rot=270)
    left_rot, right_rot = 90.0, 270.0
    left_order = [("P2", left_rot), ("S1", left_rot), ("S2", left_rot), ("P4", left_rot)]
    right_order = [("P3", right_rot), ("S5", right_rot), ("S3", right_rot), ("S4", right_rot)]
    left_c = pack_col(left_order)
    right_c = pack_col(right_order)

    for ref, rot in left_order:
        place_align_edge(ref, rot, cy=left_c[ref], left=-0.15)
    for ref, rot in right_order:
        place_align_edge(ref, rot, cy=right_c[ref], right=W + 0.15)

    # Bottom: USB_PWR + RJ45 facing down
    bot_order = [("J2", 0.0), ("J1", 180.0)]
    # Prefer USB rot with signal pads toward board interior (up)
    for rot in (0.0, 180.0):
        fps["J2"].SetOrientationDegrees(rot)
        fps["J2"].SetPosition(V(0, 0))
        ys = [to_mm(p.GetPosition())[1] for p in fps["J2"].Pads() if p.GetNumber().startswith(("A", "B"))]
        if ys and sum(ys) / len(ys) < 0:
            bot_order[0] = ("J2", rot)
            break
    bot_c = pack_row(bot_order)
    for ref, rot in bot_order:
        place_align_edge(ref, rot, cx=bot_c[ref], bottom=H + (0.25 if ref == "J1" else 0.15))

    # Mid-left: USB_DBG + Navi (pads toward board interior / +X)
    j3_rot = 90.0
    for rot in (90.0, 270.0):
        fps["J3"].SetOrientationDegrees(rot)
        fps["J3"].SetPosition(V(0, 0))
        xs = [to_mm(p.GetPosition())[0] for p in fps["J3"].Pads() if p.GetNumber().startswith(("A", "B"))]
        if xs and sum(xs) / len(xs) > 0:
            j3_rot = rot
            break
    # Just below the left terminal column so MCU can sit under with antenna left-out
    p4_placed = get_courtyard(fps["P4"])
    s4_placed = get_courtyard(fps["S4"])
    mid_y = p4_placed[3] + 7.0
    place_align_edge("J3", j3_rot, cy=mid_y, left=-0.2)
    j3b = get_courtyard(fps["J3"])
    # Grove on the right edge. Local +Y is the shroud (wire exit); rot 90 maps it to +X.
    j4_cy = s4_placed[3] + 6.0
    place_align_edge("J4", 90.0, cy=j4_cy, right=W + 0.15)

    j1b = get_courtyard(fps["J1"])
    j2b = get_courtyard(fps["J2"])
    j4b = get_courtyard(fps["J4"])

    # 12V enters at USB_PWR and stacks upward: F1, then D1, then U0.
    # Kept left of the RJ45 courtyard (x < 13.8).
    if "F1" in fps:
        fix_place("F1", bot_c["J2"], j2b[1] - 3.5, rot=0.0)
        f1b = get_courtyard(fps["F1"])
    else:
        f1b = [bot_c["J2"] - 3, j2b[1] - 6, bot_c["J2"] + 3, j2b[1] - 2]
    if "D1" in fps:
        db = courtyard_at_origin("D1", 180.0)
        dw, dh = db[2] - db[0], db[3] - db[1]
        d1_cy = f1b[1] - 0.45 - dh / 2.0
        d1_cx = (f1b[0] + f1b[2]) / 2.0
        if d1_cx + dw / 2.0 > 13.5:
            d1_cx = 13.5 - dw / 2.0
        fix_place("D1", d1_cx - dw / 2.0 - db[0], d1_cy - (db[1] + db[3]) / 2.0, rot=180.0)
        d1b = get_courtyard(fps["D1"])
    else:
        d1b = f1b
    if "U0" in fps:
        ub = courtyard_at_origin("U0", 0.0)
        uw, uh = ub[2] - ub[0], ub[3] - ub[1]
        u0_right = 13.7
        u0_left = u0_right - uw
        u0_cy = d1b[1] - 0.6 - uh / 2.0
        fix_place("U0", u0_left - ub[0], u0_cy - (ub[1] + ub[3]) / 2.0, rot=0.0)

    # RS-485 above RJ45
    if "U3" in fps:
        fix_place("U3", bot_c["J1"], j1b[1] - 5.0, rot=0.0)
        ANCHORS["JP1"] = (bot_c["J1"] + 4.0, j1b[1] - 5.0)
        ANCHORS["D8"] = (bot_c["J1"], j1b[1] - 2.2)
        ANCHORS["F3"] = (bot_c["J1"] - 4.0, j1b[1] - 2.5)

    # FETs + clamp diodes next to turn lamps; U6 next to S4
    if "Q1" in fps:
        p2b = get_courtyard(fps["P2"])
        fix_place("Q1", p2b[2] + 2.2, left_c["P2"], rot=0.0)
        if "D4" in fps:
            fix_place("D4", p2b[2] + 2.6, left_c["P2"] + 4.0, rot=0.0)
    if "Q2" in fps:
        p3b = get_courtyard(fps["P3"])
        fix_place("Q2", p3b[0] - 2.2, right_c["P3"], rot=0.0)
        if "D5" in fps:
            fix_place("D5", p3b[0] - 2.6, right_c["P3"] + 4.0, rot=0.0)
    if "U6" in fps:
        s4b = get_courtyard(fps["S4"])
        # Place inward (board center) from right-edge S4
        u6_x = max(10.0, s4b[0] - 2.8)
        fix_place("U6", u6_x, right_c["S4"], rot=0.0)
        if "R14" in fps:
            fix_place("R14", u6_x + 1.1, right_c["S4"] + 2.8, rot=0.0)

    # Measured on this footprint: local antenna is -Y.
    # rot 90° maps that axis to board -X (left). rot 270° points it right — do not use.
    # Module tip (silk y=-10.6) lands at x = cx-10.6. cx≈5.5 puts ~5mm of antenna past the left edge
    # while pads (local y>=-4.45) stay on the board.
    # USB_DBG (J3) is already on the left edge, above this module.
    u4_rot = 90.0
    u4_cx = 5.5
    u4_cy = max(j3b[3] + 14.0, 58.0)

    def u4_box(cx, cy):
        # Shielded body only. Antenna is the -X side and is off the board.
        return [0.6, cy - 8.5, cx + 11.0, cy + 8.5]

    side_boxes = [get_courtyard(fps[r]) for r in (
        "P2", "S1", "S2", "P4", "P3", "S5", "S3", "S4", "J3", "J4", "J1", "J2",
        "F1", "D1", "U0", "U3", "Q1", "Q2", "U6", "D4", "D5",
    ) if r in fps and (r in placed or r in ("J1", "J2", "J3", "J4", "P2", "P3", "P4", "S1", "S2", "S3", "S4", "S5"))]

    for _ in range(160):
        body = u4_box(u4_cx, u4_cy)
        hit = None
        for i, box in enumerate(side_boxes):
            if boxes_overlap(body, expand_box(box, 0.5)):
                hit = i
                break
        if hit is None:
            break
        # Prefer sliding down; never move right (that pulls antenna back onto the board)
        u4_cy += 0.5
        if u4_cy > H - 38:
            raise RuntimeError(
                f"MCU cannot fit below left DBG with left overhang on {W}x{H} "
                f"(last {u4_cx:.1f},{u4_cy:.1f})"
            )
    else:
        raise RuntimeError(f"MCU still collides near ({u4_cx:.1f},{u4_cy:.1f}) on {W}x{H}")

    u4_body = u4_box(u4_cx, u4_cy)
    fix_place("U4", u4_cx, u4_cy, rot=u4_rot, custom_obs=u4_body)
    tip_x = u4_cx - 10.6
    if tip_x > -3.0:
        raise RuntimeError(f"Antenna tip only at x={tip_x:.2f}; need clear left overhang")
    # Off-board + thin on-board RF-edge keepout
    ant_keepout = [-12.0, u4_body[1] - 1.0, 1.2, u4_body[3] + 1.0]
    obstacles.append(("ANT", ant_keepout))
    print(f"  U4 antenna tip x={tip_x:.2f}mm (left overhang), USB_DBG on left at y={mid_y:.1f}")
    ANCHORS["SW1"] = (u4_cx + 8.0, u4_cy - 6.0)
    ANCHORS["SW2"] = (u4_cx + 8.0, u4_cy + 6.0)
    ANCHORS["D7"] = (u4_cx + 10.0, u4_cy)
    # 12V enters at the bottom USB. Buck sits below the MCU and above U0.
    # Output caps stay on L1's output pad; the buzzer stays up by the Grove plug.
    u0_top = get_courtyard(fps["U0"])[1] if "U0" in placed else (H - 18.0)
    buck_y = min(u4_body[3] + 14.0, u0_top - 14.0)
    buck_y = max(buck_y, u4_body[3] + 11.0)

    def place_left_center(ref, rot, left, cy):
        b = courtyard_at_origin(ref, rot)
        fix_place(ref, left - b[0], cy - (b[1] + b[3]) / 2.0, rot=rot)
        return get_courtyard(fps[ref])

    gap = 0.4
    widths = {}
    # rot 180 puts the switch pin on the inductor side.
    buck_rot = {"U1": 180.0, "L1": 0.0, "C7": 0.0}
    for ref, rot in buck_rot.items():
        b = courtyard_at_origin(ref, rot)
        widths[ref] = b[2] - b[0]
    total = widths["U1"] + widths["L1"] + widths["C7"] + 2 * gap
    left = max(6.0, min((W - total) / 2.0, W - 0.5 - total))
    u1c = place_left_center("U1", buck_rot["U1"], left, buck_y)
    l1c = place_left_center("L1", 0.0, u1c[2] + gap, buck_y)
    c7c = place_left_center("C7", 0.0, l1c[2] + gap, buck_y)
    # 22µF ceramics sit on L1, same output node as C7, not up against the MCU.
    c5b = courtyard_at_origin("C5", 0.0)
    c6b = courtyard_at_origin("C6", 0.0)
    c5w, c5h = c5b[2] - c5b[0], c5b[3] - c5b[1]
    c6w = c6b[2] - c6b[0]
    pair_w = c5w + c6w + 0.3
    pair_left = l1c[0] + max(0.0, (l1c[2] - l1c[0] - pair_w) / 2.0)
    cap_cy = l1c[1] - 0.35 - c5h / 2.0
    c5c = place_left_center("C5", 0.0, pair_left, cap_cy)
    place_left_center("C6", 0.0, c5c[2] + 0.3, cap_cy)
    # Buzzer above the inductor, just under the right-edge Grove plug.
    bz = courtyard_at_origin("BZ1", 0.0)
    bz_h = bz[3] - bz[1]
    bz_cy = j4b[3] + 1.2 + bz_h / 2.0
    place_align_edge("BZ1", 0.0, cy=bz_cy, right=W - 0.3)
    # CFG1 resistor sits on the pin, so the 24k pull is one short segment.
    if "R23" in fps and "U0" in placed:
        pin = next(p for p in fps["U0"].Pads() if p.GetNumber() == "9")
        pb = _world_box(pin)
        fp = fps["R23"]
        fp.SetOrientationDegrees(0.0)
        fp.SetPosition(V(0, 0))
        cfg = next(p for p in fp.Pads() if "CFG1" in (p.GetNetname() or ""))
        kx, ky = to_mm(cfg.GetPosition())
        cfg_box = _world_box(cfg)
        half_x = (cfg_box[2] - cfg_box[0]) / 2.0
        target_x = pb[2] + 0.45 + half_x
        target_y = (pb[1] + pb[3]) / 2.0
        # Courtyard of a 0603 extends past the pad; keep it off U0's courtyard.
        fp.SetPosition(V(target_x - kx, target_y - ky))
        rb = get_courtyard(fp)
        ub = get_courtyard(fps["U0"])
        if boxes_overlap(rb, ub):
            target_x += ub[2] - rb[0] + 0.25
        fix_place("R23", target_x - kx, target_y - ky, rot=0.0)
        print(f"  R23 beside U0 pin 9 at x={pad_xy(fps['R23'], '1')[0]:.2f}")
    ANCHORS["U7"] = ("J3", "A6")
    print(
        f"  Buck y={buck_y:.1f} U1/L1/C7 tight, ceramics on L1, "
        f"BZ1 y={bz_cy:.1f} (L1 {l1c[1]:.1f}..{l1c[3]:.1f}, C7 {c7c[0]:.1f}..{c7c[2]:.1f})"
    )

    raw = {"U4": u4_body}
    for ref in ("J1", "J2", "J3", "J4", "P2", "P3", "P4", "S1", "S2", "S3", "S4", "S5"):
        if ref in fps:
            raw[ref] = get_courtyard(fps[ref])
    for href in ("F1", "D1", "U0", "U3", "Q1", "Q2", "U6", "R14", "D4", "D5"):
        if href in fps and href in placed:
            raw[href] = get_courtyard(fps[href])

    check_pairs = [
        ("P2", "S1"), ("S1", "S2"), ("S2", "P4"),
        ("P3", "S5"), ("S5", "S3"), ("S3", "S4"),
        ("J2", "J1"), ("S4", "J4"), ("J3", "P4"),
        ("U4", "J1"), ("U4", "J2"), ("U4", "J3"), ("U4", "J4"), ("U4", "P2"), ("U4", "P3"),
    ]
    for a, b in check_pairs:
        if a in raw and b in raw and boxes_overlap(raw[a], raw[b]):
            raise RuntimeError(f"Fixed overlap {a}{raw[a]} x {b}{raw[b]} on {W}x{H}mm")

    print("  Fixed placement courtyards:")
    for name, b in obstacles:
        print(f"    {name:4s} [{b[0]:6.2f},{b[1]:6.2f},{b[2]:6.2f},{b[3]:6.2f}]")
    print(
        f"  L: " + ", ".join(f"{r}@{left_c[r]:.1f}" for r, _ in left_order)
        + f" | R: " + ", ".join(f"{r}@{right_c[r]:.1f}" for r, _ in right_order)
        + f" | Bot: " + ", ".join(f"{r}@{bot_c[r]:.1f}" for r, _ in bot_order)
        + f" | DBG@L y={mid_y:.1f} | U4@{u4_cx:.1f},{u4_cy:.1f}"
    )

    obstacles = [b for _, b in obstacles]
    # 2. Search-grid placement for remaining SMD components sorted by importance
    offsets = []
    step = 0.5
    max_r = 28.0
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

    remaining = [r for r in comps if r not in placed and not r.startswith("H")]
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

    # Silkscreen callouts
    add_silk_label(board, "P2", 5.0, left_c["P2"], size=0.65, rot=90.0)
    add_silk_label(board, "S1", 5.0, left_c["S1"], size=0.65, rot=90.0)
    add_silk_label(board, "P3", W - 5.0, right_c["P3"], size=0.65, rot=90.0)
    add_silk_label(board, "S5", W - 5.0, right_c["S5"], size=0.65, rot=90.0)
    add_silk_label(board, "USB_PWR", bot_c["J2"], H - 3.5, size=0.65)
    add_silk_label(board, "RJ45", bot_c["J1"], j1b[1] - 1.0, size=0.65)
    add_silk_label(board, "USB_DBG", 5.5, mid_y, size=0.65, rot=90.0)
    add_silk_label(board, "NAVI", W - 6.5, j4_cy, size=0.6, rot=90.0)

    fps["U4"].Reference().SetPosition(V(u4_cx + 2.0, u4_cy - 10.0))
    for ref in ("J1", "J2", "J3", "J4", "P2", "P3", "P4", "S1", "S2", "S3", "S4", "S5"):
        if ref in fps:
            fps[ref].Reference().SetVisible(False)
    bt = pcbnew.PCB_TEXT(board)
    bt.SetText("LaserBlinker Front Core v1.0")
    bt.SetLayer(pcbnew.B_SilkS)
    bt.SetPosition(V(W / 2.0, H / 2.0))
    bt.SetMirrored(True)
    bt.SetTextSize(pcbnew.VECTOR2I(MM(1.1), MM(1.1)))
    bt.SetTextThickness(MM(0.15))
    board.Add(bt)
    return board, net_items, fps


def u4_antenna_keepout(board):
    """Board-relative mm box cleared of copper near the left-overhanging ESP antenna."""
    for fp in board.GetFootprints():
        if fp.GetReference() != "U4":
            continue
        cx, cy = to_mm(fp.GetPosition())
        # rot 90°: antenna keepout is on the -X side of the module
        return [cx - 14.0, cy - 9.0, 1.2, cy + 9.0]
    return None


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
    # Full board pour; hole cut for left-edge antenna keepout when MCU is present
    for x, y in [(0.35, 0.35), (W - 0.35, 0.35), (W - 0.35, H - 0.35), (0.35, H - 0.35)]:
        ol.Append(V(x, y))
    ant = u4_antenna_keepout(board)
    if ant:
        x0 = max(0.35, ant[0])
        y0 = max(0.35, ant[1])
        x1 = min(W - 0.35, ant[2])
        y1 = min(H - 0.35, ant[3])
        if x1 > x0 and y1 > y0:
            ol.NewOutline()
            for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
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
    # Keep the hand-routed VBUS tie and the 12V spine. Freerouting rips up `(type route)`.
    with open(dsn, encoding="utf-8") as fh:
        dsn_txt = fh.read()
    protected = dsn_txt.replace("(type route)", "(type protect)")
    if protected != dsn_txt:
        with open(dsn, "w", encoding="utf-8") as fh:
            fh.write(protected)
    cmd = [
        JAVA_BIN,
        "-jar", FREEROUTING_JAR,
        "-de", dsn,
        "-do", ses,
        "-mp", str(FREEROUTING_PASSES),
        "-mt", "1",  # multi-thread optimize is known to create clearance violations
        "-dct", "0",
        "-da",
    ]
    print(f"Running Freerouting (-mp {FREEROUTING_PASSES} -dct 0 -da)...")
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
        want_mm = floor
        if tr.GetWidth() >= MM(want_mm):
            continue
        ax, ay = to_mm(tr.GetStart())
        bx, by = to_mm(tr.GetEnd())
        # A neck through a USB-C pin row or next to U1 cannot take the full power width.
        if _copper_clear(board, [(ax, ay), (bx, by)], want_mm, tr.GetNetCode(), tr.GetLayer(), clearance=0.2):
            continue
        tr.SetWidth(MM(want_mm))
        widened += 1
    return widened


def _segment_clears_foreign_pads(board, a, b, clearance_mm: float = 0.25) -> bool:
    """Reject a straight power hop that runs across a pad of another net."""
    ax = pcbnew.ToMM(a.GetPosition().x)
    ay = pcbnew.ToMM(a.GetPosition().y)
    bx = pcbnew.ToMM(b.GetPosition().x)
    by = pcbnew.ToMM(b.GetPosition().y)
    vx, vy = bx - ax, by - ay
    l2 = vx * vx + vy * vy
    half_track = POWER_TRACK_WIDTH_MM.get((a.GetNetname() or "").lstrip("/"), 0.4) / 2.0
    net = a.GetNetCode()
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() == net:
                continue
            px = pcbnew.ToMM(pad.GetPosition().x)
            py = pcbnew.ToMM(pad.GetPosition().y)
            if l2 < 1e-9:
                dist = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / l2))
                dist = math.hypot(px - (ax + t * vx), py - (ay + t * vy))
            half_pad = pcbnew.ToMM(max(pad.GetSize().x, pad.GetSize().y)) / 2.0
            if dist < half_pad + half_track + clearance_mm:
                return False
    return True


def pre_route_power_nets(board) -> int:
    """Star-route power nets with fat copper before Freerouting."""
    pads_by_net = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            name = (pad.GetNetname() or "").lstrip("/")
            if name not in POWER_TRACK_WIDTH_MM:
                continue
            pads_by_net.setdefault(name, []).append(pad)
    added = 0
    for name, pads in pads_by_net.items():
        if len(pads) < 2:
            continue
        width = MM(POWER_TRACK_WIDTH_MM[name])
        # nearest-neighbor chain from leftmost pad
        pads = sorted(pads, key=lambda p: (p.GetPosition().x, p.GetPosition().y))
        connected = {0}
        while len(connected) < len(pads):
            best = None
            for i in connected:
                for j in range(len(pads)):
                    if j in connected:
                        continue
                    a, b = pads[i], pads[j]
                    d = math.hypot(
                        pcbnew.ToMM(a.GetPosition().x - b.GetPosition().x),
                        pcbnew.ToMM(a.GetPosition().y - b.GetPosition().y),
                    )
                    if d > 10.0:
                        continue  # long L-hops cause shorts; leave to Freerouting
                    if not _segment_clears_foreign_pads(board, a, b):
                        continue  # e.g. VBUS straight across USB-C CC/D+/D-
                    if best is None or d < best[0]:
                        best = (d, i, j, a, b)
            if best is None:
                break
            _, _, j, a, b = best
            # Direct segment only (short hops); avoid board-wide L-stubs
            tr = pcbnew.PCB_TRACK(board)
            tr.SetStart(a.GetPosition())
            tr.SetEnd(b.GetPosition())
            tr.SetWidth(width)
            tr.SetLayer(pcbnew.F_Cu)
            tr.SetNet(a.GetNet())
            board.Add(tr)
            added += 1
            connected.add(j)
    return added


def _find_pad(board, ref, number):
    for fp in board.GetFootprints():
        if fp.GetReference() != ref:
            continue
        for pad in fp.Pads():
            if pad.GetNumber() == number:
                return pad
    return None


def _seg_hits_box(ax, ay, bx, by, box, margin):
    x0, y0, x1, y1 = box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin

    def inside(x, y):
        return x0 <= x <= x1 and y0 <= y <= y1

    if inside(ax, ay) or inside(bx, by):
        return True

    def crosses(cx, cy, dx, dy):
        rx, ry = bx - ax, by - ay
        sx, sy = dx - cx, dy - cy
        den = rx * sy - ry * sx
        if abs(den) < 1e-12:
            return False
        t = ((cx - ax) * sy - (cy - ay) * sx) / den
        u = ((cx - ax) * ry - (cy - ay) * rx) / den
        return 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0

    return (
        crosses(x0, y0, x1, y0)
        or crosses(x1, y0, x1, y1)
        or crosses(x1, y1, x0, y1)
        or crosses(x0, y1, x0, y0)
    )


def _point_seg_dist(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    l2 = vx * vx + vy * vy
    if l2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / l2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _segs_hit(ax, ay, bx, by, cx, cy, dx, dy):
    rx, ry = bx - ax, by - ay
    sx, sy = dx - cx, dy - cy
    den = rx * sy - ry * sx
    if abs(den) < 1e-12:
        return False
    t = ((cx - ax) * sy - (cy - ay) * sx) / den
    u = ((cx - ax) * ry - (cy - ay) * rx) / den
    return 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0


def _seg_seg_dist(ax, ay, bx, by, cx, cy, dx, dy):
    if _segs_hit(ax, ay, bx, by, cx, cy, dx, dy):
        return 0.0
    return min(
        _point_seg_dist(ax, ay, cx, cy, dx, dy),
        _point_seg_dist(bx, by, cx, cy, dx, dy),
        _point_seg_dist(cx, cy, ax, ay, bx, by),
        _point_seg_dist(dx, dy, ax, ay, bx, by),
    )


def _copper_clear(board, points, width, netcode, layer, clearance=0.2):
    """None when clear, otherwise a short reason. SMD pads block F.Cu only."""
    half = width / 2.0
    segs = [(a, b) for a, b in zip(points, points[1:]) if a != b]
    if not segs and points:
        segs = [(points[0], points[0])]
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() == netcode:
                continue
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and layer != pcbnew.F_Cu:
                continue
            box = _world_box(pad)
            for (ax, ay), (bx, by) in segs:
                if _seg_hits_box(ax, ay, bx, by, box, half + clearance):
                    return f"{fp.GetReference()}.{pad.GetNumber() or 'NP'}"
    for tr in board.GetTracks():
        if tr.GetNetCode() == netcode:
            continue
        if tr.GetClass() == "PCB_VIA":
            cx, cy = to_mm(tr.GetPosition())
            vr = 0.3
            for (ax, ay), (bx, by) in segs:
                if _point_seg_dist(cx, cy, ax, ay, bx, by) < vr + half + clearance:
                    return "via"
            continue
        if tr.GetLayer() != layer:
            continue
        sx, sy = to_mm(tr.GetStart())
        ex, ey = to_mm(tr.GetEnd())
        other = pcbnew.ToMM(tr.GetWidth()) / 2.0
        for (ax, ay), (bx, by) in segs:
            if _seg_seg_dist(ax, ay, bx, by, sx, sy, ex, ey) < half + other + clearance:
                return (tr.GetNetname() or "track").lstrip("/")
    return None


def _commit_poly(board, points, width, layer, net):
    netcode = net.GetNetCode()
    if len(points) < 2:
        return 0
    reason = _copper_clear(board, points, width, netcode, layer)
    if reason:
        _commit_poly.last_reason = reason
        return 0
    _commit_poly.last_reason = ""
    n = 0
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        if abs(ax - bx) < 1e-4 and abs(ay - by) < 1e-4:
            continue
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(V(ax, ay))
        tr.SetEnd(V(bx, by))
        tr.SetWidth(MM(width))
        tr.SetLayer(layer)
        tr.SetNet(net)
        board.Add(tr)
        n += 1
    return n


def _commit_via(board, x, y, net, clearance=0.2):
    netcode = net.GetNetCode()
    if _copper_clear(board, [(x, y), (x, y)], 0.6, netcode, pcbnew.F_Cu, clearance):
        return None
    if _copper_clear(board, [(x, y), (x, y)], 0.6, netcode, pcbnew.B_Cu, clearance):
        return None
    return _add_via(board, V(x, y), net)


def route_critical(board) -> int:
    """Hand routes the autorouter cannot finish without shorting the USB-C pin row."""
    added = 0

    def poly(points, width, layer, net, tag):
        nonlocal added
        n = _commit_poly(board, points, width, layer, net)
        if n == 0:
            print(f"  skip {tag}: {getattr(_commit_poly, 'last_reason', '')}")
        else:
            added += n
        return n

    # --- J2 VBUS: tie the two pad columns on the board-edge side of the pin row ---
    a4 = _find_pad(board, "J2", "A4")
    a9 = _find_pad(board, "J2", "A9")
    f1 = _find_pad(board, "F1", "1")
    if a4 and a9 and f1 and a4.GetNetCode() == a9.GetNetCode():
        b4, b9 = _world_box(a4), _world_box(a9)
        # Drop on the side of each VBUS pad that clears the adjacent NPTH anchor.
        left_x = b4[2] - 0.06
        right_x = b9[0] + 0.06
        bus_y = max(b4[3], b9[3]) + 1.55
        net = a4.GetNet()
        if poly([(left_x, (b4[1] + b4[3]) / 2.0), (left_x, bus_y)], 0.20, pcbnew.F_Cu, net, "J2 VBUS left drop"):
            _commit_via(board, left_x, bus_y, net)
        if poly([(right_x, (b9[1] + b9[3]) / 2.0), (right_x, bus_y)], 0.20, pcbnew.F_Cu, net, "J2 VBUS right drop"):
            _commit_via(board, right_x, bus_y, net)
        poly([(left_x, bus_y), (right_x, bus_y)], 0.45, pcbnew.B_Cu, net, "J2 VBUS back tie")
        # Stay on the VBUS pad's own column until clear of the NC pin beside it.
        cx = (b4[0] + b4[2]) / 2.0
        cy = (b4[1] + b4[3]) / 2.0
        fx, fy = to_mm(f1.GetPosition())
        if poly([(cx, cy), (cx, cy - 2.2)], 0.35, pcbnew.F_Cu, net, "J2 VBUS escape"):
            poly([(cx, cy - 2.2), (fx, fy)], 0.60, pcbnew.F_Cu, net, "J2 VBUS to F1")

    # --- J2 CC1: leave the pin row toward the board edge, come up beside U0 ---
    a5 = _find_pad(board, "J2", "A5")
    u0_cc = _find_pad(board, "U0", "7")
    if a5 and u0_cc and a5.GetNetCode() == u0_cc.GetNetCode():
        ab = _world_box(a5)
        ub = _world_box(u0_cc)
        ax = (ab[0] + ab[2]) / 2.0
        ay = (ab[1] + ab[3]) / 2.0
        uy = (ub[1] + ub[3]) / 2.0
        via_y = ab[3] + 1.7
        side_x = ub[2] + 0.85
        net = a5.GetNet()
        if poly([(ax, ay), (ax, via_y)], 0.25, pcbnew.F_Cu, net, "CC1 drop"):
            if _commit_via(board, ax, via_y, net):
                poly(
                    [(ax, via_y), (13.0, via_y), (13.0, uy), (side_x, uy), (ub[2] + 0.15, uy)],
                    0.25,
                    pcbnew.B_Cu,
                    net,
                    "CC1 back",
                )
                # The last point is still on B.Cu. Rise beside the pin and finish on F.Cu.
                if _commit_via(board, side_x, uy, net):
                    poly([(side_x, uy), (ub[2], uy)], 0.25, pcbnew.F_Cu, net, "CC1 into U0")

    # --- CFG1: R23 now sits on the pin ---
    r23 = _find_pad(board, "R23", "1")
    u0_cfg = _find_pad(board, "U0", "9")
    if r23 and u0_cfg and r23.GetNetCode() == u0_cfg.GetNetCode():
        poly(
            [to_mm(u0_cfg.GetPosition()), to_mm(r23.GetPosition())],
            0.25,
            pcbnew.F_Cu,
            r23.GetNet(),
            "CFG1",
        )

    # --- J3 VBUS: tie both pads on the shell side, left of the NPTH anchors ---
    j3a4 = _find_pad(board, "J3", "A4")
    j3a9 = _find_pad(board, "J3", "A9")
    if j3a4 and j3a9 and j3a4.GetNetCode() == j3a9.GetNetCode():
        p4b, p9b = _world_box(j3a4), _world_box(j3a9)
        net = j3a4.GetNet()
        bus_x = p4b[0] - 2.3
        y_top = p4b[3] - 0.08
        y_bot = p9b[1] + 0.08
        if poly([(p4b[2] - 0.3, y_top), (bus_x, y_top)], 0.15, pcbnew.F_Cu, net, "J3 VBUS top stub"):
            _commit_via(board, bus_x, y_top, net)
        if poly([(p9b[2] - 0.3, y_bot), (bus_x, y_bot)], 0.15, pcbnew.F_Cu, net, "J3 VBUS bot stub"):
            _commit_via(board, bus_x, y_bot, net)
        poly([(bus_x, y_top), (bus_x, y_bot)], 0.40, pcbnew.B_Cu, net, "J3 VBUS edge tie")

    # --- +12V spine on the back, inboard of the screw terminals, up to P2 and P4 ---
    d1 = None
    for fp in board.GetFootprints():
        if fp.GetReference() != "D1":
            continue
        for pad in fp.Pads():
            if (pad.GetNetname() or "").lstrip("/") == "+12V":
                d1 = pad
    p2 = _find_pad(board, "P2", "1")
    p4 = _find_pad(board, "P4", "1")
    u1_12 = _find_pad(board, "U1", "3")
    if d1 and p2 and p4 and (d1.GetNetname() or "").lstrip("/") == "+12V":
        net = d1.GetNet()
        db = _world_box(d1)
        # Inboard of the screw pins and clear of J3's through-hole shell.
        spine_x = 9.2
        src_y = db[1] - 0.7
        sx = (db[0] + db[2]) / 2.0
        p2y = to_mm(p2.GetPosition())[1]
        p4y = to_mm(p4.GetPosition())[1]
        if poly([(sx, (db[1] + db[3]) / 2.0), (sx, src_y)], 0.60, pcbnew.F_Cu, net, "+12V leave D1"):
            if _commit_via(board, sx, src_y, net):
                poly([(sx, src_y), (spine_x, src_y), (spine_x, p2y)], 0.80, pcbnew.B_Cu, net, "+12V spine")
                poly([(spine_x, p2y), (to_mm(p2.GetPosition())[0], p2y)], 0.80, pcbnew.B_Cu, net, "+12V to P2")
                poly([(spine_x, p4y), (to_mm(p4.GetPosition())[0], p4y)], 0.80, pcbnew.B_Cu, net, "+12V to P4")
        if u1_12:
            ub = _world_box(u1_12)
            pad_x = (ub[0] + ub[2]) / 2.0
            pad_y = (ub[1] + ub[3]) / 2.0
            swpad = _find_pad(board, "U1", "2")
            sw_y = to_mm(swpad.GetPosition())[1] if swpad else pad_y + 1.0
            # Leave the pin on the side facing away from the switch pin.
            leave_y = ub[1] - 0.9 if sw_y > pad_y else ub[3] + 0.9
            if poly([(pad_x, pad_y), (pad_x, leave_y), (spine_x, leave_y)], 0.40, pcbnew.F_Cu, net, "+12V neck at U1"):
                _commit_via(board, spine_x, leave_y, net)

    # --- BUCK_SW: with U1 at 180° the switch pin faces L1, so this is a short straight run ---
    sw = _find_pad(board, "U1", "2")
    l1 = _find_pad(board, "L1", "1")
    if sw and l1 and sw.GetNetCode() == l1.GetNetCode():
        sb, lb = _world_box(sw), _world_box(l1)
        net = sw.GetNet()
        sx, sy = (sb[0] + sb[2]) / 2.0, (sb[1] + sb[3]) / 2.0
        lx, ly = (lb[0] + lb[2]) / 2.0, (lb[1] + lb[3]) / 2.0
        if sx < lx and abs(sy - ly) < 2.0:
            poly([(sx, sy), (lx, sy)], 0.50, pcbnew.F_Cu, net, "SW to L1")
        else:
            poly([(sx, sy), (lx, ly)], 0.40, pcbnew.F_Cu, net, "SW to L1")

    return added


def neck_12v_near_switch(board):
    """Keep the fat 12V copper off U1's switch pin. The spine itself is on the back."""
    sw = _find_pad(board, "U1", "2")
    if sw is None:
        return 0
    box = _world_box(sw)
    n = 0
    for tr in board.GetTracks():
        if tr.GetClass() != "PCB_TRACK":
            continue
        if (tr.GetNetname() or "").lstrip("/") != "+12V":
            continue
        if tr.GetLayer() != pcbnew.F_Cu:
            continue
        ax, ay = to_mm(tr.GetStart())
        bx, by = to_mm(tr.GetEnd())
        half = pcbnew.ToMM(tr.GetWidth()) / 2.0
        if _seg_hits_box(ax, ay, bx, by, box, half + 0.05) and half > 0.30:
            tr.SetWidth(MM(0.50))
            n += 1
    return n


def _add_track(board, start, end, width, layer, net):
    if start == end:
        return None
    tr = pcbnew.PCB_TRACK(board)
    tr.SetStart(start)
    tr.SetEnd(end)
    tr.SetWidth(width)
    tr.SetLayer(layer)
    tr.SetNet(net)
    board.Add(tr)
    return tr


def _add_via(board, pos, net, size_mm=0.6, drill_mm=0.3):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pos)
    via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetWidth(MM(size_mm))
    via.SetDrill(MM(drill_mm))
    via.SetNet(net)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    board.Add(via)
    return via


def try_bridge_short_rats(board, max_len_mm: float = 20.0) -> int:
    """Bridge remaining same-net pad pairs with straight / L / via-L routes."""
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

    def width_for(netname: str) -> int:
        floor = POWER_TRACK_WIDTH_MM.get((netname or "").lstrip("/"), 0.2)
        return MM(max(0.2, floor if floor else 0.2))

    def try_candidates(a, b, width):
        """Yield (items_added_list) candidate geometries; caller commits if helpful."""
        pa, pb = a.GetPosition(), b.GetPosition()
        net = a.GetNet()
        mid1 = pcbnew.VECTOR2I(pb.x, pa.y)
        mid2 = pcbnew.VECTOR2I(pa.x, pb.y)
        # 1) straight F
        yield [(_add_track, (board, pa, pb, width, pcbnew.F_Cu, net))]
        # 2) L on F (two elbows)
        yield [
            (_add_track, (board, pa, mid1, width, pcbnew.F_Cu, net)),
            (_add_track, (board, mid1, pb, width, pcbnew.F_Cu, net)),
        ]
        yield [
            (_add_track, (board, pa, mid2, width, pcbnew.F_Cu, net)),
            (_add_track, (board, mid2, pb, width, pcbnew.F_Cu, net)),
        ]
        # 3) via near A, B-side on back, via near B
        yield [
            (_add_via, (board, pa, net)),
            (_add_track, (board, pa, mid1, width, pcbnew.B_Cu, net)),
            (_add_track, (board, mid1, pb, width, pcbnew.B_Cu, net)),
            (_add_via, (board, pb, net)),
        ]
        yield [
            (_add_via, (board, pa, net)),
            (_add_track, (board, pa, mid2, width, pcbnew.B_Cu, net)),
            (_add_track, (board, mid2, pb, width, pcbnew.B_Cu, net)),
            (_add_via, (board, pb, net)),
        ]

    added = 0
    for net, pads in pads_by_net.items():
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
            width = width_for(net)
            improved = False
            for cand in try_candidates(a, b, width):
                items = []
                for fn, args in cand:
                    items.append(fn(*args))
                board.BuildConnectivity()
                nxt = board.GetConnectivity().GetUnconnectedCount(False)
                if nxt < cur:
                    added += 1
                    improved = True
                    break
                for it in items:
                    if it is not None:
                        board.Delete(it)
            if improved and board.GetConnectivity().GetUnconnectedCount(False) == 0:
                return added
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
    ant = u4_antenna_keepout(board)
    foreign = []
    for tr in board.GetTracks():
        if tr.GetNetCode() == gnd.GetNetCode():
            continue
        if tr.GetClass() == "PCB_VIA":
            foreign.append((to_mm(tr.GetPosition()), to_mm(tr.GetPosition()), 0.3))
        else:
            foreign.append((to_mm(tr.GetStart()), to_mm(tr.GetEnd()), pcbnew.ToMM(tr.GetWidth()) / 2.0))
    y = 1.5
    while y < H - 1.5:
        x = 2.0
        while x < W - 2.0:
            if ant and ant[0] - 0.5 <= x <= ant[2] + 0.5 and ant[1] <= y <= ant[3]:
                x += pitch
                continue
            if any(_point_seg_dist(x, y, a[0], a[1], b[0], b[1]) < 0.3 + half + 0.2 for a, b, half in foreign):
                x += pitch
                continue
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

    zip_path = os.path.join(FAB_DIR, "front-core-gerber.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn in sorted(os.listdir(gerber_dir)):
            zf.write(os.path.join(gerber_dir, fn), arcname=fn)

    # 2. JLCPCB BOM (SMD parts only, excluding DNP J1..J3, jumpers, mounting holes, testpoints)
    bom_path = os.path.join(FAB_DIR, "jlcpcb-bom.csv")
    subprocess.run([
        KCLI, "sch", "export", "bom",
        "--fields", "Value,Reference,Footprint,LCSC",
        "--labels", "Comment,Designator,Footprint,JLCPCB Part #",
        "--group-by", "Value,Footprint,LCSC",
        "--exclude-dnp",
        "--output", bom_path,
        SCH_PATH,
    ], check=True)

    # 3. JLCPCB CPL (Component Placement List)
    pos_raw = os.path.join(FAB_DIR, "pos-raw.csv")
    subprocess.run([
        KCLI, "pcb", "export", "pos",
        "--side", "front",
        "--format", "csv",
        "--units", "mm",
        "--smd-only",
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


def main():
    export_netlist()
    comps, net_map = parse_netlist()
    best = None  # (unrouted, W, H, path) — restored if no size reaches zero

    sizes = CANDIDATE_SIZES
    only = os.environ.get("FRONT_BOARD_SIZE", "").strip().lower()
    if only:
        w_s, h_s = only.split("x")
        sizes = [(float(w_s), float(h_s))]

    for W, H in sizes:
        print(f"Trying board size {W} x {H} mm...")
        try:
            board, net_items, fps = build_board(W, H, comps, net_map)
        except RuntimeError as e:
            print(f"  Placement skipped ({W}x{H}): {e}")
            continue

        # Save once so .kicad_pro netclasses apply before routing
        add_gnd_zone(board, net_items["GND"], pcbnew.B_Cu, W, H)
        pcbnew.SaveBoard(PCB_PATH, board)

        board = pcbnew.LoadBoard(PCB_PATH)
        pre = pre_route_power_nets(board)
        crit = route_critical(board)
        if pre or crit:
            print(f"  Pre-routed {pre} power segment(s), {crit} hand segment(s)")
            pcbnew.SaveBoard(PCB_PATH, board)
            board = pcbnew.LoadBoard(PCB_PATH)
        try:
            autoroute_headless_dialogfree(board)
        except RuntimeError as e:
            print(f"  Freerouting failed ({W}x{H}): {e}")
            continue
        widened = thicken_power_tracks(board)
        necked = neck_12v_near_switch(board)
        if widened or necked:
            print(f"  Widened {widened} power track segment(s), necked {necked} near U1 SW")
        add_gnd_zone(board, board.FindNet("GND"), pcbnew.F_Cu, W, H)
        pcbnew.SaveBoard(PCB_PATH, board)

        # Reload with project rules, fill zones, check unrouted count, add stitching vias
        board = pcbnew.LoadBoard(PCB_PATH)
        filler = pcbnew.ZONE_FILLER(board)
        filler.Fill(board.Zones())
        # Straight pad-to-pad bridges cross other nets (USB-C and the 12 V bus).
        # Leave residuals as ratsnest instead of painting shorts.
        vias = stitch_gnd_vias(board, W, H)
        filler.Fill(board.Zones())
        board.BuildConnectivity()
        unrouted = board.GetConnectivity().GetUnconnectedCount(False)
        print(f"  {W}x{H} mm -> unrouted: {unrouted} ({vias} GND vias)", flush=True)
        pcbnew.SaveBoard(PCB_PATH, board)
        if best is None or unrouted < best[0]:
            best_path = os.path.join(OUT_DIR, "best-board.kicad_pcb")
            shutil.copy2(PCB_PATH, best_path)
            best = (unrouted, W, H, best_path)
        if unrouted == 0:
            print(f"SUCCESS: Saved {PCB_PATH} ({W}x{H} mm, {vias} stitching vias)", flush=True)
            break
    else:
        if best is None:
            raise RuntimeError("All candidate sizes failed during placement")
        shutil.copy2(best[3], PCB_PATH)
        print(
            f"WARNING: residual unrouted nets "
            f"(best {best[0]} on {best[1]}x{best[2]} mm). "
            f"Restored that board to {PCB_PATH}.",
            flush=True,
        )

    export_jlcpcb_and_renders()


if __name__ == "__main__":
    main()
