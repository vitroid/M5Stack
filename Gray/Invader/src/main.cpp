#include <M5Stack.h>

// ---- Screen ----
static const int W = 320;
static const int H = 240;

// ---- Layout ----
static const int HUD_H = 16;
static const int PLAY_TOP = HUD_H + 2;
static const int PLAY_BOTTOM = 210;

// ---- Player ----
static const int PLAYER_W = 16;
static const int PLAYER_H = 8;
static const int PLAYER_Y = 200;
static const int PLAYER_SPEED = 3;

// ---- Invaders ----
static const int INV_COLS = 8;
static const int INV_ROWS = 4;
static const int INV_W = 14;
static const int INV_H = 10;
static const int INV_GAP_X = 8;
static const int INV_GAP_Y = 6;
static const int INV_COUNT = INV_COLS * INV_ROWS;

// ---- Bullets ----
static const int PBULLET_H = 6;
static const int ABULLET_H = 6;
static const int MAX_ABULLETS = 4;

// ---- Bunkers ----
static const int BUNKER_COUNT = 4;
static const int BUNKER_W = 28;
static const int BUNKER_H = 16;
static const int BUNKER_Y = 168;

enum GameState { STATE_TITLE, STATE_PLAY, STATE_CLEAR, STATE_OVER };

struct Bullet {
  int16_t x, y;
  bool alive;
};

struct Invader {
  int16_t ox, oy;  // offset within formation
  uint8_t type;    // 0..2
  bool alive;
};

struct Bunker {
  int16_t x;
  uint8_t cells[BUNKER_H][BUNKER_W];  // 0 empty, 1 solid
};

TFT_eSprite fb = TFT_eSprite(&M5.Lcd);

GameState state = STATE_TITLE;
uint32_t score = 0;
uint32_t highScore = 0;
uint8_t lives = 3;
uint8_t wave = 1;

int16_t playerX = (W - PLAYER_W) / 2;
bool playerAlive = true;
uint32_t playerRespawnAt = 0;
uint32_t lastShotAt = 0;

Bullet pBullet = {0, 0, false};
Bullet aBullets[MAX_ABULLETS];

Invader invaders[INV_COUNT];
int16_t formX = 20;
int16_t formY = PLAY_TOP + 8;
int8_t formDir = 1;
uint32_t lastMoveAt = 0;
uint16_t moveInterval = 500;
uint8_t animFrame = 0;
uint8_t aliveCount = 0;

Bunker bunkers[BUNKER_COUNT];

uint32_t lastFrameAt = 0;
uint32_t stateEnteredAt = 0;
bool titleBlink = true;

// ---- Sounds ----
void beep(uint16_t freq, uint32_t ms) {
  M5.Speaker.tone(freq, ms);
}

void sfxShoot() { beep(880, 30); }
void sfxHit() { beep(220, 40); }
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

// ---- Drawing helpers ----
void drawPlayer(int x, int y, uint16_t color) {
  // classic cannon silhouette
  fb.fillRect(x + 6, y, 4, 2, color);
  fb.fillRect(x + 4, y + 2, 8, 2, color);
  fb.fillRect(x, y + 4, PLAYER_W, 4, color);
}

