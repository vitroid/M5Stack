#include <M5Stack.h>

// ---- Screen ----
static const int W = 320;
static const int H = 240;

// ---- Layout ----
static const int HUD_H = 16;
static const int PLAY_TOP = HUD_H + 2;
static const int PLAY_BOTTOM = 228;
static const int WALL = 2;

// ---- Paddle ----
static const int PADDLE_H = 6;
static const int PADDLE_Y = 214;
static const int PADDLE_SPEED = 5;
static const int PADDLE_W_MAX = 48;
static const int PADDLE_W_MIN = 28;

// ---- Ball ----
static const int BALL_R = 3;
static const float BALL_SPEED_BASE = 2.6f;
static const float BALL_SPEED_MAX = 5.2f;

// ---- Bricks ----
static const int BRICK_COLS = 10;
static const int BRICK_ROWS = 6;
static const int BRICK_GAP = 2;
static const int BRICK_AREA_L = 8;
static const int BRICK_AREA_R = W - 8;
static const int BRICK_AREA_T = PLAY_TOP + 10;
static const int BRICK_W =
    (BRICK_AREA_R - BRICK_AREA_L - BRICK_GAP * (BRICK_COLS - 1)) / BRICK_COLS;
static const int BRICK_H = 10;
static const int BRICK_COUNT = BRICK_COLS * BRICK_ROWS;

enum GameState { STATE_TITLE, STATE_PLAY, STATE_CLEAR, STATE_OVER };

struct Ball {
  float x, y;
  float vx, vy;
  bool stuck;  // held on paddle before launch
};

struct Brick {
  int16_t x, y;
  uint8_t hits;   // remaining hits (0 = gone)
  uint8_t maxHits;
  uint8_t kind;   // 0..5 row/color style
};

TFT_eSprite fb = TFT_eSprite(&M5.Lcd);

GameState state = STATE_TITLE;
uint32_t score = 0;
uint32_t highScore = 0;
uint8_t lives = 3;
uint8_t wave = 1;

int16_t paddleX = (W - PADDLE_W_MAX) / 2;
int16_t paddleW = PADDLE_W_MAX;

Ball ball;
Brick bricks[BRICK_COUNT];
uint8_t bricksLeft = 0;

uint32_t lastFrameAt = 0;
uint32_t stateEnteredAt = 0;
bool titleBlink = true;
uint8_t titleAnim = 0;

// ---- Sounds ----
void beep(uint16_t freq, uint32_t ms) { M5.Speaker.tone(freq, ms); }

void sfxBounce() { beep(440, 18); }
void sfxBrick() { beep(660, 28); }
void sfxHard() { beep(520, 22); }
void sfxLaunch() { beep(880, 40); }
void sfxDie() { beep(110, 180); }
void sfxClear() {
  beep(523, 80);
  delay(40);
  beep(659, 80);
  delay(40);
  beep(784, 120);
}
void sfxOver() {
  beep(300, 120);
  delay(60);
  beep(200, 160);
  delay(60);
  beep(120, 220);
}

// ---- Helpers ----
uint16_t brickColor(uint8_t kind, uint8_t hits, uint8_t maxHits) {
  // dim when damaged
  bool dim = (hits < maxHits);
  switch (kind) {
    case 0:
      return dim ? TFT_MAROON : TFT_RED;
    case 1:
      return dim ? TFT_OLIVE : TFT_ORANGE;
    case 2:
      return dim ? TFT_DARKGREEN : TFT_YELLOW;
    case 3:
      return dim ? TFT_NAVY : TFT_GREEN;
    case 4:
      return dim ? TFT_PURPLE : TFT_CYAN;
    default:
      return dim ? TFT_DARKGREY : TFT_MAGENTA;
  }
}

int brickScore(uint8_t kind) {
  return 10 + kind * 10;
}

int paddleWidthForWave(uint8_t waveNum) {
  int w = PADDLE_W_MAX - (int)(waveNum - 1) * 3;
  if (w < PADDLE_W_MIN) w = PADDLE_W_MIN;
  return w;
}

