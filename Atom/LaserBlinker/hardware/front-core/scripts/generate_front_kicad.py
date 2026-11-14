#!/usr/bin/env python3
"""
Generate complete KiCad 10 schematic & project for LaserBlinker Front All-in-One PCB:
  - hardware/front-core/front-core.kicad_pro
  - hardware/front-core/front-core.kicad_sch  (ERC 0 errors / 0 warnings, full PCBA BOM)
  - hardware/front-core/front-core.kicad_pcb  (Placeholder outline only — layout deferred)
"""

import copy
import json
import math
import os
import re
import uuid

SHARE = "/Applications/KiCad/KiCad.app/Contents/SharedSupport"
OUT_DIR = "/Volumes/Caches/Dropbox/gitbox/M5Stack/Atom/LaserBlinker/hardware/front-core"
PROJ = "front-core"


def u(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"laserblinker.frontcore.v1.{key}"))


def snap(val: float) -> float:
    v = round(val, 4)
    return 0.0 if abs(v) < 1e-6 else v


def fmt(val: float) -> str:
    s = f"{val:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


# ---------------------------------------------------------------------------
# S-expression parser & serializer
# ---------------------------------------------------------------------------

def parse_sexp(text: str):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()]+', text)
    stack = [[]]
    for tok in tokens:
        if tok == "(":
            lst = []
            stack[-1].append(lst)
            stack.append(lst)
        elif tok == ")":
            stack.pop()
        else:
            stack[-1].append(tok)
    return stack[0][0]


SINGLE_LINE_HEADS = {
    "at", "xy", "size", "offset", "start", "end", "mid", "pts", "color",
    "diameter", "width", "type", "hide", "bold", "italic", "justify",
    "length", "exclude_from_sim", "in_bom", "on_board", "in_pos_files",
    "dnp", "unit", "body_style", "embedded_fonts",
    "duplicate_pin_numbers_are_jumpers", "pin_numbers",
}


def dump_sexp(node, indent=0) -> str:
    if not isinstance(node, list):
        return str(node)
    if not node:
        return "()"
    head = node[0]
    if head in SINGLE_LINE_HEADS:
        inner = " ".join(dump_sexp(c, indent + 1) for c in node)
        return f"({inner})"
    tab = "\t" * indent
    parts = [f"({head}"]
    idx = 1
    while idx < len(node) and not isinstance(node[idx], list):
        parts[0] += f" {node[idx]}"
        idx += 1
    if idx == len(node):
        return parts[0] + ")"
    lines = [parts[0]]
    for child in node[idx:]:
        lines.append(f"{tab}\t{dump_sexp(child, indent + 1)}")
    lines.append(f"{tab})")
    return "\n".join(lines)


LIB_CACHE = {}


def load_flattened_symbol(lib: str, sym_name: str):
    if lib not in LIB_CACHE:
        LIB_CACHE[lib] = parse_sexp(open(f"{SHARE}/symbols/{lib}.kicad_sym").read())
    tree = LIB_CACHE[lib]
    syms = {
        item[1].strip('"'): item
        for item in tree[1:]
        if isinstance(item, list) and item[0] == "symbol"
    }
    raw = copy.deepcopy(syms[sym_name])
    ext = [x[1].strip('"') for x in raw if isinstance(x, list) and x[0] == "extends"]
    if ext:
        parent_name = ext[0]
        parent = copy.deepcopy(syms[parent_name])
        child_props = {
            x[1]: x for x in raw if isinstance(x, list) and x[0] == "property"
        }
        merged = ["symbol", f'"{lib}:{sym_name}"']
        for item in parent[2:]:
            if isinstance(item, list) and item[0] == "property" and item[1] in child_props:
                merged.append(child_props.pop(item[1]))
            elif isinstance(item, list) and item[0] == "symbol":
                sub = copy.deepcopy(item)
                sub_id = sub[1].strip('"')
                if sub_id.startswith(parent_name + "_"):
                    suffix = sub_id[len(parent_name):]
                    sub[1] = f'"{sym_name}{suffix}"'
                merged.append(sub)
            else:
                merged.append(item)
        for leftover in child_props.values():
            merged.insert(2, leftover)
        return merged
    else:
        raw[1] = f'"{lib}:{sym_name}"'
        return raw


def extract_symbol_pins(sym_tree):
    pins = []
    for sub in sym_tree:
        if isinstance(sub, list) and sub[0] == "symbol":
            for p in sub:
                if isinstance(p, list) and p[0] == "pin":
                    at = [x for x in p if isinstance(x, list) and x[0] == "at"][0]
                    nm = [x for x in p if isinstance(x, list) and x[0] == "name"][0][1].strip('"')
                    nu = [x for x in p if isinstance(x, list) and x[0] == "number"][0][1].strip('"')
                    pins.append((nu, nm, float(at[1]), float(at[2]), int(float(at[3])), p[1]))
    return pins


# ---------------------------------------------------------------------------
# Schematic Builder
# ---------------------------------------------------------------------------

