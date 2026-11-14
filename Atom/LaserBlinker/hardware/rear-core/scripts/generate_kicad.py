#!/usr/bin/env python3
"""
Generate complete KiCad 10 project for LaserBlinker Rear Core PCB:
  - hardware/rear-core/RearCore.kicad_sym          (ESP32-C3-MINI-1 symbol)
  - hardware/rear-core/footprints.pretty/ESP32-C3-MINI-1.kicad_mod
  - hardware/rear-core/sym-lib-table
  - hardware/rear-core/fp-lib-table
  - hardware/rear-core/rear-core.kicad_pro
  - hardware/rear-core/rear-core.kicad_sch         (ERC-clean full schematic)
  - hardware/rear-core/rear-core.kicad_pcb         (Initialized board file 34x44mm)
"""

import copy
import json
import math
import os
import re
import uuid

SHARE = "/opt/homebrew/Caskroom/kicad/10.0.8/KiCad/KiCad.app/Contents/SharedSupport"
OUT_DIR = "/Volumes/Caches/Dropbox/gitbox/M5Stack/Atom/LaserBlinker/hardware/rear-core"
PROJ = "rear-core"


def u(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"laserblinker.rearcore.v1.{key}"))


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


# ---------------------------------------------------------------------------
# 1. Custom Footprint: ESP32-C3-MINI-1 (13.2 x 16.6 mm, 53 pads)
# ---------------------------------------------------------------------------

def generate_c3_mini_footprint():
    src = open(f"{SHARE}/footprints/RF_Module.pretty/ESP32-C6-MINI-1.kicad_mod").read()
    fp = src.replace("ESP32-C6-MINI-1", "ESP32-C3-MINI-1")
    fp = fp.replace(
        "esp32-c6-mini-1_mini-1u_datasheet_en.pdf",
        "esp32-c3-mini-1_datasheet_en.pdf",
    )
    fp = fp.replace(
        "2.4 GHz Wi-Fi, Bluetooth, Zigbee and Thread combo chip, external antenna",
        "RF Module, ESP32-C3-MINI-1-N4, Wi-Fi and BLE 5.0, onboard PCB antenna, 13.2x16.6mm",
    )
    fp = re.sub(
        r'\(model "[^"]*"',
        '(model "${KIPRJMOD}/3d/ESP32-C3-MINI-1.wrl"',
        fp,
    )
    with open(f"{OUT_DIR}/footprints.pretty/ESP32-C3-MINI-1.kicad_mod", "w") as f:
        f.write(fp)

    # Generate lightweight VRML 3D model for 3D viewer inspection
    os.makedirs(f"{OUT_DIR}/3d", exist_ok=True)
    def wrl_box(cx, cy, cz, sx, sy, sz, rgb):
        scale = 2.54
        return (
            f"Transform {{ translation {cx/scale:.4f} {cy/scale:.4f} {cz/scale:.4f} children Shape {{"
            f" appearance Appearance {{ material Material {{ diffuseColor {rgb} specularColor 0.3 0.3 0.3 }} }}"
            f" geometry Box {{ size {sx/scale:.4f} {sy/scale:.4f} {sz/scale:.4f} }} }} }}\n"
        )
    wrl = "#VRML V2.0 utf8\n"
    wrl += wrl_box(0, 2.7, 0.4, 13.2, 16.6, 0.8, "0.06 0.08 0.06")
    wrl += wrl_box(0, -0.1, 1.6, 12.4, 10.6, 1.6, "0.76 0.77 0.80")
    wrl += wrl_box(0, 8.3, 0.85, 11.5, 4.2, 0.1, "0.78 0.62 0.20")
    with open(f"{OUT_DIR}/3d/ESP32-C3-MINI-1.wrl", "w") as f:
        f.write(wrl)


# ---------------------------------------------------------------------------
# 2. Custom Symbol Library: RearCore.kicad_sym (ESP32-C3-MINI-1)
# ---------------------------------------------------------------------------