float ballSpeedForWave(uint8_t waveNum) {
  float s = BALL_SPEED_BASE + (waveNum - 1) * 0.28f;
  if (s > BALL_SPEED_MAX) s = BALL_SPEED_MAX;
  return s;
}

void stickBallToPaddle() {
  ball.stuck = true;
  ball.x = paddleX + paddleW / 2.0f;
  ball.y = PADDLE_Y - BALL_R - 1;
  ball.vx = 0;
  ball.vy = 0;
}

void launchBall() {
  if (!ball.stuck) return;
  ball.stuck = false;
  float speed = ballSpeedForWave(wave);
  // Prefer mostly upward with sideways bias from paddle center
  float bias = ((ball.x - (paddleX + paddleW / 2.0f)) / (paddleW / 2.0f));
  if (bias < -1) bias = -1;
  if (bias > 1) bias = 1;
  ball.vx = speed * (0.55f * bias + 0.15f * (random(0, 2) ? 1 : -1));
  ball.vy = -speed;
  float mag = sqrtf(ball.vx * ball.vx + ball.vy * ball.vy);
  if (mag > 0.01f) {
    ball.vx = ball.vx / mag * speed;
    ball.vy = ball.vy / mag * speed;
  }
  sfxLaunch();
}

void initBricks(uint8_t waveNum) {
  bricksLeft = 0;
  int totalW = BRICK_COLS * BRICK_W + (BRICK_COLS - 1) * BRICK_GAP;
  int originX = (W - totalW) / 2;

  for (int r = 0; r < BRICK_ROWS; r++) {
    uint8_t kind = r;  // top rows worth more
    // harder bricks appear from wave 2+
    uint8_t maxHits = 1;
    if (waveNum >= 2 && r <= 1) maxHits = 2;
    if (waveNum >= 4 && r == 0) maxHits = 3;
    // some random hard bricks later
    for (int c = 0; c < BRICK_COLS; c++) {
      Brick &b = bricks[r * BRICK_COLS + c];
      b.x = originX + c * (BRICK_W + BRICK_GAP);
      b.y = BRICK_AREA_T + r * (BRICK_H + BRICK_GAP);
      b.kind = kind;
      b.maxHits = maxHits;
      // skip a few bricks on later waves for variety? keep full for classic feel
      // wave 3+: checkerboard holes on bottom row only
      bool skip = false;
      if (waveNum >= 3 && r == BRICK_ROWS - 1 && ((c + waveNum) & 1) == 0) {
        skip = true;
      }
      if (skip) {
        b.hits = 0;
      } else {
        b.hits = maxHits;
        bricksLeft++;
      }
    }
  }
}

void startWave(uint8_t waveNum) {
  wave = waveNum;
  paddleW = paddleWidthForWave(wave);
  paddleX = (W - paddleW) / 2;
  initBricks(wave);
  stickBallToPaddle();
}

void startGame() {
  score = 0;
  lives = 3;
  startWave(1);
  state = STATE_PLAY;
  stateEnteredAt = millis();
  beep(660, 60);
}

void loseLife() {
  lives--;
  sfxDie();
  if (lives == 0) {
    if (score > highScore) highScore = score;
    state = STATE_OVER;
    stateEnteredAt = millis();
    delay(50);
    sfxOver();
  } else {
    paddleX = (W - paddleW) / 2;
    stickBallToPaddle();
  }
}

void reflectFromPaddle() {
  // Hit position -1 .. 1 across paddle
  float hit = (ball.x - (paddleX + paddleW / 2.0f)) / (paddleW / 2.0f);
  if (hit < -1) hit = -1;
  if (hit > 1) hit = 1;

  float speed = sqrtf(ball.vx * ball.vx + ball.vy * ball.vy);
  float target = ballSpeedForWave(wave);
  // slight speed-up on paddle hits
  speed = min(BALL_SPEED_MAX, max(target, speed) + 0.05f);

  // angle from ~150deg to 30deg (upward)
  float angle = -PI / 2.0f + hit * (PI / 3.0f);  // -90deg +/- 60deg
  ball.vx = cosf(angle) * speed;
  ball.vy = sinf(angle) * speed;
  if (ball.vy > -0.8f) ball.vy = -0.8f;  // always go up
  // re-normalize
  float mag = sqrtf(ball.vx * ball.vx + ball.vy * ball.vy);
  ball.vx = ball.vx / mag * speed;
  ball.vy = ball.vy / mag * speed;

  ball.y = PADDLE_Y - BALL_R - 1;
  sfxBounce();
}

