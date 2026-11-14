# LaserBlinker

前後分離のウインカー／ブレーキ連動。幹線は **12V + RS-485**。

## ビルド

```bash
pio run -e esp32-c3-supermini-front
pio run -e esp32-c3-supermini-rear
```

現行ファームは前後とも **ESP32-C3 SuperMini**（`platformio.ini`）。ピン定義は `src/front/pins.h` / `src/rear/pins.h`。

## ハードウェア正本

| 役割 | 正本 | 備考 |
| --- | --- | --- |
| 後部 PCB・発注／配線 | **`hardware/rear-core/`** | `docs/rear-pcb-design.md`・`docs/rear-circuit.md` と対になる |
| 前部 PCB（JLCPCB 向け） | `hardware/front-core/` | MCU は **ESP32-S3-MINI-1**。現行 FW は C3 のまま |
| 前部プロト配線（実機） | `docs/front-circuit.md` | C3 SuperMini + GX12-4 + MAX485 |

`hardware/rear-core-claude/` は **非正本**（別生成のアーカイブ）。リポジトリには含めない（`.gitignore`）。手元に残っていても発注・配線の参照先にしないこと。

## ドキュメント

- `docs/front-circuit.md` — 前部プロト（C3）結線
- `docs/front-pcb-design.md` — 前部オールインワン PCB（S3）
- `docs/rear-circuit.md` — 後部プロト（C3）結線
- `docs/rear-pcb-design.md` — 後部コア PCB（C3-MINI-1）

## 幹線コネクタの注意

- プロト／`*-circuit.md`: **GX12-4**（1:12V, 2:GND, 3:A, 4:B）
- PCB 設計／`hardware/*-core`: **RJ45**（Passive PoE + A/B）

前後を混在させるときはアダプタかピン対応表が必要。

## Assembly status（front-core 手配線）

未接続は **5 → 3**（2026-11-14）。残オープン:

| Ref | ネット | Done |
| --- | --- | --- |
| **R21** (10k) | `VBUS_PD` → **CH224K** (`U0`) Pin8 `VBUS`（移設 U0 まわり） | 両端はんだ＋≈10k 導通 |
| **R22** (1k 0805) | `VBUS_PD` → **U0** Pin1 `VDD`（同上） | 両端はんだ＋≈1k 導通 |
| **R3** (5.1k) | **J3 USB_DBG** CC1 (`A5`) → R3 → GND | CC1〜R3〜GND 連続 |

回路: `hardware/front-core/front-core.kicad_sch`（ブロック 1 = PD/CH224K、ブロック 3 = USB_DBG）。詳細チェックリストは Project store の `docs/laserblinker-front-wiring.md`。