class SchematicBuilder:
    def __init__(self):
        self.root_uuid = u("root_sheet")
        self.lib_symbols = {}
        self.symbols = []
        self.wires = []
        self.labels = []
        self.junctions = set()
        self.no_connects = []
        self.graphics = []
        self.pwr_idx = 1

    def ensure_lib(self, lib_id: str):
        if lib_id not in self.lib_symbols:
            lib, name = lib_id.split(":", 1)
            self.lib_symbols[lib_id] = load_flattened_symbol(lib, name)
        return self.lib_symbols[lib_id]

    def place(
        self,
        lib_id: str,
        ref: str,
        value: str,
        x: float,
        y: float,
        angle: int = 0,
        footprint: str = "",
        lcsc: str = "",
        mpn: str = "",
        dnp: bool = False,
        in_bom: bool = True,
        on_board: bool = True,
        ref_offset=(0.0, -5.08),
        val_offset=(0.0, 5.08),
    ):
        sym_tree = self.ensure_lib(lib_id)
        pins_local = extract_symbol_pins(sym_tree)
        sx, sy = snap(x), snap(y)
        rad = math.radians(angle)
        ca, sa = round(math.cos(rad)), round(math.sin(rad))

        pin_coords = {}
        pin_numbers = []
        for nu, nm, lx, ly, la, ptype in pins_local:
            rx = lx * ca - ly * sa
            ry = lx * sa + ly * ca
            px = snap(sx + rx)
            py = snap(sy - ry)
            pin_coords[nu] = (px, py)
            pin_numbers.append(nu)

        sym_uuid = u(f"sym.{ref}")
        rx_lbl = snap(sx + ref_offset[0])
        ry_lbl = snap(sy + ref_offset[1])
        vx_lbl = snap(sx + val_offset[0])
        vy_lbl = snap(sy + val_offset[1])

        props = [
            ["property", '"Reference"', f'"{ref}"', ["at", fmt(rx_lbl), fmt(ry_lbl), "0"],
             *( [["hide", "yes"]] if ref.startswith("#") else [] ),
             ["effects", ["font", ["size", "1.27", "1.27"]]]],
            ["property", '"Value"', f'"{value}"', ["at", fmt(vx_lbl), fmt(vy_lbl), "0"],
             *( [["hide", "yes"]] if ref.startswith("#FLG") else [] ),
             ["effects", ["font", ["size", "1.27", "1.27"]]]],
            ["property", '"Footprint"', f'"{footprint}"', ["at", fmt(sx), fmt(sy), "0"],
             ["hide", "yes"], ["effects", ["font", ["size", "1.27", "1.27"]]]],
            ["property", '"Datasheet"', '""', ["at", fmt(sx), fmt(sy), "0"],
             ["hide", "yes"], ["effects", ["font", ["size", "1.27", "1.27"]]]],
        ]
        if lcsc:
            props.append(
                ["property", '"LCSC"', f'"{lcsc}"', ["at", fmt(sx), fmt(sy), "0"],
                 ["hide", "yes"], ["effects", ["font", ["size", "1.27", "1.27"]]]]
            )
        if mpn:
            props.append(
                ["property", '"MPN"', f'"{mpn}"', ["at", fmt(sx), fmt(sy), "0"],
                 ["hide", "yes"], ["effects", ["font", ["size", "1.27", "1.27"]]]]
            )

        node = [
            "symbol",
            ["lib_id", f'"{lib_id}"'],
            ["at", fmt(sx), fmt(sy), str(angle)],
            ["unit", "1"],
            ["exclude_from_sim", "no"],
            ["in_bom", "yes" if in_bom else "no"],
            ["on_board", "yes" if on_board else "no"],
            ["dnp", "yes" if dnp else "no"],
            ["uuid", f'"{sym_uuid}"'],
        ] + props
        for nu in pin_numbers:
            node.append(["pin", f'"{nu}"', ["uuid", f'"{u(f"pin.{ref}.{nu}")}"']])
        node.append([
            "instances",
            ["project", f'"{PROJ}"',
             ["path", f'"/{self.root_uuid}"', ["reference", f'"{ref}"'], ["unit", "1"]]],
        ])
        self.symbols.append(node)
        return pin_coords

    def place_pwr(self, net_name: str, x: float, y: float, angle: int = 0):
        ref = f"#FLG{self.pwr_idx:03d}" if net_name == "PWR_FLAG" else f"#PWR{self.pwr_idx:03d}"
        self.pwr_idx += 1
        val_off = (0.0, 2.54) if net_name == "GND" else (0.0, -2.54)
        return self.place(
            f"power:{net_name}",
            ref,
            net_name,
            x,
            y,
            angle=angle,
            in_bom=False,
            on_board=False,
            val_offset=val_off,
        )

    def wire(self, x1: float, y1: float, x2: float, y2: float):
        x1, y1, x2, y2 = snap(x1), snap(y1), snap(x2), snap(y2)
        if x1 == x2 and y1 == y2:
            return
        idx = len(self.wires)
        self.wires.append([
            "wire",
            ["pts", ["xy", fmt(x1), fmt(y1)], ["xy", fmt(x2), fmt(y2)]],
            ["stroke", ["width", "0"], ["type", "default"]],
            ["uuid", f'"{u(f"wire.{idx}.{x1}.{y1}.{x2}.{y2}")}"'],
        ])

    def chain(self, *pts):
        for i in range(len(pts) - 1):
            self.wire(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])

    def junc(self, x: float, y: float):
        self.junctions.add((snap(x), snap(y)))

    def label(self, name: str, x: float, y: float, angle: int = 0):
        sx, sy = snap(x), snap(y)
        just = "left bottom" if angle in (0, 90) else "right bottom"
        idx = len(self.labels)
        self.labels.append([
            "label", f'"{name}"',
            ["at", fmt(sx), fmt(sy), str(angle)],
            ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", just]],
            ["uuid", f'"{u(f"lbl.{idx}.{name}.{sx}.{sy}")}"'],
        ])

    def stub(self, pin_xy, name: str, dx: float = -6.35):
        px, py = pin_xy
        tx = snap(px + dx)
        self.wire(px, py, tx, py)
        self.label(name, tx, py, angle=(180 if dx < 0 else 0))
        return (tx, py)

    def gnd_at(self, pin_xy, dy: float = 3.81):
        px, py = pin_xy
        gy = snap(py + dy)
        self.wire(px, py, px, gy)
        self.place_pwr("GND", px, gy, angle=0)

    def rail_at(self, pin_xy, rail: str, dy: float = -3.81):
        px, py = pin_xy
        ry = snap(py + dy)
        self.wire(px, py, px, ry)
        self.place_pwr(rail, px, ry, angle=0)

    def nc(self, pin_xy):
        px, py = pin_xy
        idx = len(self.no_connects)
        self.no_connects.append([
            "no_connect",
            ["at", fmt(px), fmt(py)],
            ["uuid", f'"{u(f"nc.{idx}.{px}.{py}")}"'],
        ])

    def box(self, title: str, x1: float, y1: float, x2: float, y2: float):
        idx = len(self.graphics)
        self.graphics.append([
            "rectangle",
            ["start", fmt(x1), fmt(y1)],
            ["end", fmt(x2), fmt(y2)],
            ["stroke", ["width", "0.15"], ["type", "dash"], ["color", "130", "130", "130", "1"]],
            ["fill", ["type", "none"]],
            ["uuid", f'"{u(f"rect.{idx}")}"'],
        ])
        self.graphics.append([
            "text", f'"{title}"',
            ["exclude_from_sim", "no"],
            ["at", fmt(x1 + 2.54), fmt(y1 + 5.08), "0"],
            ["effects", ["font", ["size", "2.032", "2.032"], ["bold", "yes"]], ["justify", "left bottom"]],
            ["uuid", f'"{u(f"txt.{idx}")}"'],
        ])

    def build_sexp(self) -> str:
        lib_node = ["lib_symbols"] + list(self.lib_symbols.values())
        junc_nodes = [
            ["junction", ["at", fmt(jx), fmt(jy)], ["diameter", "0"], ["color", "0", "0", "0", "0"],
             ["uuid", f'"{u(f"junc.{jx}.{jy}")}"']]
            for (jx, jy) in sorted(self.junctions)
        ]
        root = [
            "kicad_sch",
            ["version", "20250901"],
            ["generator", '"eeschema"'],
            ["generator_version", '"10.0"'],
            ["uuid", f'"{self.root_uuid}"'],
            ["paper", '"A2"'],
            [
                "title_block",
                ["title", '"LaserBlinker Front All-in-One Master PCB"'],
                ["date", '"2026-11-12"'],
                ["rev", '"v1.0"'],
                ["comment", "1", '"MCU: ESP32-S3-MINI-1-N8 | USB-PD 12V Sink: CH224K | Buzzer: MLT-8530"'],
                ["comment", "2", '"Trunk: CAT5 RJ45 (Passive PoE + Bidirectional RS-485) | Navi: Grove HY2.0-4P"'],
                ["comment", "3", '"Full JLCPCB PCBA (SMD + THT Connectors Populated, Zero Hand-Soldering)"'],
            ],
            lib_node,
        ]
        root.extend(self.graphics)
        root.extend(junc_nodes)
        root.extend(self.no_connects)
        root.extend(self.wires)
        root.extend(self.labels)
        root.extend(self.symbols)
        root.append(["sheet_instances", ["path", '"/"', ["page", '"1"']]])
        root.append(["embedded_fonts", "no"])
        return dump_sexp(root, indent=0) + "\n"


# ---------------------------------------------------------------------------
# Build Front Unit Full Schematic (A2: 594 x 420 mm)
# ---------------------------------------------------------------------------

