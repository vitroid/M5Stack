"""design.py から KiCad 基板を生成（部品配置 → Freerouting 自動配線 → GND ベタ）。

KiCad 同梱の Python で実行する:
  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 scripts/gen_pcb.py
"""
import math
import os
import subprocess
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from design import NET_WIDTH, PARTS, PROJECT  # noqa: E402
from sexp import KICAD, uid  # noqa: E402

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB = f"{OUT}/{PROJECT}.kicad_pcb"
FREEROUTING = os.path.expanduser("~/.cache/freerouting/freerouting-1.9.0.jar")
OX, OY = 100.0, 100.0          # 基板左上の座標
EDGE = 0.5                     # 縁から部品までの最小距離
GAP = 0.15                     # コートヤード同士の追加すき間
SIZES = [(30, 40), (35, 45), (35, 50), (38, 50), (40, 50), (40, 55), (45, 55)]

MM = pcbnew.FromMM


def V(x, y):
    return pcbnew.VECTOR2I_MM(OX + x, OY + y)


def to_mm(v):
    return pcbnew.ToMM(v.x) - OX, pcbnew.ToMM(v.y) - OY


def load_fp(spec):
    lib, name = spec.split(":")
    path = f"{OUT}/{lib}.pretty" if lib == "LaserBlinker" else f"{KICAD}/footprints/{lib}.pretty"
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise RuntimeError(f"footprint not found: {spec}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def courtyard(fp):
    xs, ys = [], []
    boxes = [it.GetBoundingBox() for it in fp.GraphicalItems() if it.GetLayer() == pcbnew.F_CrtYd]
    if not boxes:
        boxes = [fp.GetBoundingBox(False)]
    for b in boxes:
        for v in (b.GetOrigin(), b.GetEnd()):
            x, y = to_mm(v)
            xs.append(x)
            ys.append(y)
    return [min(xs), min(ys), max(xs), max(ys)]


def pad_pos(fp, num):
    for p in fp.Pads():
        if p.GetNumber() == num:
            return to_mm(p.GetPosition())
    raise KeyError(num)


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def unconnected_pin_nets():
    """回路図ネットリストで未接続ピンに付く単独ネット名（check_sch.py が出力）。"""
    import xml.etree.ElementTree as ET
    root = ET.parse(f"{OUT}/out_netlist.xml").getroot()
    out = {}
    for net in root.iter("net"):
        if net.get("name", "").startswith("unconnected-"):
            for node in net.iter("node"):
                out[(node.get("ref"), node.get("pin"))] = net.get("name")
    return out


def build(W, H):
    nc_nets = unconnected_pin_nets()
    board = pcbnew.NewBoard(PCB)
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)

    nets = {}
    for p in PARTS:
        for n in p["pins"].values():
            if n not in nets:
                ni = pcbnew.NETINFO_ITEM(board, "/" + n)
                board.Add(ni)
                nets[n] = ni

    fps = {}
    for p in PARTS:
        fp = load_fp(p["fp"])
        fp.SetReference(p["ref"])
        fp.SetValue(p["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + uid(PROJECT, "sym", p["ref"])))
        if p.get("lcsc"):
            fp.SetField("LCSC", p["lcsc"])
            f = fp.GetField("LCSC")
            f.SetVisible(False)
            f.SetLayer(pcbnew.F_Fab)
        ref = fp.Reference()
        ref.SetLayer(pcbnew.F_Fab)
        ref.SetTextSize(pcbnew.VECTOR2I(MM(0.6), MM(0.6)))
        ref.SetTextThickness(MM(0.1))
        ref.SetPosition(fp.GetPosition())
        if p["ref"] in ("U5", "USB1"):
            fp.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
        board.Add(fp)
        for pad in fp.Pads():
            n = p["pins"].get(pad.GetNumber())
            if n:
                pad.SetNet(nets[n])
            elif (p["ref"], pad.GetNumber()) in nc_nets:
                ni = pcbnew.NETINFO_ITEM(board, nc_nets[(p["ref"], pad.GetNumber())])
                board.Add(ni)
                pad.SetNet(ni)
        fps[p["ref"]] = fp

    # 外形
    pts = [(0, 0), (W, 0), (W, H), (0, H)]
    for i in range(4):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(*pts[i]))
        s.SetEnd(V(*pts[(i + 1) % 4]))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(MM(0.1))
        board.Add(s)

    obstacles = []

    def place_edge(ref, rot, side, x=None, y=None):
        """コートヤードを基板の縁に揃えて固定配置。"""
        fp = fps[ref]
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(V(0, 0))
        b = courtyard(fp)
        cx = (b[0] + b[2]) / 2 if x is None else x
        cy = (b[1] + b[3]) / 2 if y is None else y
        dx = {"left": -b[0], "right": W - b[2]}.get(side, cx - (b[0] + b[2]) / 2) if side in ("left", "right") else cx - (b[0] + b[2]) / 2
        dy = {"top": -b[1], "bottom": H - b[3]}.get(side, 0) if side in ("top", "bottom") else cy - (b[1] + b[3]) / 2
        if side == "bottom-left":
            dx, dy = -b[0], H - b[3]
        if side == "bottom-right":
            dx, dy = W - b[2], H - b[3]
        fp.SetPosition(V(dx, dy))
        obstacles.append(courtyard(fp))

    # ESP32: アンテナを上辺に。上 5.55mm はアンテナ禁止帯
    u4 = fps["U4"]
    u4.SetPosition(V(W / 2, 11.15))
    obstacles.append([W / 2 - 6.8, 0, W / 2 + 6.8, 16.95])
    obstacles.append([-1, -1, W + 1, 5.55])

    # USB-C: 開口を右辺へ（信号パッドが基板内側に来る向きを選ぶ）
    usb = fps["USB1"]
    best = None
    for rot in (0, 90, 180, 270):
        usb.SetOrientationDegrees(rot)
        usb.SetPosition(V(0, 0))
        sig = [to_mm(p.GetPosition()) for p in usb.Pads() if p.GetNumber().startswith(("A", "B"))]
        mx = sum(s[0] for s in sig) / len(sig)
        if best is None or mx < best[1]:
            best = (rot, mx)
    place_edge("USB1", best[0], "right", y=24.0)
    place_edge("J1", 0, "bottom-left")
    place_edge("J3", 0, "bottom-right")
    place_edge("J2", 90, "left", y=H - 15.5)

    # 自動配置
    offsets = []
    step, R = 0.25, 30.0
    n = int(R / step)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            d = math.hypot(i * step, j * step)
            if d <= R:
                offsets.append((d, i * step, j * step))
    offsets.sort()

    placed = {"U4", "USB1", "J1", "J2", "J3"}

    def try_place(p):
        fp = fps[p["ref"]]
        near = p.get("near")
        if near is None:
            return True
        if isinstance(near[0], str):
            if near[0] not in placed:
                return False
            tx, ty = pad_pos(fps[near[0]], near[1])
            tnet = next(pp for pp in PARTS if pp["ref"] == near[0])["pins"][near[1]]
            key = [k for k, v in p["pins"].items() if v == tnet]
        else:
            tx, ty = near
            key = []
        rots = (0, 90, 180, 270)
        best = None
        for rot in rots:
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(V(0, 0))
            b = courtyard(fp)
            kx, ky = pad_pos(fp, key[0]) if key else (0.0, 0.0)
            for d, ox, oy in offsets:
                if best and d >= best[0]:
                    break
                px, py = tx - kx + ox, ty - ky + oy
                bb = [b[0] + px - GAP, b[1] + py - GAP, b[2] + px + GAP, b[3] + py + GAP]
                if bb[0] < EDGE or bb[1] < EDGE or bb[2] > W - EDGE or bb[3] > H - EDGE:
                    continue
                if any(overlap(bb, o) for o in obstacles):
                    continue
                best = (d, rot, px, py)
                break
        if best is None:
            raise RuntimeError(f"no room for {p['ref']}")
        fp.SetOrientationDegrees(best[1])
        fp.SetPosition(V(best[2], best[3]))
        obstacles.append(courtyard(fp))
        placed.add(p["ref"])
        return True

    def area(p):
        fp = fps[p["ref"]]
        fp.SetOrientationDegrees(0)
        b = courtyard(fp)
        return (b[2] - b[0]) * (b[3] - b[1])

    todo = [p for p in PARTS if p["ref"] not in placed]
    first = [p for p in todo if p["ref"][0] in "UQ"]
    big = sorted((p for p in todo if p not in first and area(p) > 12), key=area, reverse=True)
    caps = [p for p in todo if p not in first and p not in big
            and (p["value"] == "100nF" or p["value"].startswith("10uF"))]
    rest = [p for p in todo if p not in first and p not in big and p not in caps]
    queue = first + big + caps + rest
    while queue:
        progressed = False
        for p in list(queue):
            if try_place(p):
                queue.remove(p)
                progressed = True
        if not progressed:
            raise RuntimeError("unresolved anchors: " + ", ".join(p["ref"] for p in queue))
    return board, nets


def add_zone(board, net, layer, W, H):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net)
    z.SetMinThickness(MM(0.2))
    z.SetLocalClearance(MM(0.2))
    z.SetThermalReliefGap(MM(0.3))
    z.SetThermalReliefSpokeWidth(MM(0.4))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in [(0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, H - 0.3), (0.3, H - 0.3)]:
        ol.Append(V(x, y))
    board.Add(z)
    return z


