# Hardware Expandability Notes

Working notes from the design-review round held before releasing the first
Wisp board for fabrication. Goal: keep the board open for future extensions
without hurting v1 cost or function. This is a living discussion doc, not a
frozen spec — see "Open questions" for items still needing a decision.

## Baseline (schematic as of this review)

- ESP32-WROOM-32 (certified module, no custom RF/antenna design)
- USB-C for power and programming only, no battery path
- (Rev A) CH340C USB-UART bridge with an auto-reset circuit. Removed in Rev B:
  the ESP32-S3 has native USB, so the bridge, its decoupling and both
  auto-reset transistors are gone.
- AP63203WU buck regulator, 5V -> 3.3V, 2.2uH inductor. Note the part is the
  **2A** AP6320x, not 3A — an earlier revision of this document said 3A, which
  is the AP6330x. 2.2uH is inside the datasheet's recommended 2.2-10uH band,
  and 2A is still ~3x the worst-case load below.
- I2C sensor trio on one bus: SCD41 (CO2/temp/humidity, 0x62), BME680 (VOC,
  0x76/0x77), BH1750 (lux, 0x23)
- Single status LED, boot/reset buttons
- No PCB layout yet at time of this review — schematic only

Of the ~25 WROOM-32 GPIOs, only a handful are committed (I2C, status LED,
EN/IO0 for auto-reset). Most pins are free.

## Architecture decision: single board, not stackable

Considered a stackable shield-style concept (base board + pluggable
extension boards). **Rejected as overkill for this product**: the
expansion list below is a handful of one-off additions for a single-unit
DIY device, not a family of interchangeable third-party modules — the
usual case where a stacking interface earns its mechanical and connector
cost. Enclosure design also isn't final yet, which makes a multi-board
stack riskier, not safer.

**Decision: one board, generous DNP (do-not-populate) footprints and
header pads for future extensions.** The one exception is the optional
OLED, which gets a simple cable/JST connector rather than being soldered
on directly, since it needs front-panel placement that depends on the
final enclosure.

## Expansion items — decided

| Item | Verdict | Notes |
|---|---|---|
| I2S MEMS microphone (INMP441) | Include (DNP) | Placement should favor a spot near a future enclosure sound port — acoustic performance inside a closed case is poor otherwise. Revisit footprint placement once enclosure exists. |
| UART header for mmWave presence (LD2410) | Include (DNP) | No pin conflicts, ESP32 has multiple HW UARTs. |
| Second, independent I2C bus with own pull-ups | Include (DNP) | For external sensor add-ons; keeps the internal sensor bus isolated from external wiring noise/address clashes. |
| Switched output (fan/dehumidifier control) | Include (DNP), **DC only** | Low-voltage DC via N-channel MOSFET (e.g. switching a 5V/12V fan or an external supply). Mains/230V switching explicitly excluded — needs galvanic isolation, creepage distances, and safety certification out of scope for this board. |
| Piezo buzzer | Include (DNP) | Local alarm, low cost/complexity. |
| WS2812 RGB status LED | Include, **replaces** the single-color LED | Marginal cost over a plain LED; keeping both footprints wasn't worth the area. |
| Reed/Hall sensor pads (window contact) | Include (DNP) | One GPIO with internal pull-up, no external components needed. |
| Supercap/goldcap OTA brownout buffer | **Dropped** | ESP-IDF's dual-partition OTA already keeps the previous firmware bootable if a write is interrupted; the supercap would be the single largest DNP footprint on the board for a risk that's largely already covered in firmware. |
| OLED connector (SSD1306, I2C, 0x3C) | Include, cable/JST connector, not soldered | No address conflict with existing sensors. Deferred to enclosure finalization. |
| Generic expansion header (3V3/GND + 4-6 spare GPIO) | Include | Best cost-to-future-proofing ratio of the whole list — covers ideas nobody's had yet. |
| I2C multiplexer (TCA9548A) for multi-room-on-one-board | **Dropped** | Wisp is one board per room by design (MQTT topic per room); a mux only matters if that changes. |
| SPI pins reserved for future peripherals | **Dropped** | No concrete need identified (OLED candidate is I2C, microSD dropped). Falls back to the generic expansion header if a real need shows up later. |
| microSD slot for offline logging | **Dropped** | Doesn't fit the MQTT-first, self-hosted concept; the slot also costs real board edge space. |
| Test points on key nets (3V3, GND, SDA, SCL, EN, IO0, TX/RX) | Include | Free (copper only), helps factory test / recovery flashing without opening the case. |
| JTAG header/testpads | Include as testpads only | Developer convenience, not a user feature. Bundled with the general test point item above, near-zero extra cost. Note: JTAG uses GPIO12-15 — keep these free when assigning other DNP features. |
| ESD/overvoltage protection on all off-board signals | Include | Applies to reed contact, second I2C bus, switched output, expansion header — anything leaving the enclosure. Cheap TVS arrays. |

