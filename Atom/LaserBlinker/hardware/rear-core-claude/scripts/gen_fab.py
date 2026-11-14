"""JLCPCB 用の製造データ（ガーバー zip / BOM / CPL）と確認用画像を出力する。"""
import csv
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from design import PARTS, PROJECT  # noqa: E402

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
PCB = f"{OUT}/{PROJECT}.kicad_pcb"
SCH = f"{OUT}/{PROJECT}.kicad_sch"
FAB = f"{OUT}/fab"

# 手はんだ（J*: スルーホール）と実装しない部品（はんだジャンパ・テストパッド）
NO_ASSEMBLY = {p["ref"] for p in PARTS if p["ref"].startswith(("J", "JP", "TP"))}


def cli(*args):
    subprocess.run([CLI, *args], check=True, capture_output=True)


def gerbers():
    g = f"{FAB}/gerber"
    os.makedirs(g)
    cli("pcb", "export", "gerbers", "--layers",
        "F.Cu,B.Cu,F.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
        "--subtract-soldermask", "--no-x2", "-o", g + "/", PCB)
    cli("pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
        "-o", g + "/", PCB)
    shutil.make_archive(f"{FAB}/{PROJECT}-gerber", "zip", g)


def bom():
    groups = {}
    for p in PARTS:
        if p["ref"] in NO_ASSEMBLY:
            continue
        key = (p["value"], p["fp"].split(":")[1], p.get("lcsc", ""))
        groups.setdefault(key, []).append(p["ref"])
    with open(f"{FAB}/{PROJECT}-bom.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for (val, fp, lcsc), refs in sorted(groups.items(), key=lambda kv: kv[1][0]):
            w.writerow([val, ",".join(refs), fp, lcsc])
    return [refs for (_, _, lcsc), refs in groups.items() if not lcsc]


def cpl():
    raw = f"{FAB}/pos-raw.csv"
    cli("pcb", "export", "pos", "--side", "front", "--format", "csv", "--units", "mm",
        "-o", raw, PCB)
    with open(raw) as fi, open(f"{FAB}/{PROJECT}-cpl.csv", "w", newline="") as fo:
        w = csv.writer(fo)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in csv.DictReader(fi):
            if r["Ref"] in NO_ASSEMBLY:
                continue
            w.writerow([r["Ref"], f'{float(r["PosX"]):.3f}mm', f'{float(r["PosY"]):.3f}mm',
                        "Top", f'{float(r["Rot"]):.0f}'])
    os.remove(raw)


def images():
    img = f"{OUT}/out"
    os.makedirs(img, exist_ok=True)
    for name, layers, extra in (("top", "F.Cu,F.SilkS,F.Fab,Edge.Cuts", []),
                                ("bottom", "B.Cu,B.SilkS,Edge.Cuts", ["--mirror"])):
        svg = f"{img}/{name}.svg"
        cli("pcb", "export", "svg", "--layers", layers, "--mode-single", "--exclude-drawing-sheet",
            "--fit-page-to-board", *extra, "-o", svg, PCB)
        subprocess.run(["rsvg-convert", "-w", "800", "-b", "white", svg, "-o", f"{img}/{name}.png"], check=True)
    cli("pcb", "render", "--side", "top", "--quality", "high", "-w", "1200", "-h", "1400",
        "-o", f"{img}/3d-top.png", PCB)
    cli("pcb", "render", "--side", "bottom", "-w", "1200", "-h", "1400", "-o", f"{img}/3d-bottom.png", PCB)
    cli("pcb", "render", "--rotate", "-45,0,30", "--perspective", "-w", "1600", "-h", "1200",
        "-o", f"{img}/3d-iso.png", PCB)
    cli("sch", "export", "pdf", "-o", f"{OUT}/{PROJECT}-schematic.pdf", SCH)


if __name__ == "__main__":
    shutil.rmtree(FAB, ignore_errors=True)
    os.makedirs(FAB)
    gerbers()
    missing = bom()
    cpl()
    images()
    print("fab written:", FAB)
    for refs in missing:
        print("  LCSC 未指定:", ",".join(refs))
