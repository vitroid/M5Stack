# lora_send

M5TimerCamX に ES920LR3（Grove UART）を接続し、LoRa で送信するプロジェクトです。サンプル（LR3_ENV_sample 等）の LoRa.cpp 方式を使用。将来的にカメラ画像の送信にも対応予定です。

## ハードウェア

- **M5TimerCamX** (TimerCamera-X)
- **ES920LR3** LoRa モジュール（Grove または 4 ピン UART）

### ピン接続

TimerCamX の Grove: G4=TX, G13=RX。ES920LR3 の TX → TimerCamX RX、RX → TimerCamX TX でクロス接続。

| ES920LR3 | TimerCamX | 備考       |
| -------- | --------- | ---------- |
| TX       | RX (G13)  | クロス接続 |
| RX       | TX (G4)   | クロス接続 |
| 5V       | 5V        |            |
| GND      | GND       |            |

RESET/BOOT ピンなしでも、LoRa.cpp 内の TX/RX トグルで config モードに入ります。

## ビルド・書き込み

```bash
cd lora_send
make compile
make upload
make monitor
```

## 送信内容

- 5 秒ごとに `OK#1`, `OK#2`, ... を送信
- 送信時に LED 点灯（TimerCAM.Power.setLed）
- 受信側の液晶で受信可否を確認

## LoRa パラメータ（受信側と一致）

- PAN ID: 2345
- Channel: 3
- Own ID: 1（送信側）
- Dest: ffff（ブロードキャスト）
