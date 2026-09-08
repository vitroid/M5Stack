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
static const int PADDLE_W_WIDE = 72;

// ---- Ball ----
static const int BALL_R = 3;
static const float BALL_SPEED_BASE = 2.6f;
static const float BALL_SPEED_MAX = 5.2f;
static const int MAX_BALLS = 3;

// ---- Drops (power-ups) ----
static const int MAX_DROPS = 4;
static const int DROP_W = 16;
static const int DROP_H = 10;
static const float DROP_SPEED = 1.5f;
static const int DROP_CHANCE = 28;  // percent on brick destroy

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

enum DropType : uint8_t {
  DROP_MULTI = 0,  // multiball
  DROP_WIDE = 1,   // wider paddle
  DROP_LIFE = 2    // extra life
};

struct Ball {
  float x, y;
  float vx, vy;
  bool alive;
  bool stuck;  // held on paddle before launch
};

struct Brick {
  int16_t x, y;
  uint8_t hits;  // remaining hits (0 = gone)
  uint8_t maxHits;
  uint8_t kind;  // 0..5 row/color style
};

struct Drop {
  float x, y;
  DropType type;
  bool alive;
};

TFT_eSprite fb = TFT_eSprite(&M5.Lcd);

GameState state = STATE_TITLE;
uint32_t score = 0;
uint32_t highScore = 0;
uint8_t lives = 3;
uint8_t wave = 1;

int16_t paddleX = (W - PADDLE_W_MAX) / 2;
int16_t paddleW = PADDLE_W_MAX;
int16_t paddleWBase = PADDLE_W_MAX;
bool wideActive = false;

Ball balls[MAX_BALLS];
Drop drops[MAX_DROPS];
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
void sfxPower() {
  beep(784, 40);
  delay(20);
  beep(1046, 60);
}
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

int brickScore(uint8_t kind) { return 10 + kind * 10; }

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

int countAliveBalls() {
  int n = 0;
  for (int i = 0; i < MAX_BALLS; i++)
    if (balls[i].alive) n++;
  return n;
}

int findStuckBall() {
  for (int i = 0; i < MAX_BALLS; i++)
    if (balls[i].alive && balls[i].stuck) return i;
  return -1;
}

int findFreeBallSlot() {
  for (int i = 0; i < MAX_BALLS; i++)
    if (!balls[i].alive) return i;
  return -1;
}

int findFlyingBall() {
  for (int i = 0; i < MAX_BALLS; i++)
    if (balls[i].alive && !balls[i].stuck) return i;
  return -1;
}

void clearDrops() {
  for (int i = 0; i < MAX_DROPS; i++) drops[i].alive = false;
}

void clearExtraBalls() {
  for (int i = 1; i < MAX_BALLS; i++) {
    balls[i].alive = false;
    balls[i].stuck = false;
  }
}

void applyPaddleWidth() {
  int target = wideActive ? max(paddleWBase + 20, PADDLE_W_WIDE) : paddleWBase;
  if (target > PADDLE_W_WIDE) target = PADDLE_W_WIDE;
  int mid = paddleX + paddleW / 2;
  paddleW = target;
  paddleX = mid - paddleW / 2;
  if (paddleX < WALL) paddleX = WALL;
  if (paddleX > W - WALL - paddleW) paddleX = W - WALL - paddleW;
}

void stickBallToPaddle() {
  clearExtraBalls();
  clearDrops();
  wideActive = false;
  applyPaddleWidth();
  balls[0].alive = true;
  balls[0].stuck = true;
  balls[0].x = paddleX + paddleW / 2.0f;
  balls[0].y = PADDLE_Y - BALL_R - 1;
  balls[0].vx = 0;
  balls[0].vy = 0;
}

void setBallVelocity(Ball &b, float vx, float vy, float speed) {
  float mag = sqrtf(vx * vx + vy * vy);
  if (mag < 0.01f) {
    b.vx = 0;
    b.vy = -speed;
    return;
  }
  b.vx = vx / mag * speed;
  b.vy = vy / mag * speed;
}

