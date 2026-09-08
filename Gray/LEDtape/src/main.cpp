#include <M5Stack.h>
#include <FastLED.h>

// --- LED tape (GROVE Port B = GPIO 26) ---
#define LED_PIN 26
#define NUM_LEDS 144
#define COLOR_ORDER GRB
#define BRIGHTNESS 40

// 「白いボックス」のドット幅
#define BOX_SIZE 3
#define MAX_BOXES (NUM_LEDS / BOX_SIZE)

// 物理パラメータ（見た目で調整）
static const float GRAVITY = 160.0f;     // LED/s^2
static const float RESTITUTION = 0.68f;  // 反発係数 (<1 で収束)
static const float STOP_SPEED = 5.0f;    // これ以下で着地静止
static const float FLOOR_EPS = 0.08f;

CRGB leds[NUM_LEDS];

enum class BoxState : uint8_t { Falling, Settled, Ejecting };

struct Box {
  float pos;  // 上端 (0=先頭/上、大きいほど下)
  float vel;  // LED/s（下向き正）
  BoxState state;
  CRGB color;
};

Box boxes[MAX_BOXES];
int boxCount = 0;
bool colorMode = false;  // false=白一色, true=各ボックス別色

uint32_t lastMs = 0;
bool lcdDirty = true;

CRGB randomBoxColor() {
  // 暗すぎない彩度高めの色
  return CHSV(random8(), 255, 255);
}

void clearLeds() { fill_solid(leds, NUM_LEDS, CRGB::Black); }

void drawBoxes() {
  clearLeds();
  for (int i = 0; i < boxCount; ++i) {
    CRGB c = colorMode ? boxes[i].color : CRGB::White;
    int start = int(boxes[i].pos + 0.5f);
    for (int j = 0; j < BOX_SIZE; ++j) {
      int idx = start + j;
      if (idx >= 0 && idx < NUM_LEDS) {
        leds[idx] = c;
      }
    }
  }
  FastLED.show();
}

void toggleColorMode() {
  colorMode = !colorMode;
  if (colorMode) {
    for (int i = 0; i < boxCount; ++i) {
      boxes[i].color = randomBoxColor();
    }
  }
  lcdDirty = true;
}

int countSettled() {
  int n = 0;
  for (int i = 0; i < boxCount; ++i) {
    if (boxes[i].state == BoxState::Settled) ++n;
  }
  return n;
}

bool canDrop() {
  if (boxCount >= MAX_BOXES) return false;
  for (int i = 0; i < boxCount; ++i) {
    if (boxes[i].pos < float(BOX_SIZE + 1)) return false;
  }
  return true;
}

void dropFromTop() {
  if (!canDrop()) return;
  Box &b = boxes[boxCount++];
  b.pos = 0.0f;
  b.vel = 0.0f;
  b.state = BoxState::Falling;
  b.color = randomBoxColor();
  lcdDirty = true;
}

void ejectAll() {
  if (boxCount == 0) return;
  for (int i = 0; i < boxCount; ++i) {
    boxes[i].state = BoxState::Ejecting;
    if (boxes[i].vel < 40.0f) boxes[i].vel = 40.0f;
  }
  lcdDirty = true;
}

void removeFinishedEjects() {
  for (int i = boxCount - 1; i >= 0; --i) {
    if (boxes[i].state == BoxState::Ejecting &&
        boxes[i].pos >= float(NUM_LEDS)) {
      for (int j = i; j < boxCount - 1; ++j) {
        boxes[j] = boxes[j + 1];
      }
      --boxCount;
      lcdDirty = true;
    }
  }
}

// 自分より下の箱（または床）に乗るときの、自分の上端位置
float supportTop(int self) {
  float best = float(NUM_LEDS - BOX_SIZE);
  for (int i = 0; i < boxCount; ++i) {
    if (i == self) continue;
    const Box &o = boxes[i];
    if (o.state == BoxState::Ejecting) continue;
    if (o.pos + 0.01f < boxes[self].pos) continue;  // 自分より上は無視
    float land = o.pos - float(BOX_SIZE);
    if (land < best) best = land;
  }
  return best;
}

