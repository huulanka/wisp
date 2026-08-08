# hardware

KiCad project for the Wisp board. See `/hardware/kicad` for schematic/PCB
source, `/hardware/scripts` for the generators that produce them, and
`/hardware/fab` for exported Gerbers/drill/BOM/CPL.

Board: **60 x 80 mm, 4 layers**, single-sided assembly (all parts on F.Cu).

## The design is generated, not hand-drawn

This is the most important thing to know before touching anything here.

| File | Role |
|---|---|
| `scripts/wisp_netlist.py` | **The design.** Every part, value, footprint, MPN and net. |
| `scripts/wisp_floorplan.py` | **The placement.** Fixed positions for the parts whose location is a decision; anchors for everything else. Also the board outline. |
| `scripts/gen_schematic.py` | builds `wisp.kicad_sch` |
| `scripts/gen_pcb.py` | builds `wisp.kicad_pcb`, in stages |

Edit the data, re-run the generators. **Do not hand-edit `wisp.kicad_sch`** —
it is overwritten. Rev A's schematic was produced by a throwaway script that
was never committed, which is why by Rev B nobody could reconstruct how it had
been built. That is the problem these two files exist to prevent.

```
python3 hardware/scripts/gen_schematic.py

KI=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
for s in strip outline build bond fill; do $KI hardware/scripts/gen_pcb.py $s; done
# ... route (see below) ...
for s in close join polish silk fill; do $KI hardware/scripts/gen_pcb.py $s; done
```

The PCB generator runs as **separate processes per stage on purpose**. pcbnew's
SWIG bindings stop resolving types for the rest of the interpreter once
anything has been `Remove()`d from the board — zones come back as raw
`SwigPyObject`, `GetTracks()` stops being iterable, `FootprintLoad()` breaks,
and some combinations segfault outright. Every stage therefore does its reads
first, its deletions last, and hands off through the file.

### Stages

| Stage | Does |
|---|---|
| `strip` | resets the antenna keepout and the zone outlines, then deletes all copper and footprints |
| `outline` | rewrites Edge.Cuts from `wisp_floorplan.OUTLINE` (plain text — it both deletes and creates) |
| `build` | places all 91 footprints and assigns every net from the schematic netlist |
| `bond` | gives each SMD power pad its own via to its plane, plus a GND stitching grid |
| `fill` | refills all five zones |
| `close` | deletes vias/tracks the router left dangling; run until it reports none |
| `join` | closes any connection the router left open, with a collision-checked A* |
| `polish` | widens anything below the 0.15mm minimum track width |
| `silk` | makes the silkscreen manufacturable (see below) |

## Validating the design

```
kicad-cli sch erc --severity-all --format json --output erc.json hardware/kicad/wisp.kicad_sch
kicad-cli pcb drc --severity-all --format json --output drc.json hardware/kicad/wisp.kicad_pcb
```

Run these against the project directory, not against a copy of
`wisp.kicad_pcb` somewhere else: `kicad-cli` only picks up
`wisp.kicad_dru` and `wisp.kicad_pro` by path, and the project file is where
the design rules live.

`gen_schematic.py` additionally refuses to emit anything unless every net
references a pin that exists, every footprint file resolves, and **every pin
of every part is claimed by exactly one net or explicitly listed in
`NO_CONNECT`**. That last check is what stops a forgotten pin from quietly
becoming an unrouted net three stages later.

## Stackup

| Layer | Use |
|---|---|
| **F.Cu** | components + signal routing, GND fill in the gaps |
| **In1.Cu** (`GND`) | **solid, uncut ground plane** |
| **In2.Cu** (`PWR`) | **solid +3V3 plane** |
| **B.Cu** | signal routing, GND fill in the gaps |

Nothing is ever routed on the two inner layers — they are planes only. The
Specctra DSN handed to the autorouter declares them `(type power)` so the
router cannot cut them; if you re-export the DSN, re-apply that patch, since
KiCad exports all four layers as `(type signal)` by default.

