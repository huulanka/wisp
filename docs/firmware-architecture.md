# Firmware Architecture

Working design doc for `/firmware`, written before any code exists. Captures
the decisions made in a planning Q&A round so implementation has a concept to
follow instead of being designed ad hoc file by file.

## Language & toolchain

- **Rust**, via `esp-idf-svc` (std Rust running on top of ESP-IDF), not the
  `no_std`/bare-metal `esp-hal` path. Chosen over both C++ and bare-metal
  Rust: it keeps ESP-IDF's OTA (`esp_https_ota`), Secure Boot v2, and WiFi
  provisioning tooling usable largely as-is, while still getting memory
  safety on a network-facing, OTA-updated device — a deliberate tradeoff
  against the smaller Rust embedded ecosystem (see open questions).
- ESP32-S3 is Xtensa, not RISC-V, so the toolchain is Espressif's Rust fork,
  installed and managed via `espup` — not stock `rustup`. Worth calling out
  explicitly since it affects onboarding and CI image choice.
- Build via `cargo build`; `esp-idf-sys`'s build script drives the
  underlying ESP-IDF/`idf.py` build underneath. Flashing via `espflash` /
  `cargo espflash`.
- Secure Boot v2 key generation and image signing are ESP-IDF's own Python
  tooling (`espsecure.py`) — this is toolchain-level, not language-level, so
  it applies the same way it would have under C++.

## Provisioning & device identity

Each physical board runs the **same OTA image** — nothing room-specific gets
compiled in — so a fleet of boards can share one firmware build and one OTA
pipeline.

| Set at | What | How |
|---|---|---|
| Build time | Internal CA public certificate (for validating the MQTT broker and OTA server) | Baked into the firmware image; identical for every board, not a secret |
| Build time | Signing public key (Secure Boot v2) | Burned into eFuses during the *initial* USB flash — one-time, matches "no USB reflashing after initial flash" from `CLAUDE.md` |
| Runtime (first boot) | WiFi SSID/password, room slug (e.g. `wohnzimmer`), MQTT username/password, MQTT broker host | Captive-portal web form served from the board's own SoftAP |

SoftAP + a plain browser-based captive portal was chosen over BLE so
provisioning needs no companion phone app — consistent with the project's
no-cloud, self-hosted stance.

ESP-IDF's `wifi_provisioning` component (the usual C-side answer here) is
protobuf/event-loop-heavy and not a first-class `esp-idf-svc` API — treat
relying on it as a risk to verify early, not an assumption. The recommended
default is to **roll a minimal provisioning flow directly on `esp-idf-svc`'s
supported surface**: its own WiFi AP-mode API, `EspHttpServer` for the
captive-portal form, and NVS for storing the result. All three are
first-class, well-supported `esp-idf-svc` APIs, so this avoids depending on
FFI coverage of a C component that may be incomplete from Rust.

The device's internal unique ID (used for the MQTT client ID and HA's
`unique_id` fields) is derived from the ESP32's base MAC address, not the
room slug — so renaming a room later doesn't orphan HA entity history.

MQTT username/password are per-device, scoped by broker ACL to that device's
own room (see `infra-architecture.md`). Provisioning a new board is
therefore a two-sided step: generate the credentials/ACL on the broker side,
then run the board through SoftAP setup with those credentials.

## Sensor concurrency architecture

