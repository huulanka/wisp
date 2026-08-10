# Infra Architecture

Working design doc for `/infra`, written before any code exists. Captures
the decisions made in a planning Q&A round. Everything below runs as Docker
Compose services on the user's NAS — no cloud dependency, per `CLAUDE.md`.

## Services

| Service | Role | Status |
|---|---|---|
| `mosquitto` | MQTT broker: auth (username/password), TLS, no anonymous access, per-topic ACLs | v1 |
| `homeassistant` | Fresh instance (not integrating into a pre-existing one); bridges MQTT into entities via MQTT Discovery, exposes them to Apple HomeKit | v1 |
| `ota-server` | Self-hosted HTTPS static file/manifest server for signed firmware images | v1 |
| `influxdb` + `grafana` | Long-term history/trends | deferred, out of scope for this round — already flagged as "optional, later" in `docs/concept.md` |

## Network & TLS

- A self-signed **internal CA**, generated once. Its private key is kept
  offline — never in the repo, never in a running container — since it's the
  trust anchor every board and every service relies on.
- Leaf certificates for `mosquitto` and `ota-server`, signed by that CA,
  long validity (proposed: 3–5 years) — this is a closed home network with
  manual renewal anyway, so short-lived certs would only add operational
  churn without a real security benefit here.
- The CA's public certificate is baked into the firmware at build time (see
  `firmware-architecture.md`) — identical for every board, not a secret.
- Boards reach `mosquitto` and `ota-server` as plain host ports on the NAS's
  LAN (they're outside Docker), e.g. `mosquitto:8883`, `ota-server:8443`
  (placeholder ports, finalize alongside the compose file).
- **Time sync:** the boards need correct system time via SNTP before TLS
  certificate validation will succeed at all (no RTC battery, per
  `docs/concept.md`) — worth calling out explicitly since it's easy to
  discover only when the very first TLS handshake mysteriously fails.

## Secrets management

`.env` file, git-ignored, read by `docker-compose`; a checked-in
`.env.example` documents the required variables with placeholder values so a
fresh checkout is self-documenting without leaking anything.

Proposed contents of `.env`:

- Mosquitto admin/HA MQTT credentials
- Paths to the internal CA and leaf cert/key files (the files themselves
  stay outside the repo, referenced by path or Docker secret mount)
- Any Home-Assistant-specific bootstrap secrets

## Home Assistant integration

- Fresh instance, stood up by this compose stack (not bridging into an
  already-running one).
- Built-in MQTT integration, discovery prefix `homeassistant/` — matches the
  discovery topics the firmware publishes (see `firmware-architecture.md`).
  No manual YAML entity definitions needed; new rooms/boards just appear.
- HomeKit exposure via HA's own HomeKit Bridge integration, layered on top
  of the MQTT-derived entities.

## Access control (Mosquitto ACLs)

- Each board authenticates as its own MQTT user, scoped to:
  - read/write `home/climate/<room>/#`
  - write (retained) `homeassistant/sensor/wisp_<room>_+/config` — needed
    because the board itself publishes its HA discovery config
- Home Assistant's MQTT user gets broad read access (`home/climate/#`,
  `homeassistant/#`) but, for v1, **no** write access to any `cmd` topic —
  HA can observe everything but can't currently trigger a reboot or OTA
  check on a board. Extending that is an open question in
  `firmware-architecture.md`, not a v1 commitment.

## Add-a-board runbook

Provisioning a new room/board touches both sides of the stack:

1. On the broker: generate a new MQTT username/password for the room slug,
   append an ACL block scoping it to `home/climate/<room>/#` (+ its
   discovery-config write, per above), reload/restart Mosquitto.
2. On the board: put it into provisioning mode (SoftAP), submit WiFi +
   the new MQTT credentials + the room slug through the captive portal (see
   `firmware-architecture.md`).

Worth turning step 1 into a small script once more than one or two boards
exist — not needed to design further before that point.

## Backup

The three volumes that matter — `mosquitto` data (persistence DB,
password/ACL files), Home Assistant config (`.storage`, its database), and
`ota-images` (firmware binaries + manifests) — are placed on a path already
covered by the NAS's own snapshot/backup functionality. `/infra` documents
which paths matter; it does not run its own backup job.

## Roadmap / explicitly out of scope for this round

- **InfluxDB + Grafana** for long-term history — already noted in
  `docs/concept.md` as "optional, later."
- **Automatic OTA rollout** — explicitly rejected for v1 in
  `firmware-architecture.md`; a bad release must not be able to reach every
  room at once.
- **CI-driven release signing** — flagged as an open question in
  `firmware-architecture.md`; leaning toward local/offline signing instead
  of a CI-held key, not yet decided.
- **HA-initiated commands** (HA writing to a board's `cmd` topic, e.g. a
  reboot button) — ACLs above currently block this; would need a deliberate
  decision to open it up.