bool collideBrick(Brick &b) {
  if (b.hits == 0) return false;

  float left = b.x;
  float right = b.x + BRICK_W;
  float top = b.y;
  float bottom = b.y + BRICK_H;

  float nearestX = constrain(ball.x, left, right);
  float nearestY = constrain(ball.y, top, bottom);
  float dx = ball.x - nearestX;
  float dy = ball.y - nearestY;
  if (dx * dx + dy * dy > (float)BALL_R * BALL_R) return false;

  // Determine bounce axis by penetration
  float overlapL = (ball.x + BALL_R) - left;
  float overlapR = right - (ball.x - BALL_R);
  float overlapT = (ball.y + BALL_R) - top;
  float overlapB = bottom - (ball.y - BALL_R);

  float minOverlap = min(min(overlapL, overlapR), min(overlapT, overlapB));
  if (minOverlap == overlapL) {
    ball.vx = -fabsf(ball.vx);
    ball.x = left - BALL_R;
  } else if (minOverlap == overlapR) {
    ball.vx = fabsf(ball.vx);
    ball.x = right + BALL_R;
  } else if (minOverlap == overlapT) {
    ball.vy = -fabsf(ball.vy);
    ball.y = top - BALL_R;
  } else {
    ball.vy = fabsf(ball.vy);
    ball.y = bottom + BALL_R;
  }

  b.hits--;
  if (b.hits == 0) {
    bricksLeft--;
    score += brickScore(b.kind);
    sfxBrick();
  } else {
    sfxHard();
  }
  return true;
}

void updatePlay() {
  // input
  if (M5.BtnA.isPressed()) paddleX -= PADDLE_SPEED;
  if (M5.BtnC.isPressed()) paddleX += PADDLE_SPEED;
  if (paddleX < WALL) paddleX = WALL;
  if (paddleX > W - WALL - paddleW) paddleX = W - WALL - paddleW;

  if (ball.stuck) {
    stickBallToPaddle();
    if (M5.BtnB.wasPressed()) launchBall();
    return;
  }

  // move ball (substeps for tunneling safety)
  const int steps = 2;
  for (int s = 0; s < steps; s++) {
    ball.x += ball.vx / steps;
    ball.y += ball.vy / steps;

    // walls
    if (ball.x - BALL_R < WALL) {
      ball.x = WALL + BALL_R;
      ball.vx = fabsf(ball.vx);
      sfxBounce();
    } else if (ball.x + BALL_R > W - WALL) {
      ball.x = W - WALL - BALL_R;
      ball.vx = -fabsf(ball.vx);
      sfxBounce();
    }
    if (ball.y - BALL_R < PLAY_TOP) {
      ball.y = PLAY_TOP + BALL_R;
      ball.vy = fabsf(ball.vy);
      sfxBounce();
    }

    // paddle
    if (ball.vy > 0 && ball.y + BALL_R >= PADDLE_Y &&
        ball.y - BALL_R <= PADDLE_Y + PADDLE_H && ball.x + BALL_R >= paddleX &&
        ball.x - BALL_R <= paddleX + paddleW) {
      reflectFromPaddle();
    }

    // bricks (one hit per substep)
    for (int i = 0; i < BRICK_COUNT; i++) {
      if (collideBrick(bricks[i])) break;
    }
  }

  // fell off
  if (ball.y - BALL_R > PLAY_BOTTOM) {
    loseLife();
    return;
  }

  if (bricksLeft == 0) {
    state = STATE_CLEAR;
    stateEnteredAt = millis();
    sfxClear();
  }
}

