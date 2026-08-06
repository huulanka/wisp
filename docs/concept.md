# Wisp — Design Concept

Wisp is an open-source, self-hosted ESP32 room climate monitor. It tracks CO2,
VOC/air quality, temperature, humidity, and ambient light, and publishes
readings over MQTT into a local Home Assistant instance, which exposes them
to Apple HomeKit. No cloud dependency — self-hosted only.

First deployment target: living room (`wohnzimmer`).

## Hardware

- MCU: ESP32-WROOM-32 module (certified module, no custom RF/antenna
  matching required).
- Sensors, all I2C, SMD, soldered directly to the main board (no plug-in
  breakout modules):
  - SCD41 — CO2, temperature, humidity (addr `0x62`)
  - BME680 — VOC / air quality (addr `0x76`/`0x77`)
  - BH1750 — ambient light in lux (addr `0x23`)
  - Fixed 4.7kΩ I2C pull-ups on SDA/SCL (all sensors are onboard, no
    external I2C header planned that could bring its own pull-ups).
- Power: USB-C only, 5V → 3.3V buck switching regulator (not an LDO) to
  handle ESP32 WiFi TX current peaks (~500 mA) efficiently and stay cool.
  No battery buffer — mains-powered only.
- USB-UART: onboard CH340C for flashing over USB-C, with auto-reset
  circuit (EN/GPIO0 via DTR/RTS). After initial flash, all further updates
  go over OTA.
- RESET and BOOT tactile buttons (EN, GPIO0) as a manual fallback to the
  auto-reset circuit.
- Status LED: single-color, GPIO-driven through a series resistor.
- Enclosure: no fixed mounting holes for a specific case yet — a compact,
  sensible board outline is chosen now, and mounting is finalized once the
  board exists.
- Target form factor: compact rectangular PCB, roughly 50×70mm.
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
home/climate/<room>/{co2,temperature,humidity,voc,lux}
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
