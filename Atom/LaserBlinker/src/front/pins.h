#pragma once

// ESP32-C3 SuperMini — 前部マスタ
// スイッチは押下時に GND へ落ちる（INPUT_PULLUP）。
// G2/G8/G9 は起動ストラップ関連のため使用しない。

#define PIN_SW_TURN_L  0
#define PIN_SW_TURN_R  1
#define PIN_SW_BRAKE   3

// 12V 前ウインカー用 N-MOSFET（HIGH で点灯）
#define PIN_MOSFET_TURN_L 4
#define PIN_MOSFET_TURN_R 5

// 前部状態表示用 WS2812（左、右の2灯）
#define PIN_STATUS_WS2812 10
#define NUM_STATUS_LEDS   2
#define STATUS_BRIGHTNESS 64

// MAX485。現状は前→後の一方向で、DIへ送信する。
// ROを接続する場合は5VをC3へ入れないようレベル変換すること。
#define PIN_LINK_RX 20
#define PIN_LINK_TX 21

#define BLINK_HALF_MS      250
#define SW_DEBOUNCE_MS     30
#define LINK_SEND_MS       100  // 状態送信周期
