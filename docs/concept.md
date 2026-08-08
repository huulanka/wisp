# Wisp — Design Concept

Wisp is an open-source, self-hosted ESP32 room climate monitor. It tracks CO2,
VOC/air quality, temperature, humidity, and ambient light, and publishes
readings over MQTT into a local Home Assistant instance, which exposes them
to Apple HomeKit. No cloud dependency — self-hosted only.

First deployment target: living room (`wohnzimmer`).

## Hardware

- MCU: ESP32-S3-WROOM-1-N8 module (certified module, no custom RF/antenna
  matching required). Chosen over the original ESP32-WROOM-32 for its **native
  USB**: the USB-C data pair goes straight to the module, so the CH340C bridge,
  its decoupling and the two-transistor auto-reset circuit all disappear —
  nine parts and, with them, the whole class of auto-reset polarity bugs. It
  also brings USB-Serial-JTAG, so debugging needs no extra connector and no
  strapping-pin trickery.
- Sensors, all I2C, SMD, soldered directly to the main board (no plug-in
  breakout modules):
  - SCD41 — CO2, temperature, humidity (addr `0x62`)
  - SGP41 — VOC index and NOx index (addr `0x59`)
  - BME280 — barometric pressure + a second T/RH reading (addr `0x76`)
  - BH1750 — ambient light in lux (addr `0x23`)

  The SGP41 replaces the BME680. The BME680's gas signal is a bare resistance
  that only becomes an air-quality number through Bosch's BSEC library — a
  closed-source binary blob whose licence sits badly with an MIT-licensed
  firmware and with "full control over the code". Sensirion ships its Gas
  Index Algorithm as BSD-3-Clause C, and the SGP41 adds a NOx channel on top
  of VOC. Dropping the BME680 would have lost barometric pressure, so the
  BME280 comes in beside it — not as a nicety, but because the SCD41 wants
  ambient pressure to compensate its CO2 reading.

  Deliberately **not** included: particulate matter (PM2.5). It is the biggest
  remaining gap in "air quality", but every credible sensor needs a fan, is
  physically large, audible, and costs more than the rest of the sensor set
  together. Recorded here so the omission reads as a decision rather than an
  oversight.
  - Fixed 4.7kΩ I2C pull-ups on SDA/SCL (all sensors are onboard, no
    external I2C header planned that could bring its own pull-ups).
- Power: USB-C only, 5V → 3.3V buck switching regulator (not an LDO) to
  handle ESP32 WiFi TX current peaks (~500 mA) efficiently and stay cool.
  No battery buffer — mains-powered only.
- USB: native, straight into the module. No UART bridge, no auto-reset
  transistors, no driver to install on the host. UART0 is still broken out to
  two test pads as a fallback console that survives a USB reset. After the
  initial flash, all further updates go over OTA.
- RESET and BOOT tactile buttons (EN, GPIO0) as a manual fallback to the
  auto-reset circuit.
- Status LED: WS2812B addressable RGB on one GPIO. Fed from the fused 5V rail
  through a series diode (~4.3V) rather than from 3.3V: the part is specified
  from 3.5V, and the diode drop also pulls its logic threshold below the
  ESP32's 3.3V output. Keeps the LED's 60mA peaks off the 3.3V rail as well.
  A separate plain green LED indicates that 3.3V is present even when no
  firmware is running.
- Enclosure: no fixed mounting holes for a specific case yet — a compact,
  sensible board outline is chosen now, and mounting is finalized once the
  board exists.
- Target form factor: compact rectangular PCB. Actual: 60×80mm, 4 layers,
  with the sensors on a tab milled free on three sides so they read room
  temperature rather than board temperature.
- Fabrication: JLCPCB (PCBA), so BOM and CPL must stay compatible with the
  JLCPCB/LCSC parts catalog for direct upload.
- Assembly: SMT hand-soldered by the author (electronics technician by
  trade); JLCPCB used for bare boards / fab, not necessarily assembly.

## Firmware

- Framework: ESP-IDF, C++ — not Arduino, not ESPHome. Full control over
  the code and its extensibility.
- OTA updates are a first-class requirement from the start — no USB
  reflashing needed after the initial flash.
- Publishes sensor readings over MQTT.

## MQTT topic structure

```
home/climate/<room>/{co2,temperature,humidity,voc,nox,pressure,lux}
```

First room: `wohnzimmer` (living room).

## Infrastructure

- Mosquitto MQTT broker, running as a Docker container on the user's NAS.
  - Authentication (username/password), TLS, no anonymous access.
  - Per-topic ACLs so devices can only read/write the topics they need.
- Home Assistant, running as a Docker container on the same NAS.
  - Bridges MQTT topics into entities and exposes them to Apple HomeKit.
- Optional, later: InfluxDB + Grafana for long-term history/trends.

## Security

- MQTT: auth + TLS required, anonymous access disabled.
- Topic-level ACLs to limit blast radius of a compromised or misbehaving
  device.

## Licensing

Each subfolder carries its own license matching its content type:

- `/hardware` → CERN-OHL-S v2
- `/firmware` → MIT
- `/docs` → CC-BY-4.0

## Status

This document captures the initial concept. Hardware schematic, firmware,
and infrastructure implementation follow in their respective subfolders.
