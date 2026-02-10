/**
 * @file lora_send.ino
 * @brief M5TimerCamX + ES920LR3 LoRa 送信（サンプル準拠）
 *
 * LoRa.cpp 方式で ES920LR3 に送信。受け取れたかは受信側の液晶で確認。
 * いずれカメラ画像の送信にも対応予定。
 *
 * @Hardwares: M5TimerCamX + ES920LR3（Grove: G4=TX, G13=RX）
 */

#include "M5TimerCAM.h"
#include "LoRa.h"

#define RX_PIN 13   // TimerCamX Grove RX（ES920LR3 TX を接続）
#define TX_PIN 4    // TimerCamX Grove TX（ES920LR3 RX を接続）
#define RESET_PIN -1
#define BOOT_PIN -1

#define SEND_INTERVAL_MS 5000

uint32_t sendCount = 0;

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== M5TimerCamX LoRa Send ===");

  TimerCAM.begin();

  if (LoRaInit(RX_PIN, TX_PIN, RESET_PIN, BOOT_PIN) < 0) {
    Serial.println("LoRa init FAIL");
    while (1) {
      TimerCAM.Power.setLed(255);
      delay(300);
      TimerCAM.Power.setLed(0);
      delay(300);
    }
  }

  Serial.println("LoRa init OK. Sending...");
}

void loop() {
  sendCount++;
  String msg = "OK#" + String(sendCount);

  TimerCAM.Power.setLed(128);
  LoRaCommand(msg);
  TimerCAM.Power.setLed(0);

  Serial.printf("Sent: %s\n", msg.c_str());

  for (int i = SEND_INTERVAL_MS / 1000; i > 0; i--) {
    Serial.printf("Next in %d sec...\n", i);
    delay(1000);
  }
}
