# MerossRemote (ESP32 DevKit Amica)

Breadboard remote: two momentary buttons → HTTP → Mac-side Meross bridge → ランプ / ファン (`mss110`).

MCU stays simple (AtomSwitch pattern): Wi‑Fi + `HTTPClient` GET only. Meross credentials stay on the Mac.

## Pin map

Use Amica / DevKit **silkscreen D labels** when wiring (GPIO in parentheses).

| Button | Function | Silkscreen | Wiring |
|--------|----------|------------|--------|
| A | toggle **ランプ** (`/toggle/lamp`) | **D18** (GPIO 18) | D18 ↔ switch ↔ GND (`INPUT_PULLUP`) |
| B | toggle **ファン** (`/toggle/fan`) | **D19** (GPIO 19) | D19 ↔ switch ↔ GND (`INPUT_PULLUP`) |

Also connect Amica **3V3 / 5V / GND** to breadboard power rails as usual. No external pull-ups required.

## Night-friendly LEDs (dark-by-default)

Sketch policy: **no idle glow**. Optional press flash is disabled unless you set `FLASH_ON_PRESS` in `secrets.h`.

| LED | Can software turn it off? | What to do |
|-----|---------------------------|------------|
| Blue/status (often **GPIO2**) | Yes | Sketch forces it OFF at boot / after each press |
| Red **power** LED | No (hard-wired to 3V3/5V) | Cover with black tape, or desolder / cut the series resistor next to the LED |
| External feedback LED | Yes | Leave `FLASH_ON_PRESS` unset (default). To enable a brief flash: `#define FEEDBACK_LED_PIN 25` + `#define FLASH_ON_PRESS 1` |

Prefer tape first (reversible). Resistor cut is permanent — only if you want a truly dark bedside unit.

## Flash

1. Install Arduino IDE (or PlatformIO) with **esp32** board support (Espressif).
2. Board: **ESP32 Dev Module** (DevKit Amica / NodeMCU-32S family).
3. `cp secrets.h.example secrets.h` and set Wi‑Fi + bridge host/IP.
4. Open `MerossRemote.ino`, upload via USB.
5. Serial Monitor 115200: confirm Wi‑Fi IP and `/health` response. Board should stay dark aside from any untaped power LED.

Bridge must be running on the LAN first (`meross/bridge` — see `meross/README.md`).
