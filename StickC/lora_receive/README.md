# lora_receive

M5StickC Plus + ES920LR3 LoRa UNIT（Grove）で、lora_send からのデータを受信するプロジェクトです。サンプル（LR3_ENV_sample 等）準拠の LoRa.cpp 方式。受信内容を液晶に表示し、ビープで通知します。

## ハードウェア

- **M5StickC Plus**（または M5StickC Plus 2）
- **ES920LR3 LoRa UNIT**（Grove 接続）

LoRa UNIT を M5StickC Plus の Grove ポートに接続します。

## ピン

Grove: G32=TX, G33=RX（ES920LR3 の TX/RX とクロス接続）

## ビルド・書き込み

```bash
cd lora_receive
make compile
make upload
make monitor
```

## 表示

- 待機中: "LoRa Receive" / "Stand-by"
- 受信時: "Received!" + 受信データ + RSSI、緑円・ビープ

## LoRa パラメータ（送信側と一致）

- PAN ID: 2345
- Channel: 3
- Own ID: 0（受信側）
- Dest: ffff
- RSSI: on（4 文字 hex + データ形式で受信）