def build_schematic():
    sb = SchematicBuilder()

    FP_R0603 = "Resistor_SMD:R_0603_1608Metric"
    FP_R0805 = "Resistor_SMD:R_0805_2012Metric"
    FP_C0603 = "Capacitor_SMD:C_0603_1608Metric"
    FP_C0805 = "Capacitor_SMD:C_0805_2012Metric"
    FP_C1206 = "Capacitor_SMD:C_1206_3216Metric"
    FP_SOD123 = "Diode_SMD:D_SOD-123"
    FP_TB35_2P = "TerminalBlock_4Ucon:TerminalBlock_4Ucon_1x02_P3.50mm_Horizontal"
    FP_TB254_2P = "TerminalBlock:TerminalBlock_Xinya_XY308-2.54-2P_1x02_P2.54mm_Horizontal"
    FP_TB254_3P = "TerminalBlock:TerminalBlock_Xinya_XY308-2.54-3P_1x03_P2.54mm_Horizontal"

    # =======================================================================
    # BLOCK 1: USB-PD 12V Sink (J_PWR + CH224K + 3A Polyfuse + SS34 -> +12V)
    #          (Top-Left: x=15.24..238.76, y=15.24..134.62)
    # =======================================================================
    sb.box("1. USB-PD 12V Power Input (USB_PWR + CH224K -> +12V Bus)", 15.24, 15.24, 238.76, 134.62)

    # J_PWR: USB Type-C Power Input (NO 5.1k on CC1/CC2 — CH224K handles CC negotiation!)
    jpwr = sb.place(
        "Connector:USB_C_Receptacle_USB2.0_16P", "J2", "USB_PWR_12V_PD", 38.10, 78.74, angle=0,
        footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        lcsc="C165948", mpn="TYPE-C-31-M-12",
        ref_offset=(-5.08, -24.13), val_offset=(-5.08, -21.59),
    )
    sb.gnd_at(jpwr["A1"], dy=5.08)
    sb.gnd_at(jpwr["SH"], dy=5.08)
    sb.nc(jpwr["A8"])
    sb.nc(jpwr["B8"])
    # GND global PWR_FLAG right next to J_PWR GND
    sb.junc(jpwr["A1"][0], jpwr["A1"][1] + 2.54)
    sb.wire(jpwr["A1"][0], jpwr["A1"][1] + 2.54, jpwr["A1"][0] + 6.35, jpwr["A1"][1] + 2.54)
    sb.place_pwr("PWR_FLAG", jpwr["A1"][0] + 6.35, jpwr["A1"][1] + 2.54)

    # U0: CH224K at (119.38, 78.74)
    # Local pins:
    #   1 VDD=(+2.54, +10.16)->(121.92, 68.58)
    #   8 VBUS=(0, +10.16)->(119.38, 68.58)
    #   7 CC1=(-10.16, +5.08)->(109.22, 73.66)
    #   6 CC2=(-10.16, +2.54)->(109.22, 76.20)
    #   5 DM=(-10.16, -2.54)->(109.22, 81.28)
    #   4 DP=(-10.16, -5.08)->(109.22, 83.82)
    #   10 PG=(+10.16, +5.08)->(129.54, 73.66)
    #   9 CFG1=(+10.16, 0)->(129.54, 78.74)
    #   2 CFG2=(+10.16, -2.54)->(129.54, 81.28)
    #   3 CFG3=(+10.16, -5.08)->(129.54, 83.82)
    #   11 GND=(0, -10.16)->(119.38, 88.90)
    u0 = sb.place(
        "Interface_USB:CH224K", "U0", "CH224K", 119.38, 78.74, angle=0,
        footprint="Package_SO:SSOP-10-1EP_3.9x4.9mm_P1mm_EP2.1x3.3mm",
        lcsc="C970725", mpn="CH224K",
        ref_offset=(-8.89, -12.70), val_offset=(-8.89, -10.16),
    )
    sb.gnd_at(u0["11"], dy=5.08)
    sb.nc(u0["2"])
    sb.nc(u0["3"])

    # Wire CC1 (A5: 53.34, 68.58 -> U0.7: 109.22, 73.66) & CC2 (B5: 53.34, 71.12 -> U0.6: 109.22, 76.20)
    sb.chain(jpwr["A5"], (83.82, jpwr["A5"][1]), (83.82, u0["7"][1]), u0["7"])
    sb.chain(jpwr["B5"], (80.01, jpwr["B5"][1]), (80.01, u0["6"][1]), u0["6"])

    # Wire D- (A7: 53.34, 76.20 & B7: 53.34, 78.74 -> U0.5: 109.22, 81.28)
    sb.chain(jpwr["A7"], (60.96, jpwr["A7"][1]), (60.96, jpwr["B7"][1]), jpwr["B7"])
    sb.junc(60.96, jpwr["B7"][1])
    sb.chain((60.96, jpwr["B7"][1]), (76.20, jpwr["B7"][1]), (76.20, u0["5"][1]), u0["5"])

    # Wire D+ (A6: 53.34, 81.28 & B6: 53.34, 83.82 -> U0.4: 109.22, 83.82)
    sb.chain(jpwr["A6"], (60.96, jpwr["A6"][1]), (60.96, jpwr["B6"][1]), jpwr["B6"])
    sb.junc(60.96, jpwr["B6"][1])
    sb.wire(60.96, jpwr["B6"][1], *u0["4"])

    # VBUS_PD bus at y=35.56 from J_PWR VBUS (53.34, 63.50) -> F1 -> D1 -> +12V
    sb.chain(jpwr["A4"], (68.58, jpwr["A4"][1]), (68.58, 35.56), (177.80, 35.56))
    sb.label("VBUS_PD", 152.40, 35.56, angle=0)

    # R_VBUS (R21: 10k) to U0.8 (VBUS sense at x=119.38)
    r21 = sb.place(
        "Device:R", "R21", "10k", 111.76, 48.26, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(-5.08, -1.905), val_offset=(-5.08, 1.905),
    )
    sb.junc(111.76, 35.56)
    sb.wire(111.76, 35.56, *r21["1"])
    sb.chain(r21["2"], (111.76, 60.96), (u0["8"][0], 60.96), u0["8"])

    # R_VDD (R22: 1k 0805) to U0.1 (VDD at x=121.92, y=68.58) + C18 (1uF/25V) + PWR_FLAG
    r22 = sb.place(
        "Device:R", "R22", "1k_0805", 127.00, 48.26, angle=0,
        footprint=FP_R0805, lcsc="C17513", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.junc(127.00, 35.56)
    sb.wire(127.00, 35.56, *r22["1"])
    sb.chain(r22["2"], (127.00, 58.42), (u0["1"][0], 58.42), u0["1"])
    sb.junc(127.00, 58.42)
    sb.wire(127.00, 58.42, 144.78, 58.42)
    sb.junc(135.89, 58.42)
    sb.wire(135.89, 58.42, 135.89, 53.34)
    sb.place_pwr("PWR_FLAG", 135.89, 53.34)

    c18 = sb.place(
        "Device:C", "C18", "1uF/25V", 144.78, 66.04, angle=0,
        footprint=FP_C0603, lcsc="C15849", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.wire(144.78, 58.42, *c18["1"])
    sb.gnd_at(c18["2"], dy=2.54)

    # CFG1 (Pin 9): R23 = 24k 1% to GND -> Requests fixed 12V PD
    r23 = sb.place(
        "Device:R", "R23", "24k_1%", 142.24, 91.44, angle=0,
        footprint=FP_R0603, lcsc="C23350", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.chain(u0["9"], (142.24, u0["9"][1]), r23["1"])
    sb.gnd_at(r23["2"], dy=3.81)

    # PG (Pin 10): 12V Power Good Green Indicator (+12V -> 4.7k R24 -> D9 Green LED -> PG)
    d9 = sb.place(
        "Device:LED", "D9", "PG_GREEN", 162.56, u0["10"][1], angle=0,
        footprint="LED_SMD:LED_0603_1608Metric", lcsc="C72043",
        ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    r24 = sb.place(
        "Device:R", "R24", "4.7k", 177.80, u0["10"][1], angle=90,
        footprint=FP_R0603, lcsc="C23162", ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.wire(*u0["10"], *d9["1"])
    sb.wire(*d9["2"], *r24["1"])
    sb.chain(r24["2"], (187.96, u0["10"][1]), (187.96, 68.58))
    sb.place_pwr("+12V", 187.96, 68.58)

    # Main 3A Polyfuse F1 + SS34 Reverse/Backfeed Schottky D1 -> +12V Bus
    f1 = sb.place(
        "Device:Polyfuse", "F1", "3A_1812", 181.61, 35.56, angle=90,
        footprint="Fuse:Fuse_1812_4532Metric", lcsc="C70069",
        ref_offset=(0, -5.08), val_offset=(0, 5.08),
    )
    d1 = sb.place(
        "Diode:SS34", "D1", "SS34", 198.12, 35.56, angle=180,
        footprint="Diode_SMD:D_SMA", lcsc="C8678", mpn="SS34",
        ref_offset=(0, -5.08), val_offset=(0, 5.08),
    )
    sb.wire(*f1["2"], *d1["2"])
    sb.label("V12_FUSED", (f1["2"][0] + d1["2"][0]) / 2.0, f1["2"][1], angle=0)
    sb.wire(*d1["1"], 226.06, 35.56)
    sb.junc(213.36, 35.56)
    sb.rail_at((213.36, 35.56), "+12V", dy=-5.08)
    sb.wire(226.06, 35.56, 226.06, 27.94)
    sb.place_pwr("PWR_FLAG", 226.06, 27.94)

    # =======================================================================
    # BLOCK 2: Power Regulation (12V -> 5V 3A Buck + USB/5V OR + 3.3V LDO)
    #          (Top-Right: x=243.84..579.12, y=15.24..134.62)
    # =======================================================================
    sb.box("2. Power Regulation (12V->5V 3A Buck + USB/5V OR + 3.3V LDO)", 243.84, 15.24, 579.12, 134.62)

    # +12V rail into Buck Input + SMAJ15A TVS + C1/C2/C3
    sb.wire(259.08, 45.72, 325.12, 45.72)
    sb.rail_at((259.08, 45.72), "+12V", dy=-5.08)

    d6 = sb.place(
        "Diode:SMAJ15A", "D6", "SMAJ15A", 269.24, 60.96, angle=270,
        footprint="Diode_SMD:D_SMA", lcsc="C123805", mpn="SMAJ15A",
        ref_offset=(4.45, -1.905), val_offset=(4.45, 1.905),
    )
    sb.junc(269.24, 45.72)
    sb.wire(269.24, 45.72, *d6["1"])
    sb.gnd_at(d6["2"], dy=5.08)

    for cref, cval, cfp, clcsc, cx in [
        ("C1", "22uF/25V", FP_C1206, "C12891", 284.48),
        ("C2", "22uF/25V", FP_C1206, "C12891", 297.18),
        ("C3", "100nF/50V", FP_C0603, "C14663", 309.88),
    ]:
        c = sb.place(
            "Device:C", cref, cval, cx, 60.96, angle=0,
            footprint=cfp, lcsc=clcsc, ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
        )
        sb.junc(cx, 45.72)
        sb.wire(cx, 45.72, *c["1"])
        sb.gnd_at(c["2"], dy=5.08)

    # U1: TPS54302DDCR (EN left floating per TI datasheet 7V abs max!)
    u1 = sb.place(
        "Regulator_Switching:TPS54302", "U1", "TPS54302DDCR", 335.28, 48.26, angle=0,
        footprint="Package_TO_SOT_SMD:SOT-23-6", lcsc="C311038", mpn="TPS54302DDCR",
        ref_offset=(0, -8.89), val_offset=(0, -6.35),
    )
    sb.nc(u1["5"])
    sb.gnd_at(u1["1"], dy=13.97)

    c4 = sb.place(
        "Device:C", "C4", "100nF/25V", 355.60, 38.10, angle=90,
        footprint=FP_C0603, lcsc="C14663", ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.chain(u1["6"], (347.98, 45.72), (347.98, 38.10), c4["1"])
    sb.chain(c4["2"], (361.95, 38.10), (361.95, 48.26))
    sb.junc(361.95, 48.26)

    l1 = sb.place(
        "Device:L", "L1", "4.7uH/4.5A", 370.84, 48.26, angle=90,
        footprint="Inductor_SMD:L_6.3x6.3_H3", lcsc="C408412",
        ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.wire(*u1["2"], *l1["1"])
    sb.label("BUCK_SW", (u1["2"][0] + l1["1"][0]) / 2.0, u1["2"][1], angle=0)
    sb.wire(*l1["2"], 439.42, 48.26)

    r1 = sb.place(
        "Device:R", "R1", "75k_1%", 383.54, 60.96, angle=0,
        footprint=FP_R0603, lcsc="C23240", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    r2 = sb.place(
        "Device:R", "R2", "10k_1%", 383.54, 78.74, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.junc(383.54, 48.26)
    sb.wire(383.54, 48.26, *r1["1"])
    sb.wire(*r1["2"], *r2["1"])
    sb.junc(383.54, 69.85)
    sb.chain(u1["4"], (350.52, 50.80), (350.52, 69.85), (383.54, 69.85))
    sb.gnd_at(r2["2"], dy=3.81)

    sb.junc(391.16, 48.26)
    sb.rail_at((391.16, 48.26), "+5V", dy=-5.08)
    sb.junc(397.51, 48.26)
    sb.wire(397.51, 48.26, 397.51, 40.64)
    sb.place_pwr("PWR_FLAG", 397.51, 40.64)

    for cref, cval, cfp, clcsc, cx in [
        ("C5", "22uF/10V", FP_C0805, "C45783", 406.40),
        ("C6", "22uF/10V", FP_C0805, "C45783", 417.83),
    ]:
        c = sb.place(
            "Device:C", cref, cval, cx, 63.50, angle=0,
            footprint=cfp, lcsc=clcsc, ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
        )
        sb.junc(cx, 48.26)
        sb.wire(cx, 48.26, *c["1"])
        sb.gnd_at(c["2"], dy=5.08)

    c7 = sb.place(
        "Device:C_Polarized", "C7", "220uF/10V", 430.53, 63.50, angle=0,
        footprint="Capacitor_SMD:CP_Elec_6.3x7.7", lcsc="C128268",
        ref_offset=(4.45, -1.905), val_offset=(4.45, 1.905),
    )
    sb.junc(430.53, 48.26)
    sb.wire(430.53, 48.26, *c7["1"])
    sb.gnd_at(c7["2"], dy=5.08)

    # Dual Schottky OR-ing (+5V and VBUS_DBG -> V5_LOGIC)
    d2 = sb.place(
        "Diode:1N5819WS", "D2", "B5819W", 443.23, 48.26, angle=180,
        footprint=FP_SOD123, lcsc="C8598", mpn="B5819W",
        ref_offset=(0, -4.45), val_offset=(0, 4.45),
    )
    d3 = sb.place(
        "Diode:1N5819WS", "D3", "B5819W", 443.23, 63.50, angle=180,
        footprint=FP_SOD123, lcsc="C8598", mpn="B5819W",
        ref_offset=(0, -4.45), val_offset=(0, 4.45),
    )
    sb.chain(d3["2"], (435.61, 63.50), (435.61, 58.42))
    sb.place_pwr("VBUS", 435.61, 58.42)

    u2 = sb.place(
        "Regulator_Linear:AP2112K-3.3", "U2", "AP2112K-3.3", 495.30, 50.80, angle=0,
        footprint="Package_TO_SOT_SMD:SOT-23-5", lcsc="C51118", mpn="AP2112K-3.3TRG1",
        ref_offset=(0, -8.89), val_offset=(0, -6.35),
    )
    sb.wire(*d2["1"], *u2["1"])
    sb.chain(d3["1"], (452.12, 63.50), (452.12, 48.26))
    sb.junc(452.12, 48.26)
    sb.label("V5_LOGIC", 454.66, 48.26, angle=0)
    sb.wire(452.12, 48.26, 452.12, 40.64)
    sb.place_pwr("PWR_FLAG", 452.12, 40.64)

    for cref, cval, clcsc, cx in [
        ("C8", "1uF", "C15849", 464.82),
        ("C9", "10uF", "C19702", 476.25),
    ]:
        c = sb.place(
            "Device:C", cref, cval, cx, 63.50, angle=0,
            footprint=FP_C0603, lcsc=clcsc, ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
        )
        sb.junc(cx, 48.26)
        sb.wire(cx, 48.26, *c["1"])
        sb.gnd_at(c["2"], dy=5.08)

    sb.chain((483.87, 48.26), (483.87, 50.80), u2["3"])
    sb.junc(483.87, 48.26)
    sb.nc(u2["4"])
    sb.gnd_at(u2["2"], dy=10.16)

    sb.wire(*u2["5"], 546.10, 48.26)
    sb.junc(515.62, 48.26)
    sb.rail_at((515.62, 48.26), "+3V3", dy=-5.08)

    for cref, cval, clcsc, cx in [
        ("C10", "10uF", "C19702", 528.32),
        ("C11", "100nF", "C14663", 546.10),
    ]:
        c = sb.place(
            "Device:C", cref, cval, cx, 63.50, angle=0,
            footprint=FP_C0603, lcsc=clcsc, ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
        )
        if cx < 546.10:
            sb.junc(cx, 48.26)
        sb.wire(cx, 48.26, *c["1"])
        sb.gnd_at(c["2"], dy=5.08)

    # =======================================================================
    # BLOCK 3: MCU Debug USB-C + ESD Protection (Middle-Left: x=15.24..167.64, y=142.24..259.08)
    # =======================================================================
    sb.box("3. MCU Debug USB-C (USB_DBG + ESD)", 15.24, 142.24, 167.64, 259.08)

    jdbg = sb.place(
        "Connector:USB_C_Receptacle_USB2.0_16P", "J3", "USB_DBG_PC", 40.64, 200.66, angle=0,
        footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        lcsc="C165948", mpn="TYPE-C-31-M-12",
        ref_offset=(-5.08, -24.13), val_offset=(-5.08, -21.59),
    )
    sb.wire(*jdbg["A4"], 106.68, jdbg["A4"][1])
    sb.rail_at((78.74, jdbg["A4"][1]), "VBUS", dy=-5.08)
    sb.junc(78.74, jdbg["A4"][1])
    sb.wire(88.90, jdbg["A4"][1], 88.90, jdbg["A4"][1] - 5.08)
    sb.junc(88.90, jdbg["A4"][1])
    sb.place_pwr("PWR_FLAG", 88.90, jdbg["A4"][1] - 5.08)

    r3 = sb.place(
        "Device:R", "R3", "5.1k", 76.20, 238.76, angle=0,
        footprint=FP_R0603, lcsc="C23186", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    r4 = sb.place(
        "Device:R", "R4", "5.1k", 66.04, 238.76, angle=0,
        footprint=FP_R0603, lcsc="C23186", ref_offset=(-5.08, -1.905), val_offset=(-5.08, 1.905),
    )
    sb.chain(jdbg["A5"], (76.20, jdbg["A5"][1]), r3["1"])
    sb.chain(jdbg["B5"], (66.04, jdbg["B5"][1]), r4["1"])
    sb.gnd_at(r3["2"], dy=3.81)
    sb.gnd_at(r4["2"], dy=3.81)

    u7 = sb.place(
        "Power_Protection:USBLC6-2SC6", "U7", "USBLC6-2SC6", 106.68, 200.66, angle=0,
        footprint="Package_TO_SOT_SMD:SOT-23-6", lcsc="C7519", mpn="USBLC6-2SC6",
        ref_offset=(0, -8.89), val_offset=(0, -6.35),
    )
    sb.wire(106.68, jdbg["A4"][1], *u7["5"])
    sb.gnd_at(u7["2"], dy=5.08)

    sb.chain(jdbg["A7"], (60.96, jdbg["A7"][1]), (60.96, jdbg["B7"][1]), jdbg["B7"])
    sb.junc(60.96, jdbg["B7"][1])
    sb.wire(60.96, jdbg["B7"][1], *u7["1"])
    sb.stub(u7["6"], "USB_DN", dx=12.70)

    sb.chain(jdbg["A6"], (60.96, jdbg["A6"][1]), (60.96, jdbg["B6"][1]), jdbg["B6"])
    sb.junc(60.96, jdbg["A6"][1])
    sb.wire(60.96, jdbg["A6"][1], *u7["3"])
    sb.stub(u7["4"], "USB_DP", dx=12.70)

    sb.nc(jdbg["A8"])
    sb.nc(jdbg["B8"])
    sb.gnd_at(jdbg["A1"], dy=5.08)
    sb.gnd_at(jdbg["SH"], dy=5.08)

    # =======================================================================
    # BLOCK 4: Handlebar Switches (RC Debounce + ESD Filter) & Mounting
    #          (Bottom-Left: x=15.24..167.64, y=264.16..403.86)
    # =======================================================================
    sb.box("4. Handlebar Switches (RC Filter) & M2 Mounting", 15.24, 264.16, 167.64, 403.86)

    # S1: Left Turn SW 2P / S5: Right Turn SW 2P (split for left/right board edges)
    s1 = sb.place(
        "Connector_Generic:Conn_01x02", "S1", "SW_TURN_L_2P", 30.48, 284.48, angle=180,
        footprint=FP_TB254_2P, lcsc="C557685", mpn="XY308-2.54-2P",
        dnp=False, ref_offset=(-2.54, -6.35), val_offset=(-2.54, 5.08),
    )
    sb.gnd_at(s1["1"], dy=5.08)

    s5 = sb.place(
        "Connector_Generic:Conn_01x02", "S5", "SW_TURN_R_2P", 30.48, 309.88, angle=180,
        footprint=FP_TB254_2P, lcsc="C557685", mpn="XY308-2.54-2P",
        dnp=False, ref_offset=(-2.54, -6.35), val_offset=(-2.54, 5.08),
    )
    sb.gnd_at(s5["1"], dy=5.08)

    # S2: Left Brake Micro-SW 2P at angle=180 (2=top, 1=bot)
    s2 = sb.place(
        "Connector_Generic:Conn_01x02", "S2", "SW_BRAKE_L_2P", 30.48, 335.28, angle=180,
        footprint=FP_TB254_2P, lcsc="C557685", mpn="XY308-2.54-2P",
        dnp=False, ref_offset=(-2.54, -6.35), val_offset=(-2.54, 5.08),
    )
    sb.gnd_at(s2["1"], dy=5.08)

    # S3: Right Brake Micro-SW 2P at angle=180 (2=top, 1=bot)
    s3 = sb.place(
        "Connector_Generic:Conn_01x02", "S3", "SW_BRAKE_R_2P", 30.48, 365.76, angle=180,
        footprint=FP_TB254_2P, lcsc="C557685", mpn="XY308-2.54-2P",
        dnp=False, ref_offset=(-2.54, -6.35), val_offset=(-2.54, 5.08),
    )
    sb.gnd_at(s3["1"], dy=5.08)

    # 4-channel Input Protection: 10k pull-up to +3V3 + 1k series + 100nF to GND
    sw_channels = [
        (s5["2"], "SW_TURN_R", "R25", "R26", "C19", 284.48, 63.50),
        (s1["2"], "SW_TURN_L", "R27", "R28", "C20", 307.34, 73.66),
        (s2["2"], "SW_BRAKE_L", "R29", "R30", "C21", 332.74, 63.50),
        (s3["2"], "SW_BRAKE_R", "R31", "R32", "C22", 363.22, 63.50),
    ]
    for src_pin, net_lbl, rpu_ref, rser_ref, cap_ref, row_y, turn_x in sw_channels:
        sb.chain(src_pin, (turn_x, src_pin[1]), (turn_x, row_y), (86.36, row_y))
        rpu = sb.place(
            "Device:R", rpu_ref, "10k", 86.36, row_y - 7.62, angle=0,
            footprint=FP_R0603, lcsc="C25804", ref_offset=(-4.45, -1.27), val_offset=(-4.45, 1.27),
        )
        sb.rail_at(rpu["1"], "+3V3", dy=-2.54)
        sb.wire(*rpu["2"], 86.36, row_y)
        sb.junc(86.36, row_y)

        rser = sb.place(
            "Device:R", rser_ref, "1k", 101.60, row_y, angle=90,
            footprint=FP_R0603, lcsc="C21190", ref_offset=(0, -3.175), val_offset=(0, 3.175),
        )
        sb.wire(86.36, row_y, *rser["1"])
        sb.wire(*rser["2"], 134.62, row_y)
        sb.label(net_lbl, 134.62, row_y, angle=0)

        cf = sb.place(
            "Device:C", cap_ref, "100nF", 119.38, row_y + 6.35, angle=0,
            footprint=FP_C0603, lcsc="C14663", ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
        )
        sb.junc(119.38, row_y)
        sb.wire(119.38, row_y, *cf["1"])
        sb.gnd_at(cf["2"], dy=2.54)

    # M2 Grounded Mounting Holes H1..H4
    for idx, hx in enumerate([27.94, 48.26, 68.58, 88.90], start=1):
        h = sb.place(
            "Mechanical:MountingHole_Pad", f"H{idx}", "M2", hx, 391.16, angle=0,
            footprint="MountingHole:MountingHole_2.2mm_M2_Pad_Via",
            in_bom=False, ref_offset=(0, -5.08), val_offset=(0, -2.54),
        )
        sb.gnd_at(h["1"], dy=3.81)

    # =======================================================================
    # BLOCK 5: MCU (ESP32-S3-MINI-1-N8), 12V ADC Monitor & Onboard Buzzer
    #          (Center: x=175.26..365.76, y=142.24..403.86)
    # =======================================================================
    sb.box("5. MCU (ESP32-S3-MINI-1-N8), 12V Monitor & Buzzer", 175.26, 142.24, 365.76, 403.86)

    u4 = sb.place(
        "RF_Module:ESP32-S3-MINI-1", "U4", "ESP32-S3-MINI-1-N8", 274.32, 236.22, angle=0,
        footprint="RF_Module:ESP32-S2-MINI-1", lcsc="C2913206", mpn="ESP32-S3-MINI-1-N8",
        ref_offset=(-8.89, -31.75), val_offset=(6.35, -31.75),
    )

    sb.wire(*u4["3"], u4["3"][0], 195.58)
    sb.rail_at((u4["3"][0], 195.58), "+3V3", dy=-3.81)
    sb.junc(u4["3"][0], 198.12)
    sb.wire(u4["3"][0], 198.12, 322.58, 198.12)
    for cref, cval, clcsc, cx in [
        ("C12", "10uF", "C19702", 309.88),
        ("C13", "100nF", "C14663", 322.58),
    ]:
        c = sb.place(
            "Device:C", cref, cval, cx, 204.47, angle=0,
            footprint=FP_C0603, lcsc=clcsc, ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
        )
        if cx < 322.58:
            sb.junc(cx, 198.12)
        sb.wire(cx, 198.12, *c["1"])
        sb.gnd_at(c["2"], dy=2.54)

    sb.gnd_at(u4["1"], dy=5.08)

    r5 = sb.place(
        "Device:R", "R5", "10k", 218.44, 198.12, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.rail_at(r5["1"], "+3V3", dy=-3.81)
    sb.chain(r5["2"], (218.44, u4["45"][1]), u4["45"])
    sb.junc(218.44, u4["45"][1])

    c14 = sb.place(
        "Device:C", "C14", "1uF", 218.44, 220.98, angle=0,
        footprint=FP_C0603, lcsc="C15849", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.wire(218.44, u4["45"][1], *c14["1"])
    sb.gnd_at(c14["2"], dy=2.54)

    sw1 = sb.place(
        "Switch:SW_Push", "SW1", "RST", 198.12, u4["45"][1], angle=0,
        footprint="Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", lcsc="C318884",
        ref_offset=(0, -5.08), val_offset=(0, 5.08),
    )
    sb.wire(*sw1["2"], 218.44, u4["45"][1])
    sb.chain(sw1["1"], (185.42, u4["45"][1]), (185.42, u4["45"][1] + 6.35))
    sb.place_pwr("GND", 185.42, u4["45"][1] + 6.35)

    sb.chain(u4["4"], (236.22, u4["4"][1]), (236.22, 170.18), (205.74, 170.18))
    sb.junc(236.22, 170.18)
    r6 = sb.place(
        "Device:R", "R6", "10k", 236.22, 160.02, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.rail_at(r6["1"], "+3V3", dy=-2.54)
    sb.wire(*r6["2"], 236.22, 170.18)

    sw2 = sb.place(
        "Switch:SW_Push", "SW2", "BOOT", 198.12, 170.18, angle=0,
        footprint="Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", lcsc="C318884",
        ref_offset=(0, -5.08), val_offset=(0, 5.08),
    )
    sb.wire(*sw2["2"], 205.74, 170.18)
    sb.chain(sw2["1"], (185.42, 170.18), (185.42, 176.53))
    sb.place_pwr("GND", 185.42, 176.53)

    sb.stub(u4["5"], "SW_TURN_R", dx=-15.24)
    sb.stub(u4["6"], "SW_TURN_L", dx=-15.24)
    sb.nc(u4["7"])
    sb.stub(u4["8"], "TURN_FET_L", dx=-15.24)
    sb.stub(u4["9"], "TURN_FET_R", dx=-15.24)
    sb.stub(u4["10"], "VIN_12V_ADC", dx=-15.24)
    sb.stub(u4["11"], "BUZZER_PWM", dx=-15.24)
    sb.stub(u4["12"], "SW_BRAKE_L", dx=-15.24)
    sb.stub(u4["13"], "SW_BRAKE_R", dx=-15.24)
    sb.stub(u4["14"], "WS2812_TX", dx=-15.24)

    tp1 = sb.place(
        "Connector:TestPoint", "TP1", "IO11_AUX", 231.14, u4["15"][1], angle=90,
        footprint="TestPoint:TestPoint_Pad_D1.5mm", in_bom=False,
        ref_offset=(-5.08, -2.54), val_offset=(-5.08, 2.54),
    )
    sb.wire(*u4["15"], *tp1["1"])

    sb.stub(u4["16"], "NAVI_RX", dx=-15.24)
    sb.stub(u4["17"], "NAVI_TX", dx=-15.24)
    sb.nc(u4["18"])
    sb.stub(u4["19"], "RS485_DE", dx=-15.24)
    sb.stub(u4["20"], "LINK_RX", dx=-15.24)
    sb.stub(u4["21"], "LINK_TX", dx=-15.24)
    sb.nc(u4["22"])

    sb.nc(u4["39"])
    sb.nc(u4["40"])
    sb.stub(u4["23"], "USB_DN", dx=12.70)
    sb.stub(u4["24"], "USB_DP", dx=12.70)

    r8 = sb.place(
        "Device:R", "R8", "1k", 309.88, u4["25"][1], angle=90,
        footprint=FP_R0603, lcsc="C21190", ref_offset=(0, -3.175), val_offset=(0, 3.175),
    )
    d7 = sb.place(
        "Device:LED", "D7", "STATUS_BLUE", 327.66, u4["25"][1], angle=180,
        footprint="LED_SMD:LED_0603_1608Metric", lcsc="C72041",
        ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.wire(*u4["25"], *r8["1"])
    sb.wire(*r8["2"], *d7["2"])
    sb.chain(d7["1"], (337.82, u4["25"][1]), (337.82, u4["25"][1] + 5.08))
    sb.place_pwr("GND", 337.82, u4["25"][1] + 5.08)

    for pnum in ["26", "28", "29", "31", "32", "33", "34", "35", "36", "37", "38", "41", "44", "27", "30"]:
        sb.nc(u4[pnum])

    r33 = sb.place(
        "Device:R", "R33", "100k_1%", 198.12, 332.74, angle=0,
        footprint=FP_R0603, lcsc="C25803", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    r34 = sb.place(
        "Device:R", "R34", "22k_1%", 198.12, 353.06, angle=0,
        footprint=FP_R0603, lcsc="C25768", ref_offset=(-5.08, -1.905), val_offset=(-5.08, 1.905),
    )
    c23 = sb.place(
        "Device:C", "C23", "100nF", 215.90, 353.06, angle=0,
        footprint=FP_C0603, lcsc="C14663", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.rail_at(r33["1"], "+12V", dy=-3.81)
    sb.wire(*r33["2"], *r34["1"])
    sb.junc(198.12, 342.90)
    sb.wire(198.12, 342.90, 223.52, 342.90)
    sb.label("VIN_12V_ADC", 223.52, 342.90, angle=0)
    sb.junc(215.90, 342.90)
    sb.wire(215.90, 342.90, *c23["1"])
    sb.gnd_at(r34["2"], dy=3.81)
    sb.gnd_at(c23["2"], dy=3.81)

    r35 = sb.place(
        "Device:R", "R35", "15R_0805", 302.26, 327.66, angle=0,
        footprint=FP_R0805, lcsc="C17471", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    c24 = sb.place(
        "Device:C", "C24", "10uF", 281.94, 327.66, angle=0,
        footprint=FP_C0603, lcsc="C19702", ref_offset=(-5.08, -1.905), val_offset=(-5.08, 1.905),
    )
    sb.chain(c24["1"], (281.94, 317.50), (302.26, 317.50), r35["1"])
    sb.junc(281.94, 317.50)
    sb.wire(271.78, 317.50, 281.94, 317.50)
    sb.label("V5_LOGIC", 271.78, 317.50, angle=180)
    sb.gnd_at(c24["2"], dy=2.54)

    bz1 = sb.place(
        "Device:Buzzer", "BZ1", "MLT-8530", 314.96, 347.98, angle=0,
        footprint="Buzzer_Beeper:MagneticBuzzer_CUI_CMT-8504-100-SMT",
        lcsc="C94599", mpn="MLT-8530",
        ref_offset=(5.08, -2.54), val_offset=(5.08, 2.54),
    )
    d10 = sb.place(
        "Diode:1N5819WS", "D10", "B5819W", 294.64, 347.98, angle=270,
        footprint=FP_SOD123, lcsc="C8598", mpn="B5819W",
        ref_offset=(-5.08, -1.905), val_offset=(-5.08, 1.905),
    )
    sb.chain(r35["2"], (302.26, 339.09), (312.42, 339.09), bz1["1"])
    sb.junc(302.26, 339.09)
    sb.chain((302.26, 339.09), (294.64, 339.09), d10["1"])

    q3 = sb.place(
        "Transistor_FET:AO3400A", "Q3", "AO3400A", 299.72, 373.38, angle=0,
        footprint="Package_TO_SOT_SMD:SOT-23", lcsc="C20917", mpn="AO3400A",
        ref_offset=(5.08, -1.905), val_offset=(5.08, 1.905),
    )
    sb.chain(bz1["2"], (312.42, 358.14), (302.26, 358.14), q3["3"])
    sb.junc(302.26, 358.14)
    sb.chain(d10["2"], (294.64, 358.14), (302.26, 358.14))
    sb.gnd_at(q3["2"], dy=3.81)

    r36 = sb.place(
        "Device:R", "R36", "100R", 281.94, 373.38, angle=90,
        footprint=FP_R0603, lcsc="C22775", ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.wire(*r36["2"], *q3["1"])
    sb.stub(r36["1"], "BUZZER_PWM", dx=-6.35)

    r37 = sb.place(
        "Device:R", "R37", "10k", 289.56, 383.54, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(-4.45, -1.905), val_offset=(-4.45, 1.905),
    )
    sb.junc(289.56, 373.38)
    sb.wire(289.56, 373.38, *r37["1"])
    sb.gnd_at(r37["2"], dy=2.54)

    # =======================================================================
    # BLOCK 6: Bidirectional RS-485, CAT5 RJ45 Trunk & M5Stack Navi (Grove)
    #          (Middle-Right: x=373.38..579.12, y=142.24..264.16)
    # =======================================================================
    sb.box("6. RS-485, CAT5 RJ45 Trunk & M5Stack Navi (HY2.0-4P)", 373.38, 142.24, 579.12, 264.16)

    u3 = sb.place(
        "Interface_UART:SP3485EN", "U3", "SP3485EN-L/TR", 414.02, 187.96, angle=0,
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", lcsc="C9945", mpn="SP3485EN-L/TR",
        ref_offset=(-5.08, -17.78), val_offset=(6.35, -17.78),
    )
    sb.rail_at(u3["8"], "+3V3", dy=-5.08)
    sb.gnd_at(u3["5"], dy=5.08)

    c15 = sb.place(
        "Device:C", "C15", "100nF", 426.72, 165.10, angle=0,
        footprint=FP_C0603, lcsc="C14663", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.rail_at(c15["1"], "+3V3", dy=-2.54)
    sb.gnd_at(c15["2"], dy=2.54)

    sb.wire(*u3["1"], 386.08, u3["1"][1])
    sb.label("LINK_RX", 386.08, u3["1"][1], angle=180)
    r9 = sb.place(
        "Device:R", "R9", "10k", 397.51, 170.18, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(-5.08, -1.905), val_offset=(-5.08, 1.905),
    )
    sb.rail_at(r9["1"], "+3V3", dy=-2.54)
    sb.wire(*r9["2"], 397.51, u3["1"][1])
    sb.junc(397.51, u3["1"][1])

    sb.chain(u3["2"], (400.05, u3["2"][1]), (400.05, u3["3"][1]), u3["3"])
    sb.junc(400.05, u3["3"][1])
    sb.wire(400.05, u3["3"][1], 384.81, u3["3"][1])
    sb.junc(384.81, u3["3"][1])
    sb.label("RS485_DE", 391.16, u3["3"][1], angle=0)
    r10 = sb.place(
        "Device:R", "R10", "10k", 384.81, 200.66, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(-4.45, -1.905), val_offset=(-4.45, 1.905),
    )
    sb.wire(384.81, u3["3"][1], *r10["1"])
    sb.gnd_at(r10["2"], dy=3.81)

    sb.stub(u3["4"], "LINK_TX", dx=-11.43)

    sb.wire(*u3["6"], 462.28, u3["6"][1])
    sb.label("RS485_A", 462.28, u3["6"][1], angle=0)
    sb.wire(*u3["7"], 462.28, u3["7"][1])
    sb.label("RS485_B", 462.28, u3["7"][1], angle=0)

    jp1 = sb.place(
        "Jumper:SolderJumper_2_Bridged", "JP1", "TERM_EN", 440.69, 198.12, angle=0,
        footprint="Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm",
        in_bom=False, ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    r11 = sb.place(
        "Device:R", "R11", "120R", 453.39, 198.12, angle=90,
        footprint=FP_R0805, lcsc="C17440", ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.junc(435.61, u3["6"][1])
    sb.chain((435.61, u3["6"][1]), jp1["1"])
    sb.wire(*jp1["2"], *r11["1"])
    sb.junc(457.20, u3["7"][1])
    sb.chain(r11["2"], (457.20, 198.12), (457.20, u3["7"][1]))

    d8 = sb.place(
        "Diode:SM712_SOT23", "D8", "SM712", 445.77, 213.36, angle=0,
        footprint="Package_TO_SOT_SMD:SOT-23", lcsc="C15919", mpn="SM712",
        ref_offset=(0, -5.08), val_offset=(0, -2.54),
    )
    sb.junc(435.61, 198.12)
    sb.chain((435.61, 198.12), (435.61, 213.36), d8["1"])
    sb.junc(457.20, 198.12)
    sb.chain((457.20, 198.12), (457.20, 213.36), d8["2"])
    sb.gnd_at(d8["3"], dy=3.81)

    f3 = sb.place(
        "Device:Polyfuse", "F3", "1.5A_TRUNK", 500.38, 177.80, angle=90,
        footprint="Fuse:Fuse_1206_3216Metric", lcsc="C70062",
        ref_offset=(0, -5.08), val_offset=(0, 5.08),
    )
    sb.chain(f3["1"], (491.49, 177.80), (491.49, 172.72))
    sb.place_pwr("+12V", 491.49, 172.72)

    j1 = sb.place(
        "Connector:RJ45_Shielded", "J1", "RJ45_CAT5_TRUNK", 525.78, 177.80, angle=0,
        footprint="Connector_RJ:RJ45_Amphenol_RJHSE5380",
        lcsc="C386757", mpn="R-RJ45R08P-C000",
        dnp=False, ref_offset=(-5.08, -15.24), val_offset=(2.54, -15.24),
    )
    sb.chain(j1["8"], (543.56, j1["8"][1]), (543.56, j1["7"][1]), j1["7"])
    sb.junc(543.56, j1["7"][1])
    sb.chain((543.56, j1["7"][1]), (553.72, j1["7"][1]))
    sb.place_pwr("GND", 553.72, j1["7"][1], angle=90)
    sb.nc(j1["6"])
    sb.chain(j1["5"], (543.56, j1["5"][1]), (543.56, j1["4"][1]), j1["4"])
    sb.junc(543.56, j1["5"][1])
    sb.stub((543.56, j1["5"][1]), "V12_TRUNK", dx=7.62)
    sb.stub(f3["2"], "V12_TRUNK", dx=5.08)
    sb.nc(j1["3"])
    sb.stub(j1["2"], "RS485_B", dx=15.24)
    sb.stub(j1["1"], "RS485_A", dx=15.24)
    sb.gnd_at(j1["SH"], dy=2.54)

    d_navi = sb.place(
        "Diode:SS34", "D11", "SS34", 401.32, 246.38, angle=180,
        footprint="Diode_SMD:D_SMA", lcsc="C8678", mpn="SS34",
        ref_offset=(0, -4.45), val_offset=(0, 4.45),
    )
    jp_navi = sb.place(
        "Jumper:SolderJumper_2_Open", "JP2", "NAVI_5V_BYP", 401.32, 234.95, angle=0,
        footprint="Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm",
        in_bom=False, ref_offset=(0, -3.81), val_offset=(0, -6.35),
    )
    f2 = sb.place(
        "Device:Polyfuse", "F2", "1.1A_NAVI", 421.64, 246.38, angle=90,
        footprint="Fuse:Fuse_1206_3216Metric", lcsc="C70059",
        ref_offset=(0, -4.45), val_offset=(0, 4.45),
    )
    sb.chain(d_navi["2"], (388.62, 246.38), (388.62, 241.30))
    sb.place_pwr("+5V", 388.62, 241.30)
    sb.junc(393.70, 246.38)
    sb.chain((393.70, 246.38), (393.70, 234.95), jp_navi["1"])
    sb.chain(jp_navi["2"], (408.94, 234.95), (408.94, 246.38))
    sb.junc(408.94, 246.38)
    sb.wire(*d_navi["1"], *f2["1"])

    j_navi = sb.place(
        "Connector_Generic:Conn_01x04", "J4", "GROVE_NAVI_HY2.0", 538.48, 241.30, angle=0,
        footprint="Connector_JST:JST_PH_S4B-PH-K_1x04_P2.00mm_Horizontal",
        lcsc="C265452", mpn="S4B-PH-K(LF)(SN)",
        dnp=False, ref_offset=(2.54, -6.35), val_offset=(2.54, 8.89),
    )
    sb.chain(f2["2"], (436.88, 246.38), (436.88, j_navi["3"][1]), j_navi["3"])
    sb.chain(j_navi["4"], (525.78, j_navi["4"][1]), (525.78, 252.73))
    sb.place_pwr("GND", 525.78, 252.73)

    r39 = sb.place(
        "Device:R", "R39", "220R", 505.46, j_navi["2"][1], angle=90,
        footprint=FP_R0603, lcsc="C22962", ref_offset=(0, -3.175), val_offset=(0, 3.175),
    )
    sb.wire(*r39["2"], *j_navi["2"])
    sb.stub(r39["1"], "NAVI_TX", dx=-10.16)

    sb.chain(j_navi["1"], (520.70, j_navi["1"][1]), (520.70, 229.87), (495.30, 229.87))
    r38 = sb.place(
        "Device:R", "R38", "220R", 491.49, 229.87, angle=90,
        footprint=FP_R0603, lcsc="C22962", ref_offset=(0, -3.175), val_offset=(0, 3.175),
    )
    sb.wire(*r38["1"], 472.44, 229.87)
    sb.label("NAVI_RX", 472.44, 229.87, angle=180)
    r40 = sb.place(
        "Device:R", "R40", "10k", 480.06, 220.98, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(-4.45, -1.27), val_offset=(-4.45, 1.27),
    )
    sb.rail_at(r40["1"], "+3V3", dy=-2.54)
    sb.wire(*r40["2"], 480.06, 229.87)
    sb.junc(480.06, 229.87)

    # =======================================================================
    # BLOCK 7: Front 12V Lamp Drivers (P2/P3/P4) & Status WS2812 (S4)
    #          (Placed above A2 title block: x=373.38..579.12, y=271.78..363.22)
    # =======================================================================
    sb.box("7. Front 12V Lamp Terminals (P2/P3/P4) & Status WS2812 (S4)", 373.38, 271.78, 579.12, 363.22)

    p4 = sb.place(
        "Connector_Generic:Conn_01x02", "P4", "HEADLIGHT_12V_2P", 411.48, 294.64, angle=0,
        footprint=FP_TB35_2P, lcsc="C474892", mpn="KF350-3.5-2P",
        dnp=False, ref_offset=(2.54, -5.08), val_offset=(2.54, 5.08),
    )
    sb.chain(p4["1"], (393.70, p4["1"][1]), (393.70, 289.56))
    sb.place_pwr("+12V", 393.70, 289.56)
    sb.chain(p4["2"], (393.70, p4["2"][1]), (393.70, 303.53))
    sb.place_pwr("GND", 393.70, 303.53)

    u6 = sb.place(
        "Logic_LevelTranslator:SN74LV1T34DBV", "U6", "SN74LV1T34DBVR", 401.32, 335.28, angle=0,
        footprint="Package_TO_SOT_SMD:SOT-23-5", lcsc="C100022", mpn="SN74LV1T34DBVR",
        ref_offset=(-5.08, -10.16), val_offset=(5.08, -10.16),
    )
    sb.nc(u6["1"])
    sb.stub(u6["2"], "WS2812_TX", dx=-10.16)
    sb.rail_at(u6["5"], "+5V", dy=-2.54)
    sb.gnd_at(u6["3"], dy=2.54)

    c16 = sb.place(
        "Device:C", "C16", "100nF", 383.54, 350.52, angle=0,
        footprint=FP_C0603, lcsc="C14663", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.rail_at(c16["1"], "+5V", dy=-2.54)
    sb.gnd_at(c16["2"], dy=2.54)

    r14 = sb.place(
        "Device:R", "R14", "330R", 416.56, 335.28, angle=90,
        footprint=FP_R0603, lcsc="C23138", ref_offset=(0, -3.175), val_offset=(0, 3.175),
    )
    sb.wire(*u6["4"], *r14["1"])

    s4 = sb.place(
        "Connector_Generic:Conn_01x03", "S4", "STATUS_WS2812_3P", 449.58, 335.28, angle=0,
        footprint=FP_TB254_3P, lcsc="C557686", mpn="XY308-2.54-3P",
        dnp=False, ref_offset=(2.54, -6.35), val_offset=(2.54, 6.35),
    )
    sb.chain(s4["1"], (434.34, s4["1"][1]), (434.34, 327.66))
    sb.place_pwr("GND", 434.34, 327.66, angle=180)
    sb.wire(*r14["2"], *s4["2"])
    sb.chain(s4["3"], (434.34, s4["3"][1]), (434.34, 344.17))
    sb.place_pwr("+5V", 434.34, 344.17, angle=180)

    c17 = sb.place(
        "Device:C", "C17", "22uF/10V", 464.82, 307.34, angle=0,
        footprint=FP_C0805, lcsc="C45783", ref_offset=(-5.08, -1.905), val_offset=(-5.08, 1.905),
    )
    sb.rail_at(c17["1"], "+5V", dy=-2.54)
    sb.gnd_at(c17["2"], dy=2.54)

    for qref, rg_ref, rpd_ref, dfly_ref, p_ref, p_val, in_lbl, qx in [
        ("Q1", "R15", "R16", "D4", "P2", "TURN_LAMP_L_2P", "TURN_FET_L", 500.38),
        ("Q2", "R17", "R18", "D5", "P3", "TURN_LAMP_R_2P", "TURN_FET_R", 553.72),
    ]:
        q = sb.place(
            "Transistor_FET:AO3400A", qref, "AO3400A", qx, 335.28, angle=0,
            footprint="Package_TO_SOT_SMD:SOT-23", lcsc="C20917", mpn="AO3400A",
            ref_offset=(5.08, -1.905), val_offset=(5.08, 1.905),
        )
        sb.gnd_at(q["2"], dy=3.81)

        rg = sb.place(
            "Device:R", rg_ref, "100R", qx - 15.24, 335.28, angle=90,
            footprint=FP_R0603, lcsc="C22775", ref_offset=(0, -3.175), val_offset=(0, 3.175),
        )
        sb.wire(*rg["2"], *q["1"])
        sb.stub(rg["1"], in_lbl, dx=-5.08)

        rpd = sb.place(
            "Device:R", rpd_ref, "10k", qx - 8.89, 345.44, angle=0,
            footprint=FP_R0603, lcsc="C25804", ref_offset=(-4.45, -1.905), val_offset=(-4.45, 1.905),
        )
        sb.junc(qx - 8.89, 335.28)
        sb.wire(qx - 8.89, 335.28, *rpd["1"])
        sb.gnd_at(rpd["2"], dy=2.54)

        dx = q["3"][0]
        dfly = sb.place(
            "Diode:1N5819WS", dfly_ref, "B5819W", dx - 7.62, 309.88, angle=270,
            footprint=FP_SOD123, lcsc="C8598", mpn="B5819W",
            ref_offset=(-5.08, -1.905), val_offset=(-5.08, 1.905),
        )
        ptb = sb.place(
            "Connector_Generic:Conn_01x02", p_ref, p_val, dx + 10.16, 302.26, angle=0,
            footprint=FP_TB35_2P, lcsc="C474892", mpn="KF350-3.5-2P",
            dnp=False, ref_offset=(2.54, -5.08), val_offset=(2.54, 5.08),
        )
        sb.chain(dfly["1"], (dx - 7.62, 302.26), ptb["1"])
        sb.junc(dx - 7.62, 302.26)
        sb.rail_at((dx - 7.62, 302.26), "+12V", dy=-3.81)

        sb.wire(dx, q["3"][1], dx, 304.80)
        sb.wire(dx, 304.80, *ptb["2"])
        sb.junc(dx, 318.77)
        sb.chain(dfly["2"], (dx - 7.62, 318.77), (dx, 318.77))

    return sb


def write_project_files():
    pro = json.loads(open(f"{SHARE}/template/kicad.kicad_pro").read())
    pro["meta"]["filename"] = f"{PROJ}.kicad_pro"
    pro["board"]["design_settings"]["rules"] = {
        "min_clearance": 0.15,
        "min_track_width": 0.15,
        "min_via_annular_width": 0.15,
        "min_via_diameter": 0.6,
        "min_through_hole_diameter": 0.3,
        "min_copper_edge_clearance": 0.3,
        "min_hole_to_hole": 0.25,
    }
    base_cls = {
        "name": "Default",
        "clearance": 0.15,
        "track_width": 0.2,
        "via_diameter": 0.6,
        "via_drill": 0.3,
        "wire_width": 6,
        "bus_width": 12,
        "line_style": 0,
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "diff_pair_gap": 0.25,
        "diff_pair_width": 0.2,
        "diff_pair_via_gap": 0.25,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "priority": 2147483647,
    }
    net_widths = {
        "VBUS_PD": 1.0,
        "V12_FUSED": 1.0,
        "+12V": 1.2,
        "V12_TRUNK": 0.8,
        "BUCK_SW": 0.8,
        "+5V": 0.5,
        "V5_LOGIC": 0.5,
        "VBUS": 0.5,
        "+3V3": 0.25,
        "GND": 0.3,
    }
    classes = [base_cls]
    patterns = []
    for w in sorted(set(net_widths.values())):
        cname = f"W{int(w * 1000)}"
        c = dict(base_cls, name=cname, track_width=w, priority=0, clearance=(0.2 if w >= 0.6 else 0.15))
        classes.append(c)
        for net_nm, nw in net_widths.items():
            if nw == w:
                patterns.append({"netclass": cname, "pattern": f"/{net_nm}"})
                patterns.append({"netclass": cname, "pattern": net_nm})
    pro["net_settings"] = {
        "classes": classes,
        "netclass_patterns": patterns,
        "meta": {"version": 4},
    }
    with open(f"{OUT_DIR}/{PROJ}.kicad_pro", "w") as f:
        json.dump(pro, f, indent=2)
        f.write("\n")

    pcb_text = f"""(kicad_pcb
\t(version 20250907)
\t(generator "pcbnew")
\t(generator_version "10.0")
\t(general
\t\t(thickness 1.6)
\t\t(legacy_teardrops no)
\t)
\t(paper "A4")
\t(title_block
\t\t(title "LaserBlinker Front All-in-One Master PCB")
\t\t(date "2026-11-12")
\t\t(rev "v1.0")
\t\t(comment 1 "PCB layout deferred until schematic review is finalized")
\t)
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(2 "B.Cu" signal)
\t\t(9 "F.Adhes" user "F.Adhesive")
\t\t(11 "B.Adhes" user "B.Adhesive")
\t\t(13 "F.Paste" user)
\t\t(15 "B.Paste" user)
\t\t(5 "F.SilkS" user "F.Silkscreen")
\t\t(7 "B.SilkS" user "B.Silkscreen")
\t\t(1 "F.Mask" user)
\t\t(3 "B.Mask" user)
\t\t(17 "Dwgs.User" user "User.Drawings")
\t\t(19 "Cmts.User" user "User.Comments")
\t\t(21 "Eco1.User" user "User.Eco1")
\t\t(23 "Eco2.User" user "User.Eco2")
\t\t(25 "Edge.Cuts" user)
\t\t(27 "Margin" user)
\t\t(31 "F.CrtYd" user "F.Courtyard")
\t\t(29 "B.CrtYd" user "B.Courtyard")
\t\t(35 "F.Fab" user)
\t\t(33 "B.Fab" user)
\t)
\t(setup
\t\t(pad_to_mask_clearance 0)
\t)
\t(net 0 "")
\t(gr_rect
\t\t(start 100 80)
\t\t(end 150 135)
\t\t(stroke (width 0.15) (type solid))
\t\t(fill no)
\t\t(layer "Edge.Cuts")
\t\t(uuid "{u('pcb.outline')}")
\t)
\t(embedded_fonts no)
)
"""
    with open(f"{OUT_DIR}/{PROJ}.kicad_pcb", "w") as f:
        f.write(pcb_text)


def main():
    os.makedirs(f"{OUT_DIR}/out", exist_ok=True)
    write_project_files()
    sb = build_schematic()
    sch_path = f"{OUT_DIR}/{PROJ}.kicad_sch"
    with open(sch_path, "w") as f:
        f.write(sb.build_sexp())
    print(f"Generated {sch_path} with {len(sb.symbols)} symbol instances and {len(sb.wires)} wires.")


if __name__ == "__main__":
    main()