## Power budget check (AP63203WU)

Worst-case simultaneous draw across all DNP options, rough datasheet
estimates:

| Load | Peak current |
|---|---|
| ESP32-S3 WiFi TX burst | ~350 mA |
| SCD41 measurement peak (~1s) | ~205 mA |
| BME680 heater peak | ~20 mA |
| WS2812 at full white | ~60 mA |
| LD2410 mmWave | ~100 mA |
| INMP441 microphone | ~1.5 mA |
| Buzzer active | ~30 mA |
| **Total worst case** | **~760 mA** |

The AP63203WU is rated for 2000 mA — roughly 2.6x headroom over the
worst realistic case, so no regulator change is needed even with every
DNP option populated and active at once. 5V input current in that
scenario (~480 mA at ~90% efficiency) also stays within what a
default USB-C connection provides without power negotiation.

## New ideas from this round

Brainstormed while looking for anything still missing from the list
above:

- **1-Wire bus pad (e.g. DS18B20)** — one GPIO plus a pull-up resistor,
  essentially free. Popular for external/waterproof temperature probes
  (outdoor, water tank, etc.), complements the I2C-only sensor story
  without adding a real bus. **Recommendation: include as DNP.**
- **PTC resettable fuse on the externally-exposed 5V pins** (as built it sits
  on `+5V_EXT`, feeding J3/J5 and the status LED, not on the board's own VBUS
  input — a 500mA fuse in the main path would nuisance-trip at ~480mA input
  current). Originally written up as — now that the board grows a
  number of off-board connectors (switched output, reed contact, second
  I2C bus, expansion header), a fuse protects both the board and the
  upstream USB port from a wiring mistake on any of them. Cheap,
  pairs naturally with the ESD protection already planned.
  **Recommendation: include.**
- **ADC-capable analog pad**, in addition to the digital expansion
  header, for future analog sensors (soil moisture, analog gas sensors,
  etc.). Free if planned early — main constraint is that ESP32 ADC2
  pins are unusable while WiFi is active, so any analog pad must be
  wired to an ADC1-capable GPIO. **Recommendation: include, but note the
  ADC1-only constraint for the pin plan.**

## Dropped

- **PIR motion sensor footprint**: redundant next to the already-planned
  LD2410 mmWave header (PIR is motion-only, no presence-while-still
  detection, more false negatives). Not added.
- **RS485/Modbus transceiver footprint**: too much of a stretch for a
  home climate monitor without a concrete use case. Not added.

## GPIO pin plan (ESP32-S3-WROOM-1)

Rewritten for the S3. The WROOM-32 plan that used to live here is gone with
the part; nothing below is a rename of an old assignment, because the S3's
pin numbering, strapping pins and USB handling are all different.

Read from `hardware/scripts/wisp_netlist.py`, which is the actual source of
the netlist, not from a hand-kept copy that can drift.

**Committed by the base design:**

| Pin | Function |
|---|---|
| USB_D+ / USB_D- | native USB to J1, via the USBLC6 ESD array. No bridge chip. |
| TXD0 / RXD0 (IO43/IO44) | UART0, broken out to TP11/TP12 only |
| EN, IO0 | reset / boot strapping, with buttons SW1/SW2 |
| IO8, IO9 | SDA, SCL — onboard sensor bus (SCD41, SGP41, BME280, BH1750) |
| IO7 | WS2812B status LED data |

**DNP expansion assignments:**