## Power distribution

Every **surface-mount** `+3V3`/`GND` pad gets its own short stub and via
straight down to the plane that owns that net, placed just off the pad by a
collision-checked search. Power connectivity never depends on a pour reaching
a pad. Rev A's long-running "unconnected pour island" findings were all that
failure mode; with a via per pad, a power pad can only be unconnected if its
via is missing, which DRC reports directly.

Two deliberate exceptions:

- **Plated through-hole pads are not bonded.** A PTH pad already spans
  F.Cu..B.Cu and meets its plane on the way through. Adding a via beside it
  buys nothing and puts a second drill 0.4mm from the first — that was the
  source of most hole-to-hole violations and of two dangling `+3V3` vias
  during the Rev B bring-up.
- **Large exposed pads get a via array inside the pad** (the SCD41's 4.8mm
  thermal pad, the module's 3.9mm one). A stub to a via outside them cannot
  even be searched for, because every candidate within 3mm of the pad centre
  is still on the pad. This is what a thermal pad wants anyway.

Both the via *and the stub track leading to it* are collision-checked.
Checking only the via lets the stub cut straight across whatever pad lies
between — 61 GND/+3V3 shorts on the first attempt.

## Floorplan

Placement is by function, not by arithmetic.

```
 y 0.0-7.5    antenna keepout, all four copper layers, x 8..52
 y 0.75-26.3  U3 ESP32-S3-WROOM-1, antenna flush with the top edge
 y 8-30       left: EN/IO0 support, reset+boot buttons, status LED
              right: J2/J3 headers on the right edge
 y 30-46      USB-C (left edge) -> U8 ESD -> F1 -> U2 buck -> L1
 y 43-48      test point grid, 4.0mm pitch
 y 48-62      left: small headers; right: J4/J9; buzzer
 y 62-80      sensor tab, milled free on three sides
```

Rules this enforces:

- **Decoupling sits next to the pin it serves.** `wisp_floorplan.ANCHOR` names
  the pad each passive belongs to and `gen_pcb.py` runs a collision-checked
  spiral search outward from it. The ESP32's 100nF and 10uF, the SCD41's
  100nF, and the SGP41's RC element all land within a few millimetres of their
  pin. Rev A had all of its decoupling on the *opposite* copper layer, 8-20mm
  away, where above a few MHz it does essentially nothing.
- **A part may not cross the milled slot to reach its pin.** The slot splits
  the board into exactly two regions, and the placer requires a part to land
  in the same one as its anchor pad. Without that check the SCD41's bulk
  capacitor was placed 10mm away with a slot in between.
- **Fixed placements are checked against each other.** Pin headers are
  anchored at pin 1, not at their centre, so a 1x08 header extends ~20mm
  *downwards* from its coordinate; spacing them by centre is how J5/J7 and
  J9/MH4 first ended up overlapping.
- **All 91 parts are on the front.** Single-sided assembly is cheaper, and it
  keeps the inner ground plane the only thing between the two routing layers.

## RF: antenna placement

`U3` sits at the top board edge with its antenna end pointing off-board, so
the required clearance is mostly free air rather than reserved board area. A
rule area over `x 8..52, y 0..7.5` forbids tracks, vias, pads and zone fill on
**all four copper layers**.

Rev A cleared only the module's own width (x 18..42), which left GND pour
flush with the antenna on both sides. This clears ~9mm either side. It stops
short of the board corners so the M3 mounting holes still have somewhere to
live — the keepout forbids pads, and a mounting hole is a pad.

### The module footprint is project-local, and why

`wisp:ESP32-S3-WROOM-1` is a copy of the stock KiCad footprint with two
changes:

1. **The courtyard is trimmed to the module body** (x -9.75..9.75,
   y -12.75..13.45). The stock courtyard is **48 x 41mm**: it applies
   Espressif's 15mm antenna clearance symmetrically around the whole module
   instead of only off the antenna end. Left alone it swallows a third of a
   60x80mm board, blocks every nearby placement, and produces
   courtyard-overlap DRC errors against parts nowhere near the module. Rev A
   hit exactly this with the WROOM-32.
2. **Its built-in antenna keepout zone is removed**, so the board carries one
   deliberate antenna rule area instead of two overlapping ones with different
   extents.

## Thermal isolation of the sensors

SCD41 (`U4`), SGP41 (`U5`), BH1750 (`U6`) and BME280 (`U7`) sit on a tab at
the bottom of the board, x 19.5-49, y 62-80, cut free by a 1.5mm milled slot
on three sides and joined to the main board through a 9mm neck. This is
Sensirion's and Bosch's own recommendation: without it the parts report PCB
temperature rather than room temperature, which for a room climate monitor
defeats the primary function.

The tab is larger than Rev A's 25 x 16.5mm. The SCD41 alone fills 40% of that,
leaving nowhere to put its own decoupling — which is exactly what went wrong
the first time. At 29.5 x 18mm every sensor keeps its decoupling on its own
side of the slot.

The SGP41 is placed at the far end of the tab from the SCD41: it runs a
hotplate, and the SCD41 is the sensor whose temperature reading has to stay
honest.

**Known tradeoff, deliberate:** the GND and +3V3 planes still run through the
neck, so the isolation comes from slot geometry and distance rather than from
a copper break. Narrowing the planes at the neck would improve it further and
remains a reasonable future refinement.

## Routing

Signals are routed with Freerouting (headless, `--gui.enabled=false -mt 1`;
multi-threaded optimisation is flagged by Freerouting itself as producing
clearance violations). The DSN is exported with `pcbnew.ExportSpecctraDSN` —
note that `kicad-cli pcb export` has no `specctra-dsn` subcommand — then
patched so the inner layers are `(type power)`.

Afterwards, `close` removes anything the router left dangling and `join`
closes any remaining open connection with a collision-checked A* over
F.Cu/B.Cu with via transitions. `join` reads the DRC report to find what is
open and rasterises the **whole** target net as its goal; aiming at a single
reported coordinate is fragile, because a track's `GetPosition()` is one end
of it rather than the nearest point.

**Minimum track width is 0.15mm.** The escapes under the fine-pitch sensors
genuinely need it, and it is comfortably inside JLCPCB's 4-layer capability
(0.127mm). Rev A instead routed at 0.25mm clearance and widened the router's
0.15mm stubs back to 0.20mm afterwards; doing that here created clearance
violations against neighbouring pads, and re-routing at 0.25mm made the router
thrash without converging.

**If a net comes back unroutable, look at the test points first.** They sit in
the busiest part of the board, and at Rev A's 3.2mm pitch the router boxed one
in completely — a net that no amount of post-processing can reach, because the
pad has no escape lane in any direction. They are at 4.0mm pitch now.

### J1 (USB-C)

The receptacle brings D+ out on pads A6/B6 and D- on A7/B7, interleaved down
the column as **B6, A7, A6, B7** at 0.5mm pitch, so connecting each pair needs
exactly one layer crossing and a 0.6mm via needs ~1.2mm of vertical room. On
Rev A this required a hand-placed fanout before autorouting.

On Rev B the pair runs J1 -> U8 (USBLC6 ESD array) -> U3 rather than J1 -> a
UART bridge, and U8 is placed to give the crossing room, so the autorouter
solves it unaided. If you re-place J1 or U8 and D- comes back unroutable, this
is why.

## Silkscreen

At 91 parts on 60x80mm a footprint's own silk outline routinely lands on the
neighbouring part's pads. The `silk` stage:

- moves every footprint silk **graphic** to F.Fab, where it still appears in
  the assembly drawing;
- **auto-places the reference designators** with a collision-checked search
  against pads, board edge and each other, largest parts first, and demotes
  only the ones with nowhere to go;
- moves **Value** to F.Fab;
- and hides the custom metadata fields.

That last one matters more than it sounds. `MPN`, `Manufacturer`, `Rating` and
`LCSC` are created on **F.SilkS by default and parked at the footprint
origin**, stacked on top of each other and on the pads — 422 text items nobody
ever intended to print. They are not returned by `GraphicalItems()`, so they
are invisible to every other pass, and they were the entire source of ~440
silkscreen DRC violations. If silkscreen violations reappear after adding a
field, this is the first place to look.

## Known ERC warnings (accepted, not bugs)

**`Pins of type Bidirectional and Power output are connected`** (U7 pin 5 /
SDO tied to GND)

`U7` (BME280) pin 5 (SDO) is intentionally strapped to GND to select I2C
address `0x76`. The symbol marks SDO `Bidirectional`, so ERC flags any
bidirectional pin wired to a power net. Either address strap produces this;
it cannot be avoided while the address is fixed in hardware.

Rev A's two `lib_symbol_mismatch` warnings are gone: the generator embeds
symbols straight from the installed library, so a cached copy cannot drift
from it.

## Known DRC findings

None. `kicad-cli pcb drc --severity-all` is clean: 0 violations, 0 unconnected
items, 0 schematic-parity errors.

Two design rules were deliberately changed from Rev A, both recorded in
`wisp.kicad_pro`:

- `min_track_width` 0.20 -> **0.15mm** — see Routing above.
- `min_resolved_spokes` 2 -> **1** — a handful of GND pads can only get one
  thermal spoke past their neighbours. One spoke is a valid connection, and
  every affected pad is a power pad that also carries its own plane via, so
  the spoke is a secondary path in any case.

## Fab outputs

`hardware/fab/gerbers/` contains only the layers a fab actually needs — the
four copper layers, paste, silkscreen, mask and the board profile, plus
separate PTH/NPTH Excellon drill files and their maps.

Check `wisp-job.gbrjob` after any re-export: it must report `LayerNumber: 4`
with `Copper,L1,Top` / `Copper,L2,Inr` / `Copper,L3,Inr` / `Copper,L4,Bot`.
That file, not the filename extension, is what states the stackup order.

## Before ordering

**`wisp:BH1750FVI-TR_WSOF6` is still a DRAFT footprint.** Its pad geometry was
derived from datasheet *text*, never checked against ROHM's mechanical
drawing, and that drawing could not be retrieved to verify it (404 from both
ROHM CDNs, 403 from rohm.com, Mouser serves HTML instead of the PDF). A
courtyard has been added — it previously had none at all, so it got no
collision protection — but **the land pattern itself is unverified**. Print it
1:1 and compare against the part, or replace the footprint, before committing
to an assembly run.

`wisp:Sensirion_DFN-6-1EP_2.44x2.44mm_P0.8mm_EP1.25x1.7mm` (SGP41) *was*
verified against the datasheet's land-pattern figure. Note that the `2.3`
dimension in that figure is **centre-to-centre** across the two pad columns,
not outer-to-outer; reading it the other way puts the terminal pads at
±0.875mm where they physically overlap the die pad, which DRC catches as four
shorts inside the part.

**No LCSC part numbers are in the BOM.** Every part carries an `MPN`,
`Manufacturer` and a `Rating` (voltage/tolerance/current class), which is what
you need to buy them from a distributor. LCSC numbers were deliberately not
guessed — a wrong one silently orders the wrong part. Fill them in from the
LCSC catalogue before uploading for PCBA.

**Sensor handling.** Sensirion specifies that the SGP41 must **not** be hand-
soldered or vapour-phase soldered, and that board wash and ultrasonic cleaning
must be avoided; Bosch says the same about cleaning agents near the BME280's
sensing element. If you order PCBA, ask for no-clean and no board wash.
