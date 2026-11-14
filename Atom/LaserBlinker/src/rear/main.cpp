#include <Arduino.h>
#include <FastLED.h>
#include "pins.h"
#include "protocol.h"

static CRGB leds[NUM_LEDS];
static HardwareSerial LinkSerial(1);
static char turn = TURN_OFF;
static bool brake = false;
static bool blink_on = false;
static uint32_t last_blink_ms = 0;
static uint32_t last_rx_ms = 0;
static char line_buf[64];
static size_t line_len = 0;
static bool demo_mode = false;
static uint8_t demo_step = 0;

struct DemoState {
  char turn;
  bool brake;
};

static const DemoState DEMO_STATES[] = {
    {TURN_OFF, false},  // idle（尾灯）
    {TURN_OFF, true},   // ブレーキ
    {TURN_L, false},    // 左ウインカー
    {TURN_R, false},    // 右ウインカー
    {'B', false},       // ハザード
};
static const size_t DEMO_STATE_COUNT =
    sizeof(DEMO_STATES) / sizeof(DEMO_STATES[0]);

static bool linkOk() { return (millis() - last_rx_ms) < FAILSAFE_MS; }

static bool effectiveLinkOk() { return linkOk() || demo_mode; }

static void allOff() {
  fill_solid(leds, NUM_LEDS, CRGB::Black);
  FastLED.show();
}

// 内蔵青LED（active LOW）: 無通信=点灯 / 通信またはデモ=点滅 or 消灯
static void renderStatusLed() {
  if (!effectiveLinkOk()) {
    digitalWrite(PIN_STATUS_LED, LOW);  // ON
    return;
  }
  if (turn != TURN_OFF) {
    digitalWrite(PIN_STATUS_LED, blink_on ? LOW : HIGH);
    return;
  }
  if (brake) {
    digitalWrite(PIN_STATUS_LED, LOW);
    return;
  }
  digitalWrite(PIN_STATUS_LED, HIGH);  // idle: OFF
}

static void renderTape() {
  if (!effectiveLinkOk()) {
    allOff();
    return;
  }

  fill_solid(leds, NUM_LEDS, CRGB::Black);

  if (brake) {
    fill_solid(leds, NUM_LEDS, CRGB(120, 0, 0));
  } else {
    const int mid0 = NUM_LEDS / 4;
    const int mid1 = NUM_LEDS - mid0;
    for (int i = mid0; i < mid1; ++i) {
      leds[i] = CRGB(40, 0, 0);
    }
  }

  if (blink_on) {
    if (turn == TURN_L || turn == 'B') {
      for (int i = 0; i < EDGE_LEDS && i < NUM_LEDS; ++i) {
        leds[i] = CRGB(255, 140, 0);
      }
    }
    if (turn == TURN_R || turn == 'B') {
      for (int i = 0; i < EDGE_LEDS && i < NUM_LEDS; ++i) {
        leds[NUM_LEDS - 1 - i] = CRGB(255, 140, 0);
      }
    }
  }

  FastLED.show();
}

static void render() {
  renderStatusLed();
  renderTape();
}

static void bootSelfTest() {
  for (int i = 0; i < NUM_LEDS; ++i) {
    fill_solid(leds, NUM_LEDS, CRGB::Black);
    leds[i] = CRGB(60, 60, 60);
    FastLED.show();
    delay(20);
  }
  fill_solid(leds, NUM_LEDS, CRGB(0, 40, 0));
  FastLED.show();
  delay(150);
  allOff();
}

static void handleLine(char *line) {
  Serial.printf("[rear] line: %s\n", line);
  if (strncmp(line, "S,", 2) != 0) {
    Serial.println("[rear] ignore (not S,)");
    return;
  }

  char t = TURN_OFF;
  int b = 0;
  char *p = line + 2;
  while (*p) {
    if (strncmp(p, "turn=", 5) == 0) {
      t = p[5];
      p += 6;
    } else if (strncmp(p, "brake=", 6) == 0) {
      b = atoi(p + 6);
      p += 7;
    } else {
      ++p;
    }
  }

  turn = t;
  brake = (b != 0);
  demo_mode = false;
  last_rx_ms = millis();
  LinkSerial.print("ACK\n");
  Serial.printf("[rear] ok turn=%c brake=%d\n", turn, brake ? 1 : 0);
  render();
}

