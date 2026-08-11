#include <M5Stack.h>
#include "utility/MPU9250.h"
#include <math.h>

MPU9250 IMU;
TFT_eSprite img = TFT_eSprite(&M5.Lcd);

static const int W = 320;
static const int H = 240;
static const int CX = W / 2;
static const int CY = H / 2;

static const uint16_t COL_SKY    = 0x051D;   // deep blue (original)
static const uint16_t COL_GROUND = 0x6A06;   // brown (original bit pattern)
static const uint16_t COL_ORANGE = 0xFBE4;
static const uint16_t COL_WHITE  = TFT_WHITE;
static const uint16_t COL_BLACK  = TFT_BLACK;

// Hershey Simplex digits (Paul Bourke). Width first, then x,y pairs.
// Pen-up = 127,127. Glyph end = 126. Y is up; we flip when drawing.
static const int8_t HER_PEN = 127;
static const int8_t HER_END = 126;

static const int8_t HER_0[] = {
    20, 9, 21, 6, 20, 4, 17, 3, 12, 3, 9, 4, 4, 6, 1, 9, 0, 11, 0, 14, 1,
    16, 4, 17, 9, 17, 12, 16, 17, 14, 20, 11, 21, 9, 21, HER_END};
static const int8_t HER_1[] = {
    20, 6, 17, 8, 18, 11, 21, 11, 0, HER_END};
static const int8_t HER_2[] = {
    20, 4, 16, 4, 17, 5, 19, 6, 20, 8, 21, 12, 21, 14, 20, 15, 19, 16, 17,
    16, 15, 15, 13, 13, 10, 3, 0, 17, 0, HER_END};
static const int8_t HER_3[] = {
    20, 5, 21, 16, 21, 10, 13, 13, 13, 15, 12, 16, 11, 17, 8, 17, 6, 16, 3,
    14, 1, 11, 0, 8, 0, 5, 1, 4, 2, 3, 4, HER_END};
static const int8_t HER_4[] = {
    20, 13, 21, 3, 7, 18, 7, HER_PEN, HER_PEN, 13, 21, 13, 0, HER_END};
static const int8_t HER_5[] = {
    20, 15, 21, 5, 21, 4, 12, 5, 13, 8, 14, 11, 14, 14, 13, 16, 11, 17, 8,
    17, 6, 16, 3, 14, 1, 11, 0, 8, 0, 5, 1, 4, 2, 3, 4, HER_END};
static const int8_t HER_6[] = {
    20, 16, 18, 15, 20, 12, 21, 10, 21, 7, 20, 5, 17, 4, 12, 4, 7, 5, 3, 7,
    1, 10, 0, 11, 0, 14, 1, 16, 3, 17, 6, 17, 7, 16, 10, 14, 12, 11, 13, 10,
    13, 7, 12, 5, 10, 4, 7, HER_END};
static const int8_t HER_7[] = {
    20, 17, 21, 7, 0, HER_PEN, HER_PEN, 3, 21, 17, 21, HER_END};
static const int8_t HER_8[] = {
    20, 8, 21, 5, 20, 4, 18, 4, 16, 5, 14, 7, 13, 11, 12, 14, 11, 16, 9, 17,
    7, 17, 4, 16, 2, 15, 1, 12, 0, 8, 0, 5, 1, 4, 2, 3, 4, 3, 7, 4, 9, 6, 11,
    9, 12, 13, 13, 15, 14, 16, 16, 16, 18, 15, 20, 12, 21, 8, 21, HER_END};
static const int8_t HER_9[] = {
    20, 16, 14, 15, 11, 13, 9, 10, 8, 9, 8, 6, 9, 4, 11, 3, 14, 3, 15, 4, 18,
    6, 20, 9, 21, 10, 21, 13, 20, 15, 18, 16, 14, 16, 9, 15, 4, 13, 1, 10, 0,
    8, 0, 5, 1, 4, 3, HER_END};

static const int8_t *const HER_DIGITS[10] = {
    HER_0, HER_1, HER_2, HER_3, HER_4, HER_5, HER_6, HER_7, HER_8, HER_9};

static const float BANK_MARK_DEG[] = {-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60};
static const float BANK_MARK_LEN[] = {2, 1, 2, 1, 1, 2, 1, 1, 2, 1, 2};

struct Vec2 {
  float x, y;
};

