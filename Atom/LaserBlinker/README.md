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