One `std::thread` per sensor (each maps to its own FreeRTOS task under
`esp-idf-svc`'s std environment), each with its own read/publish cadence
rather than a single shared polling loop — the four sensors have genuinely
different native measurement cycles:

| Sensor | Thread interval | Publishes | Notes |
|---|---|---|---|
| SCD41 | ~5 s (its own measurement cycle) | `co2`, `temperature`, `humidity` | Primary temperature/humidity source per `CLAUDE.md` |
| SGP41 | ~1 s (per Sensirion's Gas Index Algorithm requirement) | `voc`, `nox` | Needs live RH/T compensation from the SCD41 thread; ~10 s NOx conditioning phase after boot before readings are valid |
| BME280 | 30–60 s (pressure changes slowly) | `pressure` | Also feeds ambient-pressure compensation to the SCD41 thread; its temperature/humidity are read internally as a plausibility cross-check, not published as primary values |
| BH1750 | ~10 s | `lux` | |

All four share one physical I2C bus at 100 kHz (the SCD41's ceiling, see
`CLAUDE.md`). The bus handle (`esp_idf_hal::i2c::I2cDriver`) is wrapped in
`Arc<Mutex<_>>` so only one thread transacts on the bus at a time.
Cross-sensor values (SGP41's RH/T compensation, SCD41's pressure
compensation) are exchanged through small `Arc<Mutex<_>>`-protected shared
state, not by one thread reaching into another's driver instance.

**Plausibility cross-check:** if SCD41 and BME280 temperature/humidity
diverge beyond a threshold (proposed starting point: >2 °C or >10% RH, for
more than a few consecutive reads — to be tuned empirically once hardware
exists), the firmware does **not** stop publishing SCD41 data (it stays
primary), but flags the mismatch on the `diag` topic and via the status LED,
so a drifting/failing sensor is visible without pulling the board apart.

## MQTT topic structure

Extends the topic root already fixed in `CLAUDE.md`:
`home/climate/<room>/{co2,temperature,humidity,voc,nox,pressure,lux}`.

| Topic | Direction | Retained | Payload |
|---|---|---|---|
| `home/climate/<room>/{co2,temperature,humidity,voc,nox,pressure,lux}` | publish | yes | plain numeric value |
| `home/climate/<room>/status` | publish (LWT + birth) | yes | `online` / `offline` |
| `home/climate/<room>/cmd` | subscribe | no | JSON command (see below) |
| `home/climate/<room>/diag` | publish | no | JSON diagnostics |
| `homeassistant/sensor/wisp_<room>_<metric>/config` | publish (HA discovery) | yes | HA discovery config JSON, `availability_topic` set to the `status` topic above |

Sensor value topics are retained so Home Assistant shows the last known
reading immediately after its own restart, rather than a blank entity until
the next measurement; the `status` topic (with LWT) is what tells HA whether
that retained value is current or stale.

MQTT client: `esp_idf_svc::mqtt::client::EspMqttClient`, which wraps
ESP-IDF's own MQTT component and its TLS support — no separate MQTT crate
needed.

## Command channel (`cmd` topic)

v1 scope, kept deliberately small:

| Command | Effect |
|---|---|
| `reboot` | Restart the board |
| `ota_check` | Fetch the OTA manifest, report the available version on `diag` |
| `ota_apply` | Download, verify, and flash the signed image found by the last `ota_check`, then reboot |

No auto-discovery of arbitrary settings yet (e.g. remote-tunable publish
intervals) — that's an open question below, not a v1 commitment.

## OTA

- **Delivery:** a self-hosted HTTPS static file server, run as a service in
  the `/infra` docker-compose stack (see `infra-architecture.md`), serving
  signed images plus a small JSON manifest (version, SHA-256, signature).
- **Image signing:** ESP-IDF Secure Boot v2. The board verifies the image
  signature before switching the boot partition to it — independent of, and
  in addition to, the OTA server being reached over TLS. This matches the
  security posture already set for MQTT (auth + TLS + ACLs) rather than
  trusting the transport alone. From Rust, downloading and flashing goes
  through `esp-idf-svc`'s `EspOta` wrapper around `esp_https_ota`.
- **Rollout:** manual only, per board, via `ota_check` / `ota_apply` on the
  `cmd` topic — no background auto-update. Deliberate: a bad release
  shouldn't be able to take out every deployed room at once. ESP-IDF's
  dual-partition OTA still keeps the previous image bootable if a flash or
  verification step fails.
- **Versioning:** SemVer, via git tags (proposed scheme: `firmware-vX.Y.Z`,
  prefixed since hardware/infra share the repo). A tag push is meant to
  trigger a release build in CI; the firmware embeds its own version string
  (from `Cargo.toml` / a build-time env var) for use in the OTA manifest
  comparison and the `diag` topic.

## Diagnostics

- **`diag` MQTT topic** (JSON, published periodically and on notable state
  change): firmware version, uptime, free heap, WiFi RSSI, per-sensor
  last-successful-read age, per-sensor consecutive-failure count, and the
  SCD41/BME280 plausibility-check status described above.
- **Status LED (WS2812B)** — starting proposal, to be refined once hardware
  exists:

  | Pattern | Meaning |
  |---|---|
  | Slow breathing (steady color) | Normal operation |
  | Blinking yellow | Provisioning mode active (SoftAP open) |
  | Blinking orange | WiFi/MQTT disconnected, retrying |
  | Blinking red | Persistent sensor fault |
  | Fast red blink | OTA failure / rollback occurred |
  | Solid white | OTA in progress — do not power-cycle |

- **Serial/USB-Serial-JTAG console** stays available for bench debugging
  (the `log` crate routed through `esp-idf-svc`'s logger onto UART0, per
  `docs/concept.md`), but it's not the production diagnostics channel once
  the board is closed up in a room — that's the `diag` topic and the LED.

## CI

GitHub Actions build-check on push/PR touching `/firmware`: install the
Espressif Rust toolchain (via `espup`, cached, or a pre-built image such as
`espressif/idf-rust`) and run `cargo build --release`. Check the `esp-rs`
project's current recommended CI setup at implementation time — tooling in
this ecosystem moves faster than in mainline ESP-IDF. Scope for now is "does
it build," not on-hardware testing or automatic release signing (see open
questions).

## Open questions / follow-ups

- **Sensor driver crates:** verify what exists on crates.io for the SCD41,
  SGP41, BME280, and BH1750 (embedded-hal-compatible, working against
  `esp-idf-hal`'s I2C implementation) before committing to a timeline —
  worst case, register-level protocol code has to be written from the
  datasheets by hand, in which case Rust's safety guarantees buy the least
  exactly where the risk is highest.
- **Provisioning approach:** confirm the "roll it on `esp-idf-svc`'s HTTP
  server + AP mode" plan above works in practice before investing in it;
  fall back to raw `esp-idf-sys` FFI bindings to the C provisioning
  component only if necessary.
- **Secure Boot key custody in CI:** should the release signing key live as
  a GitHub Actions secret (convenient, but exposes it to CI compromise), or
  should CI only produce an unsigned build artifact that a human signs
  locally with an offline key before uploading to the OTA server? Leaning
  toward the latter as the safer default; not yet a final decision.
- **Panic behavior:** decide how the firmware should react to a Rust panic
  on a device that has to run unattended (likely: let it reboot via the
  watchdog rather than trying to recover in-process), and confirm that
  reboot itself gets surfaced on `diag`/the LED after the fact.
- Whether the `cmd` channel should ever grow remote-tunable settings (e.g.
  publish interval) beyond the fixed v1 set, and if so, whether such changes
  persist to NVS or are session-only.
- Cross-check thresholds (SCD41 vs. BME280) are placeholders pending real
  sensor data.
- Whether Home Assistant should ever be allowed to *send* `cmd` messages
  (e.g. a "reboot" button entity) — not scoped for v1, ACLs in
  `infra-architecture.md` currently only grant HA read access.
