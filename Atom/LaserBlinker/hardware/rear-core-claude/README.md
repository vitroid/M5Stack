# rear-core-claude

`docs/rear-pcb-design.md` に基づく後方ユニット中核基板（ESP32-C3-MINI-1）の KiCad 10 プロジェクト。
回路図・基板・製造データはすべて `scripts/design.py`（部品とネットの一覧）から自動生成する。

## 現状

| 項目 | 結果 |
|---|---|
| 基板サイズ | 40 × 55 mm、2 層、片面 SMD |
| ERC | 0 件 |
| 回路図 ↔ design.py 照合 | 207 ピン / 40 ネット、不一致 0 |
| DRC | エラー 0、未配線 0、回路図との不一致 0（警告 4: ESP32 モジュール自身のシルクが基板端に掛かるもの） |
| 配線 | Freerouting 自動配線、表裏 GND ベタ + スティッチングビア |

設計書の目安 30×40 mm は、部品のコートヤード合計（約 1,200 mm²）とアンテナ禁止帯を考えると片面実装では入らない。
生成スクリプトは 30×40 から順に試し、配置と配線が両方完了した最小サイズを採用する（38×50 では未配線 2 本が残った）。

## 再生成

```sh
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3
$KP scripts/gen_sch.py     # ライブラリ・プロジェクト・回路図
$KP scripts/check_sch.py   # ERC とネットリスト照合（out_netlist.xml は gen_pcb.py が使う）
$KP scripts/gen_pcb.py     # 配置 → Freerouting → GND ベタ（約 2 分）
$KP scripts/gen_fab.py     # fab/ に JLCPCB 用データ、out/ に画像、回路図 PDF
```

Freerouting 1.9.0 の jar を `~/.cache/freerouting/` に置いておくこと。

## 製造データ（fab/）

- `rear-core-claude-gerber.zip`: ガーバーとドリル
- `rear-core-claude-bom.csv` / `rear-core-claude-cpl.csv`: JLCPCB PCBA 用。J1〜J3（スルーホールのコネクタ）、JP1/JP2、TP1 は実装対象外
- LCSC 番号が未指定の部品: C1, C2（22µF/25V 1206）、C8（220µF/10V 電解）、F1（3A 1812 ポリスイッチ）。発注時に選ぶ
