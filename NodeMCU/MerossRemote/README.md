# MerossRemote (DOIT.AM ESP8266 NodeMCU)

Breadboard remote: two tactile buttons → HTTP → Mac Meross bridge → ランプ / ファン (`mss110`).

MCU: **ESP8266 NodeMCU** (module text `ESP8266MOD` / `DOIT.AM`) — not ESP32 Amica. Bridge stays on the Mac (`meross/bridge`).

Flash with **PlatformIO only** (no Arduino IDE).

## Wiring (silkscreen)

Bottom-row silk (L→R, photo-confirmed):  
`3V3 GND TX RX D8 D7 D6 D5 GND 3V3 D4 D3 D2 D1 D0`

| Button | Function | Silkscreen | GPIO | Wiring |
|--------|----------|------------|------|--------|
| A | toggle **ランプ** | **D1** | 5 | **D1** ↔ switch ↔ **GND** |
| B | toggle **ファン** | **D2** | 4 | **D2** ↔ switch ↔ **GND** |

- Use `INPUT_PULLUP` — switch other side to **GND**, never 3V3.
- Do **not** use **D3 / D4 / D8** for buttons (boot / flash / onboard LED).
- Power the rail from NodeMCU **3V3** / **GND** (or **VIN** if needed).

## Night-friendly LEDs

Dark-by-default: no idle glow; press flash off unless opted in via `secrets.h`.

| LED | Notes |
|-----|--------|
| Blue onboard (usually **D4** / GPIO2, active-low) | Sketch forces OFF |
| Red power (if present) | Tape if it stays on |

## Flash (PlatformIO)

From the sketch directory:

```bash
cd NodeMCU/MerossRemote
cp secrets.h.example include/secrets.h   # edit Wi‑Fi + BRIDGE_HOST; never commit
pio run -t upload
pio device monitor -b 115200
# or: pio run -t upload -t monitor
```

From the repo root:

```bash
cp NodeMCU/MerossRemote/secrets.h.example NodeMCU/MerossRemote/include/secrets.h
# edit include/secrets.h
pio run -d NodeMCU/MerossRemote -t upload
pio device monitor -d NodeMCU/MerossRemote -b 115200
```

Board envs: `nodemcuv2` (default) or `esp12e` (`pio run -e esp12e -t upload`).

Optional instead of `include/secrets.h` (still no secrets in git):

```bash
export WIFI_SSID='...' WIFI_PASSWORD='...' BRIDGE_HOST='192.168.x.x'
pio run -d NodeMCU/MerossRemote -t upload
```

Bridge first: see `meross/README.md` (`python -m bridge`, port **8787**).  
Toggle endpoints return **HTTP 202** quickly (queued); sketch treats 202 as success so buttons stay responsive.
