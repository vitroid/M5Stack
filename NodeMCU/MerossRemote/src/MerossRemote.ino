/*
 * MerossRemote — DOIT.AM ESP8266 NodeMCU breadboard remote
 *
 * Day-to-day: buttons POST signed Meross LAN HTTP to each plug's /config
 * (no Mac required). Key + device IP/uuid live in secrets.h (gitignored).
 * Optional Mac bridge remains as fallback / future key-refresh stub only.
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
 * Copy secrets.h.example → include/secrets.h. Flash: pio run -t upload.
 */

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>
#include <MD5Builder.h>
#include <time.h>

#if __has_include("secrets.h")
#include "secrets.h"
#endif

#ifndef WIFI_SSID
#error "Copy secrets.h.example → include/secrets.h (WIFI_SSID / WIFI_PASSWORD / MEROSS_*)"
#endif
#ifndef WIFI_PASSWORD
#error "Set WIFI_PASSWORD"
#endif

// Prefer LAN direct when device key + IPs are present.
#if defined(MEROSS_KEY) && defined(LAMP_IP) && defined(LAMP_UUID) && defined(FAN_IP) && defined(FAN_UUID)
#define USE_LAN_DIRECT
#else
#ifndef BRIDGE_HOST
#error "Set MEROSS LAN macros (preferred) or BRIDGE_HOST fallback in secrets.h"
#endif
#endif

#ifndef BRIDGE_PORT
#define BRIDGE_PORT 8787
#endif

#ifndef MEROSS_CHANNEL
#define MEROSS_CHANNEL 0
#endif

// ---- fixed breadboard pin map (NodeMCU silkscreen) ----
static const int PIN_BTN_LAMP = D1;  // silk D1 → toggle ランプ
static const int PIN_BTN_FAN  = D2;  // silk D2 → toggle ファン

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

#ifndef DEBOUNCE_MS
#define DEBOUNCE_MS 40
#endif

#ifndef COOLDOWN_MS
#define COOLDOWN_MS 800
#endif

#ifndef NTP_SERVER
#define NTP_SERVER "pool.ntp.org"
#endif

WiFiClient wifiClient;
HTTPClient http;

struct Target {
  const char* name;
  const char* lanIp;
  const char* uuid;
  const char* bridgePath;  // fallback only
  // Optimistic channel-0 state; unknown until first successful GET.
  int8_t onGuess;  // -1 unknown, 0 off, 1 on
};

Target targets[] = {
#ifdef USE_LAN_DIRECT
  {"lamp", LAMP_IP, LAMP_UUID, "/toggle/lamp", -1},
  {"fan",  FAN_IP,  FAN_UUID,  "/toggle/fan",  -1},
#else
  {"lamp", "", "", "/toggle/lamp", -1},
  {"fan",  "", "", "/toggle/fan",  -1},
#endif
};

struct Button {
  Target* target;
  int pin;
  bool lastStable;
  bool lastRaw;
  unsigned long lastChangeMs;
  unsigned long lastFireMs;
};

Button buttons[] = {
  {&targets[0], PIN_BTN_LAMP, true, true, 0, 0},
  {&targets[1], PIN_BTN_FAN,  true, true, 0, 0},
};

// Cleared on auth/protocol failure — day-to-day reuse until fail.
bool g_lanKeyValid = true;
bool g_timeOk = false;

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

bool syncTime() {
  // Meross sign uses unix seconds; NTP required for valid MD5 signature.
  configTime(0, 0, NTP_SERVER, "time.nist.gov");
  Serial.print("NTP");
  for (int i = 0; i < 40; i++) {
    time_t now = time(nullptr);
    if (now > 1700000000) {  // roughly 2023+
      Serial.printf(" OK now=%ld\n", (long)now);
      g_timeOk = true;
      return true;
    }
    delay(250);
    Serial.print(".");
  }
  Serial.println(" fail");
  g_timeOk = false;
  return false;
}