void launchBall() {
  int idx = findStuckBall();
  if (idx < 0) return;
  Ball &b = balls[idx];
  b.stuck = false;
  float speed = ballSpeedForWave(wave);
  float bias = ((b.x - (paddleX + paddleW / 2.0f)) / (paddleW / 2.0f));
  if (bias < -1) bias = -1;
  if (bias > 1) bias = 1;
  float vx = speed * (0.55f * bias + 0.15f * (random(0, 2) ? 1 : -1));
  float vy = -speed;
  setBallVelocity(b, vx, vy, speed);
  sfxLaunch();
}

void spawnDrop(float x, float y) {
  if (random(0, 100) >= DROP_CHANCE) return;
  int slot = -1;
  for (int i = 0; i < MAX_DROPS; i++) {
    if (!drops[i].alive) {
      slot = i;
      break;
    }
  }
  if (slot < 0) return;

  // Prefer multiball; keep others as occasional spice
  int roll = random(0, 100);
  DropType type;
  if (roll < 55)
    type = DROP_MULTI;
  else if (roll < 85)
    type = DROP_WIDE;
  else
    type = DROP_LIFE;

  drops[slot].alive = true;
  drops[slot].type = type;
  drops[slot].x = x - DROP_W / 2.0f;
  drops[slot].y = y;
}

void activateMultiball() {
  int src = findFlyingBall();
  if (src < 0) src = findStuckBall();
  if (src < 0) return;

  Ball &origin = balls[src];
  float speed = ballSpeedForWave(wave);
  if (!origin.stuck) {
    float cur = sqrtf(origin.vx * origin.vx + origin.vy * origin.vy);
    if (cur > 0.5f) speed = min(BALL_SPEED_MAX, cur);
  }

  // Ensure origin is flying
  if (origin.stuck) {
    origin.stuck = false;
    setBallVelocity(origin, 0.4f, -1.0f, speed);
  }

  // Spawn up to 2 extra balls with spread angles
  const float spreads[] = {-0.75f, 0.75f};
  for (int s = 0; s < 2; s++) {
    int slot = findFreeBallSlot();
    if (slot < 0) break;
    Ball &nb = balls[slot];
    nb.alive = true;
    nb.stuck = false;
    nb.x = origin.x;
    nb.y = origin.y;
    float vx = origin.vx + spreads[s] * speed;
    float vy = (origin.vy < 0) ? origin.vy : -fabsf(origin.vy);
    if (fabsf(vy) < 0.6f) vy = -speed * 0.85f;
    setBallVelocity(nb, vx, vy, speed);
  }
  score += 50;
}

void activateWide() {
  wideActive = true;
  applyPaddleWidth();
  score += 20;
}

void activateLife() {
  if (lives < 5) lives++;
  score += 30;
}

void collectDrop(Drop &d) {
  d.alive = false;
  switch (d.type) {
    case DROP_MULTI:
      activateMultiball();
      break;
    case DROP_WIDE:
      activateWide();
      break;
    case DROP_LIFE:
      activateLife();
      break;
  }
  sfxPower();
}

void initBricks(uint8_t waveNum) {
  bricksLeft = 0;
  int totalW = BRICK_COLS * BRICK_W + (BRICK_COLS - 1) * BRICK_GAP;
  int originX = (W - totalW) / 2;

  for (int r = 0; r < BRICK_ROWS; r++) {
    uint8_t kind = r;
    uint8_t maxHits = 1;
    if (waveNum >= 2 && r <= 1) maxHits = 2;
    if (waveNum >= 4 && r == 0) maxHits = 3;
    for (int c = 0; c < BRICK_COLS; c++) {
      Brick &b = bricks[r * BRICK_COLS + c];
      b.x = originX + c * (BRICK_W + BRICK_GAP);
      b.y = BRICK_AREA_T + r * (BRICK_H + BRICK_GAP);
      b.kind = kind;
      b.maxHits = maxHits;
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
  paddleWBase = paddleWidthForWave(wave);
  paddleW = paddleWBase;
  paddleX = (W - paddleW) / 2;
  wideActive = false;
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
    paddleX = (W - paddleWBase) / 2;
    stickBallToPaddle();
  }
}

void reflectFromPaddle(Ball &ball) {
  float hit = (ball.x - (paddleX + paddleW / 2.0f)) / (paddleW / 2.0f);
  if (hit < -1) hit = -1;
  if (hit > 1) hit = 1;

  float speed = sqrtf(ball.vx * ball.vx + ball.vy * ball.vy);
  float target = ballSpeedForWave(wave);
  speed = min(BALL_SPEED_MAX, max(target, speed) + 0.05f);

  float angle = -PI / 2.0f + hit * (PI / 3.0f);
  ball.vx = cosf(angle) * speed;
  ball.vy = sinf(angle) * speed;
  if (ball.vy > -0.8f) ball.vy = -0.8f;
  float mag = sqrtf(ball.vx * ball.vx + ball.vy * ball.vy);
  ball.vx = ball.vx / mag * speed;
  ball.vy = ball.vy / mag * speed;

  ball.y = PADDLE_Y - BALL_R - 1;
  sfxBounce();
}

bool collideBrick(Ball &ball, Brick &b) {
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
    spawnDrop(b.x + BRICK_W / 2.0f, b.y + BRICK_H);
  } else {
    sfxHard();
  }
  return true;
}

