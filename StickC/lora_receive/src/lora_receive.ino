/**
 * @file lora_receive.ino
 * @brief M5StickC Plus + ES920LR3 LoRa 受信（サンプル準拠）
 *
 * lora_send からのデータを受信し、液晶に表示。受信時にビープ。
 *
 * @Hardwares: M5StickC Plus + LoRa UNIT（Grove: G32=TX, G33=RX）
 */

#include <M5Unified.h>
#include "LoRa.h"

#define RX_PIN 33   // Grove - ES920LR3 TX 接続
#define TX_PIN 32   // Grove - ES920LR3 RX 接続
#define RESET_PIN -1
#define BOOT_PIN -1

#define ROT 3
#define SX 210
#define SY 30
#define SR 12

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);

  M5.Display.setRotation(ROT);
  M5.Display.fillScreen(BLACK);
  M5.Display.setTextColor(WHITE);
  M5.Display.setTextSize(2);
  M5.Display.setCursor(0, 0);
  M5.Display.println("LoRa Receive");
  M5.Display.println("Init...");

  Serial.begin(115200);
  delay(300);

  if (LoRaInit(RX_PIN, TX_PIN, RESET_PIN, BOOT_PIN) < 0) {
    M5.Display.println("LoRa FAIL");
    Serial.println("LoRa init FAIL");
    while (1) delay(1000);
  }

  M5.Display.fillScreen(BLACK);
  M5.Display.setCursor(0, 0);
  M5.Display.println("LoRa Receive");
  M5.Display.println("Stand-by");
  Serial.println("=== LoRa Receive Ready ===");
}

void loop() {
  if (Serial2.available()) {
    String rxs = Serial2.readString();
    Serial.print(rxs);

    // 先頭4文字 = RSSI(hex)、以降 = データ
    int16_t rssi = -128;
    String data = rxs;
    if (rxs.length() >= 4) {
      char buf[5] = {0};
      rxs.substring(0, 4).toCharArray(buf, 5);
      rssi = (int16_t)strtol(buf, NULL, 16);
      data = rxs.substring(4);
    }

    M5.Display.fillScreen(BLACK);
    M5.Display.fillCircle(SX, SY, SR, GREEN);
    M5.Display.setCursor(0, 8);
    M5.Display.setTextSize(2);
    M5.Display.println("Received!");
    M5.Display.println();
    M5.Display.println(data);
    M5.Display.println();
    M5.Display.printf("RSSI: %d dBm", rssi);

    M5.Speaker.tone(4000, 100);

    delay(400);
    M5.Display.fillCircle(SX, SY, SR, BLACK);
  }
  delay(10);
}