static inline Vec2 v2(float x, float y) { return {x, y}; }
static inline Vec2 operator+(Vec2 a, Vec2 b) { return {a.x + b.x, a.y + b.y}; }
static inline Vec2 operator-(Vec2 a, Vec2 b) { return {a.x - b.x, a.y - b.y}; }
static inline Vec2 operator*(Vec2 a, float s) { return {a.x * s, a.y * s}; }
static inline Vec2 perp(Vec2 a) { return {-a.y, a.x}; }
static inline float dot(Vec2 a, Vec2 b) { return a.x * b.x + a.y * b.y; }
static inline float lengthSq(Vec2 a) { return dot(a, a); }

// Half-width of circle at scanline y. Returns false if the row misses the circle.
static bool circleSpan(int y, float r, int &x0, int &x1) {
  float dy = (float)y - CY;
  float t = r * r - dy * dy;
  if (t < 0) return false;
  float dx = sqrtf(t);
  x0 = (int)ceilf(CX - dx);
  x1 = (int)floorf(CX + dx);
  if (x0 < 0) x0 = 0;
  if (x1 >= W) x1 = W - 1;
  return x0 <= x1;
}

static void hline(int x0, int x1, int y, uint16_t c) {
  if (x1 < x0 || y < 0 || y >= H) return;
  if (x0 < 0) x0 = 0;
  if (x1 >= W) x1 = W - 1;
  img.drawFastHLine(x0, y, x1 - x0 + 1, c);
}

// Fill disk: each scanline split by the horizon plane (point · bankUp vs pitch offset).
static void fillDiskHorizon(float r, Vec2 bankUp, float pitchDeg) {
  // Signed distance from screen center to horizon along bankUp.
  const float horizon = pitchDeg * 3.0f;

  for (int y = (int)floorf(CY - r); y <= (int)ceilf(CY + r); y++) {
    int x0, x1;
    if (!circleSpan(y, r, x0, x1)) continue;

    // On this row, horizon crosses where (p - C) · bankUp == horizon.
    // (x - CX) * ux + (y - CY) * uy = horizon
    float uy = bankUp.y;
    float ux = bankUp.x;
    float rowTerm = ((float)y - CY) * uy;

    if (fabsf(ux) < 1e-4f) {
      // +bankUp side of the horizon is sky (original blue poly).
      uint16_t c = (rowTerm >= horizon) ? COL_SKY : COL_GROUND;
      hline(x0, x1, y, c);
      continue;
    }

    float xH = CX + (horizon - rowTerm) / ux;
    int xSplit = (int)floorf(xH);

    // Larger x raises (p-C)·bankUp when ux > 0 → sky.
    uint16_t cLowX  = (ux > 0) ? COL_GROUND : COL_SKY;
    uint16_t cHighX = (ux > 0) ? COL_SKY : COL_GROUND;

    if (xSplit < x0) {
      hline(x0, x1, y, cHighX);
    } else if (xSplit >= x1) {
      hline(x0, x1, y, cLowX);
    } else {
      hline(x0, xSplit, y, cLowX);
      hline(xSplit + 1, x1, y, cHighX);
    }
  }
}

// Fill annulus with bank-relative sky/ground (independent of pitch).
static void fillAnnulusBank(float rInner, float rOuter, Vec2 bankUp) {
  for (int y = (int)floorf(CY - rOuter); y <= (int)ceilf(CY + rOuter); y++) {
    int xo0, xo1, xi0, xi1;
    if (!circleSpan(y, rOuter, xo0, xo1)) continue;
    bool hasInner = circleSpan(y, rInner, xi0, xi1);

    auto paintSpan = [&](int a, int b) {
      if (b < a) return;
      float uy = bankUp.y;
      float ux = bankUp.x;
      float rowTerm = ((float)y - CY) * uy;

      if (fabsf(ux) < 1e-4f) {
        hline(a, b, y, (rowTerm >= 0) ? COL_SKY : COL_GROUND);
        return;
      }

      float xH = CX + (0.0f - rowTerm) / ux;
      int xSplit = (int)floorf(xH);
      uint16_t cLowX  = (ux > 0) ? COL_GROUND : COL_SKY;
      uint16_t cHighX = (ux > 0) ? COL_SKY : COL_GROUND;

      if (xSplit < a) {
        hline(a, b, y, cHighX);
      } else if (xSplit >= b) {
        hline(a, b, y, cLowX);
      } else {
        hline(a, xSplit, y, cLowX);
        hline(xSplit + 1, b, y, cHighX);
      }
    };

    if (!hasInner) {
      paintSpan(xo0, xo1);
    } else {
      paintSpan(xo0, xi0 - 1);
      paintSpan(xi1 + 1, xo1);
    }
  }
}

