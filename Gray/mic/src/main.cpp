#include <M5Stack.h>
#include <math.h>

// Unit MIC analog is 5V-side MAX4466.
// ESP32 ADC tops out ~3.3V -> easy to rail at 4095 and look "not like audio".
static const int MIC_ANALOG_PIN = 36;
static const int MIC_DIGITAL_PIN = 26;
static const int SPK_PIN = 25;

static const int N = 512;
static const uint32_t SAMPLE_US = 200;  // 5 kHz

static uint16_t buf[N];

static void silenceSpeaker() { dacWrite(SPK_PIN, 0); }

static void enableDacSpeaker() {
  M5.Speaker.end();
  silenceSpeaker();
}

static void playSine() {
  enableDacSpeaker();
  const uint32_t hz = 22050;
  const uint32_t us = 1000000UL / hz;
  const int nSamples = (int)(hz * 0.6f);
  float phase = 0;
  const float step = 2.0f * (float)M_PI * 440.0f / (float)hz;
  uint32_t next = micros();
  for (int i = 0; i < nSamples; i++) {
    while ((int32_t)(micros() - next) < 0) {
    }
    next += us;
    int out = 128 + (int)(sinf(phase) * 40);
    dacWrite(SPK_PIN, (uint8_t)constrain(out, 0, 255));
    phase += step;
    if (phase > 6.2831853f) phase -= 6.2831853f;
  }
  silenceSpeaker();
}

struct Stats {
  int vmin, vmax, mean;
  int nLow, nMid, nHigh;  // <400, 400..3695, >3695
  int zc;                 // zero-cross around mean
  float zcHz;
  const char *kind;
};

static Stats analyze() {
  uint32_t next = micros();
  uint32_t sum = 0;
  int vmin = 4095, vmax = 0;
  for (int i = 0; i < N; i++) {
    while ((int32_t)(micros() - next) < 0) {
    }
    next += SAMPLE_US;
    int v = analogRead(MIC_ANALOG_PIN);
    buf[i] = (uint16_t)v;
    sum += (uint32_t)v;
    if (v < vmin) vmin = v;
    if (v > vmax) vmax = v;
  }

  Stats s;
  s.vmin = vmin;
  s.vmax = vmax;
  s.mean = (int)(sum / (uint32_t)N);
  s.nLow = s.nMid = s.nHigh = 0;
  s.zc = 0;

  for (int i = 0; i < N; i++) {
    int v = buf[i];
    if (v < 400) {
      s.nLow++;
    } else if (v > 3695) {
      s.nHigh++;
    } else {
      s.nMid++;
    }
    if (i > 0) {
      bool a = buf[i - 1] >= s.mean;
      bool b = v >= s.mean;
      if (a != b) s.zc++;
    }
  }

  const float durSec = (float)N * (float)SAMPLE_US * 1e-6f;
  s.zcHz = (durSec > 0) ? (0.5f * (float)s.zc / durSec) : 0;

  const int rail = s.nLow + s.nHigh;
  if (rail > N * 3 / 10) {
    s.kind = "CLIP/RAIL (5V amp vs 3.3V ADC?)";
  } else if (s.zcHz > 800) {
    s.kind = "HF/noise-like (not voice)";
  } else if ((s.vmax - s.vmin) < 40) {
    s.kind = "almost flat";
  } else if (s.zcHz > 80 && s.zcHz < 600 && rail < N / 10) {
    s.kind = "maybe audio-ish";
  } else {
    s.kind = "odd / check wiring";
  }
  return s;
}

static void drawWave(const Stats &s) {
  const int top = 120;
  const int bot = 210;
  const int mid = (top + bot) / 2;
  M5.Lcd.fillRect(0, top, 320, bot - top, BLACK);
  M5.Lcd.drawFastHLine(0, mid, 320, DARKGREY);

  int half = (s.vmax - s.vmin) / 2;
  if (half < 80) half = 80;
  int lo = s.mean - half;
  int hi = s.mean + half;

  int prevY = mid;
  for (int x = 0; x < 320; x++) {
    int idx = x * N / 320;
    int y = map((int)buf[idx], lo, hi, bot - 1, top);
    y = constrain(y, top, bot - 1);
    if (x > 0) M5.Lcd.drawLine(x - 1, prevY, x, y, GREEN);
    prevY = y;
  }
}

static void drawUi(const Stats &s) {
  M5.Lcd.fillRect(0, 0, 320, 118, BLACK);
  M5.Lcd.setTextSize(1);
  M5.Lcd.setTextColor(WHITE, BLACK);
  M5.Lcd.setCursor(4, 4);
  M5.Lcd.print("Signal classify (not delta-sigma)");

  M5.Lcd.setTextColor(GREEN, BLACK);
  M5.Lcd.setCursor(4, 20);
  M5.Lcd.printf("min=%d max=%d mean=%d span=%d", s.vmin, s.vmax, s.mean,
                s.vmax - s.vmin);

  M5.Lcd.setCursor(4, 36);
  M5.Lcd.setTextColor(YELLOW, BLACK);
  M5.Lcd.printf("low%%=%d mid%%=%d high%%=%d", s.nLow * 100 / N,
                s.nMid * 100 / N, s.nHigh * 100 / N);

  M5.Lcd.setCursor(4, 52);
  M5.Lcd.printf("zc~%.0f Hz   DIG26=%d", s.zcHz, digitalRead(MIC_DIGITAL_PIN));

  M5.Lcd.setTextSize(2);
  M5.Lcd.setTextColor(CYAN, BLACK);
  M5.Lcd.setCursor(4, 70);
  M5.Lcd.print(s.kind);

  M5.Lcd.setTextSize(1);
  M5.Lcd.setTextColor(WHITE, BLACK);
  M5.Lcd.setCursor(4, 220);
  M5.Lcd.print("Quiet vs shout. C:Sine  If CLIP: divide 5V->3.3V");
}

void setup() {
  M5.begin(true, false, true);
  M5.Power.begin();
  enableDacSpeaker();
  pinMode(MIC_DIGITAL_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(MIC_ANALOG_PIN, ADC_11db);
  Serial.begin(115200);
  M5.Lcd.fillScreen(BLACK);
}

void loop() {
  M5.update();
  if (M5.BtnC.wasPressed()) playSine();

  Stats s = analyze();
  drawUi(s);
  drawWave(s);

  Serial.printf(
      "min=%d max=%d mean=%d low=%d mid=%d high=%d zcHz=%.1f dig=%d | %s\n",
      s.vmin, s.vmax, s.mean, s.nLow, s.nMid, s.nHigh, s.zcHz,
      digitalRead(MIC_DIGITAL_PIN), s.kind);
}
