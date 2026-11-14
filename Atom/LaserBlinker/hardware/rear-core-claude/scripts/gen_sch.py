"""design.py から KiCad 回路図・プロジェクト・自作ライブラリを生成する。

実行: python3 scripts/gen_sch.py   （hardware/rear-core-claude/ に出力）
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from design import PARTS, PROJECT, PWR_FLAG_NETS  # noqa: E402
from sexp import KICAD, Q, dump, find, find1, flatten_symbol, load_lib, parse, q, symbol_pins, uid  # noqa: E402

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBNAME = "LaserBlinker"
ROOT_UUID = uid(PROJECT, "root")
FONT = ["effects", ["font", ["size", "1.27", "1.27"]]]
# I2C モードでは SDO/SA0 はアドレス選択入力（GND 直結）なので出力扱いを外す
PIN_TYPE_OVERRIDE = {("Sensor_Motion:LIS3DH", "7"): "passive"}


def f(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


# ------------------------------------------------------------------
# 自作ライブラリ: ESP32-C3-MINI-1（シンボル／フットプリント／簡易3D）
# ------------------------------------------------------------------
ESP_LEFT = [("3", "3V3", "power_in"), ("8", "EN", "input"), ("12", "IO0", "bidirectional"),
            ("13", "IO1", "bidirectional"), ("5", "IO2", "bidirectional"), ("6", "IO3", "bidirectional"),
            ("18", "IO4", "bidirectional"), ("19", "IO5", "bidirectional")]
ESP_RIGHT = [("20", "IO6", "bidirectional"), ("21", "IO7", "bidirectional"), ("22", "IO8", "bidirectional"),
             ("23", "IO9", "bidirectional"), ("16", "IO10", "bidirectional"), ("26", "IO18/USB_D-", "bidirectional"),
             ("27", "IO19/USB_D+", "bidirectional"), ("30", "RXD0/IO20", "bidirectional"),
             ("31", "TXD0/IO21", "bidirectional")]
ESP_GND = ["1", "2", "11", "14"] + [str(n) for n in range(36, 54)]
ESP_NC = ["4", "7", "9", "10", "15", "17", "24", "25", "28", "29", "32", "33", "34", "35"]


def esp_symbol():
    name = "ESP32-C3-MINI-1"
    pins = []

    def pin(num, nm, typ, x, y, ang, hide=False):
        p = ["pin", typ, "line", ["at", f(x), f(y), str(ang)], ["length", "2.54"]]
        if hide:
            p.append(["hide", "yes"])
        p += [["name", q(nm), FONT], ["number", q(num), FONT]]
        pins.append(p)

    y = 22.86
    for num, nm, typ in ESP_LEFT:
        pin(num, nm, typ, -15.24, y, 0)
        y -= 2.54
    y = 22.86
    for num, nm, typ in ESP_RIGHT:
        pin(num, nm, typ, 15.24, y, 180)
        y -= 2.54
    for i, num in enumerate(ESP_GND):
        pin(num, "GND", "power_in" if i == 0 else "passive", 0, -27.94, 90, hide=i > 0)
    for num in ESP_NC:
        pin(num, "NC", "no_connect", -12.7, -22.86, 0, hide=True)
    body = ["rectangle", ["start", "-12.7", "25.4"], ["end", "12.7", "-25.4"],
            ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", "background"]]]

    def prop(k, v, x, y, hide=False):
        p = ["property", q(k), q(v), ["at", f(x), f(y), "0"]]
        if hide:
            p.append(["hide", "yes"])
        return p + [FONT]

    return ["symbol", q(name), ["pin_names", ["offset", "1.016"]], ["exclude_from_sim", "no"],
            ["in_bom", "yes"], ["on_board", "yes"],
            prop("Reference", "U", -12.7, 26.67), prop("Value", name, 0, 26.67),
            prop("Footprint", f"{LIBNAME}:{name}", 0, -30.48, True),
            prop("Datasheet", "https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.pdf", 0, -33, True),
            prop("Description", "ESP32-C3 Wi-Fi/BLE module, PCB antenna, 13.2x16.6mm", 0, -35.5, True),
            prop("LCSC", "C2838502", 0, -38, True),
            ["symbol", q(name + "_0_1"), body], ["symbol", q(name + "_1_1")] + pins]


def write_libs():
    sym = esp_symbol()
    lib = ["kicad_symbol_lib", ["version", "20241209"], ["generator", q("rear_core_claude")],
           ["generator_version", q("10.0")], sym]
    open(f"{OUT}/{LIBNAME}.kicad_sym", "w", encoding="utf-8").write(dump(lib) + "\n")

    os.makedirs(f"{OUT}/{LIBNAME}.pretty", exist_ok=True)
    src = open(f"{KICAD}/footprints/RF_Module.pretty/ESP32-C6-MINI-1.kicad_mod", encoding="utf-8").read()
    src = src.replace('(footprint "ESP32-C6-MINI-1"', '(footprint "ESP32-C3-MINI-1"')
    src = src.replace('(property "Value" "ESP32-C6-MINI-1"', '(property "Value" "ESP32-C3-MINI-1"')
    src = re.sub(r'\(descr "[^"]*"\)',
                 '(descr "ESP32-C3-MINI-1 (land pattern identical to ESP32-C6-MINI-1: 13.2x16.6mm, 53 pads, 0.8mm pitch)")',
                 src)
    src = re.sub(r'\(model "[^"]*"', '(model "${KIPRJMOD}/3d/ESP32-C3-MINI-1.wrl"', src)
    open(f"{OUT}/{LIBNAME}.pretty/ESP32-C3-MINI-1.kicad_mod", "w", encoding="utf-8").write(src)

    # 簡易3D（VRML: 1単位 = 2.54mm、Y軸は基板上方向が正）
    os.makedirs(f"{OUT}/3d", exist_ok=True)

    def box(cx, cy, cz, sx, sy, sz, rgb):
        u = 2.54
        return (f"Transform {{ translation {cx/u:.4f} {cy/u:.4f} {cz/u:.4f} children Shape {{"
                f" appearance Appearance {{ material Material {{ diffuseColor {rgb} specularColor 0.3 0.3 0.3 }} }}"
                f" geometry Box {{ size {sx/u:.4f} {sy/u:.4f} {sz/u:.4f} }} }} }}\n")
    # モジュール外形 y: -11.15..5.75（フットプリント座標）→ VRML では符号反転
    wrl = "#VRML V2.0 utf8\n"
    wrl += box(0, 2.7, 0.4, 13.2, 16.6, 0.8, "0.05 0.05 0.08")          # 基板
    wrl += box(0, -0.1, 1.6, 12.4, 10.6, 1.6, "0.75 0.75 0.78")         # シールド缶
    wrl += box(0, 8.3, 0.85, 11.5, 4.2, 0.1, "0.75 0.6 0.2")            # アンテナ導体
    open(f"{OUT}/3d/ESP32-C3-MINI-1.wrl", "w").write(wrl)

    open(f"{OUT}/sym-lib-table", "w").write(
        f'(sym_lib_table\n\t(version 7)\n\t(lib (name "{LIBNAME}")(type "KiCad")'
        f'(uri "${{KIPRJMOD}}/{LIBNAME}.kicad_sym")(options "")(descr "project parts"))\n)\n')
    open(f"{OUT}/fp-lib-table", "w").write(
        f'(fp_lib_table\n\t(version 7)\n\t(lib (name "{LIBNAME}")(type "KiCad")'
        f'(uri "${{KIPRJMOD}}/{LIBNAME}.pretty")(options "")(descr "project footprints"))\n)\n')
    return sym


# ------------------------------------------------------------------
# 回路図
# ------------------------------------------------------------------
def label_len(s):
    return len(s) * 1.05 + 2.0


def build_schematic(esp_sym):
    load_lib(LIBNAME, f"{OUT}/{LIBNAME}.kicad_sym")
    parts = list(PARTS)
    for i, net in enumerate(PWR_FLAG_NETS, 1):
        parts.append(dict(ref=f"#FLG0{i}", lib="power:PWR_FLAG", value="PWR_FLAG", fp="", lcsc="",
                          pins={"1": net}, group="PWR_FLAG"))

    lib_symbols, symdefs = {}, {}
    for p in parts:
        lib, name = p["lib"].split(":")
        if p["lib"] not in symdefs:
            s = flatten_symbol(lib, name)
            for sub in find(s, "symbol"):
                for pin in find(sub, "pin"):
                    t = PIN_TYPE_OVERRIDE.get((p["lib"], str(find1(pin, "number")[1])))
                    if t:
                        pin[1] = t
            symdefs[p["lib"]] = s
            emb = list(s)
            emb[1] = Q(p["lib"])
            lib_symbols[p["lib"]] = emb

    items, errors = [], []

    def snap(v):
        return round(v / 2.54) * 2.54

    # 1パス目: 各シンボルのセル寸法（ラベル長込み）
    geo = {}
    for p in parts:
        pins = symbol_pins(symdefs[p["lib"]])
        known = {pn[0] for pn in pins}
        for num in p["pins"]:
            if num not in known:
                errors.append(f"{p['ref']}: pin {num} not in symbol {p['lib']}")
        xs = [pn[3] for pn in pins] or [0]
        ys = [-pn[4] for pn in pins] or [0]
        xmin, xmax = min(xs + [-2.54]), max(xs + [2.54])
        ymin, ymax = min(ys + [-2.54]), max(ys + [2.54])
        margin = {0: 0, 90: 0, 180: 0, 270: 0}
        for num, nm, typ, px, py, ang, hid in pins:
            if p["pins"].get(num):
                margin[ang] = max(margin[ang], label_len(p["pins"][num]))
        left, right, bottom, top = margin[0], margin[180], margin[90], margin[270]
        top = max(top, 1.27) + 5.08  # Reference / Value の行
        geo[p["ref"]] = dict(pins=pins, xmin=xmin, ymin=ymin, left=left, top=top,
                             w=left + (xmax - xmin) + right + 5.08, h=top + (ymax - ymin) + bottom + 5.08)

    # 2パス目: グループ内をフロー配置 → グループをシートへ棚詰め
    GROUP_W, SHEET_W, X0, Y0 = 150.0, 570.0, 12.7, 17.78
    groups = []
    for p in parts:
        if not groups or groups[-1][0] != p["group"]:
            groups.append([p["group"], []])
        groups[-1][1].append(p)
    blocks = []
    for name, members in groups:
        cx = cy = row_h = bw = 0.0
        local = {}
        for p in members:
            g = geo[p["ref"]]
            if cx > 0 and cx + g["w"] > GROUP_W:
                cx, cy, row_h = 0.0, cy + row_h, 0.0
            local[p["ref"]] = (cx, cy)
            cx += g["w"]
            bw = max(bw, cx)
            row_h = max(row_h, g["h"])
        blocks.append((name, local, bw, cy + row_h + 6.35))
    pos, sx_, sy_, shelf_h = {}, X0, Y0, 0.0
    for name, local, bw, bh in blocks:
        if sx_ > X0 and sx_ + bw > SHEET_W:
            sx_, sy_, shelf_h = X0, sy_ + shelf_h + 5.08, 0.0
        items.append(["text", q(f"■ {name}"), ["exclude_from_sim", "no"], ["at", f(sx_), f(sy_ + 3.81), "0"],
                      ["effects", ["font", ["size", "2.54", "2.54"], ["bold", "yes"]],
                       ["justify", "left", "bottom"]], ["uuid", q(uid(PROJECT, "grp", name))]])
        items.append(["rectangle", ["start", f(sx_ - 2.54), f(sy_)],
                      ["end", f(sx_ + bw), f(sy_ + bh)],
                      ["stroke", ["width", "0.15"], ["type", "dash"], ["color", "120", "120", "120", "1"]],
                      ["fill", ["type", "none"]], ["uuid", q(uid(PROJECT, "box", name))]])
        for ref, (lx, ly) in local.items():
            pos[ref] = (sx_ + lx, sy_ + 6.35 + ly)
        sx_ += bw + 7.62
        shelf_h = max(shelf_h, bh)
    sheet_h = sy_ + shelf_h

    for p in parts:
        g = geo[p["ref"]]
        pins, xmin, ymin, top = g["pins"], g["xmin"], g["ymin"], g["top"]
        cx, cy = pos[p["ref"]]
        X = snap(cx + g["left"] - xmin)
        Y = snap(cy + top - ymin)

        ref = p["ref"]
        is_flag = ref.startswith("#")
        su = uid(PROJECT, "sym", ref)
        top_y = Y + ymin - top + 5.08

        def prop(k, v, x, y, hide=False, just=None):
            e = ["effects", ["font", ["size", "1.27", "1.27"]]]
            if just:
                e.append(["justify"] + just)
            out = ["property", q(k), q(v), ["at", f(x), f(y), "0"]]
            if hide:
                out.append(["hide", "yes"])
            return out + [e]

        node = ["symbol", ["lib_id", q(p["lib"])], ["at", f(X), f(Y), "0"], ["unit", "1"],
                ["exclude_from_sim", "no"],
                ["in_bom", "no" if is_flag or p["lib"].startswith(("Jumper:", "Connector:TestPoint")) else "yes"],
                ["on_board", "no" if is_flag else "yes"], ["dnp", "no"], ["uuid", q(su)],
                prop("Reference", ref, X + xmin, top_y - 3.81, hide=is_flag, just=["left"]),
                prop("Value", p["value"], X + xmin, top_y - 1.27, just=["left"]),
                prop("Footprint", p["fp"], X, Y, hide=True),
                prop("Datasheet", "", X, Y, hide=True),
                prop("Description", "", X, Y, hide=True)]
        if p.get("lcsc"):
            node.append(prop("LCSC", p["lcsc"], X, Y, hide=True))
        for num in sorted({pn[0] for pn in pins}):
            node.append(["pin", q(num), ["uuid", q(uid(PROJECT, "pin", ref, num))]])
        node.append(["instances", ["project", q(PROJECT),
                                   ["path", q("/" + ROOT_UUID), ["reference", q(ref)], ["unit", "1"]]]])
        items.append(node)

        done = {}
        for num, nm, typ, px, py, ang, hid in pins:
            sx, sy = round(X + px, 4), round(Y - py, 4)
            net = p["pins"].get(num)
            key = (sx, sy)
            if key in done:
                if net and done[key] and done[key] != net:
                    errors.append(f"{ref}: stacked pins at {key} have different nets")
                if net and not done[key]:
                    done[key] = net
                continue
            done[key] = net
        for (sx, sy), net in done.items():
            pinang = next(pn[5] for pn in pins if (round(X + pn[3], 4), round(Y - pn[4], 4)) == (sx, sy))
            types = [pn[2] for pn in pins if (round(X + pn[3], 4), round(Y - pn[4], 4)) == (sx, sy)]
            if net:
                la = (pinang + 180) % 360
                just = ["left", "bottom"] if la in (0, 90) else ["right", "bottom"]
                items.append(["label", q(net), ["at", f(sx), f(sy), str(la)],
                              ["effects", ["font", ["size", "1.27", "1.27"]], ["justify"] + just],
                              ["uuid", q(uid(PROJECT, "lbl", ref, sx, sy))]])
            elif not all(t == "no_connect" for t in types):
                items.append(["no_connect", ["at", f(sx), f(sy)], ["uuid", q(uid(PROJECT, "nc", ref, sx, sy))]])

    sch = ["kicad_sch", ["version", "20250114"], ["generator", q("eeschema")],
           ["generator_version", q("10.0")], ["uuid", q(ROOT_UUID)], ["paper", q("A2")],
           ["title_block", ["title", q("LaserBlinker 後方コア PCB（Claude 版）")],
            ["date", q("2026-11-12")], ["rev", q("0.1")],
            ["comment", "1", q("docs/rear-pcb-design.md 準拠 / scripts/gen_sch.py で自動生成")]],
           ["lib_symbols"] + list(lib_symbols.values())]
    sch += items
    sch.append(["sheet_instances", ["path", q("/"), ["page", q("1")]]])
    sch.append(["embedded_fonts", "no"])
    open(f"{OUT}/{PROJECT}.kicad_sch", "w", encoding="utf-8").write(dump(sch) + "\n")
    return errors


def write_project():
    from design import NET_WIDTH
    classes = [{"name": "Default", "clearance": 0.15, "track_width": 0.2, "via_diameter": 0.6,
                "via_drill": 0.3, "wire_width": 6, "bus_width": 12, "line_style": 0,
                "schematic_color": "rgba(0, 0, 0, 0.000)", "pcb_color": "rgba(0, 0, 0, 0.000)",
                "diff_pair_gap": 0.25, "diff_pair_width": 0.2, "diff_pair_via_gap": 0.25,
                "microvia_diameter": 0.3, "microvia_drill": 0.1, "priority": 2147483647}]
    assigns = []
    for w in sorted(set(NET_WIDTH.values())):
        nm = f"W{int(w*1000)}"
        c = dict(classes[0], name=nm, track_width=w, priority=0, clearance=0.2 if w >= 0.6 else 0.15)
        classes.append(c)
        for net, ww in NET_WIDTH.items():
            if ww == w:
                assigns.append({"netclass": nm, "pattern": "/" + net})
    pro = {
        "meta": {"filename": f"{PROJECT}.kicad_pro", "version": 3},
        "board": {"design_settings": {"rules": {
            "min_clearance": 0.15, "min_track_width": 0.15, "min_via_diameter": 0.5,
            "min_through_hole_diameter": 0.3, "min_copper_edge_clearance": 0.3,
            "min_hole_to_hole": 0.25}}},
        "net_settings": {"classes": classes, "netclass_patterns": assigns, "meta": {"version": 4}},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [[ROOT_UUID, "Root"]],
        "erc": {"rule_severities": {"lib_symbol_issues": "warning", "footprint_link_issues": "ignore",
                                    "lib_symbol_mismatch": "ignore"}},
    }
    open(f"{OUT}/{PROJECT}.kicad_pro", "w").write(json.dumps(pro, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    esp = write_libs()
    write_project()
    errs = build_schematic(esp)
    for e in errs:
        print("ERROR:", e)
    print("schematic written:", f"{OUT}/{PROJECT}.kicad_sch", "errors:", len(errs))
    sys.exit(1 if errs else 0)