def make_c3_mini_symbol_tree(lib_prefixed=False):
    sym_name = "RearCore:ESP32-C3-MINI-1" if lib_prefixed else "ESP32-C3-MINI-1"
    left_pins = [
        ("8", "EN", "input", 17.78),
        ("12", "IO0", "bidirectional", 12.70),
        ("13", "IO1", "bidirectional", 10.16),
        ("5", "IO2", "bidirectional", 7.62),
        ("6", "IO3", "bidirectional", 5.08),
        ("18", "IO4", "bidirectional", 2.54),
        ("19", "IO5", "bidirectional", 0.00),
        ("20", "IO6", "bidirectional", -2.54),
        ("21", "IO7", "bidirectional", -5.08),
        ("22", "IO8", "bidirectional", -7.62),
        ("23", "IO9", "bidirectional", -10.16),
        ("16", "IO10", "bidirectional", -12.70),
    ]
    right_pins = [
        ("30", "RXD0/IO20", "bidirectional", 12.70),
        ("31", "TXD0/IO21", "bidirectional", 10.16),
        ("26", "USB_D-/IO18", "bidirectional", -7.62),
        ("27", "USB_D+/IO19", "bidirectional", -10.16),
    ]
    nc_pins = ["4", "7", "9", "10", "15", "17", "24", "25", "28", "29", "32", "33", "34", "35"]
    gnd_extra = ["2", "11", "14"] + [str(i) for i in range(36, 54)]

    pin_nodes = [
        [
            "pin", "power_in", "line",
            ["at", "0", "22.86", "270"],
            ["length", "2.54"],
            ["name", '"3V3"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
            ["number", '"3"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
        ]
    ]
    for num, name, ptype, py in left_pins:
        pin_nodes.append([
            "pin", ptype, "line",
            ["at", "-15.24", fmt(py), "0"],
            ["length", "2.54"],
            ["name", f'"{name}"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
            ["number", f'"{num}"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
        ])
    for num, name, ptype, py in right_pins:
        pin_nodes.append([
            "pin", ptype, "line",
            ["at", "15.24", fmt(py), "180"],
            ["length", "2.54"],
            ["name", f'"{name}"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
            ["number", f'"{num}"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
        ])
    pin_nodes.append([
        "pin", "power_in", "line",
        ["at", "0", "-22.86", "90"],
        ["length", "2.54"],
        ["name", '"GND"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
        ["number", '"1"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
    ])
    for num in gnd_extra:
        pin_nodes.append([
            "pin", "passive", "line",
            ["at", "0", "-22.86", "90"],
            ["length", "2.54"],
            ["hide", "yes"],
            ["name", '"GND"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
            ["number", f'"{num}"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
        ])
    for idx, num in enumerate(nc_pins):
        nx = -8.89 + idx * 1.27
        pin_nodes.append([
            "pin", "no_connect", "line",
            ["at", fmt(nx), "-19.05", "90"],
            ["length", "0"],
            ["hide", "yes"],
            ["name", '"NC"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
            ["number", f'"{num}"', ["effects", ["font", ["size", "1.27", "1.27"]]]],
        ])

    return [
        "symbol", f'"{sym_name}"',
        ["exclude_from_sim", "no"],
        ["in_bom", "yes"],
        ["on_board", "yes"],
        ["in_pos_files", "yes"],
        ["duplicate_pin_numbers_are_jumpers", "no"],
        ["property", '"Reference"', '"U"', ["at", "-11.43", "21.59", "0"], ["effects", ["font", ["size", "1.27", "1.27"]]]],
        ["property", '"Value"', '"ESP32-C3-MINI-1-N4"', ["at", "6.35", "21.59", "0"], ["effects", ["font", ["size", "1.27", "1.27"]]]],
        ["property", '"Footprint"', '"RearCore:ESP32-C3-MINI-1"', ["at", "0", "-26.67", "0"], ["hide", "yes"], ["effects", ["font", ["size", "1.27", "1.27"]]]],
        ["property", '"Datasheet"', '"https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.pdf"', ["at", "0", "0", "0"], ["hide", "yes"], ["effects", ["font", ["size", "1.27", "1.27"]]]],
        ["property", '"Description"', '"RF Module, ESP32-C3-MINI-1-N4, 4MB Flash, PCB Antenna"', ["at", "0", "0", "0"], ["hide", "yes"], ["effects", ["font", ["size", "1.27", "1.27"]]]],
        [
            "symbol", '"ESP32-C3-MINI-1_0_1"',
            [
                "rectangle",
                ["start", "-12.7", "20.32"],
                ["end", "12.7", "-20.32"],
                ["stroke", ["width", "0.254"], ["type", "default"]],
                ["fill", ["type", "background"]],
            ],
        ],
        ["symbol", '"ESP32-C3-MINI-1_1_1"'] + pin_nodes,
        ["embedded_fonts", "no"],
    ]


def write_custom_sym_lib():
    lib_tree = [
        "kicad_symbol_lib",
        ["version", "20241209"],
        ["generator", '"kicad_symbol_editor"'],
        ["generator_version", '"10.0"'],
        make_c3_mini_symbol_tree(lib_prefixed=False),
    ]
    with open(f"{OUT_DIR}/RearCore.kicad_sym", "w") as f:
        f.write(dump_sexp(lib_tree, indent=0) + "\n")


# ---------------------------------------------------------------------------
# 3. Extract & Flatten Standard Symbols
# ---------------------------------------------------------------------------

LIB_CACHE = {}


def load_flattened_symbol(lib: str, sym_name: str):
    if lib == "RearCore" and sym_name == "ESP32-C3-MINI-1":
        return make_c3_mini_symbol_tree(lib_prefixed=True)

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
# 4. Schematic Builder
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
            ["paper", '"A3"'],
            [
                "title_block",
                ["title", '"LaserBlinker Rear Core PCB"'],
                ["date", '"2026-11-12"'],
                ["rev", '"v1.0"'],
                ["comment", "1", '"MCU: ESP32-C3-MINI-1-N4 | RS-485: SP3485EN (Bidirectional) | IMU: LIS3DHTR"'],
                ["comment", "2", '"Power: 12V->5V 3A Buck (TPS54302) + USB/5V OR-ing + 3.3V LDO (AP2112K-3.3)"'],
                ["comment", "3", '"Outputs: WS2812 5V Buffer (SN74LV1T34) + Expansion port J3 (+12V/+5V/GND/EXP_CMD)"'],
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
# 5. Assemble Full Rear Core Circuit Schematic (A3: 420 x 297 mm)
# ---------------------------------------------------------------------------

def build_schematic():
    sb = SchematicBuilder()

    FP_R0603 = "Resistor_SMD:R_0603_1608Metric"
    FP_R0805 = "Resistor_SMD:R_0805_2012Metric"
    FP_C0603 = "Capacitor_SMD:C_0603_1608Metric"
    FP_C0805 = "Capacitor_SMD:C_0805_2012Metric"
    FP_C1206 = "Capacitor_SMD:C_1206_3216Metric"
    FP_SOD123 = "Diode_SMD:D_SOD-123"

    # =======================================================================
    # BLOCK 1: CAT5 RJ45 Trunk, Terminal I/O & Mounting (x=12.7..101.6, y=12.7..139.7)
    # =======================================================================
    sb.box("1. CAT5 RJ45 Trunk & Terminal I/O", 12.70, 12.70, 101.60, 139.70)

    # J1: Non-magnetic Shielded RJ45 (Passive PoE Mode B pinout: 1/2=RS485, 4/5=+12V, 7/8=GND, 3/6=NC guard)
    # Local pins at angle=0: 8=(+10.16, sy-10.16) .. 1=(+10.16, sy+7.62), SH=(0, sy+12.70)
    j1 = sb.place(
        "Connector:RJ45_Shielded", "J1", "RJ45_CAT5_TRUNK", 30.48, 40.64, angle=0,
        footprint="Connector_RJ:RJ45_Amphenol_RJHSE5380",
        lcsc="C386756", mpn="R-RJ45R08P-B000",  # Non-LED; matches Amphenol RJHSE5380-style pads
        dnp=False, ref_offset=(-5.08, -15.24), val_offset=(2.54, -15.24),
    )
    # Pin 7 & 8 (Brown pair) -> GND + PWR_FLAG
    sb.chain(j1["8"], (48.26, j1["8"][1]), (48.26, j1["7"][1]), j1["7"])
    sb.junc(48.26, j1["7"][1])
    sb.chain((48.26, j1["8"][1]), (55.88, j1["8"][1]))
    sb.place_pwr("PWR_FLAG", 55.88, j1["8"][1])
    sb.chain((48.26, j1["7"][1]), (60.96, j1["7"][1]))
    sb.place_pwr("GND", 60.96, j1["7"][1], angle=90)

    # Pin 6 (Green) -> NC guard between GND and +12V
    sb.nc(j1["6"])

    # Pin 4 & 5 (Blue pair) -> V12_RAW (paralleled +12V input)
    sb.chain(j1["5"], (48.26, j1["5"][1]), (48.26, j1["4"][1]), j1["4"])
    sb.junc(48.26, j1["5"][1])
    sb.stub((48.26, j1["5"][1]), "V12_RAW", dx=7.62)

    # Pin 3 (White/Green) -> NC guard between +12V and RS-485
    sb.nc(j1["3"])

    # Pin 1 & 2 (Orange twisted pair) -> RS485_A / RS485_B
    sb.stub(j1["2"], "RS485_B", dx=15.24)
    sb.stub(j1["1"], "RS485_A", dx=15.24)

    # Shield -> GND
    sb.gnd_at(j1["SH"], dy=2.54)

    j2 = sb.place(
        "Connector_Generic:Conn_01x03", "J2", "WS2812_TAPE_3P", 73.66, 73.66, angle=0,
        footprint="Connector_JST:JST_XH_S3B-XH-A_1x03_P2.50mm_Horizontal",
        lcsc="C157927", mpn="S3B-XH-A(LF)(SN)",
        dnp=False, ref_offset=(2.54, -6.35), val_offset=(2.54, 6.35),
    )
    sb.chain(j2["1"], (45.72, j2["1"][1]), (45.72, 68.58))
    sb.place_pwr("+5V", 45.72, 68.58)
    sb.stub(j2["2"], "LED_DATA_5V", dx=-17.78)
    sb.chain(j2["3"], (45.72, j2["3"][1]), (45.72, 81.28))
    sb.place_pwr("GND", 45.72, 81.28)

    # Expansion port (option C): power rails + single CMD line for a future laser/IO daughterboard
    j3 = sb.place(
        "Connector_Generic:Conn_01x04", "J3", "EXP_4P", 73.66, 102.87, angle=0,
        footprint="Connector_JST:JST_XH_S4B-XH-A_1x04_P2.50mm_Horizontal",
        lcsc="C157928", mpn="S4B-XH-A(LF)(SN)",
        dnp=False, ref_offset=(2.54, -6.35), val_offset=(2.54, 8.89),
    )
    sb.chain(j3["1"], (40.64, j3["1"][1]), (40.64, 95.25))
    sb.place_pwr("+12V", 40.64, 95.25)
    sb.chain(j3["2"], (43.18, j3["2"][1]), (43.18, 97.79))
    sb.place_pwr("+5V", 43.18, 97.79)
    sb.chain(j3["3"], (45.72, j3["3"][1]), (45.72, 113.03))
    sb.place_pwr("GND", 45.72, 113.03)
    # Keep EXP_CMD stub short so it does not cross the GND drop
    sb.stub(j3["4"], "EXP_CMD", dx=-10.16)

    # M2 grounded mounting holes (layout places H1 top-right, H2 top-left).
    for idx, hx in enumerate([88.90, 27.94], start=1):
        h = sb.place(
            "Mechanical:MountingHole_Pad", f"H{idx}", "M2", hx, 68.58, angle=0,
            footprint="MountingHole:MountingHole_2.2mm_M2_Pad_Via",
            in_bom=False, ref_offset=(0, -5.08), val_offset=(0, -2.54),
        )
        sb.gnd_at(h["1"], dy=3.81)

    # =======================================================================
    # BLOCK 2: Power Supply (12V -> 5V 3A Buck & USB/5V OR -> 3.3V LDO)
    #          (x=106.68..406.40, y=12.70..96.52)
    # =======================================================================
    sb.box("2. Power Supply (12V->5V 3A Buck + USB/5V OR + 3.3V LDO)", 106.68, 12.70, 406.40, 96.52)

    f1 = sb.place(
        "Device:Polyfuse", "F1", "3A_1812", 129.54, 40.64, angle=90,
        footprint="Fuse:Fuse_1812_4532Metric", lcsc="C70069",
        ref_offset=(0, -5.08), val_offset=(0, 5.08),
    )
    sb.stub(f1["1"], "V12_RAW", dx=-8.89)

    d1 = sb.place(
        "Diode:SS34", "D1", "SS34", 144.78, 40.64, angle=180,
        footprint="Diode_SMD:D_SMA", lcsc="C8678", mpn="SS34",
        ref_offset=(0, -5.08), val_offset=(0, 5.08),
    )
    # Name the fused node so PCB netclass keeps F1→D1 as fat copper (not Default 0.2mm)
    sb.wire(*f1["2"], *d1["2"])
    sb.label("V12_FUSED", (f1["2"][0] + d1["2"][0]) / 2.0, f1["2"][1], angle=0)

    # Keep +12V rail, PWR_FLAG & D6 TVS before C1..C3
    # D1 cathode (pin 1 with angle=180 placement → schematic pin "1" is +12V side)
    sb.junc(153.67, 40.64)
    sb.rail_at((153.67, 40.64), "+12V", dy=-5.08)
    sb.junc(158.75, 40.64)
    sb.wire(158.75, 40.64, 158.75, 33.02)
    sb.place_pwr("PWR_FLAG", 158.75, 33.02)

    d6 = sb.place(
        "Diode:SMAJ15A", "D6", "SMAJ15A", 165.10, 55.88, angle=270,
        footprint="Diode_SMD:D_SMA", lcsc="C123805", mpn="SMAJ15A",
        ref_offset=(4.45, -1.905), val_offset=(4.45, 1.905),
    )
    sb.junc(165.10, 40.64)
    sb.wire(165.10, 40.64, *d6["1"])
    sb.gnd_at(d6["2"], dy=5.08)

    for cref, cval, cfp, clcsc, cx in [
        ("C1", "22uF/25V", FP_C1206, "C12891", 176.53),
        ("C2", "22uF/25V", FP_C1206, "C12891", 189.23),
        ("C3", "100nF/50V", FP_C0603, "C14663", 201.93),
    ]:
        c = sb.place(
            "Device:C", cref, cval, cx, 55.88, angle=0,
            footprint=cfp, lcsc=clcsc, ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
        )
        if cx < 201.93:
            sb.junc(cx, 40.64)
        sb.wire(cx, 40.64, *c["1"])
        sb.gnd_at(c["2"], dy=5.08)

    u1 = sb.place(
        "Regulator_Switching:TPS54302", "U1", "TPS54302DDCR", 226.06, 43.18, angle=0,
        footprint="Package_TO_SOT_SMD:SOT-23-6", lcsc="C311038", mpn="TPS54302DDCR",
        ref_offset=(0, -8.89), val_offset=(0, -6.35),
    )
    sb.wire(*d1["1"], *u1["3"])
    sb.junc(201.93, 40.64)
    # TPS54302 EN (Pin 5): absolute max 7V; leave floating to use internal 0.9uA pull-up per TI datasheet
    sb.nc(u1["5"])
    sb.gnd_at(u1["1"], dy=13.97)

    c4 = sb.place(
        "Device:C", "C4", "100nF/25V", 243.84, 33.02, angle=90,
        footprint=FP_C0603, lcsc="C14663", ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.chain(u1["6"], (238.76, 40.64), (238.76, 33.02), c4["1"])
    sb.chain(c4["2"], (250.19, 33.02), (250.19, 43.18))
    sb.junc(250.19, 43.18)

    l1 = sb.place(
        "Device:L", "L1", "4.7uH/4.5A", 259.08, 43.18, angle=90,
        footprint="Inductor_SMD:L_6.3x6.3_H3", lcsc="C408412",
        ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.wire(*u1["2"], *l1["1"])
    # Switch node carries buck peak current — must not stay as anonymous Default 0.2mm
    sb.label("BUCK_SW", (u1["2"][0] + l1["1"][0]) / 2.0, u1["2"][1], angle=0)
    sb.wire(*l1["2"], 317.50, 43.18)

    r1 = sb.place(
        "Device:R", "R1", "75k_1%", 269.24, 54.61, angle=0,
        footprint=FP_R0603, lcsc="C23240", ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
    )
    r2 = sb.place(
        "Device:R", "R2", "10k_1%", 269.24, 71.12, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
    )
    sb.junc(269.24, 43.18)
    sb.wire(269.24, 43.18, *r1["1"])
    sb.wire(*r1["2"], *r2["1"])
    sb.junc(269.24, 63.50)
    sb.chain(u1["4"], (241.30, 45.72), (241.30, 63.50), (269.24, 63.50))
    sb.gnd_at(r2["2"], dy=3.81)

    sb.junc(276.86, 43.18)
    sb.rail_at((276.86, 43.18), "+5V", dy=-5.08)
    sb.junc(281.94, 43.18)
    sb.wire(281.94, 43.18, 281.94, 35.56)
    sb.place_pwr("PWR_FLAG", 281.94, 35.56)

    for cref, cval, cfp, clcsc, cx in [
        ("C5", "22uF/10V", FP_C0805, "C45783", 289.56),
        ("C6", "22uF/10V", FP_C0805, "C45783", 298.45),
    ]:
        c = sb.place(
            "Device:C", cref, cval, cx, 58.42, angle=0,
            footprint=cfp, lcsc=clcsc, ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
        )
        sb.junc(cx, 43.18)
        sb.wire(cx, 43.18, *c["1"])
        sb.gnd_at(c["2"], dy=5.08)

    c7 = sb.place(
        "Device:C_Polarized", "C7", "220uF/10V", 308.61, 58.42, angle=0,
        footprint="Capacitor_SMD:CP_Elec_6.3x7.7", lcsc="C128268",
        ref_offset=(4.45, -1.27), val_offset=(4.45, 1.27),
    )
    sb.junc(308.61, 43.18)
    sb.wire(308.61, 43.18, *c7["1"])
    sb.gnd_at(c7["2"], dy=5.08)

    d2 = sb.place(
        "Diode:1N5819WS", "D2", "B5819W", 321.31, 43.18, angle=180,
        footprint=FP_SOD123, lcsc="C8598", mpn="B5819W",
        ref_offset=(0, -4.45), val_offset=(0, 4.45),
    )
    d3 = sb.place(
        "Diode:1N5819WS", "D3", "B5819W", 321.31, 55.88, angle=180,
        footprint=FP_SOD123, lcsc="C8598", mpn="B5819W",
        ref_offset=(0, -4.45), val_offset=(0, 4.45),
    )
    sb.chain(d3["2"], (314.96, 55.88), (314.96, 50.80))
    sb.place_pwr("VBUS", 314.96, 50.80)

    u2 = sb.place(
        "Regulator_Linear:AP2112K-3.3", "U2", "AP2112K-3.3", 353.06, 45.72, angle=0,
        footprint="Package_TO_SOT_SMD:SOT-23-5", lcsc="C51118", mpn="AP2112K-3.3TRG1",
        ref_offset=(0, -8.89), val_offset=(0, -6.35),
    )
    sb.wire(*d2["1"], *u2["1"])
    sb.chain(d3["1"], (330.20, 55.88), (330.20, 43.18))
    sb.junc(330.20, 43.18)
    # OR-diode cathodes → LDO VIN (same class of oversight as V12_FUSED)
    sb.label("V5_OR", 330.20, 43.18, angle=0)
    sb.wire(330.20, 43.18, 330.20, 35.56)
    sb.place_pwr("PWR_FLAG", 330.20, 35.56)
    sb.chain((341.63, 43.18), (341.63, 45.72), u2["3"])
    sb.junc(341.63, 43.18)
    sb.nc(u2["4"])
    sb.gnd_at(u2["2"], dy=10.16)

    c8 = sb.place(
        "Device:C", "C8", "1uF", 336.55, 58.42, angle=0,
        footprint=FP_C0603, lcsc="C15849", ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
    )
    sb.junc(336.55, 43.18)
    sb.wire(336.55, 43.18, *c8["1"])
    sb.gnd_at(c8["2"], dy=5.08)

    sb.wire(*u2["5"], 393.70, 43.18)
    sb.junc(370.84, 43.18)
    sb.rail_at((370.84, 43.18), "+3V3", dy=-5.08)

    for cref, cval, clcsc, cx in [
        ("C9", "10uF", "C19702", 381.00),
        ("C10", "100nF", "C14663", 393.70),
    ]:
        c = sb.place(
            "Device:C", cref, cval, cx, 58.42, angle=0,
            footprint=FP_C0603, lcsc=clcsc, ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
        )
        if cx < 393.70:
            sb.junc(cx, 43.18)
        sb.wire(cx, 43.18, *c["1"])
        sb.gnd_at(c["2"], dy=5.08)

    # =======================================================================
    # BLOCK 3: USB Type-C + ESD Protection (x=12.7..101.6, y=144.78..279.4)
    # =======================================================================
    sb.box("3. USB Type-C + ESD Protection", 12.70, 144.78, 101.60, 279.40)

    j4 = sb.place(
        "Connector:USB_C_Receptacle_USB2.0_16P", "J4", "TYPE-C-31-M-12", 36.83, 208.28, angle=0,
        footprint="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
        lcsc="C165948", mpn="TYPE-C-31-M-12",
        ref_offset=(-5.08, -24.13), val_offset=(-5.08, -21.59),
    )
    sb.wire(*j4["A4"], 77.47, j4["A4"][1])
    sb.rail_at((63.50, j4["A4"][1]), "VBUS", dy=-5.08)
    sb.junc(63.50, j4["A4"][1])
    sb.wire(69.85, j4["A4"][1], 69.85, j4["A4"][1] - 5.08)
    sb.junc(69.85, j4["A4"][1])
    sb.place_pwr("PWR_FLAG", 69.85, j4["A4"][1] - 5.08)

    r3 = sb.place(
        "Device:R", "R3", "5.1k", 63.50, 246.38, angle=0,
        footprint=FP_R0603, lcsc="C23186", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    r4 = sb.place(
        "Device:R", "R4", "5.1k", 55.88, 246.38, angle=0,
        footprint=FP_R0603, lcsc="C23186", ref_offset=(-5.08, -1.905), val_offset=(-5.08, 1.905),
    )
    sb.chain(j4["A5"], (63.50, j4["A5"][1]), r3["1"])
    sb.chain(j4["B5"], (55.88, j4["B5"][1]), r4["1"])
    sb.gnd_at(r3["2"], dy=3.81)
    sb.gnd_at(r4["2"], dy=3.81)

    # U7: USBLC6-2SC6 ESD Protection inline on D-/D+ & VBUS
    # Local pins: 1 I/O1=(-5.08,0), 3 I/O2=(-5.08,-2.54), 6 I/O1=(5.08,0), 4 I/O2=(5.08,-2.54), 5 VBUS=(0,5.08), 2 GND=(0,-7.62)
    u7 = sb.place(
        "Power_Protection:USBLC6-2SC6", "U7", "USBLC6-2SC6", 77.47, 208.28, angle=0,
        footprint="Package_TO_SOT_SMD:SOT-23-6", lcsc="C7519", mpn="USBLC6-2SC6",
        ref_offset=(0, -8.89), val_offset=(0, -6.35),
    )
    sb.wire(77.47, j4["A4"][1], *u7["5"])
    sb.gnd_at(u7["2"], dy=3.81)

    sb.chain(j4["A7"], (59.69, j4["A7"][1]), (59.69, j4["B7"][1]), j4["B7"])
    sb.junc(59.69, j4["B7"][1])
    sb.wire(59.69, j4["B7"][1], *u7["1"])
    sb.stub(u7["6"], "USB_DN", dx=5.08)

    sb.chain(j4["A6"], (59.69, j4["A6"][1]), (59.69, j4["B6"][1]), j4["B6"])
    sb.junc(59.69, j4["A6"][1])
    sb.wire(59.69, j4["A6"][1], *u7["3"])
    sb.stub(u7["4"], "USB_DP", dx=5.08)

    sb.nc(j4["A8"])
    sb.nc(j4["B8"])
    sb.gnd_at(j4["A1"], dy=5.08)
    sb.gnd_at(j4["SH"], dy=5.08)

    # =======================================================================
    # BLOCK 4: MCU (ESP32-C3-MINI-1-N4), Reset, Boot & Status LED
    #          (x=106.68..246.38, y=104.14..279.40)
    # =======================================================================
    sb.box("4. MCU (ESP32-C3-MINI-1-N4) & Strapping/Boot", 106.68, 104.14, 246.38, 279.40)

    u4 = sb.place(
        "RearCore:ESP32-C3-MINI-1", "U4", "ESP32-C3-MINI-1-N4", 193.04, 195.58, angle=0,
        footprint="RearCore:ESP32-C3-MINI-1", lcsc="C2838502", mpn="ESP32-C3-MINI-1-N4",
        ref_offset=(-8.89, -24.13), val_offset=(6.35, -24.13),
    )

    sb.wire(*u4["3"], u4["3"][0], 162.56)
    sb.rail_at((u4["3"][0], 162.56), "+3V3", dy=-3.81)
    sb.junc(u4["3"][0], 165.10)
    sb.wire(u4["3"][0], 165.10, 231.14, 165.10)
    for cref, cval, clcsc, cx in [
        ("C11", "10uF", "C19702", 220.98),
        ("C12", "100nF", "C14663", 231.14),
    ]:
        c = sb.place(
            "Device:C", cref, cval, cx, 172.72, angle=0,
            footprint=FP_C0603, lcsc=clcsc, ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
        )
        if cx < 231.14:
            sb.junc(cx, 165.10)
        sb.wire(cx, 165.10, *c["1"])
        sb.gnd_at(c["2"], dy=2.54)

    sb.gnd_at(u4["1"], dy=5.08)

    r5 = sb.place(
        "Device:R", "R5", "10k", 147.32, 167.64, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
    )
    sb.rail_at(r5["1"], "+3V3", dy=-3.81)
    sb.chain(r5["2"], (147.32, 177.80), u4["8"])
    sb.junc(147.32, 177.80)

    c13 = sb.place(
        "Device:C", "C13", "1uF", 147.32, 187.96, angle=0,
        footprint=FP_C0603, lcsc="C15849", ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
    )
    sb.wire(147.32, 177.80, *c13["1"])
    sb.gnd_at(c13["2"], dy=3.81)

    sw1 = sb.place(
        "Switch:SW_Push", "SW1", "RST", 127.00, 177.80, angle=0,
        footprint="Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", lcsc="C318884",
        ref_offset=(0, -5.08), val_offset=(0, 5.08),
    )
    sb.wire(*sw1["2"], 147.32, 177.80)
    sb.chain(sw1["1"], (116.84, 177.80), (116.84, 185.42))
    sb.place_pwr("GND", 116.84, 185.42)

    tp1 = sb.place(
        "Connector:TestPoint", "TP1", "IO0_AUX", 160.02, u4["12"][1], angle=90,
        footprint="TestPoint:TestPoint_Pad_D1.5mm", in_bom=False,
        ref_offset=(-5.08, -2.54), val_offset=(-5.08, 2.54),
    )
    sb.wire(*u4["12"], *tp1["1"])

    sb.stub(u4["13"], "IMU_INT1", dx=-13.97)

    r7 = sb.place(
        "Device:R", "R7", "10k", 165.10, u4["5"][1], angle=90,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(0, -3.175), val_offset=(0, 3.175),
    )
    sb.wire(*r7["2"], *u4["5"])
    sb.chain(r7["1"], (157.48, u4["5"][1]), (157.48, u4["5"][1] - 3.81))
    sb.place_pwr("+3V3", 157.48, u4["5"][1] - 3.81)

    sb.stub(u4["6"], "RS485_DE", dx=-13.97)
    sb.stub(u4["18"], "EXP_CMD", dx=-13.97)  # GPIO4 → J3-4 (3.3V UART TX / command)
    sb.nc(u4["19"])  # GPIO5 reserved / unused after laser drivers removed
    sb.stub(u4["20"], "I2C_SDA", dx=-13.97)
    sb.stub(u4["21"], "I2C_SCL", dx=-13.97)

    d7 = sb.place(
        "Device:LED", "D7", "BLUE", 156.21, u4["22"][1], angle=180,
        footprint="LED_SMD:LED_0603_1608Metric", lcsc="C72041",
        ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    r8 = sb.place(
        "Device:R", "R8", "1k", 142.24, u4["22"][1], angle=90,
        footprint=FP_R0603, lcsc="C21190", ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.wire(*d7["1"], *u4["22"])
    sb.wire(*r8["2"], *d7["2"])
    sb.chain(r8["1"], (134.62, u4["22"][1]), (134.62, u4["22"][1] - 3.81))
    sb.place_pwr("+3V3", 134.62, u4["22"][1] - 3.81)

    # R19: Dedicated 10k strap pull-up on IO8 to guarantee >0.75*VDD at download boot
    r19 = sb.place(
        "Device:R", "R19", "10k", 168.91, 226.06, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.junc(168.91, u4["22"][1])
    sb.wire(168.91, u4["22"][1], *r19["1"])
    sb.chain(r19["2"], (168.91, 234.95))
    sb.place_pwr("+3V3", 168.91, 234.95, angle=180)

    sb.stub(u4["16"], "WS2812_TX", dx=-13.97)
    sb.chain(u4["23"], (152.40, u4["23"][1]), (152.40, 246.38))
    sb.junc(152.40, 246.38)
    r6 = sb.place(
        "Device:R", "R6", "10k", 152.40, 256.54, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.wire(152.40, 246.38, *r6["1"])
    sb.chain(r6["2"], (152.40, 265.43))
    sb.place_pwr("+3V3", 152.40, 265.43, angle=180)

    sw2 = sb.place(
        "Switch:SW_Push", "SW2", "BOOT_DEMO", 132.08, 246.38, angle=0,
        footprint="Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A", lcsc="C318884",
        ref_offset=(0, -5.08), val_offset=(0, 5.08),
    )
    sb.wire(*sw2["2"], 152.40, 246.38)
    sb.chain(sw2["1"], (121.92, 246.38), (121.92, 254.00))
    sb.place_pwr("GND", 121.92, 254.00)

    sb.stub(u4["30"], "LINK_RX", dx=10.16)
    sb.stub(u4["31"], "LINK_TX", dx=10.16)
    sb.stub(u4["26"], "USB_DN", dx=10.16)
    sb.stub(u4["27"], "USB_DP", dx=10.16)

    # =======================================================================
    # BLOCK 5: RS-485 Bidirectional Transceiver & 3-Axis Accelerometer
    #          (x=251.46..406.40, y=104.14..195.58)
    # =======================================================================
    sb.box("5. RS-485 (SP3485EN Bidirectional) & IMU (LIS3DHTR)", 251.46, 104.14, 406.40, 195.58)

    # U3: SP3485EN at (289.56, 152.40)
    # 1 RO=(279.40,147.32), 2 ~RE=(279.40,149.86), 3 DE=(279.40,152.40), 4 DI=(279.40,157.48)
    # 8 VCC=(289.56,137.16), 5 GND=(289.56,167.64), 6 A=(299.72,144.78), 7 B=(299.72,149.86)
    u3 = sb.place(
        "Interface_UART:SP3485EN", "U3", "SP3485EN-L/TR", 289.56, 152.40, angle=0,
        footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", lcsc="C9945", mpn="SP3485EN-L/TR",
        ref_offset=(-5.08, -17.78), val_offset=(6.35, -17.78),
    )
    sb.rail_at(u3["8"], "+3V3", dy=-5.08)
    sb.gnd_at(u3["5"], dy=5.08)

    c14 = sb.place(
        "Device:C", "C14", "100nF", 302.26, 128.27, angle=0,
        footprint=FP_C0603, lcsc="C14663", ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
    )
    sb.rail_at(c14["1"], "+3V3", dy=-2.54)
    sb.gnd_at(c14["2"], dy=2.54)

    # RO (Pin 1) -> LINK_RX + R9 (10k pull-up to +3V3)
    sb.wire(*u3["1"], 261.62, u3["1"][1])
    sb.label("LINK_RX", 261.62, u3["1"][1], angle=180)
    r9 = sb.place(
        "Device:R", "R9", "10k", 273.05, 134.62, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(-5.08, -1.27), val_offset=(-5.08, 1.27),
    )
    sb.rail_at(r9["1"], "+3V3", dy=-2.54)
    sb.wire(*r9["2"], 273.05, u3["1"][1])
    sb.junc(273.05, u3["1"][1])

    # ~RE (Pin 2) & DE (Pin 3) tied together -> RS485_DE + R10 (10k pull-down at x=260.35)
    sb.chain(u3["2"], (275.59, u3["2"][1]), (275.59, u3["3"][1]), u3["3"])
    sb.junc(275.59, u3["3"][1])
    sb.wire(275.59, u3["3"][1], 260.35, u3["3"][1])
    sb.junc(260.35, u3["3"][1])
    sb.label("RS485_DE", 266.70, u3["3"][1], angle=0)
    r10 = sb.place(
        "Device:R", "R10", "10k", 260.35, 165.10, angle=0,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(-4.45, -1.27), val_offset=(-4.45, 1.27),
    )
    sb.wire(260.35, u3["3"][1], *r10["1"])
    sb.gnd_at(r10["2"], dy=3.81)

    # DI (Pin 4) -> LINK_TX (stops at x=267.97, no crossing with x=260.35!)
    sb.stub(u3["4"], "LINK_TX", dx=-11.43)

    # RS485 A (Pin 6: y=144.78) & B (Pin 7: y=149.86) + Termination JP1/R11 + SM712 TVS (D8)
    sb.wire(*u3["6"], 337.82, u3["6"][1])
    sb.label("RS485_A", 337.82, u3["6"][1], angle=0)
    sb.wire(*u3["7"], 337.82, u3["7"][1])
    sb.label("RS485_B", 337.82, u3["7"][1], angle=0)

    # Termination: A (y=144.78) -> JP1 (vertical at x=312.42, y=156.21) -> R11 (120R at y=168.91) -> B
    # Wait: let's place JP1 & R11 below B (y=149.86) or between A & B? Between 144.78 and 149.86 is 5.08mm;
    # Instead, drop A at x=311.15 down to y=162.56 (crosses B orthogonally without junction), through JP1 & R11 horizontally to x=332.74, then up to B!
    jp1 = sb.place(
        "Jumper:SolderJumper_2_Bridged", "JP1", "TERM_EN", 316.23, 162.56, angle=0,
        footprint="Jumper:SolderJumper-2_P1.3mm_Bridged_RoundedPad1.0x1.5mm",
        in_bom=False, ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    r11 = sb.place(
        "Device:R", "R11", "120R", 328.93, 162.56, angle=90,
        footprint=FP_R0805, lcsc="C17440", ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.junc(311.15, u3["6"][1])
    sb.chain((311.15, u3["6"][1]), jp1["1"])
    sb.wire(*jp1["2"], *r11["1"])
    sb.junc(332.74, u3["7"][1])
    sb.chain(r11["2"], (332.74, 162.56), (332.74, u3["7"][1]))

    # D8: SM712_SOT23 TVS (Pin 1 A1 at -8.89, Pin 2 A2 at +8.89, Pin 3 common at (0, -3.81)->bottom)
    d8 = sb.place(
        "Diode:SM712_SOT23", "D8", "SM712", 321.31, 177.80, angle=0,
        footprint="Package_TO_SOT_SMD:SOT-23", lcsc="C15919", mpn="SM712",
        ref_offset=(0, -5.08), val_offset=(0, -2.54),
    )
    # Connect D8[1] (312.42, 177.80) to A branch at (311.15, 162.56)
    sb.junc(311.15, 162.56)
    sb.chain((311.15, 162.56), (311.15, 177.80), d8["1"])
    # Connect D8[2] (330.20, 177.80) to B branch at (332.74, 162.56)
    sb.junc(332.74, 162.56)
    sb.chain((332.74, 162.56), (332.74, 177.80), d8["2"])
    sb.gnd_at(d8["3"], dy=3.81)

    # U5: LIS3DH (LIS3DHTR) at (378.46, 152.40)
    # Pins:
    #   1 VDD_IO=(375.92,139.70), 14 VDD=(381.00,139.70)
    #   5/10/12 GND=(378.46,167.64)
    #   11 INT1=(365.76,147.32), 9 INT2=(365.76,149.86), 7 SDO=(365.76,152.40)
    #   6 SDI=(365.76,154.94), 4 SPC=(365.76,157.48), 8 CS=(365.76,160.02)
    #   3 NC=(388.62,144.78), 2 NC=(388.62,147.32)
    #   16 ADC1=(391.16,149.86), 15 ADC2=(391.16,152.40), 13 ADC3=(391.16,154.94)
    u5 = sb.place(
        "Sensor_Motion:LIS3DH", "U5", "LIS3DHTR", 378.46, 152.40, angle=0,
        footprint="Package_LGA:LGA-16_3x3mm_P0.5mm_LayoutBorder3x5y",
        lcsc="C15134", mpn="LIS3DHTR",
        ref_offset=(-5.08, -16.51), val_offset=(5.08, -16.51),
    )
    # VDD_IO & VDD tied to +3V3
    sb.chain(u5["1"], (u5["1"][0], 134.62), (u5["14"][0], 134.62), u5["14"])
    sb.junc(u5["1"][0], 134.62)
    sb.rail_at((u5["1"][0], 134.62), "+3V3", dy=-2.54)
    sb.gnd_at(u5["5"], dy=5.08)

    # Decoupling C15 (10uF) & C16 (100nF) for U5
    for cref, cval, clcsc, cx in [
        ("C15", "10uF", "C19702", 391.16),
        ("C16", "100nF", "C14663", 398.78),
    ]:
        c = sb.place(
            "Device:C", cref, cval, cx, 123.19, angle=0,
            footprint=FP_C0603, lcsc=clcsc, ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
        )
        sb.rail_at(c["1"], "+3V3", dy=-2.54)
        sb.gnd_at(c["2"], dy=2.54)

    # LIS3DH Left pins: INT1 (11), INT2 (9), SDO (7 -> 10k R20 to GND for addr 0x18), SDI (6), SPC (4), CS (8->+3V3)
    sb.stub(u5["11"], "IMU_INT1", dx=-10.16)
    sb.nc(u5["9"])
    r20 = sb.place(
        "Device:R", "R20", "10k", 358.14, u5["7"][1], angle=90,
        footprint=FP_R0603, lcsc="C25804", ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.wire(*r20["2"], *u5["7"])
    sb.wire(*r20["1"], 351.79, u5["7"][1])
    sb.place_pwr("GND", 351.79, u5["7"][1], angle=270)

    # SDI (Pin 6: y=154.94) -> I2C_SDA + R12 (4.7k pull-up)
    sb.wire(*u5["6"], 347.98, u5["6"][1])
    sb.label("I2C_SDA", 347.98, u5["6"][1], angle=180)
    # SPC (Pin 4: y=157.48) -> I2C_SCL + R13 (4.7k pull-up)
    sb.wire(*u5["4"], 347.98, u5["4"][1])
    sb.label("I2C_SCL", 347.98, u5["4"][1], angle=180)

    # CS (Pin 8: y=160.02) -> +3V3 (I2C mode enable)
    sb.chain(u5["8"], (360.68, u5["8"][1]), (360.68, 165.10))
    sb.place_pwr("+3V3", 360.68, 165.10, angle=180)

    # I2C Pull-ups R12 (SDA) & R13 (SCL) placed cleanly above at y=125.73, x=349.25 & 356.87
    r12 = sb.place(
        "Device:R", "R12", "4.7k", 349.25, 125.73, angle=0,
        footprint=FP_R0603, lcsc="C23162", ref_offset=(-4.45, -1.27), val_offset=(-4.45, 1.27),
    )
    sb.rail_at(r12["1"], "+3V3", dy=-2.54)
    sb.stub(r12["2"], "I2C_SDA", dx=5.08)

    r13 = sb.place(
        "Device:R", "R13", "4.7k", 363.22, 125.73, angle=0,
        footprint=FP_R0603, lcsc="C23162", ref_offset=(3.81, -1.27), val_offset=(3.81, 1.27),
    )
    sb.rail_at(r13["1"], "+3V3", dy=-2.54)
    sb.stub(r13["2"], "I2C_SCL", dx=5.08)

    # LIS3DH unused right pins: NC (2, 3), ADC1..3 (16, 15, 13)
    for pnum in ["2", "3", "16", "15", "13"]:
        sb.nc(u5[pnum])

    # =======================================================================
    # BLOCK 6: WS2812 5V Shifter (laser drive moved to expansion unit via J3)
    # =======================================================================
    sb.box("6. Output Drivers (WS2812 5V Shifter)", 251.46, 198.12, 330.20, 250.19)

    u6 = sb.place(
        "Logic_LevelTranslator:SN74LV1T34DBV", "U6", "SN74LV1T34DBVR", 279.40, 218.44, angle=0,
        footprint="Package_TO_SOT_SMD:SOT-23-5", lcsc="C100022", mpn="SN74LV1T34DBVR",
        ref_offset=(-5.08, -10.16), val_offset=(5.08, -10.16),
    )
    sb.nc(u6["1"])
    sb.stub(u6["2"], "WS2812_TX", dx=-10.16)
    sb.rail_at(u6["5"], "+5V", dy=-2.54)
    sb.gnd_at(u6["3"], dy=2.54)

    c17 = sb.place(
        "Device:C", "C17", "100nF", 261.62, 236.22, angle=0,
        footprint=FP_C0603, lcsc="C14663", ref_offset=(3.81, -1.905), val_offset=(3.81, 1.905),
    )
    sb.rail_at(c17["1"], "+5V", dy=-2.54)
    sb.gnd_at(c17["2"], dy=2.54)

    r14 = sb.place(
        "Device:R", "R14", "330R", 294.64, 218.44, angle=90,
        footprint=FP_R0603, lcsc="C23138", ref_offset=(0, -3.81), val_offset=(0, 3.81),
    )
    sb.wire(*u6["4"], *r14["1"])
    sb.stub(r14["2"], "LED_DATA_5V", dx=6.35)

    return sb


# ---------------------------------------------------------------------------
# 6. Project Tables, .kicad_pro, and Initial .kicad_pcb (34 x 44 mm)
# ---------------------------------------------------------------------------

def write_project_files():
    with open(f"{OUT_DIR}/sym-lib-table", "w") as f:
        f.write(
            '(sym_lib_table\n'
            '  (version 7)\n'
            '  (lib (name "RearCore")(type "KiCad")(uri "${KIPRJMOD}/RearCore.kicad_sym")(options "")(descr "LaserBlinker Rear Core Custom Symbols"))\n'
            ')\n'
        )

    with open(f"{OUT_DIR}/fp-lib-table", "w") as f:
        f.write(
            '(fp_lib_table\n'
            '  (version 7)\n'
            '  (lib (name "RearCore")(type "KiCad")(uri "${KIPRJMOD}/footprints.pretty")(options "")(descr "LaserBlinker Rear Core Custom Footprints"))\n'
            ')\n'
        )

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
    pro["board"]["design_settings"]["track_widths"] = [0.0, 0.2, 0.3, 0.5, 0.8, 1.2]
    pro["board"]["design_settings"]["via_dimensions"] = [
        {"diameter": 0.0, "drill": 0.0},
        {"diameter": 0.6, "drill": 0.3},
        {"diameter": 0.8, "drill": 0.4},
    ]
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
        "V12_RAW": 0.8,
        "V12_FUSED": 0.8,
        "BUCK_SW": 0.8,
        "+12V": 0.6,
        "+5V": 0.5,
        "VBUS": 0.5,
        "V5_OR": 0.5,
        "+3V3": 0.25,
        "GND": 0.25,
        "EXP_CMD": 0.2,
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

    # Initial 2-layer PCB with 34 x 44 mm rounded-rectangle board outline (Edge.Cuts)
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
\t\t(title "LaserBlinker Rear Core PCB")
\t\t(date "2026-11-12")
\t\t(rev "v1.0")
\t\t(comment 1 "Target size: 34 x 44 mm, 2-layer 1.6mm FR4, single-sided SMD PCBA")
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
\t\t(end 134 124)
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
    os.makedirs(f"{OUT_DIR}/footprints.pretty", exist_ok=True)
    generate_c3_mini_footprint()
    write_custom_sym_lib()
    write_project_files()
    sb = build_schematic()
    sch_path = f"{OUT_DIR}/{PROJ}.kicad_sch"
    with open(sch_path, "w") as f:
        f.write(sb.build_sexp())
    print(f"Generated {sch_path} with {len(sb.symbols)} symbol instances and {len(sb.wires)} wires.")


if __name__ == "__main__":
    main()