void drawInvader(int x, int y, uint8_t type, uint8_t frame, uint16_t color) {
  // Compact pixel art (14x10-ish) using filled rects
  if (type == 0) {
    // squid
    fb.fillRect(x + 4, y, 6, 2, color);
    fb.fillRect(x + 2, y + 2, 10, 2, color);
    fb.fillRect(x, y + 4, 14, 2, color);
    if (frame == 0) {
      fb.fillRect(x, y + 6, 2, 2, color);
      fb.fillRect(x + 4, y + 6, 2, 2, color);
      fb.fillRect(x + 8, y + 6, 2, 2, color);
      fb.fillRect(x + 12, y + 6, 2, 2, color);
      fb.fillRect(x + 2, y + 8, 2, 2, color);
      fb.fillRect(x + 10, y + 8, 2, 2, color);
    } else {
      fb.fillRect(x + 2, y + 6, 2, 2, color);
      fb.fillRect(x + 6, y + 6, 2, 2, color);
      fb.fillRect(x + 10, y + 6, 2, 2, color);
      fb.fillRect(x, y + 8, 2, 2, color);
      fb.fillRect(x + 12, y + 8, 2, 2, color);
    }
  } else if (type == 1) {
    // crab
    fb.fillRect(x + 2, y, 2, 2, color);
    fb.fillRect(x + 10, y, 2, 2, color);
    fb.fillRect(x + 4, y + 2, 6, 2, color);
    fb.fillRect(x, y + 4, 14, 2, color);
    fb.fillRect(x, y + 6, 4, 2, color);
    fb.fillRect(x + 6, y + 6, 2, 2, color);
    fb.fillRect(x + 10, y + 6, 4, 2, color);
    if (frame == 0) {
      fb.fillRect(x + 2, y + 8, 2, 2, color);
      fb.fillRect(x + 10, y + 8, 2, 2, color);
    } else {
      fb.fillRect(x, y + 8, 2, 2, color);
      fb.fillRect(x + 12, y + 8, 2, 2, color);
    }
  } else {
    // octopus
    fb.fillRect(x + 4, y, 6, 2, color);
    fb.fillRect(x + 2, y + 2, 10, 2, color);
    fb.fillRect(x, y + 4, 14, 4, color);
    if (frame == 0) {
      fb.fillRect(x + 2, y + 8, 2, 2, color);
      fb.fillRect(x + 6, y + 8, 2, 2, color);
      fb.fillRect(x + 10, y + 8, 2, 2, color);
    } else {
      fb.fillRect(x, y + 8, 2, 2, color);
      fb.fillRect(x + 4, y + 8, 2, 2, color);
      fb.fillRect(x + 8, y + 8, 2, 2, color);
      fb.fillRect(x + 12, y + 8, 2, 2, color);
    }
  }
}

uint16_t invaderColor(uint8_t type) {
  if (type == 0) return TFT_MAGENTA;
  if (type == 1) return TFT_CYAN;
  return TFT_GREENYELLOW;
}

int invaderScore(uint8_t type) {
  if (type == 0) return 30;
  if (type == 1) return 20;
  return 10;
}

// ---- Bunkers ----
void initBunker(Bunker &b, int16_t x) {
  b.x = x;
  for (int y = 0; y < BUNKER_H; y++) {
    for (int x2 = 0; x2 < BUNKER_W; x2++) {
      bool solid = true;
      // rounded top / arch cutout
      if (y < 3 && (x2 < 3 - y || x2 >= BUNKER_W - (3 - y))) solid = false;
      if (y >= 8 && x2 >= 8 && x2 < 20) {
        int cy = y - 8;
        int cx = abs(x2 - 14);
        if (cx * cx + cy * cy < 36) solid = false;
      }
      b.cells[y][x2] = solid ? 1 : 0;
    }
  }
}

void initBunkers() {
  int span = W - 40;
  for (int i = 0; i < BUNKER_COUNT; i++) {
    int x = 20 + (span * i) / (BUNKER_COUNT - 1) - BUNKER_W / 2;
    if (i == 0) x = 28;
    if (i == BUNKER_COUNT - 1) x = W - 28 - BUNKER_W;
    if (i == 1) x = 100;
    if (i == 2) x = 192;
    initBunker(bunkers[i], x);
  }
}

void drawBunkers() {
  for (int i = 0; i < BUNKER_COUNT; i++) {
    Bunker &b = bunkers[i];
    for (int y = 0; y < BUNKER_H; y++) {
      for (int x = 0; x < BUNKER_W; x++) {
        if (b.cells[y][x]) {
          fb.drawPixel(b.x + x, BUNKER_Y + y, TFT_GREEN);
        }
      }
    }
  }
}

