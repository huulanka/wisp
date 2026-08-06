# Hardware Expandability Notes

Working notes from the design-review round held before releasing the first
Wisp board for fabrication. Goal: keep the board open for future extensions
without hurting v1 cost or function. This is a living discussion doc, not a
frozen spec — see "Open questions" for items still needing a decision.

## Baseline (schematic as of this review)

- ESP32-WROOM-32 (certified module, no custom RF/antenna design)
- USB-C for power and programming only, no battery path
- CH340C USB-UART bridge with standard auto-reset circuit (DTR/RTS via a
  BJT onto EN/IO0)
- AP63203WU buck regulator, 5V -> 3.3V, 2.2uH inductor (datasheet-recommended
  value for the regulator's 3A rating)
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
| ESP32 WiFi TX burst | ~240 mA |
| SCD41 measurement peak (~1s) | ~205 mA |
| BME680 heater peak | ~20 mA |
| WS2812 at full white | ~60 mA |
| LD2410 mmWave | ~100 mA |
| INMP441 microphone | ~1.5 mA |
| Buzzer active | ~30 mA |
| **Total worst case** | **~650 mA** |

The AP63203WU is rated for 3000 mA — roughly 4.5x headroom over the
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
- **PTC resettable fuse on the VBUS input** — now that the board grows a
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

## GPIO pin plan

Read from the actual schematic netlist (`hardware/kicad/wisp.kicad_sch`,
component `U3`), not guessed, to avoid collisions.

**Already committed by the base design:**

| Pin | Function |
|---|---|
| IO1 / IO3 | UART0 TX/RX — CH340C programming interface |
| EN, IO0 | Reset / boot mode strapping |
| IO21, IO22 | SDA, SCL — onboard I2C bus (SCD41, BME680, BH1750) |
| IO2 | Status LED (becomes the WS2812 data line, see decisions above) |

**Never route anything here:** pads for `SCK/CLK`, `SCS/CMD`, `SDI/SD1`,
`SDO/SD0`, `SHD/SD2`, `SWP/SD3` (GPIO6-11) exist on the module footprint
but are internally wired to the WROOM-32's embedded SPI flash. Using them
for anything else will break the module.

**New DNP assignments:**

| Pin(s) | Feature | Notes |
|---|---|---|
| IO12, IO13, IO14, IO15 | JTAG testpads (MTDI/MTCK/MTMS/MTDO) | Pads only, no connector. These are also strapping pins — keep unloaded in normal operation. |
| IO16, IO17 | Second I2C bus (SDA2/SCL2) | Own pull-ups, isolated from the internal sensor bus. |
| IO4, IO5 | mmWave UART (TX/RX to LD2410) | Routed via a spare HW UART, no conflict with the CH340 programming UART. |
| IO25, IO26, IO27 | I2S microphone (SCK, WS, SD) | ADC2-capable pins, but unused as ADC here — no WiFi conflict since these are pure digital I2S signals. |
| IO19 | Switched DC output (MOSFET gate) | |
| IO18 | Piezo buzzer | |
| IO23 | Reed/Hall contact input | Uses the ESP32's internal pull-up, no external resistor needed. |
| IO32 | 1-Wire bus (e.g. DS18B20) | Needs an external pull-up (~4.7k) for proper open-drain operation with multiple devices. |
| VP / IO36 | ADC analog pad | True input-only ADC1 channel — ideal for an analog sensor pad, no WiFi/ADC2 conflict. |
| IO33, IO34, IO35, VN / IO39 | Generic expansion header (+ 3V3, GND) | All four are also ADC1-capable, so the expansion header doubles as extra analog inputs if needed later. |

Every currently-unused GPIO on the module is accounted for — nothing is
left both unassigned and unbroken-out, so there's no pin left over that
would need a later, undocumented decision.

## Next step

Pin plan is settled. Next: update the schematic — add the DNP footprints
above with their assigned nets, swap the status LED for a WS2812, add the
PTC fuse on VBUS and ESD protection on the off-board-facing signals
(second I2C, switched output, reed contact, 1-Wire, expansion header),
then re-run ERC via the `kicad-check` skill before layout.
