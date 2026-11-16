/*
 * MerossRemote — ESP32 DevKit Amica breadboard remote
 *
 * Two momentary buttons (INPUT_PULLUP) call a Mac-side HTTP bridge that
 * wraps meross-iot. MCU holds Wi‑Fi + bridge URL only — no Meross secrets.
 *
 * Pin map (fixed):
 *   Button A (ランプ / lamp) : GPIO 18 → GND
 *   Button B (ファン / fan)  : GPIO 19 → GND
 *
 * Night-friendly (dark-by-default):
 *   - No idle LED. Optional brief flash on press is OFF unless enabled
 *     in secrets.h (FEEDBACK_LED_PIN + FLASH_ON_PRESS).
 *   - Onboard blue LED (often GPIO2) is forced OFF at boot.
 *   - Red power LED is hardware-always-on on most Amica boards — cover
 *     with tape or remove/cut its series resistor (see README).
 *
 * Copy secrets.h.example → secrets.h and edit Wi‑Fi / bridge host.
 * Pattern mirrors Atom/AtomSwitch (Wi‑Fi + HTTP GET to a LAN bridge).
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include "secrets.h"

#ifndef WIFI_SSID
#error "Copy secrets.h.example to secrets.h and set WIFI_SSID / WIFI_PASSWORD / BRIDGE_HOST"
#endif

// ---- fixed breadboard pin map ----
static const int PIN_BTN_LAMP = 18;  // A → toggle ランプ
static const int PIN_BTN_FAN  = 19;  // B → toggle ファン

// Common DevKit Amica / NodeMCU-32S status LED (active-low on many boards).
#ifndef ONBOARD_LED_PIN
#define ONBOARD_LED_PIN 2
#endif

// Optional press feedback — dark by default (set in secrets.h to enable).
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

HTTPClient http;

struct Button {
  const char* name;
  const char* path;  // e.g. "/toggle/lamp"
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
  // Force common onboard status LED off (GPIO2 is often active-low).
  pinMode(ONBOARD_LED_PIN, OUTPUT);
  digitalWrite(ONBOARD_LED_PIN, HIGH);  // HIGH = off on typical ESP32 DevKit

  if (FEEDBACK_LED_PIN >= 0) {
    pinMode(FEEDBACK_LED_PIN, OUTPUT);
    digitalWrite(FEEDBACK_LED_PIN, LOW);  // external LED: off when LOW
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
    ledsDark();  // keep dark while waiting (no blink patterns)
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
  if (!http.begin(url)) {
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
  Serial.println("MerossRemote (Amica) boot — LEDs dark-by-default");

  ledsDark();

  pinMode(PIN_BTN_LAMP, INPUT_PULLUP);
  pinMode(PIN_BTN_FAN, INPUT_PULLUP);

  // Seed debounce from current (idle = HIGH with pull-up).
  for (Button& b : buttons) {
    bool raw = digitalRead(b.pin) == HIGH;
    b.lastRaw = raw;
    b.lastStable = raw;
    b.lastChangeMs = millis();
  }

  connectWifi();

  // Optional readiness ping (does not toggle outlets).
  callBridge("/health");
  ledsDark();
}

void loop() {
  unsigned long now = millis();

  for (Button& b : buttons) {
    bool raw = digitalRead(b.pin) == HIGH;  // HIGH = released (pull-up)
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

    // Falling edge: pressed to GND
    if (!raw) {
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