String md5Hex(const String& input) {
  MD5Builder md5;
  md5.begin();
  md5.add(input);
  md5.calculate();
  return md5.toString();  // lowercase hex
}

String randomMessageId() {
  // 16 random alnum → md5 hex (same as meross-iot)
  const char* alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  char buf[17];
  for (int i = 0; i < 16; i++) {
    buf[i] = alphabet[random(0, 36)];
  }
  buf[16] = '\0';
  return md5Hex(String(buf));
}

String buildSignedBody(const char* method, const char* ns, const String& payloadJson,
                       const char* uuid) {
  String messageId = randomMessageId();
  time_t now = time(nullptr);
  String ts = String((unsigned long)now);
#ifdef USE_LAN_DIRECT
  String sign = md5Hex(messageId + MEROSS_KEY + ts);
#else
  String sign = "";
#endif
  String body = "{";
  body += "\"header\":{";
  body += "\"from\":\"http://0.0.0.0/config\",";
  body += "\"messageId\":\"" + messageId + "\",";
  body += "\"method\":\"";
  body += method;
  body += "\",";
  body += "\"namespace\":\"";
  body += ns;
  body += "\",";
  body += "\"payloadVersion\":1,";
  body += "\"sign\":\"" + sign + "\",";
  body += "\"timestamp\":";
  body += ts;
  body += ",";
  body += "\"triggerSrc\":\"Android\",";
  body += "\"uuid\":\"";
  body += uuid;
  body += "\"";
  body += "},";
  body += "\"payload\":";
  body += payloadJson;
  body += "}";
  return body;
}