void updatePhysics(float dt) {
  for (int i = 0; i < boxCount; ++i) {
    Box &b = boxes[i];
    if (b.state == BoxState::Settled) continue;
    b.vel += GRAVITY * dt;
    b.pos += b.vel * dt;
  }

  // 下側（pos 大）から順に解決
  int order[MAX_BOXES];
  for (int i = 0; i < boxCount; ++i) order[i] = i;
  for (int a = 0; a < boxCount - 1; ++a) {
    for (int b = a + 1; b < boxCount; ++b) {
      if (boxes[order[a]].pos < boxes[order[b]].pos) {
        int t = order[a];
        order[a] = order[b];
        order[b] = t;
      }
    }
  }

  for (int k = 0; k < boxCount; ++k) {
    int i = order[k];
    Box &b = boxes[i];
    if (b.state == BoxState::Settled || b.state == BoxState::Ejecting) {
      continue;
    }

    const float floor = supportTop(i);
    if (b.pos >= floor) {
      b.pos = floor;
      b.vel = -b.vel * RESTITUTION;
      // 支えが Settled（または床）のときだけ静止判定
      bool solidSupport = true;
      for (int j = 0; j < boxCount; ++j) {
        if (j == i) continue;
        if (boxes[j].state == BoxState::Ejecting) continue;
        if (fabsf((boxes[j].pos - float(BOX_SIZE)) - floor) < 0.5f) {
          if (boxes[j].state == BoxState::Falling) {
            solidSupport = false;
          }
          break;
        }
      }
      if (solidSupport && fabsf(b.vel) < STOP_SPEED) {
        b.pos = floor;
        b.vel = 0.0f;
        b.state = BoxState::Settled;
        lcdDirty = true;
      } else if (b.pos >= floor - FLOOR_EPS) {
        b.pos = floor - FLOOR_EPS;
      }
    }

    if (b.pos < 0.0f) {
      b.pos = 0.0f;
      if (b.vel < 0.0f) b.vel = 0.0f;
    }
  }

  removeFinishedEjects();
}

void drawLcd() {
  M5.Lcd.fillScreen(TFT_BLACK);
  M5.Lcd.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(10, 20);
  M5.Lcd.println("LED Gravity Stack");

  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(10, 55);
  M5.Lcd.printf("LEDs: %d  pin: %d\n", NUM_LEDS, LED_PIN);
  M5.Lcd.setCursor(10, 75);
  M5.Lcd.printf("boxes: %d / %d  settled: %d\n", boxCount, MAX_BOXES,
                countSettled());
  M5.Lcd.setCursor(10, 95);
  M5.Lcd.printf("color: %s\n", colorMode ? "random" : "white");

  M5.Lcd.setCursor(10, 180);
  M5.Lcd.setTextSize(2);
  M5.Lcd.println("A: drop");
  M5.Lcd.setCursor(10, 205);
  M5.Lcd.println("B: eject");
  M5.Lcd.setCursor(10, 230);
  M5.Lcd.println("C: color");
}

void setup() {
  M5.begin();
  M5.Power.begin();

  FastLED.addLeds<WS2812B, LED_PIN, COLOR_ORDER>(leds, NUM_LEDS)
      .setCorrection(TypicalLEDStrip);
  FastLED.setBrightness(BRIGHTNESS);
  clearLeds();
  FastLED.show();

  boxCount = 0;
  drawBoxes();
  drawLcd();
  lastMs = millis();
}

void loop() {
  M5.update();

  if (M5.BtnA.wasPressed()) {
    dropFromTop();
  }
  if (M5.BtnB.wasPressed()) {
    ejectAll();
  }
  if (M5.BtnC.wasPressed()) {
    toggleColorMode();
  }

  uint32_t now = millis();
  float dt = (now - lastMs) * 0.001f;
  lastMs = now;
  if (dt > 0.05f) dt = 0.05f;

  updatePhysics(dt);
  drawBoxes();

  static uint32_t lastLcd = 0;
  if (lcdDirty || (now - lastLcd) > 150) {
    drawLcd();
    lcdDirty = false;
    lastLcd = now;
  }
}
