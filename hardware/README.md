# hardware

KiCad project for the Wisp board. See `/hardware/kicad` for schematic/PCB
source, `/hardware/fab` for exported Gerbers/drill/BOM/CPL.

Board: **60 x 80 mm, 4 layers**, single-sided assembly (all parts on F.Cu).

## Validating the design

```
kicad-cli sch erc --output erc.json --format json hardware/kicad/wisp.kicad_sch
kicad-cli pcb drc --severity-all --format json --output drc.json hardware/kicad/wisp.kicad_pcb
```

Run these against the project directory, not against a copy of
`wisp.kicad_pcb` somewhere else: `kicad-cli` only picks up
`wisp.kicad_dru` (project-local design-rule exceptions) by path.

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

**Why 4 layers.** The board carries a 2.4GHz radio and a switching
regulator. On the previous 2-layer version, B.Cu had to be both "the ground
plane" and a routing layer at the same time, so ~1.4m of signal traces plus
40 backside parts cut the plane into fragments — and +3V3 was a second pour
competing for F.Cu. That is the direct cause of the long-running
"unconnected GND/+3V3 pour island" findings (issue #8): the power nets
depended on pours squeezing between signal traces, and at some pins no legal
path existed at any clearance. A dedicated plane per power net removes that
failure mode structurally rather than patching it. At JLCPCB prototype
quantities a 4-layer 60x80mm board is a few dollars over 2-layer.

## Power distribution: every power pad is bonded to its plane

Power connectivity does not rely on pour fill reaching a pad. Instead each
`+3V3` and `GND` pad gets its **own short stub and via straight down to the
plane that owns that net**, placed just off the pad by a collision-checked
search (~107 bonded pads), plus ~195 GND stitching vias tying the F.Cu/B.Cu
GND fill to the In1 plane.

The consequence worth remembering: a power pad can now only be unconnected
if its via is missing, which DRC reports directly as an unconnected item.
There is no longer such a thing as a "pour island" to hunt for.

Two fine-pitch parts needed narrower escapes than the 0.4mm default stub:
`U6` (BH1750, WSOF-6, 0.5mm pitch) and `U5` (BME680, LGA-8, 0.8mm pitch) use
0.20-0.21mm stubs, which still clear the 0.20mm rule. Everything else uses
0.4mm stubs and ordinary 0.6mm/0.3mm vias.

## Floorplan

Placement is by function, not by arithmetic. The previous layout had been
produced by proportionally scaling an older, denser board, which is why
growing the board never fixed the local congestion: scaling moves parts
apart but does not change pin-level geometry.

```
 y 0-9    antenna keepout (all 4 copper layers)
 y 1-27   U3 ESP32-WROOM-32, centred, antenna at the top board edge
 y 10-30  left: EN/IO0 support, reset+boot switches, status LED
          right: J2/J3 expansion headers on the right edge
 y 30-46  USB-C (left edge) -> U1 CH340C -> F1 -> U2 buck -> L1
 y 44-48  TP1-TP10 test point grid
 y 47-62  small headers (left), J4/J9 (right edge), buzzer
 y 62-80  sensor tab, thermally isolated (see below)
```

Rules this placement enforces, all of which the previous layout broke:

- **Every decoupling capacitor sits 1.8-3.0mm from the pin it serves, on the
  same side.** Previously all of them were on the *opposite* copper layer,
  8-20mm away (C11 for the ESP32 was 11.3mm away on the back). At that
  distance the loop inductance is roughly 10-20nH instead of 1-2nH, so the
  cap does essentially nothing above a few MHz — which matters for an ESP32
  drawing ~350mA bursts on TX.
- **The buck converter loop is tight.** U2 -> L1 and the input capacitor are
  adjacent and on the same layer as the regulator. Previously the SW node
  was 8.8mm long and the input/output caps sat 8-12mm away on the other
  layer — a large radiating loop next to a 2.4GHz receiver.
- **All 73 parts are on the front.** Single-sided assembly is cheaper at
  JLCPCB and, more importantly, it keeps the inner ground plane the only
  thing between the two routing layers.
- **Connectors are on edges**, USB-C on the left, expansion headers on the
  right, sensors along the bottom.

## RF: antenna placement

`U3` sits at the top board edge with its antenna end pointing off-board, so
the required clearance is mostly free air rather than reserved board area.
A 24 x 9mm rule area above the module forbids tracks, vias, pads and zone
fill **on all four copper layers** — on a 4-layer board the inner planes are
what would detune the antenna most, so a keepout that only covered F.Cu and
B.Cu would be worse than useless.

Previously the module sat in the middle of the board with the antenna
pointing inward, burning a 26 x 16mm keepout in the board interior and
forcing every net to detour around it.

**Fixed in this pass: U3's courtyard was stale.** The courtyard polygon had
been written in absolute board coordinates into the footprint's *local*
coordinate space by an earlier "shrink the courtyard" edit, so it never
moved with the module. On the 100x100mm board it sat at x=9.8-28.9,
y=-6.3-20.8 while U3's body was at (77.3, 36.2) — partly off-board, and
genuinely overlapping J1's courtyard. The resulting `courtyards_overlap` and
`*_inside_courtyard` reports were previously recorded here as "DRC engine
noise, geometrically impossible", a conclusion reached by comparing
footprint *origin* coordinates rather than the actual courtyard geometry.
They were real. The courtyard is now rebuilt from the module body
(18 x 25.5mm + 0.25mm margin) in local coordinates.

## Thermal isolation of the sensors

SCD41 (`U4`), BME680 (`U5`) and BH1750 (`U6`) sit on a tab at the bottom of
the board, x 21.5-46.5, y 63.5-80, cut free by a 1.5mm milled slot on three
sides and joined to the main board only through an ~8.5mm neck. This is
Sensirion's and Bosch's own recommendation: without it the parts report PCB
temperature rather than room temperature, which for a room climate monitor
defeats the primary function. The nearest heat sources (ESP32 at the top,
regulator mid-board) are ~40mm away with the slot in between.

Known tradeoff, deliberate: the GND and +3V3 planes still run through the
neck, so the isolation comes from the slot geometry and distance rather than
from a copper break. Narrowing the planes at the neck would improve it
further and is a reasonable future refinement.

## Fab outputs

`hardware/fab/gerbers/` now contains only the layers a fab actually needs —
the four copper layers, paste, silkscreen, mask and the board profile, plus
separate PTH/NPTH Excellon drill files and their maps:

```
kicad-cli pcb export gerbers \
  --layers F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts \
  -o hardware/fab/gerbers/ hardware/kicad/wisp.kicad_pcb
kicad-cli pcb export drill --format excellon --excellon-separate-th \
  --generate-map --map-format gerberx2 -o hardware/fab/gerbers/ hardware/kicad/wisp.kicad_pcb
kicad-cli pcb export pos --format csv --units mm --side front --exclude-dnp \
  -o hardware/fab/wisp-cpl-prototype.csv hardware/kicad/wisp.kicad_pcb
```

The earlier export also emitted Courtyard, Fab, Adhesive, Margin and User\_\*
Gerbers. Those are documentation layers, and shipping them in the fab folder
risks the fab's layer auto-detection counting them as copper — on a 4-layer
board that is an expensive mistake, so they are no longer exported.

Check `wisp-job.gbrjob` after any re-export: it must report
`LayerNumber: 4` with `Copper,L1,Top` / `Copper,L2,Inr` / `Copper,L3,Inr` /
`Copper,L4,Bot`. That file, not the filename extension, is what states the
stackup order.

The CPL lists 42 placements, all `top` — assembly is single-sided. The BOM
is unchanged by this layout work, since the schematic was not touched.

## Known ERC warnings (accepted, not bugs)

**`Symbol '2N7002' doesn't match copy in library 'Transistor_FET'`**
**`Symbol '1N4148' doesn't match copy in library 'Diode'`**

KiCad's official libraries switched these to symbol inheritance
(`(extends ...)`) after this schematic was authored; the schematic's cached
copy still holds the old self-contained definition. Electrically identical —
a library-version diff, not a design defect. It disappears the next time
these symbols are re-placed from a matching library version.

**`Pins of type Bidirectional and Power output are connected`** (U5 pin 5 /
SDO tied to GND)

`U5` (BME680) pin 5 (SDO) is intentionally strapped to GND to select I2C
address `0x76`. The symbol marks SDO `Bidirectional`, so ERC flags any
bidirectional pin wired to a power net. Confirmed via netlist export that
U5 pin 5 sits on GND together with pins 1/7 — no short to +3V3.

## Known DRC findings

None outstanding. `kicad-cli pcb drc --severity-all` is clean: 0 violations
and 0 unconnected items.

Note that the categories this project previously carried as accepted
findings are all gone rather than suppressed:

- the 26 unconnected `GND`/`+3V3` pour islands — removed by the plane
  stackup plus per-pad plane bonding;
- the `MH1`/`MH2`/`J1` vs `U3` courtyard overlaps — a real bug (stale
  courtyard), now fixed;
- the U5 via-in-pad / via-size exception — obsolete, because +3V3 is now
  reachable straight down from the pad with a standard 0.6mm via.
  `wisp.kicad_dru` no longer defines any rule.

## Routing

Signals are routed with Freerouting (headless,
`--gui.enabled=false -mt 1`; multi-threaded optimisation is flagged by
Freerouting itself as producing clearance violations). The DSN is exported
with `pcbnew.ExportSpecctraDSN` — note that `kicad-cli pcb export` has no
`specctra-dsn` subcommand in KiCad 10 — then patched so the inner layers are
`(type power)` and the clearance rule is 0.25mm.

The 0.25mm routing clearance is deliberately above the 0.20mm board rule:
Freerouting emits some fanout stubs at 0.15mm, which have to be widened to
the 0.20mm minimum afterwards, and routing at 0.25mm leaves enough headroom
that widening them cannot create a clearance violation.

Anything Freerouting leaves unrouted is closed afterwards by a
collision-checked A* over F.Cu/B.Cu with via transitions.

### J1 (USB-C) needs a hand-placed escape fanout

This is the one part of the board the autorouter cannot be left to solve,
and it is worth knowing before anyone re-routes.

The receptacle brings D+ out on pads A6/B6 and D- on A7/B7, and the pads
interleave down the column as **B6, A7, A6, B7** at 0.5mm pitch. Connecting
each pair therefore requires exactly one crossing, which means one of them
has to change layer — and a 0.6mm via needs ~1.2mm of vertical room, so no
via fits between 0.5mm lanes. The crossing can only happen further out,
where the lanes have spread.

Left to itself the autorouter routes D+ along D-'s only escape lane and
strands A7 with no legal path at any clearance. Growing the board does not
help; this is pad-pitch geometry, not board density.

The fix is a fanout placed **before** autorouting, while the area is still
empty:

1. every J1 signal leaves in its own lane out to x=3.4
2. the lanes spread to ~0.9mm pitch by x=4.8, preserving their order
3. D- crosses under D+ on B.Cu between two vias at x=4.8
4. D+ closes on F.Cu at x=5.8, passing over that B.Cu crossing

VBUS on A9/B4 is fenced in by the connector's own NPTH alignment hole and
is bonded with a via placed inside the pad (verified clear of the hole, the
neighbouring lands and the board edge). Every fanout segment and via is
clearance-checked against all existing copper before being committed.

If you re-place J1 or re-route from scratch, re-create this fanout first —
otherwise the D- connection will fail again in exactly the same way.