// ---- Render ----
void drawHud() {
  fb.setTextDatum(TL_DATUM);
  fb.setTextColor(TFT_WHITE, TFT_BLACK);
  fb.setTextFont(1);
  fb.setTextSize(1);
  fb.setCursor(4, 4);
  fb.printf("SCORE %05lu", (unsigned long)score);
  fb.setCursor(120, 4);
  fb.printf("HI %05lu", (unsigned long)highScore);
  fb.setCursor(220, 4);
  fb.printf("WAVE %u", wave);

  // lives as small paddles
  for (int i = 0; i < lives; i++) {
    fb.fillRect(292 + i * 9, 5, 7, 3, TFT_YELLOW);
  }
  fb.drawFastHLine(0, HUD_H, W, TFT_DARKGREY);
}

void drawBricks() {
  for (int i = 0; i < BRICK_COUNT; i++) {
    Brick &b = bricks[i];
    if (b.hits == 0) continue;
    uint16_t col = brickColor(b.kind, b.hits, b.maxHits);
    fb.fillRect(b.x, b.y, BRICK_W, BRICK_H, col);
    // highlight edge
    fb.drawFastHLine(b.x, b.y, BRICK_W, TFT_WHITE);
    fb.drawFastVLine(b.x, b.y, BRICK_H, TFT_WHITE);
    if (b.maxHits > 1) {
      // mark multi-hit bricks
      fb.drawRect(b.x + 2, b.y + 2, BRICK_W - 4, BRICK_H - 4, TFT_BLACK);
    }
  }
}

void drawPaddle() {
  fb.fillRect(paddleX, PADDLE_Y, paddleW, PADDLE_H, TFT_YELLOW);
  fb.drawFastHLine(paddleX, PADDLE_Y, paddleW, TFT_WHITE);
  // grip marks
  int mid = paddleX + paddleW / 2;
  fb.drawFastVLine(mid, PADDLE_Y + 1, PADDLE_H - 2, TFT_ORANGE);
}

void drawBall() {
  fb.fillCircle((int)ball.x, (int)ball.y, BALL_R, TFT_WHITE);
  if (ball.stuck && titleBlink) {
    // launch hint sparkle
    fb.drawCircle((int)ball.x, (int)ball.y, BALL_R + 2, TFT_DARKGREY);
  }
}

void drawPlayfield() {
  fb.fillSprite(TFT_BLACK);
  drawHud();

  // side walls hint
  fb.drawFastVLine(0, PLAY_TOP, PLAY_BOTTOM - PLAY_TOP, TFT_DARKGREY);
  fb.drawFastVLine(W - 1, PLAY_TOP, PLAY_BOTTOM - PLAY_TOP, TFT_DARKGREY);

  drawBricks();
  drawPaddle();
  drawBall();

  if (ball.stuck) {
    fb.setTextDatum(MC_DATUM);
    fb.setTextColor(titleBlink ? TFT_YELLOW : TFT_DARKGREY, TFT_BLACK);
    fb.setTextSize(1);
    fb.drawString("PRESS B TO LAUNCH", W / 2, PADDLE_Y - 18);
  }

  fb.drawFastHLine(0, PLAY_BOTTOM, W, TFT_NAVY);
}