// Clip segment AB to disk. Returns false if fully outside.
static bool clipSegmentToCircle(Vec2 a, Vec2 b, float r, Vec2 &ca, Vec2 &cb) {
  Vec2 c = v2(CX, CY);
  Vec2 pa = a - c;
  Vec2 d = b - a;
  float A = lengthSq(d);
  float B = 2.0f * dot(pa, d);
  float C = lengthSq(pa) - r * r;

  if (A < 1e-12f) {
    if (C > 0) return false;
    ca = cb = a;
    return true;
  }

  float disc = B * B - 4.0f * A * C;
  if (disc < 0) return false;

  float s = sqrtf(disc);
  float t0 = (-B - s) / (2.0f * A);
  float t1 = (-B + s) / (2.0f * A);

  float u0 = fmaxf(0.0f, t0);
  float u1 = fminf(1.0f, t1);
  if (u0 > u1) return false;

  ca = a + d * u0;
  cb = a + d * u1;
  return true;
}

static void drawLineClipped(Vec2 a, Vec2 b, float r, uint16_t color) {
  Vec2 ca, cb;
  if (!clipSegmentToCircle(a, b, r, ca, cb)) return;
  img.drawLine((int)lroundf(ca.x), (int)lroundf(ca.y),
               (int)lroundf(cb.x), (int)lroundf(cb.y), color);
}

// Map Hershey (x right, y up) into screen basis (along, down).
static Vec2 hersheyToScreen(Vec2 origin, Vec2 along, Vec2 down, float scale,
                            float hx, float hy, float cx, float cy) {
  return origin + along * ((hx - cx) * scale) + down * ((cy - hy) * scale);
}

static void drawHersheyDigit(int d, Vec2 origin, Vec2 along, Vec2 down, float scale,
                             float clipR, uint16_t c) {
  if (d < 0 || d > 9) return;
  const int8_t *g = HER_DIGITS[d];
  float width = (float)g[0];
  float cx = width * 0.5f;
  float cy = 10.5f;  // mid of typical 0..21 cap height

  bool have = false;
  Vec2 prev;
  for (int i = 1; g[i] != HER_END; i += 2) {
    if (g[i] == HER_PEN && g[i + 1] == HER_PEN) {
      have = false;
      continue;
    }
    Vec2 p = hersheyToScreen(origin, along, down, scale, (float)g[i],
                             (float)g[i + 1], cx, cy);
    if (have) {
      drawLineClipped(prev, p, clipR, c);
    }
    prev = p;
    have = true;
  }
}

static void drawNumberOriented(int value, Vec2 anchor, Vec2 along, float scale,
                               float clipR, uint16_t c) {
  Vec2 down = perp(along);
  // Hershey digit cell is ~20 wide, height ~21; small tracking gap.
  float cell = 20.0f * scale;
  float gap  = 3.0f * scale;
  float totalW = cell * 2.0f + gap;

  Vec2 leftOrigin = anchor - along * (totalW * 0.5f - cell * 0.5f);
  Vec2 rightOrigin = leftOrigin + along * (cell + gap);

  drawHersheyDigit(value / 10, leftOrigin, along, down, scale, clipR, c);
  drawHersheyDigit(value % 10, rightOrigin, along, down, scale, clipR, c);
}

static void drawPitchLadder(Vec2 bankRight, Vec2 bankUp, float pitchDeg, float clipR) {
  for (int i = -6; i <= 6; i++) {
    float step = (float)(i * 5);
    Vec2 mid   = v2(CX, CY) + bankUp * ((pitchDeg + step) * 3.0f);

    float halfLen = (i == 0) ? 2.0f : ((i % 2 != 0) ? 1.0f : (float)(abs(i) + 1));
    halfLen *= (100.0f / 12.0f);

    drawLineClipped(mid - bankRight * halfLen, mid + bankRight * halfLen, clipR,
                    COL_WHITE);

    if (i == 0 || (i % 2) != 0) continue;

    float labelOff = halfLen + (100.0f / 12.0f) * 1.5f;
    drawNumberOriented(abs(i * 5), mid + bankRight * labelOff, bankRight, 0.55f,
                       clipR, COL_WHITE);
    drawNumberOriented(abs(i * 5), mid - bankRight * labelOff, bankRight, 0.55f,
                       clipR, COL_WHITE);
  }
}