void updateDrops() {
  for (int i = 0; i < MAX_DROPS; i++) {
    Drop &d = drops[i];
    if (!d.alive) continue;
    d.y += DROP_SPEED;
    if (d.y > PLAY_BOTTOM) {
      d.alive = false;
      continue;
    }
    // paddle catch
    if (d.y + DROP_H >= PADDLE_Y && d.y <= PADDLE_Y + PADDLE_H &&
        d.x + DROP_W >= paddleX && d.x <= paddleX + paddleW) {
      collectDrop(d);
    }
  }
}

void updateOneBall(Ball &ball) {
  const int steps = 2;
  for (int s = 0; s < steps; s++) {
    ball.x += ball.vx / steps;
    ball.y += ball.vy / steps;

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

    if (ball.vy > 0 && ball.y + BALL_R >= PADDLE_Y &&
        ball.y - BALL_R <= PADDLE_Y + PADDLE_H && ball.x + BALL_R >= paddleX &&
        ball.x - BALL_R <= paddleX + paddleW) {
      reflectFromPaddle(ball);
    }

    for (int i = 0; i < BRICK_COUNT; i++) {
      if (collideBrick(ball, bricks[i])) break;
    }
  }

  if (ball.y - BALL_R > PLAY_BOTTOM) {
    ball.alive = false;
    ball.stuck = false;
  }
}

void updatePlay() {
  if (M5.BtnA.isPressed()) paddleX -= PADDLE_SPEED;
  if (M5.BtnC.isPressed()) paddleX += PADDLE_SPEED;
  if (paddleX < WALL) paddleX = WALL;
  if (paddleX > W - WALL - paddleW) paddleX = W - WALL - paddleW;

  int stuck = findStuckBall();
  if (stuck >= 0) {
    balls[stuck].x = paddleX + paddleW / 2.0f;
    balls[stuck].y = PADDLE_Y - BALL_R - 1;
    if (M5.BtnB.wasPressed()) launchBall();
    updateDrops();
    return;
  }

  for (int i = 0; i < MAX_BALLS; i++) {
    if (balls[i].alive && !balls[i].stuck) updateOneBall(balls[i]);
  }

  updateDrops();

  if (countAliveBalls() == 0) {
    loseLife();
    return;
  }

  if (bricksLeft == 0) {
    clearDrops();
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
    fb.drawFastHLine(b.x, b.y, BRICK_W, TFT_WHITE);
    fb.drawFastVLine(b.x, b.y, BRICK_H, TFT_WHITE);
    if (b.maxHits > 1) {
      fb.drawRect(b.x + 2, b.y + 2, BRICK_W - 4, BRICK_H - 4, TFT_BLACK);
    }
  }
}

void drawPaddle() {
  fb.fillRect(paddleX, PADDLE_Y, paddleW, PADDLE_H, TFT_YELLOW);
  fb.drawFastHLine(paddleX, PADDLE_Y, paddleW, TFT_WHITE);
  int mid = paddleX + paddleW / 2;
  fb.drawFastVLine(mid, PADDLE_Y + 1, PADDLE_H - 2, TFT_ORANGE);
}

void drawBalls() {
  for (int i = 0; i < MAX_BALLS; i++) {
    if (!balls[i].alive) continue;
    fb.fillCircle((int)balls[i].x, (int)balls[i].y, BALL_R, TFT_WHITE);
    if (balls[i].stuck && titleBlink) {
      fb.drawCircle((int)balls[i].x, (int)balls[i].y, BALL_R + 2, TFT_DARKGREY);
    }
  }
}

