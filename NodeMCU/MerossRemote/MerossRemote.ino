/*
 * MerossRemote — DOIT.AM ESP8266 NodeMCU breadboard remote
 *
 * Two momentary buttons (INPUT_PULLUP) call a Mac-side HTTP bridge that
 * wraps meross-iot. MCU holds Wi‑Fi + bridge URL only — no Meross secrets.
 *
 * Board (photo-confirmed): ESP8266MOD / DOIT.AM NodeMCU (not ESP32 Amica).
 * Silkscreen bottom row L→R includes: … D8 D7 D6 D5 GND 3V3 D4 D3 D2 D1 D0
 *
 * Pin map (use silkscreen Dx labels):
 *   Button A (ランプ / lamp) : D1 (GPIO5) → switch → GND
 *   Button B (ファン / fan)  : D2 (GPIO4) → switch → GND
 *   Avoid D3 / D4 / D8 for buttons (boot / flash / onboard LED).
 *
 * Night-friendly (dark-by-default):
 *   - No idle LED. Press flash OFF unless enabled in secrets.h.
 *   - Onboard blue LED is usually D4 / GPIO2 (active-low) — forced OFF.
 *   - Red power LED (if present) may need tape.
 *
 * Copy secrets.h.example → secrets.h. Arduino board: "NodeMCU 1.0 (ESP-12E)".
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include "secrets.h"

#ifndef WIFI_SSID
#error "Copy secrets.h.example to secrets.h and set WIFI_SSID / WIFI_PASSWORD / BRIDGE_HOST"
#endif

// ---- fixed breadboard pin map (NodeMCU silkscreen) ----
// D1 = GPIO5, D2 = GPIO4 (pins_arduino.h defines D1/D2)
static const int PIN_BTN_LAMP = D1;  // silk D1 → toggle ランプ
static const int PIN_BTN_FAN  = D2;  // silk D2 → toggle ファン

// Onboard blue LED on most NodeMCU: D4 / GPIO2, active-low.
#ifndef ONBOARD_LED_PIN
#define ONBOARD_LED_PIN LED_BUILTIN  // typically 2
#endif

#ifndef FEEDBACK_LED_PIN
#define FEEDBACK_LED_PIN (-1)
#endif
#ifndef FLASH_ON_PRESS
#define FLASH_ON_PRESS 0
#endif
#ifndef FLASH_MS
#define FLASH_MS 60
#endif

#ifndef BRIDGE_PORT
#define BRIDGE_PORT 8787
#endif

#ifndef DEBOUNCE_MS
#define DEBOUNCE_MS 40
#endif

#ifndef COOLDOWN_MS
#define COOLDOWN_MS 800
#endif

WiFiClient wifiClient;
HTTPClient http;

struct Button {
  const char* name;
  const char* path;
  int pin;
  bool lastStable;
  bool lastRaw;
  unsigned long lastChangeMs;
  unsigned long lastFireMs;
};

Button buttons[] = {
  {"lamp", "/toggle/lamp", PIN_BTN_LAMP, true, true, 0, 0},
  {"fan",  "/toggle/fan",  PIN_BTN_FAN,  true, true, 0, 0},
};

void ledsDark() {
  pinMode(ONBOARD_LED_PIN, OUTPUT);
  digitalWrite(ONBOARD_LED_PIN, HIGH);  // active-low LED → HIGH = off

  if (FEEDBACK_LED_PIN >= 0) {
    pinMode(FEEDBACK_LED_PIN, OUTPUT);
    digitalWrite(FEEDBACK_LED_PIN, LOW);
  }
}

void briefFlash() {
#if FLASH_ON_PRESS
  if (FEEDBACK_LED_PIN < 0) {
    return;
  }
  digitalWrite(FEEDBACK_LED_PIN, HIGH);
  delay(FLASH_MS);
  digitalWrite(FEEDBACK_LED_PIN, LOW);
#else
  // dark-by-default: no flash
#endif
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi connecting");
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
    ledsDark();
    if (millis() - start > 30000) {
      Serial.println("\nWiFi timeout — retrying");
      WiFi.disconnect();
      delay(500);
      WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      start = millis();
    }
  }
  Serial.println();
  Serial.print("WiFi OK  IP=");
  Serial.println(WiFi.localIP());
  ledsDark();
}

bool callBridge(const char* path) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi down — reconnect");
    connectWifi();
  }

  String url = String("http://") + BRIDGE_HOST + ":" + String(BRIDGE_PORT) + path;
  Serial.print("GET ");
  Serial.println(url);

  http.setTimeout(15000);
  http.setReuse(false);
  if (!http.begin(wifiClient, url)) {
    Serial.println("http.begin failed");
    return false;
  }
  int code = http.GET();
  if (code > 0) {
    Serial.printf("HTTP %d\n", code);
    String body = http.getString();
    Serial.println(body);
  } else {
    Serial.printf("HTTP fail: %s\n", http.errorToString(code).c_str());
  }
  http.end();
  return code == HTTP_CODE_OK;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("MerossRemote (ESP8266 NodeMCU) boot — LEDs dark-by-default");

  ledsDark();

  pinMode(PIN_BTN_LAMP, INPUT_PULLUP);
  pinMode(PIN_BTN_FAN, INPUT_PULLUP);

  for (Button& b : buttons) {
    bool raw = digitalRead(b.pin) == HIGH;
    b.lastRaw = raw;
    b.lastStable = raw;
    b.lastChangeMs = millis();
  }

  connectWifi();
  callBridge("/health");  // readiness only — does not toggle outlets
  ledsDark();
}

void loop() {
  unsigned long now = millis();

  for (Button& b : buttons) {
    bool raw = digitalRead(b.pin) == HIGH;
    if (raw != b.lastRaw) {
      b.lastRaw = raw;
      b.lastChangeMs = now;
    }
    if ((now - b.lastChangeMs) < DEBOUNCE_MS) {
      continue;
    }
    if (raw == b.lastStable) {
      continue;
    }
    b.lastStable = raw;

    if (!raw) {  // pressed to GND
      if (now - b.lastFireMs < COOLDOWN_MS) {
        Serial.printf("skip %s (cooldown)\n", b.name);
        continue;
      }
      b.lastFireMs = now;
      Serial.printf("button %s pressed\n", b.name);
      briefFlash();
      callBridge(b.path);
      ledsDark();
    }
  }

  delay(5);
}
