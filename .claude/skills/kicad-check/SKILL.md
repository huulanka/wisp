---
name: kicad-check
description: Run ERC (electrical rules check) and DRC (design rules check) on the wisp KiCad project under /hardware using kicad-cli, and summarize violations. Use whenever schematic or PCB layout files have been changed, or the user asks to validate/check the hardware design.
---

Validate the KiCad project in `/hardware` using `kicad-cli` (bundled with KiCad 7+).

1. Locate the schematic (`.kicad_sch`) and PCB (`.kicad_pcb`) files under `/hardware`.
2. Run ERC on the schematic:
   ```
   kicad-cli sch erc --output <report>.json --format json <project>.kicad_sch
   ```
3. Run DRC on the PCB:
   ```
   kicad-cli pcb drc --output <report>.json --format json <project>.kicad_pcb
   ```
4. Parse the JSON reports and summarize violations grouped by severity (error/warning), with the offending net/component and file location for each.
5. If there are unresolved errors, do not treat the design as ready for fab/assembly (JLCPCB) — flag this clearly.
6. If `kicad-cli` is not installed, tell the user to install KiCad (7.0+) rather than attempting a workaround.
