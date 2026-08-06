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

## Open questions

- **PIR motion sensor footprint vs. the already-planned LD2410 mmWave
  header**: a PIR is cheaper and simpler than mmWave but strictly worse
  (motion-only, no "presence while still" detection, more false
  negatives). Since mmWave is already planned, a PIR footprint would
  mostly be redundant unless there's a cost-sensitive variant in mind
  where mmWave might not be populated. Leaning toward **not** adding
  it, but flagging for a decision rather than dropping unilaterally.
- **RS485/Modbus transceiver footprint**: useful for integrating with
  classic building-automation/industrial sensors, but feels like a
  stretch for a home climate monitor unless there's a specific use
  case in mind. Leaning toward **not** adding it.

## Next step

With the DNP feature set settled (pending the two open questions above),
the next concrete step is a GPIO pin plan: assigning specific ESP32 pins
to each DNP feature so nothing collides (particularly watching JTAG pins
12-15 and ADC1-vs-ADC2 for the analog pad), before touching the
schematic.
