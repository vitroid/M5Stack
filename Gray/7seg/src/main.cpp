#include <M5Stack.h>
#include <WiFi.h>
#include <time.h>
#include <sys/time.h>
#include <M5UNIT_DIGI_CLOCK.h>

// --- DigiClock (Grove Port A = I2C) ---
static const uint8_t DIGI_SDA = 21;
static const uint8_t DIGI_SCL = 22;
static const uint8_t DIGI_ADDR = 0x30;

// --- WiFi / NTP（SSID を空にすると NTP を使わない） ---
static const char *WIFI_SSID = "VitroidPlumb";
static const char *WIFI_PASS = "kokuyo-origo-salt";
static const char *NTP_SERVER = "ntp.nict.jp";
static const long GMT_OFFSET_SEC = 9 * 3600;  // JST
static const int DAYLIGHT_OFFSET_SEC = 0;
static const uint32_t WIFI_TIMEOUT_MS = 12000;

M5UNIT_DIGI_CLOCK digi;
uint8_t brightness = 7;
bool colonOn = true;
bool wifiGot = false;  // WiFi 取得できたか（小数点で表示）
int lastShownMinute = -1;
uint32_t lastBlinkMs = 0;
uint32_t lastBtnMs = 0;

void drawLcdHelp() {
  M5.Lcd.fillScreen(TFT_BLACK);
  M5.Lcd.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(10, 10);
  M5.Lcd.println("7seg DigiClock");

  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(10, 50);
  M5.Lcd.println("A: hour +1");
  M5.Lcd.setCursor(10, 70);
  M5.Lcd.println("B: minute +1");
  M5.Lcd.setCursor(10, 90);
  M5.Lcd.println("C short: brightness");
  M5.Lcd.setCursor(10, 110);
  M5.Lcd.println("C long : NTP sync");
  M5.Lcd.setCursor(10, 140);
  M5.Lcd.println("Port A (I2C 0x30)");
  M5.Lcd.setCursor(10, 160);
  M5.Lcd.println("DP on = WiFi got");
}

void drawLcdStatus(const char *msg) {
  M5.Lcd.fillRect(0, 170, 320, 50, TFT_BLACK);
  M5.Lcd.setTextSize(1);
  M5.Lcd.setTextColor(TFT_CYAN, TFT_BLACK);
  M5.Lcd.setCursor(10, 180);
  M5.Lcd.println(msg);
}

bool getNow(struct tm &out) { return getLocalTime(&out, 50); }

void setLocalHms(int hour, int minute, int second = 0) {
  struct tm t = {};
  if (!getNow(t)) {
    t.tm_year = 2026 - 1900;
    t.tm_mon = 0;
    t.tm_mday = 1;
  }
  t.tm_hour = hour;
  t.tm_min = minute;
  t.tm_sec = second;
  time_t epoch = mktime(&t);
  struct timeval tv = {.tv_sec = epoch, .tv_usec = 0};
  settimeofday(&tv, nullptr);
}

void showTime(const struct tm &t, bool showColon) {
  // DigiClock: "1.2.:3.4." のように '.' で各桁の小数点を点灯できる
  // WiFi 取得済み → 全桁の小数点 ON / 未取得 → 小数点なし
  char buf[16];
  const int h1 = t.tm_hour / 10;
  const int h0 = t.tm_hour % 10;
  const int m1 = t.tm_min / 10;
  const int m0 = t.tm_min % 10;
  if (wifiGot) {
    if (showColon) {
      snprintf(buf, sizeof(buf), "%d.%d.:%d.%d.", h1, h0, m1, m0);
    } else {
      snprintf(buf, sizeof(buf), "%d.%d.%d.%d.", h1, h0, m1, m0);
    }
  } else if (showColon) {
    snprintf(buf, sizeof(buf), "%02d:%02d", t.tm_hour, t.tm_min);
  } else {
    snprintf(buf, sizeof(buf), "%02d%02d", t.tm_hour, t.tm_min);
  }
  digi.setString(buf);
}