static void applyDemoState() {
  const DemoState &s = DEMO_STATES[demo_step];
  turn = s.turn;
  brake = s.brake;
}

static void onDemoButton() {
  if (linkOk()) return;

  if (!demo_mode) {
    demo_mode = true;
    demo_step = 0;
  } else {
    demo_step = (demo_step + 1) % DEMO_STATE_COUNT;
  }
  applyDemoState();
  render();
  Serial.printf("[rear] demo %u/%u turn=%c brake=%d\n", demo_step + 1,
                (unsigned)DEMO_STATE_COUNT, turn, brake ? 1 : 0);
}

static void pollUart() {
  static uint32_t last_rx_byte_log_ms = 0;
  static uint16_t rx_byte_count = 0;
  static uint8_t recent[16];
  static uint8_t recent_n = 0;

  while (LinkSerial.available()) {
    char c = (char)LinkSerial.read();
    rx_byte_count++;
    if (recent_n < sizeof(recent)) {
      recent[recent_n++] = (uint8_t)c;
    }
    const uint32_t now = millis();
    if ((now - last_rx_byte_log_ms) > 500) {
      Serial.printf("[rear] rx bytes=%u last=0x%02X sample:", rx_byte_count,
                    (unsigned char)c);
      for (uint8_t i = 0; i < recent_n; ++i) {
        Serial.printf(" %02X", recent[i]);
      }
      Serial.println();
      last_rx_byte_log_ms = now;
      rx_byte_count = 0;
      recent_n = 0;
    }
    if (c == '\r') continue;
    if (c == '\n') {
      line_buf[line_len] = '\0';
      if (line_len > 0) handleLine(line_buf);
      line_len = 0;
    } else if (line_len + 1 < sizeof(line_buf)) {
      line_buf[line_len++] = c;
    } else {
      line_len = 0;
    }
  }
}

static void pollDemoButton() {
  static bool raw = true;
  static bool stable = true;
  static bool was_pressed = false;
  static uint32_t last_change = 0;

  const bool now = digitalRead(PIN_DEMO_BTN);  // HIGH=離し, LOW=押し
  const uint32_t t = millis();
  if (now != raw) {
    raw = now;
    last_change = t;
  } else if ((t - last_change) >= BTN_DEBOUNCE_MS) {
    stable = raw;
  }

  const bool pressed = !stable;
  if (pressed && !was_pressed) {
    onDemoButton();
  }
  was_pressed = pressed;
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(PIN_STATUS_LED, OUTPUT);
  digitalWrite(PIN_STATUS_LED, HIGH);
  pinMode(PIN_DEMO_BTN, INPUT_PULLUP);

  LinkSerial.begin(LINK_BAUD, SERIAL_8N1, PIN_LINK_RX, PIN_LINK_TX);
  // MAX485のA/B極性やモジュール印字差で論理が反転することがある
  LinkSerial.setRxInvert(true);

  FastLED.addLeds<WS2812, PIN_WS2812, GRB>(leds, NUM_LEDS);
  FastLED.setBrightness(TAPE_BRIGHTNESS);
  allOff();
  bootSelfTest();

  last_rx_ms = 0;
  renderStatusLed();
  Serial.printf("[rear] C3 ready NUM_LEDS=%d DATA=G%d UART=G%d/G%d\n",
                NUM_LEDS, PIN_WS2812, PIN_LINK_RX, PIN_LINK_TX);
  Serial.println("[rear] standalone: press BOOT to cycle demo states");
}

void loop() {
  pollUart();
  pollDemoButton();

  const uint32_t t = millis();
  if ((t - last_blink_ms) >= BLINK_HALF_MS) {
    last_blink_ms = t;
    blink_on = !blink_on;
    render();
  }

  static uint32_t last_fail_check = 0;
  if ((t - last_fail_check) > 50) {
    last_fail_check = t;
    if (!effectiveLinkOk()) {
      allOff();
      renderStatusLed();
    }
  }
}
