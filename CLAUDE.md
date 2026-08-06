# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Wisp is an open-source, self-hosted ESP32 room climate monitor. It combines hardware, firmware, and infrastructure in one repo. No cloud — self-hosted only, integrating into a local Home Assistant instance with Apple HomeKit exposure.

It tracks CO2, VOC/air quality, temperature, humidity, and ambient light, and publishes readings over MQTT.

## Repo structure

- `/hardware` — KiCad project (schematic, PCB layout, Gerbers, BOM, CPL). Board is based on a certified ESP32-WROOM-32 module (no custom RF/antenna design), I2C sensors, USB-C-only power (no battery). Target fab/assembly is JLCPCB, so BOM/CPL parts must stay compatible with their catalog (LCSC).
- `/firmware` — ESP-IDF firmware in C++ (not Arduino, not ESPHome). Publishes sensor data over MQTT. OTA updates are a first-class requirement, not an afterthought — no USB reflashing after initial flash.
- `/infra` — Docker Compose setup: Mosquitto MQTT broker (auth + TLS, no anonymous access, topic-level ACLs) and Home Assistant, which bridges MQTT into HomeKit.
- `/docs` — design concept, sensor rationale, build/assembly notes.

These directories don't exist yet — the repo currently contains only the root `LICENSE`.

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
