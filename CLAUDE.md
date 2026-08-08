# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Wisp is an open-source, self-hosted ESP32 room climate monitor. It combines hardware, firmware, and infrastructure in one repo. No cloud — self-hosted only, integrating into a local Home Assistant instance with Apple HomeKit exposure.

It tracks CO2, VOC/air quality, temperature, humidity, and ambient light, and publishes readings over MQTT.

## Repo structure

- `/hardware` — KiCad project (schematic, PCB layout, Gerbers, BOM, CPL). Board is based on a certified ESP32-S3-WROOM-1 module (no custom RF/antenna design), I2C sensors, USB-C-only power (no battery). The S3 has native USB, so there is no USB-UART bridge and no auto-reset transistor pair. Target fab/assembly is JLCPCB, so BOM/CPL parts must stay compatible with their catalog (LCSC). Populated: schematic and PCB are routed, Gerbers and BOM/CPL are exported under `hardware/fab/`.
- `/firmware` — ESP-IDF firmware in C++ (not Arduino, not ESPHome). Publishes sensor data over MQTT. OTA updates are a first-class requirement, not an afterthought — no USB reflashing after initial flash. Not started yet.
- `/infra` — Docker Compose setup: Mosquitto MQTT broker (auth + TLS, no anonymous access, topic-level ACLs) and Home Assistant, which bridges MQTT into HomeKit. Not started yet.
- `/docs` — design concept, sensor rationale, build/assembly notes. Populated: `concept.md` and `hardware-expandability.md`.

### `/hardware` conventions

- KiCad files and project-local libraries are named `wisp.*` (`wisp.kicad_sch`, `wisp.kicad_pcb`, `wisp.pretty/`), registered under the library name `"wisp"` in `sym-lib-table`/`fp-lib-table`. New project-local symbols/footprints belong in this library, not scattered elsewhere.
- Run `kicad-cli` against the project in place (via the `kicad-check` skill), not a detached copy of `.kicad_pcb`/`.kicad_sch` elsewhere — `wisp.kicad_dru` is only picked up by path. It currently defines no rules, but keep the habit so a future exception is not silently ignored.
- The board is **4-layer**: `In1.Cu` (`GND`) and `In2.Cu` (`PWR`) are solid planes and must never be routed on. Every surface-mount `+3V3`/`GND` pad is bonded to its plane by its own via. Plated through-hole pads are deliberately *not* bonded — they already span every layer and meet their plane on the way through, so an extra via only adds a second drill next to the first.
- **The schematic and the PCB are generated, not hand-drawn.** `hardware/scripts/wisp_netlist.py` is the design; `wisp_floorplan.py` is the placement; `gen_schematic.py` and `gen_pcb.py` build the KiCad files from them. Edit the data, re-run the generators. Hand edits to `wisp.kicad_sch` are overwritten. When re-exporting the Specctra DSN for Freerouting, re-patch the inner layers to `(type power)` — KiCad exports all four as `(type signal)`, and letting the router cut the planes reintroduces the pour-fragmentation problem the 4-layer stackup was adopted to remove.
- DRC is expected to be **completely clean** (0 violations, 0 unconnected). There is no accepted-findings baseline for the PCB any more — treat any DRC hit as a real regression. `hardware/README.md` still documents 3 accepted *ERC* warnings (two symbol-library version diffs, U5's SDO-to-GND address strap).

## Sensors (all I2C)

- SCD41 — CO2, temperature, humidity (addr 0x62)
- SGP41 — VOC and NOx index (addr 0x59)
- BME280 — barometric pressure, plus a second temperature/humidity reading (addr 0x76)
- BH1750 — ambient light in lux (addr 0x23)

The SGP41 replaced the BME680 because the BME680's gas reading is only usable
through Bosch's BSEC, a closed-source binary blob that conflicts with the MIT
licence on `/firmware`. Sensirion's Gas Index Algorithm is BSD-3-Clause. The
BME280 was added alongside it because dropping the BME680 would otherwise lose
barometric pressure — and the SCD41 needs ambient pressure to compensate its
CO2 reading, so pressure is not a bonus here, it feeds the primary measurement.

Two constraints that are easy to get wrong:

- **The bus runs at 100 kHz**, because that is the SCD41's maximum. The other
  three would do 400 kHz.
- **Temperature comes from the SCD41**, not the BME280. Use the BME280's
  temperature and humidity only as a plausibility cross-check against the
  SCD41 — two independent readings are what let firmware notice a failing
  sensor.
- The SGP41 wants relative humidity and temperature fed back to it for
  compensation; take those from the SCD41.

## MQTT topic structure

`home/climate/<room>/{co2,temperature,humidity,voc,nox,pressure,lux}`

First room: living room.

## Licensing

Each subfolder gets its own LICENSE file matching its content type:

- `/hardware` → CERN-OHL-S v2
- `/firmware` → MIT
- `/docs` → CC-BY-4.0

## Conventions

- All commit messages, code, comments, and docs are in English — even if the conversation with Claude happens in another language.