bool damageBunkerAt(int px, int py, int radius) {
  bool hit = false;
  for (int i = 0; i < BUNKER_COUNT; i++) {
    Bunker &b = bunkers[i];
    int lx = px - b.x;
    int ly = py - BUNKER_Y;
    if (lx < -radius || lx >= BUNKER_W + radius || ly < -radius ||
        ly >= BUNKER_H + radius)
      continue;
    for (int dy = -radius; dy <= radius; dy++) {
      for (int dx = -radius; dx <= radius; dx++) {
        if (dx * dx + dy * dy > radius * radius) continue;
        int x = lx + dx;
        int y = ly + dy;
        if (x < 0 || x >= BUNKER_W || y < 0 || y >= BUNKER_H) continue;
        if (b.cells[y][x]) {
          b.cells[y][x] = 0;
          hit = true;
        }
      }
    }
  }
  return hit;
}

bool bunkerBlocks(int px, int py) {
  for (int i = 0; i < BUNKER_COUNT; i++) {
    Bunker &b = bunkers[i];
    int lx = px - b.x;
    int ly = py - BUNKER_Y;
    if (lx < 0 || lx >= BUNKER_W || ly < 0 || ly >= BUNKER_H) continue;
    if (b.cells[ly][lx]) return true;
  }
  return false;
}

// ---- Formation ----
void initInvaders(uint8_t waveNum) {
  formX = 20;
  formY = PLAY_TOP + 4 + min(40, (int)(waveNum - 1) * 6);
  formDir = 1;
  animFrame = 0;
  aliveCount = 0;
  moveInterval = max(90, 480 - (int)waveNum * 35);

  for (int r = 0; r < INV_ROWS; r++) {
    uint8_t type = (r == 0) ? 0 : (r == 1 ? 1 : 2);
    for (int c = 0; c < INV_COLS; c++) {
      Invader &inv = invaders[r * INV_COLS + c];
      inv.ox = c * (INV_W + INV_GAP_X);
      inv.oy = r * (INV_H + INV_GAP_Y);
      inv.type = type;
      inv.alive = true;
      aliveCount++;
    }
  }
}

void formationBounds(int16_t &minX, int16_t &maxX, int16_t &maxY) {
  minX = 32767;
  maxX = -32768;
  maxY = -32768;
  for (int i = 0; i < INV_COUNT; i++) {
    if (!invaders[i].alive) continue;
    int x = formX + invaders[i].ox;
    int y = formY + invaders[i].oy;
    if (x < minX) minX = x;
    if (x + INV_W > maxX) maxX = x + INV_W;
    if (y + INV_H > maxY) maxY = y + INV_H;
  }
  if (aliveCount == 0) {
    minX = formX;
    maxX = formX;
    maxY = formY;
  }
}

void resetBullets() {
  pBullet.alive = false;
  for (int i = 0; i < MAX_ABULLETS; i++) aBullets[i].alive = false;
}

void startWave(uint8_t waveNum) {
  wave = waveNum;
  initInvaders(wave);
  initBunkers();
  resetBullets();
  playerX = (W - PLAYER_W) / 2;
  playerAlive = true;
  playerRespawnAt = 0;
  lastMoveAt = millis();
}

void startGame() {
  score = 0;
  lives = 3;
  startWave(1);
  state = STATE_PLAY;
  stateEnteredAt = millis();
  beep(660, 60);
}

// ---- Gameplay ----
void firePlayer() {
  if (!playerAlive || pBullet.alive) return;
  if (millis() - lastShotAt < 220) return;
  pBullet.x = playerX + PLAYER_W / 2;
  pBullet.y = PLAYER_Y - 2;
  pBullet.alive = true;
  lastShotAt = millis();
  sfxShoot();
}

void maybeAlienShoot() {
  if (aliveCount == 0) return;
  int active = 0;
  for (int i = 0; i < MAX_ABULLETS; i++)
    if (aBullets[i].alive) active++;
  if (active >= min(2 + (int)wave / 2, MAX_ABULLETS)) return;
  if ((int)random(0, 100) > 2 + wave) return;

  // pick a random living column's bottom-most invader
  int col = random(0, INV_COLS);
  int shooter = -1;
  for (int r = INV_ROWS - 1; r >= 0; r--) {
    int idx = r * INV_COLS + col;
    if (invaders[idx].alive) {
      shooter = idx;
      break;
    }
  }
  if (shooter < 0) {
    // fallback: any alive
    for (int i = 0; i < INV_COUNT; i++) {
      if (invaders[i].alive) {
        shooter = i;
        break;
      }
    }
  }
  if (shooter < 0) return;

  for (int i = 0; i < MAX_ABULLETS; i++) {
    if (aBullets[i].alive) continue;
    aBullets[i].x = formX + invaders[shooter].ox + INV_W / 2;
    aBullets[i].y = formY + invaders[shooter].oy + INV_H;
    aBullets[i].alive = true;
    break;
  }
}

