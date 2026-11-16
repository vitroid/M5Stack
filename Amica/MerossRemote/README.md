# MerossRemote (ESP32 DevKit Amica)

Breadboard remote: two momentary buttons → HTTP → Mac-side Meross bridge → ランプ / ファン (`mss110`).

MCU stays simple (AtomSwitch pattern): Wi‑Fi + `HTTPClient` GET only. Meross credentials stay on the Mac.

## Pin map

Sketch uses **GPIO 18 / 19**. Do **not** assume silkscreen `D18` / `D19` — the board in hand does not use those labels. Silk is often bare `18` / `19` (or other names); confirm from a photo when available.

| Button | Function | Pin | Wiring |
|--------|----------|-----|--------|
| A | toggle **ランプ** (`/toggle/lamp`) | **GPIO 18** | pin ↔ switch ↔ GND (`INPUT_PULLUP`) |
| B | toggle **ファン** (`/toggle/fan`) | **GPIO 19** | pin ↔ switch ↔ GND (`INPUT_PULLUP`) |

### Where to find them (provisional — photo TBD)

On a common **30-pin DOIT ESP32 DevKit V1** (USB toward you / bottom, component side up), the **right header** top→bottom is typically:

`23 → 22 → TX → RX → 21 → **19** → **18** → 5 → … → 3V3`

So **19** is about the **6th** pad from the top of the right header, **18** the **7th**. NodeMCU-32S (38-pin) and other clones differ — wait for a board photo before treating silk names as gospel.

Also connect Amica **3V3 / 5V / GND** to breadboard power rails as usual. No external pull-ups required.

## Night-friendly LEDs (dark-by-default)

Sketch policy: **no idle glow**. Optional press flash is disabled unless you set `FLASH_ON_PRESS` in `secrets.h`.

| LED | Can software turn it off? | What to do |
|-----|---------------------------|------------|
| Blue/status (often **GPIO 2**) | Yes | Sketch forces it OFF at boot / after each press |
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