bool syncNtp() {
  wifiGot = false;
  lastShownMinute = -1;

  if (WIFI_SSID == nullptr || WIFI_SSID[0] == '\0') {
    drawLcdStatus("WiFi SSID empty");
    return false;
  }

  drawLcdStatus("WiFi connecting...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  const uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < WIFI_TIMEOUT_MS) {
    delay(200);
    M5.update();
  }

  if (WiFi.status() != WL_CONNECTED) {
    drawLcdStatus("WiFi failed (DP off)");
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    return false;
  }

  wifiGot = true;  // 小数点 ON
  drawLcdStatus("WiFi OK (DP on) / NTP...");
  configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);

  struct tm t;
  bool ok = false;
  for (int i = 0; i < 40; ++i) {
    if (getLocalTime(&t, 200)) {
      ok = true;
      break;
    }
  }

  if (ok) {
    char msg[40];
    snprintf(msg, sizeof(msg), "Synced %02d:%02d", t.tm_hour, t.tm_min);
    drawLcdStatus(msg);
  } else {
    drawLcdStatus("NTP failed (WiFi DP on)");
  }

  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  return ok;
}

void setup() {
  M5.begin();
  M5.Power.begin();
  Serial.begin(115200);

  drawLcdHelp();

  if (!digi.begin(&Wire, DIGI_SDA, DIGI_SCL, DIGI_ADDR)) {
    drawLcdStatus("DigiClock not found!");
    Serial.println("DigiClock init error");
  } else {
    digi.setBrightness(brightness);
    digi.setString((char *)"----");
    drawLcdStatus("DigiClock OK");
    Serial.println("DigiClock init OK");
  }

  syncNtp();

  struct tm t;
  if (!getNow(t)) {
    setLocalHms(12, 0, 0);
    getNow(t);
  }
  showTime(t, true);
}

void loop() {
  M5.update();
  const uint32_t nowMs = millis();

  if (nowMs - lastBtnMs > 180) {
    if (M5.BtnA.wasPressed()) {
      lastBtnMs = nowMs;
      struct tm t;
      if (!getNow(t)) {
        setLocalHms(0, 0, 0);
        getNow(t);
      }
      setLocalHms((t.tm_hour + 1) % 24, t.tm_min, 0);
      lastShownMinute = -1;
      drawLcdStatus("Hour +1");
    }

    if (M5.BtnB.wasPressed()) {
      lastBtnMs = nowMs;
      struct tm t;
      if (!getNow(t)) {
        setLocalHms(0, 0, 0);
        getNow(t);
      }
      setLocalHms(t.tm_hour, (t.tm_min + 1) % 60, 0);
      lastShownMinute = -1;
      drawLcdStatus("Minute +1");
    }

    if (M5.BtnC.wasReleased()) {
      lastBtnMs = nowMs;
      // 長押し (~0.8s+) で NTP、短押しで明るさ
      if (M5.BtnC.wasReleasefor(800)) {
        syncNtp();
      } else {
        brightness = (brightness % 8) + 1;  // 1..8
        digi.setBrightness(brightness);
        char msg[24];
        snprintf(msg, sizeof(msg), "Brightness %u", brightness);
        drawLcdStatus(msg);
      }
    }
  }

  if (nowMs - lastBlinkMs >= 500) {
    lastBlinkMs = nowMs;
    colonOn = !colonOn;

    struct tm t;
    if (getNow(t)) {
      showTime(t, colonOn);
      if (t.tm_min != lastShownMinute) {
        lastShownMinute = t.tm_min;
        char msg[32];
        snprintf(msg, sizeof(msg), "%04d-%02d-%02d  %02d:%02d",
                 t.tm_year + 1900, t.tm_mon + 1, t.tm_mday, t.tm_hour,
                 t.tm_min);
        drawLcdStatus(msg);
      }
    }
  }

  delay(10);
}