static void drawFixedAircraft(float tickLen) {
  img.fillRect(CX - 70, CY - 1, 50, 3, COL_ORANGE);
  img.fillRect(CX + 20, CY - 1, 50, 3, COL_ORANGE);
  img.fillTriangle(CX, (int)(tickLen * 2), CX + 10, (int)(tickLen * 2) + 20,
                   CX - 10, (int)(tickLen * 2) + 20, COL_ORANGE);
}

static void drawBankTicks(float bankRad, float r, float tickLen) {
  for (int i = 0; i < 11; i++) {
    float aa = bankRad + BANK_MARK_DEG[i] * DEG_TO_RAD;
    float c = cosf(aa);
    float s = sinf(aa);
    float l = BANK_MARK_LEN[i] * tickLen + r;
    img.drawLine(CX + (int)lroundf(r * s), CY - (int)lroundf(r * c),
                 CX + (int)lroundf(l * s), CY - (int)lroundf(l * c), COL_WHITE);
  }
}

// Boxcar moving average on the gravity vector (~12 * 30ms ≈ 360ms window).
static const int ACCEL_MA_N = 12;
static float axHist[ACCEL_MA_N];
static float ayHist[ACCEL_MA_N];
static float azHist[ACCEL_MA_N];
static int accelMaIdx = 0;
static int accelMaCount = 0;
static float axSum = 0, aySum = 0, azSum = 0;

static void pushAccelMA(float ax, float ay, float az) {
  if (accelMaCount == ACCEL_MA_N) {
    axSum -= axHist[accelMaIdx];
    aySum -= ayHist[accelMaIdx];
    azSum -= azHist[accelMaIdx];
  } else {
    accelMaCount++;
  }
  axHist[accelMaIdx] = ax;
  ayHist[accelMaIdx] = ay;
  azHist[accelMaIdx] = az;
  axSum += ax;
  aySum += ay;
  azSum += az;
  accelMaIdx = (accelMaIdx + 1) % ACCEL_MA_N;
}

void setup() {
  M5.begin();
  // M5 init may send TFT_INVON for some panel revisions; that yields
  // complementary colors (blue→orange, brown→cyan). Restore normal polarity.
  M5.Lcd.invertDisplay(true);
  M5.Lcd.fillScreen(TFT_NAVY);
  M5.Power.begin();
  Serial.begin(115200);
  Wire.begin();
  delay(200);

  // 8bpp RGB332 was mangling colors (black↔white, brown→orange, etc.).
  img.setColorDepth(16);
  if (img.createSprite(W, H) == nullptr) {
    // Fallback if 16-bit full frame is too large for heap.
    img.setColorDepth(8);
    img.createSprite(W, H);
  }
}

void loop() {
  if (!(IMU.readByte(MPU9250_ADDRESS, INT_STATUS) & 0x01)) {
    delay(30);
    return;
  }

  IMU.readAccelData(IMU.accelCount);
  IMU.getAres();

  pushAccelMA((float)IMU.accelCount[0] * IMU.aRes,
              (float)IMU.accelCount[1] * IMU.aRes,
              (float)IMU.accelCount[2] * IMU.aRes);

  float ax = axSum / (float)accelMaCount;
  float ay = aySum / (float)accelMaCount;
  float az = azSum / (float)accelMaCount;

  float br = sqrtf(ax * ax + ay * ay);
  if (br < 1e-6f) {
    delay(30);
    return;
  }

  Vec2 bankRight = v2(ay / br, ax / br);
  Vec2 bankUp    = v2(ax / br, -ay / br);

  float bankRad  = atan2f(ax, ay);
  float pitchDeg = atan2f(az, ay) * RAD_TO_DEG;

  const float rInner = H / 2.0f - 30.0f;
  const float tickLen = 15.0f;
  const float rOuter = rInner + tickLen * 2.0f;

  img.fillScreen(COL_BLACK);
  fillDiskHorizon(rInner, bankUp, pitchDeg);
  drawPitchLadder(bankRight, bankUp, pitchDeg, rInner);
  drawFixedAircraft(tickLen);
  fillAnnulusBank(rInner, rOuter, bankUp);
  drawBankTicks(bankRad, rInner, tickLen);

  img.pushSprite(0, 0);
  delay(30);
}