| Pin(s) | Feature | Notes |
|---|---|---|
| IO4 | ADC analog pad | ADC1_CH3. ADC1 is IO1-IO10 on the S3; ADC2 is unusable while WiFi runs, same as before. |
| IO5 | 1-Wire bus | external 4.7k pull-up on the bus side of the series resistor |
| IO6 | Reed/Hall contact input | |
| IO15 | Piezo buzzer | |
| IO16 | Switched DC output (MOSFET gate) | |
| IO17, IO18 | Second I2C bus (SDA2/SCL2) | own pull-ups |
| IO10, IO11 | mmWave UART to LD2410 | IO10 is the ESP32's TX (module RX), IO11 its RX |
| IO12, IO13, IO14 | I2S microphone (SCK, WS, SD) | |
| IO1, IO2, IO21, IO38, IO47, IO48 | Generic expansion header J9 | IO1/IO2 are ADC1-capable; the S3 has no input-only pins, so unlike the WROOM-32 header every one of these is bidirectional |
| IO39, IO40, IO41, IO42 | JTAG test pads (MTCK/MTDO/MTDI/MTMS) | Pads only. Kept as a fallback for the case where USB itself is what needs debugging — the S3's built-in USB-Serial-JTAG covers the normal case. |

**Left unconnected on purpose:**

| Pin | Why |
|---|---|
| IO3 | strapping (JTAG source select) |
| IO45 | strapping (VDD_SPI voltage). Internal pull-down selects 3.3V flash. |
| IO46 | strapping (ROM message printing), internal pull-down |
| IO35, IO36, IO37 | used for octal PSRAM on `-R8` module variants. Left free so the board also accepts those parts. The BOM specifies `-N8` (8MB flash, no PSRAM). |

**The WROOM-32 flash-voltage trap is gone.** On the old part, MTDI/IO12 was the
strapping pin that selects flash voltage, so attaching a JTAG probe with a
pull-up on TDI at power-up booted the module into 1.8V flash mode. On the S3
that role belongs to IO45, which is not broken out, so the JTAG pads carry no
strapping function at all and need no pull-down.

**Never route anything to the flash pins.** GPIO26-32 are wired to the
module's internal SPI flash and are not brought out on the WROOM-1 footprint.

## Status

Rev A (ESP32-WROOM-32, BME680) was fabricated-ready but never ordered. Rev B
supersedes it: ESP32-S3 with native USB, SGP41 + BME280 in place of the
BME680, and a design review's worth of fixes (see `hardware/README.md`).

**Rev B is DRC clean**: 0 violations, 0 unconnected items, 0 schematic-parity
errors, on a 60 x 80mm 4-layer board with all 91 parts on the front. ERC has
one accepted warning (the BME280's address strap).

The schematic and PCB are now **generated from committed sources**
(`hardware/scripts/`). Rev A's were produced by throwaway scripts that were
never committed — the reason nobody could tell how that board had been built.

### What gets populated on the first prototype

Only the always-on "Include" items: the four sensors, the regulator, the
module, the USB front end incl. the USBLC6 ESD array, test points TP1-TP13,
the PTC fuse F1, the ESD diodes on all off-board-facing signals, their series
resistors, and both LEDs. Everything under "Include (DNP)" — buzzer, second
I2C header, mmWave UART, mic header, switched-output header with its MOSFET,
reed header, 1-Wire header, analog pad, expansion header — stays unpopulated.

`hardware/fab/wisp-bom-prototype.csv` (69 parts) and `wisp-cpl-prototype.csv`
(56 placements) reflect that; `wisp-bom-full.csv` (87 parts) includes the DNP
parts for later builds.

### Still open before ordering

1. **The BH1750 footprint is unverified.** Its pad geometry came from
   datasheet text, and ROHM's mechanical drawing could not be retrieved to
   check it. Print 1:1 and compare, or replace the footprint.
2. **No LCSC part numbers** except the USBLC6. Every part has an MPN,
   manufacturer and rating; LCSC numbers were not guessed, because a wrong one
   silently orders the wrong part.
3. **Narrowing the planes at the sensor-tab neck** would improve thermal
   isolation further. Deliberately not done blind during the Rev B rework.
