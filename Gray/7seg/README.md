# 7seg — DigiClock 時計

M5Stack Gray の Grove Port A に接続した [Unit DigiClock](https://docs.m5stack.com/en/unit/digi_clock)（4桁7セグ）に時刻を表示する時計ファームウェアです。

## ハードウェア

| 項目 | 内容 |
|------|------|
| 本体 | M5Stack Gray（Basic 系 Core ESP32） |
| 表示 | Unit DigiClock（I2C `0x30`） |
| 接続 | Grove **Port A**（SDA=21 / SCL=22） |

## 機能

- 7セグに **HH:MM** を表示（コロン点滅）
- 起動時に WiFi → NTP（`ntp.nict.jp` / JST）で時刻合わせ
- WiFi 取得の成否を **小数点（DP）** で表示
  - 取得できた → 全桁の小数点が点灯
  - 取れなかった → 小数点なし
- ボタンで手動合わせ・明るさ・再同期

Gray 本体に RTC はないため、電源断後は再 NTP か手動合わせが必要です。

## 操作

| ボタン | 動作 |
|--------|------|
| A | 時 +1 |
| B | 分 +1 |
| C 短押し | 明るさ 1〜8 を循環 |
| C 長押し（約 0.8 秒以上） | WiFi / NTP 再同期 |

LCD には操作説明とステータス行を出します。

## 設定

`src/main.cpp` 先頭付近:

```cpp
static const char *WIFI_SSID = "...";
static const char *WIFI_PASS = "...";
```

SSID を空文字にすると NTP をスキップし、ボタン合わせのみになります。

## ビルド・書き込み

[PlatformIO](https://platformio.org/) 前提です。

```bash
cd Gray/7seg
pio run          # ビルド
pio run -t upload
pio device monitor
```

依存ライブラリ（`platformio.ini`）:

- `m5stack/M5Stack`
- `m5stack/M5Unit-DigiClock`