void drawDropIcon(const Drop &d) {
  int x = (int)d.x;
  int y = (int)d.y;
  uint16_t bg;
  const char *label;
  switch (d.type) {
    case DROP_MULTI:
      bg = TFT_MAGENTA;
      label = "M";
      break;
    case DROP_WIDE:
      bg = TFT_CYAN;
      label = "W";
      break;
    default:
      bg = TFT_GREEN;
      label = "L";
      break;
  }
  fb.fillRoundRect(x, y, DROP_W, DROP_H, 2, bg);
  fb.drawRoundRect(x, y, DROP_W, DROP_H, 2, TFT_WHITE);
  fb.setTextDatum(MC_DATUM);
  fb.setTextColor(TFT_BLACK, bg);
  fb.setTextSize(1);
  fb.drawString(label, x + DROP_W / 2, y + DROP_H / 2);
}

void drawDrops() {
  for (int i = 0; i < MAX_DROPS; i++) {
    if (drops[i].alive) drawDropIcon(drops[i]);
  }
}

void drawPlayfield() {
  fb.fillSprite(TFT_BLACK);
  drawHud();

  fb.drawFastVLine(0, PLAY_TOP, PLAY_BOTTOM - PLAY_TOP, TFT_DARKGREY);
  fb.drawFastVLine(W - 1, PLAY_TOP, PLAY_BOTTOM - PLAY_TOP, TFT_DARKGREY);

  drawBricks();
  drawDrops();
  drawPaddle();
  drawBalls();

  if (findStuckBall() >= 0) {
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
  fb.drawString("BLOCK BUSTER", W / 2, 36);

  int demoY = 68;
  uint16_t cols[] = {TFT_RED, TFT_ORANGE, TFT_YELLOW, TFT_GREEN, TFT_CYAN, TFT_MAGENTA};
  int bw = 26;
  int startX = (W - (6 * bw + 5 * 3)) / 2;
  for (int i = 0; i < 6; i++) {
    int x = startX + i * (bw + 3);
    int y = demoY + ((titleAnim + i) % 3);
    fb.fillRect(x, y, bw, 10, cols[i]);
    fb.drawFastHLine(x, y, bw, TFT_WHITE);
  }

  fb.fillRect(W / 2 - 24, 108, 48, 6, TFT_YELLOW);
  fb.fillCircle(W / 2 - 10 + (int)(sinf(titleAnim * 0.4f) * 20), 96, 3, TFT_WHITE);
  fb.fillCircle(W / 2 + 12, 92, 3, TFT_WHITE);

  // falling power demo
  int dx = W / 2 - 8;
  int dy = 118 + (titleAnim % 8);
  fb.fillRoundRect(dx, dy, 16, 10, 2, TFT_MAGENTA);
  fb.setTextDatum(MC_DATUM);
  fb.setTextColor(TFT_BLACK, TFT_MAGENTA);
  fb.setTextSize(1);
  fb.drawString("M", dx + 8, dy + 5);

  fb.setTextColor(TFT_WHITE, TFT_BLACK);
  fb.drawString("CATCH M FOR MULTIBALL", W / 2, 148);
  fb.setTextColor(TFT_DARKGREY, TFT_BLACK);
  fb.drawString("W:WIDE  L:LIFE", W / 2, 162);

  fb.setTextColor(TFT_YELLOW, TFT_BLACK);
  if (titleBlink) fb.drawString("PRESS B TO START", W / 2, 184);

  fb.setTextColor(TFT_DARKGREY, TFT_BLACK);
  fb.drawString("A:LEFT  B:LAUNCH  C:RIGHT", W / 2, 214);

  if (highScore > 0) {
    fb.setTextColor(TFT_WHITE, TFT_BLACK);
    char buf[32];
    snprintf(buf, sizeof(buf), "HI SCORE %05lu", (unsigned long)highScore);
    fb.drawString(buf, W / 2, 14);
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

  for (int i = 0; i < MAX_BALLS; i++) balls[i].alive = false;
  clearDrops();

  randomSeed(esp_random());
  state = STATE_TITLE;
  stateEnteredAt = millis();
  lastFrameAt = millis();
  stickBallToPaddle();
}

void loop() {
  M5.update();
  uint32_t now = millis();

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