bool httpPostJson(const String& url, const String& body, String& responseOut) {
  http.setTimeout(4000);
  http.setReuse(false);
  if (!http.begin(wifiClient, url)) {
    Serial.println("http.begin failed");
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  int code = http.POST(body);
  responseOut = http.getString();
  http.end();
  Serial.printf("POST %s → HTTP %d\n", url.c_str(), code);
  if (code > 0) {
    Serial.println(responseOut);
  } else {
    Serial.printf("HTTP fail: %s\n", http.errorToString(code).c_str());
  }
  return code == HTTP_CODE_OK;
}

// Optional Mac helper stub — only when LAN key is marked invalid.
bool requestMacKeyRefreshStub() {
  Serial.println("LAN key invalid — Mac refresh stub (not implemented; re-run export_lan_devices.py)");
#ifdef BRIDGE_HOST
  String url = String("http://") + BRIDGE_HOST + ":" + String(BRIDGE_PORT) + "/health";
  http.setTimeout(3000);
  if (!http.begin(wifiClient, url)) {
    return false;
  }
  int code = http.GET();
  String body = http.getString();
  http.end();
  Serial.printf("refresh stub /health → %d %s\n", code, body.c_str());
#endif
  return false;
}

void markLanKeyFailed(const char* reason) {
  Serial.printf("LAN fail: %s — clearing key-valid flag\n", reason);
  g_lanKeyValid = false;
  requestMacKeyRefreshStub();
}

#ifdef USE_LAN_DIRECT
bool lanGetOn(Target& t, bool& onOut) {
  String payload = "{}";
  String body = buildSignedBody("GET", "Appliance.System.All", payload, t.uuid);
  String url = String("http://") + t.lanIp + "/config";
  String resp;
  if (!httpPostJson(url, body, resp)) {
    markLanKeyFailed("GET HTTP error");
    return false;
  }
  // Expect GETACK. Parse "onoff":N near togglex / channel 0 (simple scan).
  if (resp.indexOf("\"method\":\"ERROR\"") >= 0 || resp.indexOf("\"method\":\"error\"") >= 0) {
    markLanKeyFailed("GET ERROR payload");
    return false;
  }
  int idx = resp.indexOf("\"onoff\"");
  if (idx < 0) {
    markLanKeyFailed("GET missing onoff");
    return false;
  }
  int colon = resp.indexOf(':', idx);
  if (colon < 0) {
    return false;
  }
  int val = resp.substring(colon + 1).toInt();
  onOut = (val == 1);
  t.onGuess = onOut ? 1 : 0;
  return true;
}

bool lanSetOnOff(Target& t, int onoff) {
  String payload = String("{\"togglex\":{\"channel\":") + String(MEROSS_CHANNEL) +
                   ",\"onoff\":" + String(onoff) + "}}";
  String body = buildSignedBody("SET", "Appliance.Control.ToggleX", payload, t.uuid);
  String url = String("http://") + t.lanIp + "/config";
  String resp;
  if (!httpPostJson(url, body, resp)) {
    markLanKeyFailed("SET HTTP error");
    return false;
  }
  if (resp.indexOf("SETACK") < 0 && resp.indexOf("\"method\":\"SETACK\"") < 0) {
    // Some firmwares still succeed without literal; treat ERROR as fail.
    if (resp.indexOf("\"method\":\"ERROR\"") >= 0) {
      markLanKeyFailed("SET ERROR");
      return false;
    }
  }
  t.onGuess = onoff;
  return true;
}

bool lanToggle(Target& t) {
  if (!g_lanKeyValid) {
    Serial.println("LAN key invalid — skip (refresh secrets via export)");
    requestMacKeyRefreshStub();
    return false;
  }
  if (!g_timeOk) {
    syncTime();
    if (!g_timeOk) {
      Serial.println("no NTP time — cannot sign");
      return false;
    }
  }

  int want;
  if (t.onGuess < 0) {
    bool on = false;
    if (!lanGetOn(t, on)) {
      return false;
    }
    want = on ? 0 : 1;
  } else {
    want = t.onGuess ? 0 : 1;
  }
  Serial.printf("LAN toggle %s → onoff=%d @%s\n", t.name, want, t.lanIp);
  return lanSetOnOff(t, want);
}
#endif

bool callBridge(const char* path) {
#ifdef BRIDGE_HOST
  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
  }
  String url = String("http://") + BRIDGE_HOST + ":" + String(BRIDGE_PORT) + path;
  Serial.print("GET ");
  Serial.println(url);
  http.setTimeout(20000);
  http.setReuse(false);
  if (!http.begin(wifiClient, url)) {
    Serial.println("http.begin failed");
    return false;
  }
  int code = http.GET();
  if (code > 0) {
    Serial.printf("HTTP %d\n", code);
    Serial.println(http.getString());
  } else {
    Serial.printf("HTTP fail: %s\n", http.errorToString(code).c_str());
  }
  http.end();
  return code == HTTP_CODE_OK || code == HTTP_CODE_ACCEPTED;
#else
  (void)path;
  Serial.println("No BRIDGE_HOST — bridge fallback unavailable");
  return false;
#endif
}

bool fireTarget(Target& t) {
#ifdef USE_LAN_DIRECT
  if (g_lanKeyValid) {
    return lanToggle(t);
  }
  Serial.println("falling back to bridge (LAN key invalid)");
#endif
  return callBridge(t.bridgePath);
}

void setup() {
  Serial.begin(115200);
  delay(200);
  randomSeed(ESP.getCycleCount() ^ micros());
#ifdef USE_LAN_DIRECT
  Serial.println("MerossRemote LAN-direct boot — LEDs dark-by-default");
#else
  Serial.println("MerossRemote bridge-fallback boot — LEDs dark-by-default");
#endif

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
  syncTime();

#ifdef USE_LAN_DIRECT
  // Warm optimistic state with one GET each (no SET — leave outlets alone).
  for (Target& t : targets) {
    bool on = false;
    if (lanGetOn(t, on)) {
      Serial.printf("boot %s on=%d\n", t.name, on ? 1 : 0);
    }
  }
#else
  callBridge("/health");
#endif
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
        Serial.printf("skip %s (cooldown)\n", b.target->name);
        continue;
      }
      b.lastFireMs = now;
      Serial.printf("button %s pressed\n", b.target->name);
      briefFlash();
      fireTarget(*b.target);
      ledsDark();
    }
  }

  delay(5);
}
