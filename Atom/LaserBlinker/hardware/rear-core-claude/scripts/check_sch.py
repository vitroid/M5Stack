"""回路図の検証: kicad-cli で ERC とネットリスト出力を行い、design.py と照合する。"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from design import PARTS, PROJECT  # noqa: E402

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
SCH = f"{OUT}/{PROJECT}.kicad_sch"
# 標準ライブラリが KiCad のグローバル設定に未登録なだけの警告（回路の問題ではない）
ENV_ONLY = {"lib_symbol_issues"}

subprocess.run([CLI, "sch", "erc", "--format", "json", "--severity-all", "-o", f"{OUT}/out_erc.json", SCH],
               check=True, capture_output=True)
erc = json.load(open(f"{OUT}/out_erc.json"))
viol = [v for s in erc["sheets"] for v in s["violations"] if v["type"] not in ENV_ONLY]
print(f"ERC: {len(viol)} violations", dict(Counter((v['severity'], v['type']) for v in viol)))
for v in viol:
    print("  ", v["severity"], v["type"], v["description"], [i["description"] for i in v["items"]])

subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadxml", "-o", f"{OUT}/out_netlist.xml", SCH],
               check=True, capture_output=True)
root = ET.parse(f"{OUT}/out_netlist.xml").getroot()
actual = {}
for net in root.iter("net"):
    name = net.get("name").lstrip("/")
    for node in net.iter("node"):
        actual[(node.get("ref"), node.get("pin"))] = name

bad = 0
expected = {(p["ref"], pin): n for p in PARTS for pin, n in p["pins"].items()}
for key, net in expected.items():
    got = actual.get(key)
    if got != net:
        bad += 1
        print(f"  MISMATCH {key}: expected {net}, got {got}")
for key, net in actual.items():
    if key not in expected and not key[0].startswith("#") and not net.startswith("unconnected-"):
        bad += 1
        print(f"  EXTRA {key}: {net}")
nets = sorted(set(expected.values()))
print(f"Netlist: {len(expected)} pin connections, {len(nets)} nets, {bad} mismatches")
sys.exit(1 if bad or any(v["severity"] == "error" for v in viol) else 0)
