# Wisp

Wisp is an open-source, self-hosted ESP32 room climate monitor. No cloud —
it publishes readings over MQTT into your own Home Assistant instance, which
exposes them to Apple HomeKit.

It tracks:

- **CO2** — SCD41
- **VOC / NOx (air quality)** — SGP41
- **Temperature & humidity** — SCD41, cross-checked against BME280
- **Barometric pressure** — BME280 (also compensates the SCD41's CO2 reading)
- **Ambient light** — BH1750

All hardware, firmware, and infrastructure needed to build and run one live
in this single repo.

## Repo structure

| Path | What's there | Status |
|---|---|---|
| [`/hardware`](hardware/) | KiCad project for the PCB — schematic, layout, Gerbers, BOM/CPL. ESP32-S3-WROOM-1 module, I2C sensors, USB-C only, 4-layer board. | Schematic and PCB routed, DRC clean, fab outputs exported. |
| `/firmware` | ESP-IDF firmware in Rust (`esp-idf-svc`), publishing sensor data over MQTT with OTA updates. | Not started. Design: [`docs/firmware-architecture.md`](docs/firmware-architecture.md). |
| `/infra` | Docker Compose: Mosquitto (MQTT, TLS, ACLs), a self-hosted OTA server, and Home Assistant bridging MQTT into HomeKit. | Not started. Design: [`docs/infra-architecture.md`](docs/infra-architecture.md). |
| [`/docs`](docs/) | Design concept, sensor rationale, expandability notes. | [`concept.md`](docs/concept.md), [`hardware-expandability.md`](docs/hardware-expandability.md). |

## Why these sensors

The SGP41 replaces the more common BME680: the BME680's gas reading only
becomes useful through Bosch's closed-source BSEC library, which doesn't sit
well with an MIT-licensed firmware. Sensirion's Gas Index Algorithm
(BSD-3-Clause) does the same job openly. Dropping the BME680 would also drop
barometric pressure, so the BME280 sits alongside the SGP41 for that —
and because the SCD41 needs ambient pressure to compensate its own CO2
reading, that pressure reading isn't a bonus, it feeds the primary
measurement.

Temperature and humidity are read from the SCD41; the BME280's readings are
kept as an independent cross-check rather than the source of truth, so
firmware can notice a failing sensor.

Full rationale: [`docs/concept.md`](docs/concept.md).

## MQTT topic structure

```
home/climate/<room>/{co2,temperature,humidity,voc,nox,pressure,lux}
```

First room: living room.

## Licensing

Each subfolder is licensed separately, matching its content type:

- [`/hardware`](hardware/LICENSE) → CERN-OHL-S v2
- `/firmware` → MIT
- `/docs` → CC-BY-4.0
