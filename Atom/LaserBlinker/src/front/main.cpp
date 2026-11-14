#include <Arduino.h>
#include <FastLED.h>
#include "pins.h"
#include "protocol.h"

struct Debounced {
  bool raw = false;
  bool stable = false;
  uint32_t last_change = 0;
};

static Debounced sw_l, sw_r, sw_brake;
static CRGB status_leds[NUM_STATUS_LEDS];
static HardwareSerial LinkSerial(1);
static bool lamp_l = false;
static bool lamp_r = false;
static bool blink_on = false;
static uint32_t last_blink_ms = 0;
static uint32_t last_send_ms = 0;
static char last_turn = TURN_OFF;
static bool last_brake = false;

static void debounce(Debounced &d, bool now, uint32_t t) {
  if (now != d.raw) {
    d.raw = now;
    d.last_change = t;
  } else if ((t - d.last_change) >= SW_DEBOUNCE_MS) {
    d.stable = d.raw;
  }
}

static bool swPressed(int pin) { return digitalRead(pin) == LOW; }

static char currentTurn() {
  if (sw_l.stable && sw_r.stable) return TURN_L;  // ハザードは左右両方点滅扱い（後部で両端）
  if (sw_l.stable) return TURN_L;
  if (sw_r.stable) return TURN_R;
  return TURN_OFF;
}

static void sendLinkState(bool force) {
  const char turn = currentTurn();
  const bool brake = sw_brake.stable;
  const uint32_t t = millis();
  if (!force && turn == last_turn && brake == last_brake &&
      (t - last_send_ms) < LINK_SEND_MS) {
    return;
  }
  last_turn = turn;
  last_brake = brake;
  last_send_ms = t;

  // ハザード時は turn=H も送れるが、ver0 は L+R 両点滅を後部で turn=L かつ両端、として
  // 別フィールドにせず、両押し時は turn=B（both）を送る
  char tcode = turn;
  if (sw_l.stable && sw_r.stable) tcode = 'B';

  char buf[48];
  snprintf(buf, sizeof(buf), "S,turn=%c,brake=%d\n", tcode, brake ? 1 : 0);
  LinkSerial.print(buf);
}

static void renderStatus() {
  fill_solid(status_leds, NUM_STATUS_LEDS, CRGB::Black);

  if (sw_brake.stable) {
    fill_solid(status_leds, NUM_STATUS_LEDS, CRGB(160, 0, 0));
  }
  if (lamp_l) {
    status_leds[0] = CRGB(255, 100, 0);
  }
  if (lamp_r) {
    status_leds[NUM_STATUS_LEDS - 1] = CRGB(255, 100, 0);
  }

  FastLED.show();
}

static void logState() {
  char turn = TURN_OFF;
  if (sw_l.stable && sw_r.stable) {
    turn = 'B';
  } else {
    turn = currentTurn();
  }
  Serial.printf("[front] turn=%c brake=%d lampL=%d lampR=%d\n", turn,
                sw_brake.stable ? 1 : 0, lamp_l ? 1 : 0, lamp_r ? 1 : 0);
}

void setup() {
  Serial.begin(115200);

  pinMode(PIN_SW_TURN_L, INPUT_PULLUP);
  pinMode(PIN_SW_TURN_R, INPUT_PULLUP);
  pinMode(PIN_SW_BRAKE, INPUT_PULLUP);
  pinMode(PIN_MOSFET_TURN_L, OUTPUT);
  pinMode(PIN_MOSFET_TURN_R, OUTPUT);
  digitalWrite(PIN_MOSFET_TURN_L, LOW);
  digitalWrite(PIN_MOSFET_TURN_R, LOW);

  FastLED.addLeds<WS2812, PIN_STATUS_WS2812, GRB>(status_leds,
                                                  NUM_STATUS_LEDS);
  FastLED.setBrightness(STATUS_BRIGHTNESS);
  renderStatus();

  LinkSerial.begin(LINK_BAUD, SERIAL_8N1, PIN_LINK_RX, PIN_LINK_TX);
  sendLinkState(true);

  Serial.printf("[front] C3 ready SW=%d/%d/%d MOSFET=%d/%d DATA=%d UART=%d/%d\n",
                PIN_SW_TURN_L, PIN_SW_TURN_R, PIN_SW_BRAKE,
                PIN_MOSFET_TURN_L, PIN_MOSFET_TURN_R, PIN_STATUS_WS2812,
                PIN_LINK_RX, PIN_LINK_TX);
}

void loop() {
  const uint32_t t = millis();

  debounce(sw_l, swPressed(PIN_SW_TURN_L), t);
  debounce(sw_r, swPressed(PIN_SW_TURN_R), t);
  debounce(sw_brake, swPressed(PIN_SW_BRAKE), t);

  if ((t - last_blink_ms) >= BLINK_HALF_MS) {
    last_blink_ms = t;
    blink_on = !blink_on;
  }

  // ハザードは左右とも点滅
  const bool want_l = sw_l.stable && blink_on;
  const bool want_r = sw_r.stable && blink_on;
  bool output_changed = false;
  if (want_l != lamp_l) {
    lamp_l = want_l;
    digitalWrite(PIN_MOSFET_TURN_L, lamp_l ? HIGH : LOW);
    output_changed = true;
  }
  if (want_r != lamp_r) {
    lamp_r = want_r;
    digitalWrite(PIN_MOSFET_TURN_R, lamp_r ? HIGH : LOW);
    output_changed = true;
  }

  sendLinkState(false);

  static bool prev_l = false, prev_r = false, prev_b = false;
  const bool input_changed = (sw_l.stable != prev_l) ||
                             (sw_r.stable != prev_r) ||
                             (sw_brake.stable != prev_b);
  if (input_changed) {
    prev_l = sw_l.stable;
    prev_r = sw_r.stable;
    prev_b = sw_brake.stable;
    logState();
  }
  if (input_changed || output_changed) {
    renderStatus();
  }
}
