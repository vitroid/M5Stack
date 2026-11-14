#pragma once

// ESP32-C3 SuperMini — 後部スレーブ
//
// MAX485 RO →（分圧推奨）→ G20
// MAX485 DI ← G21（現状は未使用可。一方向受信）
// DE/RE → GND 固定（常時受信）
// WS2812 DATA → G10
// デモ切替: BOOT ボタン（G9）

#define PIN_LINK_RX  20
#define PIN_LINK_TX  21
#define PIN_WS2812   10
#define PIN_DEMO_BTN 9
#define PIN_STATUS_LED 8  // 内蔵青LED（active LOW）

#ifndef NUM_LEDS
#define NUM_LEDS 30
#endif

#define EDGE_LEDS 4
#define FAILSAFE_MS 500
#define BLINK_HALF_MS 250
#define TAPE_BRIGHTNESS 80
#define BTN_DEBOUNCE_MS 40
