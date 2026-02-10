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
#include <string.h>

#define RX_PIN 33   // Grove - ES920LR3 TX 接続
#define TX_PIN 32   // Grove - ES920LR3 RX 接続
#define RESET_PIN -1
#define BOOT_PIN -1

#define ROT 3
#define SX 210
#define SY 30
#define SR 12

// A案用：受信画像バッファ
const uint16_t MAX_IMG_SIZE   = 4096;
const uint16_t CHUNK_DATA_LEN = 16;     // 送信側と合わせる
const uint16_t MAX_CHUNKS     = MAX_IMG_SIZE / CHUNK_DATA_LEN;
uint8_t imgBuf[MAX_IMG_SIZE];

uint8_t  currentImgId        = 0;
uint16_t expectedChunkTotal  = 0;
uint16_t receivedChunkCount  = 0;
uint16_t currentImgMaxOffset = 0;
bool     chunkReceived[MAX_CHUNKS];

int hexCharToVal(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  return 0;
}

uint16_t hexToBytes(const String& hex, uint8_t* out, uint16_t maxLen) {
  uint16_t hexLen = hex.length();
  uint16_t outLen = 0;
  for (uint16_t i = 0; i + 1 < hexLen && outLen < maxLen; i += 2) {
    uint8_t hi = hexCharToVal(hex[i]);
    uint8_t lo = hexCharToVal(hex[i + 1]);
    out[outLen++] = (hi << 4) | lo;
  }
  return outLen;
}

void handleImageChunk(const String& payload) {
  // payload: "I,imgId,chunkIdx,totalChunks,HEX..."
  // まずカンマで分割
  int p1 = payload.indexOf(',');
  int p2 = payload.indexOf(',', p1 + 1);
  int p3 = payload.indexOf(',', p2 + 1);
  int p4 = payload.indexOf(',', p3 + 1);

  if (p1 < 0 || p2 < 0 || p3 < 0 || p4 < 0) {
    Serial.println("Invalid image packet format");
    return;
  }

  String tag      = payload.substring(0, p1);      // "I"
  String imgIdStr = payload.substring(p1 + 1, p2);
  String idxStr   = payload.substring(p2 + 1, p3);
  String totStr   = payload.substring(p3 + 1, p4);
  String hexData  = payload.substring(p4 + 1);     // HEX...

  uint8_t  imgId     = (uint8_t)imgIdStr.toInt();
  uint16_t chunkIdx  = (uint16_t)idxStr.toInt();
  uint16_t chunkTot  = (uint16_t)totStr.toInt();

  if (tag != "I") {
    Serial.println("Not image packet");
    return;
  }

  // 新しい画像 ID なら状態リセット
  if (imgId != currentImgId) {
    currentImgId        = imgId;
    expectedChunkTotal  = chunkTot;
    receivedChunkCount  = 0;
    currentImgMaxOffset = 0;
    // 受信フラグをクリア
    for (uint16_t i = 0; i < MAX_CHUNKS; ++i) {
      chunkReceived[i] = false;
    }
    Serial.printf("Start receive image id=%d, totalChunks=%d\n", imgId, chunkTot);
  }

  // HEX 文字列を一時バッファにデコード
  uint8_t tmp[CHUNK_DATA_LEN];
  uint16_t dataLen = hexToBytes(hexData, tmp, CHUNK_DATA_LEN);

  // chunkIdx の範囲チェック
  if (chunkIdx >= MAX_CHUNKS) {
    Serial.println("chunkIdx out of range, dropped");
    return;
  }

  uint32_t offset = (uint32_t)chunkIdx * CHUNK_DATA_LEN;
  if (offset + dataLen > MAX_IMG_SIZE) {
    Serial.println("Image too large, dropped");
    return;
  }

  // バッファにコピー（同じ chunkIdx が複数回来た場合は単なる上書き）
  memcpy(&imgBuf[offset], tmp, dataLen);
  if (!chunkReceived[chunkIdx]) {
    chunkReceived[chunkIdx] = true;
    receivedChunkCount++;
  }
  if (offset + dataLen > currentImgMaxOffset) {
    currentImgMaxOffset = offset + dataLen;
  }

  Serial.printf("Received chunk %d/%d (len=%d)\n",
                chunkIdx + 1, chunkTot, dataLen);

  // 全チャンク受信済みか判定
  if (receivedChunkCount >= expectedChunkTotal) {
    Serial.printf("Image id=%d receive complete. size=%d bytes\n",
                  currentImgId, currentImgMaxOffset);
    // ここで本当は JPEG として描画する（A案では簡単な通知のみ）
    M5.Display.fillScreen(BLACK);
    M5.Display.setCursor(0, 8);
    M5.Display.setTextSize(2);
    M5.Display.println("Img RX DONE");
    M5.Display.printf("ID: %d\n", currentImgId);
    M5.Display.printf("Size: %d\n", currentImgMaxOffset);
  }
}

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

  // 受信時の readStringUntil のブロッキング時間を短くする
  Serial2.setTimeout(20);

  M5.Display.fillScreen(BLACK);
  M5.Display.setCursor(0, 0);
  M5.Display.println("LoRa Receive");
  M5.Display.println("Stand-by");
  Serial.println("=== LoRa Receive Ready ===");
}

void loop() {
  // シリアルバッファにある分をできるだけまとめて処理する
  while (Serial2.available()) {
    // 行単位で読むことで、複数パケットがくっつくのを防ぐ
    String rxs = Serial2.readStringUntil('\n');
    // デバッグ文字列の出力は最小限にして処理を軽くする
    // Serial.print(rxs);

    // 先頭4文字 = RSSI(hex)、以降 = データ
    int16_t rssi = -128;
    String data = rxs;
    if (rxs.length() >= 4) {
      char buf[5] = {0};
      rxs.substring(0, 4).toCharArray(buf, 5);
      rssi = (int16_t)strtol(buf, NULL, 16);
      data = rxs.substring(4);
    }

    // data が画像チャンクかどうか判定
    if (data.startsWith("I,")) {
      // 画像チャンクはひたすらバッファに溜めるだけにして、
      // 描画などの重い処理は handleImageChunk 内で
      // 「受信完了時」にだけ行う。
      handleImageChunk(data);
    } else {
      // 従来のテキストメッセージ表示
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
  }
  // ループ自体の待ち時間は最小限に
  delay(1);
}