void drawTitle() {
  fb.fillSprite(TFT_BLACK);
  fb.setTextDatum(MC_DATUM);
  fb.setTextColor(TFT_CYAN, TFT_BLACK);
  fb.setTextSize(2);
  fb.drawString("BLOCK BUSTER", W / 2, 42);

  // decorative brick row
  int demoY = 78;
  uint16_t cols[] = {TFT_RED, TFT_ORANGE, TFT_YELLOW, TFT_GREEN, TFT_CYAN, TFT_MAGENTA};
  int bw = 26;
  int startX = (W - (6 * bw + 5 * 3)) / 2;
  for (int i = 0; i < 6; i++) {
    int x = startX + i * (bw + 3);
    int y = demoY + ((titleAnim + i) % 3);
    fb.fillRect(x, y, bw, 10, cols[i]);
    fb.drawFastHLine(x, y, bw, TFT_WHITE);
  }

  // mini paddle + ball
  fb.fillRect(W / 2 - 24, 120, 48, 6, TFT_YELLOW);
  fb.fillCircle(W / 2 + (int)(sinf(titleAnim * 0.4f) * 30), 108, 3, TFT_WHITE);

  fb.setTextSize(1);
  fb.setTextColor(TFT_WHITE, TFT_BLACK);
  fb.drawString("BREAK ALL THE BLOCKS", W / 2, 150);

  fb.setTextColor(TFT_YELLOW, TFT_BLACK);
  if (titleBlink) fb.drawString("PRESS B TO START", W / 2, 178);

  fb.setTextColor(TFT_DARKGREY, TFT_BLACK);
  fb.drawString("A:LEFT  B:LAUNCH  C:RIGHT", W / 2, 210);

  if (highScore > 0) {
    fb.setTextColor(TFT_WHITE, TFT_BLACK);
    char buf[32];
    snprintf(buf, sizeof(buf), "HI SCORE %05lu", (unsigned long)highScore);
    fb.drawString(buf, W / 2, 18);
  }
}

void drawClear() {
  drawPlayfield();
  fb.setTextDatum(MC_DATUM);
  fb.setTextColor(TFT_CYAN, TFT_BLACK);
  fb.setTextSize(2);
  fb.drawString("WAVE CLEAR!", W / 2, H / 2 - 10);
  fb.setTextSize(1);
  fb.setTextColor(TFT_WHITE, TFT_BLACK);
  fb.drawString("GET READY...", W / 2, H / 2 + 20);
}

void drawOver() {
  drawPlayfield();
  fb.setTextDatum(MC_DATUM);
  fb.setTextColor(TFT_RED, TFT_BLACK);
  fb.setTextSize(2);
  fb.drawString("GAME OVER", W / 2, H / 2 - 16);
  fb.setTextSize(1);
  fb.setTextColor(TFT_WHITE, TFT_BLACK);
  char buf[40];
  snprintf(buf, sizeof(buf), "SCORE %05lu", (unsigned long)score);
  fb.drawString(buf, W / 2, H / 2 + 14);
  if (millis() - stateEnteredAt > 1200 && titleBlink) {
    fb.setTextColor(TFT_YELLOW, TFT_BLACK);
    fb.drawString("PRESS B", W / 2, H / 2 + 36);
  }
}

void render() {
  switch (state) {
    case STATE_TITLE:
      drawTitle();
      break;
    case STATE_PLAY:
      drawPlayfield();
      break;
    case STATE_CLEAR:
      drawClear();
      break;
    case STATE_OVER:
      drawOver();
      break;
  }
  fb.pushSprite(0, 0);
}

void setup() {
  M5.begin(true, false, true);
  M5.Power.begin();
  M5.Lcd.setBrightness(80);
  M5.Lcd.fillScreen(TFT_BLACK);

  fb.setColorDepth(8);
  fb.createSprite(W, H);
  fb.fillSprite(TFT_BLACK);

  randomSeed(esp_random());
  state = STATE_TITLE;
  stateEnteredAt = millis();
  lastFrameAt = millis();
  stickBallToPaddle();
}

void loop() {
  M5.update();
  uint32_t now = millis();

  // ~30 FPS cap
  if (now - lastFrameAt < 33) {
    delay(1);
    return;
  }
  lastFrameAt = now;

  titleBlink = ((now / 400) % 2 == 0);
  if ((now / 120) != ((now - 33) / 120)) titleAnim++;

  switch (state) {
    case STATE_TITLE:
      if (M5.BtnB.wasPressed()) startGame();
      break;
    case STATE_PLAY:
      updatePlay();
      break;
    case STATE_CLEAR:
      if (now - stateEnteredAt > 1500) {
        startWave(wave + 1);
        state = STATE_PLAY;
        stateEnteredAt = now;
      }
      break;
    case STATE_OVER:
      if (now - stateEnteredAt > 800 && M5.BtnB.wasPressed()) {
        state = STATE_TITLE;
        stateEnteredAt = now;
      }
      break;
  }

  render();
}