def route(board, nets):
    dsn, ses = f"{OUT}/out_route.dsn", f"{OUT}/out_route.ses"
    for f in (dsn, ses):
        if os.path.exists(f):
            os.remove(f)
    pcbnew.ExportSpecctraDSN(board, dsn)
    cmd = ["java", "-Djava.awt.headless=false", "-jar", FREEROUTING, "-de", dsn, "-do", ses, "-mp", "60", "-mt", "0"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if not os.path.exists(ses):
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise RuntimeError("freerouting failed")
    pcbnew.ImportSpecctraSES(board, ses)


def unrouted(board):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    return board.GetConnectivity().GetUnconnectedCount(False)


def main():
    no_route = "--no-route" in sys.argv
    for W, H in SIZES:
        try:
            board, nets = build(W, H)
        except RuntimeError as e:
            print(f"{W}x{H}: {e}")
            continue
        print(f"placement OK at {W}x{H} mm")
        add_zone(board, nets["GND"], pcbnew.B_Cu, W, H)
        pcbnew.SaveBoard(PCB, board)
        if no_route:
            add_zone(board, nets["GND"], pcbnew.F_Cu, W, H)
            break
        route(board, nets)
        add_zone(board, nets["GND"], pcbnew.F_Cu, W, H)
        left = unrouted(board)
        print(f"{W}x{H}: unrouted {left}")
        if left == 0:
            break
    else:
        raise SystemExit("no size gave a complete layout")

    t = pcbnew.PCB_TEXT(board)
    t.SetText("LaserBlinker REAR CORE v0.1")
    t.SetLayer(pcbnew.B_SilkS)
    t.SetPosition(V(W / 2, H / 2))
    t.SetMirrored(True)
    t.SetTextSize(pcbnew.VECTOR2I(MM(1.0), MM(1.0)))
    t.SetTextThickness(MM(0.15))
    board.Add(t)
    pcbnew.SaveBoard(PCB, board)

    # プロジェクトのルールを読み込んだ状態で充填し、表裏の GND ベタをビアで縫う
    board = pcbnew.LoadBoard(PCB)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    print(f"stitching vias: {stitch(board, W, H)}")
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)
    print(f"board saved: {PCB} ({W}x{H} mm)")


def stitch(board, W, H, pitch=2.5, r=0.6):
    gnd = board.FindNet("/GND")
    zones = {z.GetLayer(): z for z in board.Zones() if z.GetNetCode() == gnd.GetNetCode()}
    rings = [(0, 0)] + [(r * math.cos(a * math.pi / 4), r * math.sin(a * math.pi / 4)) for a in range(8)]
    n = 0
    y = 1.5
    while y < H - 1.0:
        x = 1.5
        while x < W - 1.0:
            ok = all(zones[l].GetFilledPolysList(l).Contains(V(x + dx, y + dy))
                     for l in (pcbnew.F_Cu, pcbnew.B_Cu) for dx, dy in rings)
            if ok:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(V(x, y))
                v.SetWidth(MM(0.6))
                v.SetDrill(MM(0.3))
                v.SetNet(gnd)
                board.Add(v)
                n += 1
            x += pitch
        y += pitch
    return n


if __name__ == "__main__":
    main()