void killPlayer() {
  if (!playerAlive) return;
  playerAlive = false;
  lives--;
  pBullet.alive = false;
  sfxDie();
  if (lives == 0) {
    if (score > highScore) highScore = score;
    state = STATE_OVER;
    stateEnteredAt = millis();
    delay(50);
    sfxOver();
  } else {
    playerRespawnAt = millis() + 1000;
  }
}

bool hitTestInvader(int bx, int by) {
  for (int i = 0; i < INV_COUNT; i++) {
    if (!invaders[i].alive) continue;
    int x = formX + invaders[i].ox;
    int y = formY + invaders[i].oy;
    if (bx >= x && bx < x + INV_W && by >= y && by < y + INV_H) {
      invaders[i].alive = false;
      aliveCount--;
      score += invaderScore(invaders[i].type);
      sfxHit();
      // speed up as they thin out
      moveInterval = max(55, (int)moveInterval - 12);
      return true;
    }
  }
  return false;
}

void updatePlay() {
  uint32_t now = millis();

  if (!playerAlive && playerRespawnAt && now >= playerRespawnAt) {
    playerAlive = true;
    playerX = (W - PLAYER_W) / 2;
    playerRespawnAt = 0;
    resetBullets();
  }

  // input
  if (playerAlive) {
    if (M5.BtnA.isPressed()) playerX -= PLAYER_SPEED;
    if (M5.BtnC.isPressed()) playerX += PLAYER_SPEED;
    if (playerX < 4) playerX = 4;
    if (playerX > W - PLAYER_W - 4) playerX = W - PLAYER_W - 4;
    if (M5.BtnB.wasPressed()) firePlayer();
  }

  // player bullet
  if (pBullet.alive) {
    pBullet.y -= 6;
    if (pBullet.y < PLAY_TOP) {
      pBullet.alive = false;
    } else if (bunkerBlocks(pBullet.x, pBullet.y)) {
      damageBunkerAt(pBullet.x, pBullet.y, 2);
      pBullet.alive = false;
    } else if (hitTestInvader(pBullet.x, pBullet.y)) {
      pBullet.alive = false;
    }
  }

  // alien move
  if (aliveCount > 0 && now - lastMoveAt >= moveInterval) {
    lastMoveAt = now;
    animFrame ^= 1;
    int16_t minX, maxX, maxY;
    formationBounds(minX, maxX, maxY);
    bool stepDown = false;
    if (formDir > 0 && maxX + 4 >= W - 4) stepDown = true;
    if (formDir < 0 && minX - 4 <= 4) stepDown = true;
    if (stepDown) {
      formDir = -formDir;
      formY += 8;
      beep(150 + aliveCount * 3, 20);
    } else {
      formX += formDir * 4;
      beep(80 + (animFrame ? 40 : 0), 12);
    }
    formationBounds(minX, maxX, maxY);
    if (maxY >= PLAYER_Y - 2) {
      // invasion
      lives = 0;
      if (score > highScore) highScore = score;
      state = STATE_OVER;
      stateEnteredAt = now;
      sfxOver();
      return;
    }
  }

  maybeAlienShoot();

  // alien bullets
  for (int i = 0; i < MAX_ABULLETS; i++) {
    if (!aBullets[i].alive) continue;
    aBullets[i].y += 3 + min(3, (int)wave);
    if (aBullets[i].y > PLAY_BOTTOM + 10) {
      aBullets[i].alive = false;
      continue;
    }
    if (bunkerBlocks(aBullets[i].x, aBullets[i].y)) {
      damageBunkerAt(aBullets[i].x, aBullets[i].y, 2);
      aBullets[i].alive = false;
      continue;
    }
    if (playerAlive && aBullets[i].x >= playerX &&
        aBullets[i].x < playerX + PLAYER_W && aBullets[i].y >= PLAYER_Y &&
        aBullets[i].y < PLAYER_Y + PLAYER_H) {
      aBullets[i].alive = false;
      killPlayer();
    }
  }

  // invader-player collision
  if (playerAlive) {
    for (int i = 0; i < INV_COUNT; i++) {
      if (!invaders[i].alive) continue;
      int x = formX + invaders[i].ox;
      int y = formY + invaders[i].oy;
      if (x < playerX + PLAYER_W && x + INV_W > playerX && y < PLAYER_Y + PLAYER_H &&
          y + INV_H > PLAYER_Y) {
        killPlayer();
        break;
      }
    }
  }

  if (aliveCount == 0) {
    state = STATE_CLEAR;
    stateEnteredAt = now;
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
  fb.setCursor(230, 4);
  fb.printf("WAVE %u", wave);
  for (int i = 0; i < lives; i++) {
    drawPlayer(280 + i * 12, 4, TFT_YELLOW);
  }
  fb.drawFastHLine(0, HUD_H, W, TFT_DARKGREY);
}

void drawPlayfield() {
  fb.fillSprite(TFT_BLACK);
  drawHud();

  for (int i = 0; i < INV_COUNT; i++) {
    if (!invaders[i].alive) continue;
    int x = formX + invaders[i].ox;
    int y = formY + invaders[i].oy;
    drawInvader(x, y, invaders[i].type, animFrame, invaderColor(invaders[i].type));
  }

  drawBunkers();

  if (playerAlive) {
    drawPlayer(playerX, PLAYER_Y, TFT_YELLOW);
  } else if (playerRespawnAt) {
    if (((millis() / 100) & 1) == 0) {
      drawPlayer(playerX, PLAYER_Y, TFT_DARKGREY);
    }
  }

  if (pBullet.alive) {
    fb.fillRect(pBullet.x - 1, pBullet.y, 2, PBULLET_H, TFT_WHITE);
  }
  for (int i = 0; i < MAX_ABULLETS; i++) {
    if (!aBullets[i].alive) continue;
    fb.fillRect(aBullets[i].x - 1, aBullets[i].y, 2, ABULLET_H, TFT_RED);
  }

  // ground
  fb.drawFastHLine(0, PLAY_BOTTOM, W, TFT_GREEN);
}

void drawTitle() {
  fb.fillSprite(TFT_BLACK);
  fb.setTextDatum(MC_DATUM);
  fb.setTextColor(TFT_GREEN, TFT_BLACK);
  fb.setTextSize(2);
  fb.drawString("SPACE INVADERS", W / 2, 48);

  // demo invaders
  drawInvader(70, 90, 0, titleBlink, TFT_MAGENTA);
  fb.setTextColor(TFT_WHITE, TFT_BLACK);
  fb.setTextSize(1);
  fb.setTextDatum(ML_DATUM);
  fb.drawString("= 30 PTS", 100, 94);
  drawInvader(70, 112, 1, titleBlink, TFT_CYAN);
  fb.drawString("= 20 PTS", 100, 116);
  drawInvader(70, 134, 2, titleBlink, TFT_GREENYELLOW);
  fb.drawString("= 10 PTS", 100, 138);

  fb.setTextDatum(MC_DATUM);
  fb.setTextColor(TFT_YELLOW, TFT_BLACK);
  if (titleBlink) fb.drawString("PRESS B TO START", W / 2, 175);

  fb.setTextColor(TFT_DARKGREY, TFT_BLACK);
  fb.drawString("A:LEFT  B:FIRE  C:RIGHT", W / 2, 210);

  if (highScore > 0) {
    fb.setTextColor(TFT_WHITE, TFT_BLACK);
    char buf[32];
    snprintf(buf, sizeof(buf), "HI SCORE %05lu", (unsigned long)highScore);
    fb.drawString(buf, W / 2, 20);
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

  if ((now / 400) % 2 == 0)
    titleBlink = true;
  else
    titleBlink = false;

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
