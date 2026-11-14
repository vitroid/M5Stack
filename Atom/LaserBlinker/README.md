# LaserBlinker

前後分離のウインカー／ブレーキ連動。幹線は **12V + RS-485**。

## ビルド

```bash
pio run -e esp32-c3-supermini-front
pio run -e esp32-c3-supermini-rear
```

現行ファームは、市販モジュールで組んで実装まで済ませた試作向けで、前後とも **ESP32-C3 SuperMini**（`platformio.ini`）。ピン定義は `src/front/pins.h` / `src/rear/pins.h`。`hardware/*-core` は、その試作を JLCPCB の一枚基板にまとめ、トランシーバ・幹線コネクタ・MCU・拡張端子を変えた次の基板である。ファームはまだ基板側のピンへ追従していない。いきさつと対応表は `docs/pcb-layout-policy.md` の「いきさつ」。

## ハードウェア正本

| 役割 | 正本 | 備考 |
| --- | --- | --- |
| 後部 PCB・発注／配線 | **`hardware/rear-core/`** | `docs/rear-pcb-design.md`・`docs/rear-circuit.md` と対になる |
| 前部 PCB（JLCPCB 向け） | `hardware/front-core/` | MCU は **ESP32-S3-MINI-1**。現行 FW は C3 のまま |
| 前部プロト配線（実機） | `docs/front-circuit.md` | C3 SuperMini + GX12-4 + MAX485 |

`hardware/rear-core-claude/` は **非正本**（別生成のアーカイブ）。リポジトリには含めない（`.gitignore`）。手元に残っていても発注・配線の参照先にしないこと。

## ドキュメント

- `docs/pcb-layout-policy.md` — 試作から一体基板までのいきさつ、端子配置、動かさない条件（引き継ぎの入口）
- `PLAN.md` / `PLAN2.md` — それより前のメモ（M5Stack Core / Atom Lite、幹線 5V）。実機の結線ではない
- `docs/front-circuit.md` — 実装済み試作の前部結線（C3 SuperMini、GX12、MAX485）
- `docs/front-pcb-design.md` — 前部オールインワン PCB（S3）の回路定数とピン表
- `docs/rear-circuit.md` — 実装済み試作の後部結線
- `docs/rear-pcb-design.md` — 後部コア PCB（C3-MINI-1）の回路定数とピン表

## 幹線コネクタの注意

- プロト／`*-circuit.md`: **GX12-4**（1:12V, 2:GND, 3:A, 4:B）
- PCB 設計／`hardware/*-core`: **RJ45**（Passive PoE + A/B）

前後を混在させるときはアダプタかピン対応表が必要。

## Fab readiness（front-core）

JLCPCB 発注前ゲート。手はんだ作業はない。

| 項目 | 状態 |
| --- | --- |
| KiCad | **Yes** — `kicad-cli` **10.0.8**（`scripts/build_pcb.py`） |
| ERC | 0 |
| BOM/CPL | R21 / R22 / R3 収録済 |
| DRC unconnected | **3**（発注不可のまま） |
| rear-core | fab 完了・正本 |

残銅箔未接続（回路図ネットは存在。CH224K 移設後の配置密度で Freerouting 未解決）:

1. **R21** — `/VBUS_PD` → `U0` Pin8 `VBUS`
2. **R22** — `/VBUS_PD` → `U0` Pin1 `VDD`
3. **J3** CC1 (`A5`) → **R3** → GND

次は `R21`/`R22`/`R3` の再配置（または配線チャネル確保）→ DRC 0 → `fab/` 再出力。詳細は Project store `docs/laserblinker-front-wiring.md`。FW ピン追従は PCB 確定後。
