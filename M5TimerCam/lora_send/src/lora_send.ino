/**
 * @file lora_send.ino
 * @brief M5TimerCamX + ES920LR3 LoRa 送信（画像チャンク送信 A案）
 *
 * LoRa.cpp 方式で ES920LR3 に送信。
 * 今はダミーの「画像バイト列」をチャンク分割して送信する。
 * 後でカメラの JPEG バッファに差し替える想定。
 *
 * @Hardwares: M5TimerCamX + ES920LR3（Grove: G4=TX, G13=RX）
 */

#include "M5TimerCAM.h"
#include "LoRa.h"

#define RX_PIN 13   // TimerCamX Grove RX（ES920LR3 TX を接続）
#define TX_PIN 4    // TimerCamX Grove TX（ES920LR3 RX を接続）
#define RESET_PIN -1
#define BOOT_PIN -1

// テスト用の送信間隔（実運用では 1 時間などに変更）
#define SEND_INTERVAL_MS 5000

// 擬似画像データ（A案用）
// 実際にはカメラの JPEG バッファに置き換える予定
const int IMG_WIDTH  = 160;
const int IMG_HEIGHT = 80;

// とりあえず 1KB のダミーデータを送る例
// （まずは安定動作を優先してテスト）
const uint16_t DUMMY_IMG_SIZE = 1024;
uint8_t dummyImage[DUMMY_IMG_SIZE];

// 1 チャンクあたりの生データバイト数
// 受信側と合わせておく
const uint16_t CHUNK_DATA_LEN = 16;

// NG 時の再送最大回数
const uint8_t LORA_RETRY_MAX = 5;

// チャンク送信間隔（アダプティブに変化させる）
// 初期値は 1000ms としておき、成功・失敗に応じて調整する。
uint32_t g_chunkIntervalMs = 1000;
const uint32_t LORA_INTERVAL_MIN = 200;   // これ以上は短くしない
const uint32_t LORA_INTERVAL_MAX = 10000; // これ以上は長くしない

/**
 * @brief バイト列を 16 進文字列（ASCII）に変換
 */
String bytesToHex(const uint8_t* data, uint16_t len) {
  const char hexChars[] = "0123456789ABCDEF";
  String out;
  out.reserve(len * 2);
  for (uint16_t i = 0; i < len; i++) {
    uint8_t b = data[i];
    out += hexChars[b >> 4];
    out += hexChars[b & 0x0F];
  }
  return out;
}

/**
 * @brief LoRaCommand をラップして NG の場合に再送する
 * @param msg 送信するテキスト（改行なし）
 * @return true: OK 応答を得た / false: 規定回数リトライしても NG
 */
bool sendLoRaWithRetry(const String& msg) {
  for (uint8_t attempt = 0; attempt < LORA_RETRY_MAX; ++attempt) {
    // 現在のインターバルだけ待ってから送信
    delay(g_chunkIntervalMs);

    int res = LoRaCommand(msg);
    if (res >= 0) {
      // "OK" を含む応答
      if (attempt > 0) {
        Serial.printf("LoRa OK after retry (attempt %d)\n", attempt + 1);
      }
      // 成功したので、待ち時間を少しだけ短くする（15/16倍）
      if (g_chunkIntervalMs > LORA_INTERVAL_MIN) {
        uint32_t dec = g_chunkIntervalMs / 16;
        if (dec == 0) dec = 1;
        g_chunkIntervalMs -= dec;
        if (g_chunkIntervalMs < LORA_INTERVAL_MIN) {
          g_chunkIntervalMs = LORA_INTERVAL_MIN;
        }
        Serial.printf("LoRa success, new interval %lu ms\n",
                      (unsigned long)g_chunkIntervalMs);
      }
      return true;
    }

    // NG の場合は待ち時間を 1.5 倍に伸ばす（アダプティブ待ち）
    // new = old * 1.5 ≒ old + old/2
    uint32_t inc = g_chunkIntervalMs / 2;
    if (inc == 0) inc = 1;
    g_chunkIntervalMs += inc;
    if (g_chunkIntervalMs > LORA_INTERVAL_MAX) {
      g_chunkIntervalMs = LORA_INTERVAL_MAX;
    }
    Serial.printf("LoRa NG, retry %d/%d, next interval %lu ms\n",
                  attempt + 1, LORA_RETRY_MAX, (unsigned long)g_chunkIntervalMs);
  }
  Serial.println("LoRa send failed after max retries.");
  return false;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== M5TimerCamX LoRa Send (Image chunks A-plan) ===");

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

  // ダミー画像データを適当に埋める（パターン）
  for (uint16_t i = 0; i < DUMMY_IMG_SIZE; i++) {
    dummyImage[i] = (uint8_t)(i & 0xFF);
  }

  Serial.println("LoRa init OK. Ready to send image chunks...");
}

void loop() {
  // 今回は 1 ループごとに「画像 1 枚分」を送る例。
  // 実運用ではここを「1 時間に 1 回」などに変更する。
  static uint8_t imgId = 0;
  imgId++;  // 画像 ID を更新

  uint16_t chunkTotal =
      (DUMMY_IMG_SIZE + CHUNK_DATA_LEN - 1) / CHUNK_DATA_LEN;

  Serial.printf("Start send image id=%d, size=%d, chunks=%d\n",
                imgId, DUMMY_IMG_SIZE, chunkTotal);

  for (uint16_t chunkIdx = 0; chunkIdx < chunkTotal; chunkIdx++) {
    uint16_t offset = chunkIdx * CHUNK_DATA_LEN;
    uint16_t remain = DUMMY_IMG_SIZE - offset;
    uint16_t thisLen = (remain > CHUNK_DATA_LEN) ? CHUNK_DATA_LEN : remain;

    String hexData = bytesToHex(&dummyImage[offset], thisLen);

    // ペイロードフォーマット:
    // I,<imgId>,<chunkIdx>,<totalChunks>,<hexData>
    String msg = "I," + String(imgId) + "," + String(chunkIdx) + "," +
                 String(chunkTotal) + "," + hexData;

    TimerCAM.Power.setLed(128);
    bool ok = sendLoRaWithRetry(msg);
    TimerCAM.Power.setLed(0);

    if (ok) {
      Serial.printf("Sent chunk %d/%d\n", chunkIdx + 1, chunkTotal);
    } else {
      Serial.printf("Gave up chunk %d/%d\n", chunkIdx + 1, chunkTotal);
    }
  }

  Serial.println("Image send done.");

  // 次の画像送信までの待ち時間
  for (int i = SEND_INTERVAL_MS / 1000; i > 0; i--) {
    Serial.printf("Next image in %d sec...\n", i);
    delay(1000);
  }
}

