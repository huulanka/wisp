# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Wisp is an open-source, self-hosted ESP32 room climate monitor. It combines hardware, firmware, and infrastructure in one repo. No cloud — self-hosted only, integrating into a local Home Assistant instance with Apple HomeKit exposure.

It tracks CO2, VOC/air quality, temperature, humidity, and ambient light, and publishes readings over MQTT.

## Repo structure

- `/hardware` — KiCad project (schematic, PCB layout, Gerbers, BOM, CPL). Board is based on a certified ESP32-WROOM-32 module (no custom RF/antenna design), I2C sensors, USB-C-only power (no battery). Target fab/assembly is JLCPCB, so BOM/CPL parts must stay compatible with their catalog (LCSC). Populated: schematic and PCB are routed, Gerbers and BOM/CPL are exported under `hardware/fab/`.
- `/firmware` — ESP-IDF firmware in C++ (not Arduino, not ESPHome). Publishes sensor data over MQTT. OTA updates are a first-class requirement, not an afterthought — no USB reflashing after initial flash. Not started yet.
- `/infra` — Docker Compose setup: Mosquitto MQTT broker (auth + TLS, no anonymous access, topic-level ACLs) and Home Assistant, which bridges MQTT into HomeKit. Not started yet.
- `/docs` — design concept, sensor rationale, build/assembly notes. Populated: `concept.md` and `hardware-expandability.md`.

### `/hardware` conventions

- KiCad files and project-local libraries are named `wisp.*` (`wisp.kicad_sch`, `wisp.kicad_pcb`, `wisp.pretty/`), registered under the library name `"wisp"` in `sym-lib-table`/`fp-lib-table`. New project-local symbols/footprints belong in this library, not scattered elsewhere.
- Run `kicad-cli` against the project in place (via the `kicad-check` skill), not a detached copy of `.kicad_pcb`/`.kicad_sch` elsewhere — `wisp.kicad_dru` is only picked up by path. It currently defines no rules, but keep the habit so a future exception is not silently ignored.
- The board is **4-layer**: `In1.Cu` (`GND`) and `In2.Cu` (`PWR`) are solid planes and must never be routed on. Every `+3V3`/`GND` pad is bonded to its plane by its own via. When re-exporting the Specctra DSN for Freerouting, re-patch the inner layers to `(type power)` — KiCad exports all four as `(type signal)`, and letting the router cut the planes reintroduces the pour-fragmentation problem the 4-layer stackup was adopted to remove.
- DRC is expected to be **completely clean** (0 violations, 0 unconnected). There is no accepted-findings baseline for the PCB any more — treat any DRC hit as a real regression. `hardware/README.md` still documents 3 accepted *ERC* warnings (two symbol-library version diffs, U5's SDO-to-GND address strap).

## Sensors (all I2C)

- SCD41 — CO2, temperature, humidity (addr 0x62)
- BME680 — VOC/air quality (addr 0x76/0x77)
- BH1750 — ambient light in lux (addr 0x23)

## MQTT topic structure

`home/climate/<room>/{co2,temperature,humidity,voc,lux}`

First room: living room.

## Licensing

Each subfolder gets its own LICENSE file matching its content type:

- `/hardware` → CERN-OHL-S v2
- `/firmware` → MIT
- `/docs` → CC-BY-4.0

## Conventions

- All commit messages, code, comments, and docs are in English — even if the conversation with Claude happens in another language.
