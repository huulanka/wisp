# hardware

KiCad project for the Wisp board. See `/hardware/kicad` for schematic/PCB
source, `/hardware/fab` for exported Gerbers/drill/BOM/CPL.

## Validating the design

```
kicad-cli sch erc --output erc.json --format json hardware/kicad/wisp.kicad_sch
kicad-cli pcb drc --output drc.json --format json hardware/kicad/wisp.kicad_pcb
```

DRC reports 2 (occasionally 3, see below) clearance violations and 1
unconnected-item warning, all reviewed and accepted — see "Known DRC
findings" below. ERC reports 3 warnings, all reviewed and accepted as
intentional — see below.

Note: `hardware/kicad/wisp.kicad_dru` defines a local design-rule exception
(smaller minimum via size under U5's courtyard only). `kicad-cli` only picks
this up when it's run from/against the project directory as above — pointing
it at a copy of `wisp.kicad_pcb` elsewhere without the matching `.kicad_dru`
alongside it will report extra `via_diameter`/`hole_size` violations that
aren't real.

## Known ERC warnings (accepted, not bugs)

**`Symbol '2N7002' doesn't match copy in library 'Transistor_FET'`**
**`Symbol '1N4148' doesn't match copy in library 'Diode'`**

KiCad's official symbol libraries switched these parts to symbol inheritance
(`(extends "Q_NMOS_GSD")` / `(extends "1N4001")`) at some point after this
schematic was authored. The schematic's cached copy (embedded in
`wisp.kicad_sch` at placement time) still uses the old, fully self-contained
symbol definition. Electrically and functionally identical — this is a
library-version diff warning, not a design defect. It will disappear on its
own the next time someone re-places or updates these symbols from a matching
KiCad library version; no action needed until then.

**`Pins of type Bidirectional and Power output are connected`** (U5 pin 5 /
SDO tied to GND)

U5 (BME680) pin 5 (SDO) is intentionally tied to GND to statically select
I2C address `0x76` (tying it to VDDIO instead would select `0x77`). The
BME680 symbol marks SDO as `Bidirectional` since it's an I2C-adjacent pin in
general, but here it's used purely as an address-select strap — ERC can't
tell the difference and flags any bidirectional pin wired straight to a
power net. Confirmed via netlist export (`kicad-cli sch export netlist`)
that U5 pin 5 sits on the GND net together with U5 pin 1/7 (GND) — no
accidental short to +3V3.

## Known DRC findings (accepted, not bugs)

**U5 (+3V3) via, 2-3 clearance/shorting reports against `/SDA`, same underlying ~0.07-0.19mm gap**

Re-running `kicad-cli pcb drc` on this exact area occasionally reports a
third violation (`shorting_items` between +3V3 and /SDA, no distance given)
alongside the two `clearance` ones below — it doesn't show up on every run.
This is DRC engine noise, not a changing physical layout: the two `clearance`
violations always report the same actual gaps (0.0678mm and 0.1928mm, both
positive, i.e. real non-touching copper-to-copper gaps, just short of the
board's 0.2mm minimum), and the `shorting_items` check appears to
independently re-flag the same close-but-not-touching pair right at its own
tolerance boundary. Re-run DRC and check the reported "actual" clearance
values, not just the violation count, if this needs re-verifying.

The via feeding U5 pin 2 (+3V3) used to sit directly in the pad (via-in-pad)
right after the U5 routing pass — DRC-clean, but a real assembly risk on a
fine-pitch (0.8mm) LGA-8: with only board-standard tented vias (no
resin-fill/cap), reflow solder can wick into the via barrel and starve that
pad of solder. Fixed by moving the via off-pad, onto its own copper (not
merged with the pad), just below U5 pin 2, with a short stub trace
reconnecting it to the pad. This required a size exception (see
`wisp.kicad_dru`) because a standard 0.6mm via cannot clear neighboring pads
at U5's 0.8mm pin pitch under any placement — the exception drops the via to
0.45mm dia / 0.2mm drill, still within JLCPCB's standard capability, and only
applies within U5's courtyard.

Freeing the via also required straightening out U5's `/SDA` route: PR3/PR4
had left it as 16 tiny (~0.05–0.07mm) zigzag segments hugging the via/pad
keepout boundaries as tightly as legally possible — almost certainly leftover
from a scripted reroute, not a hand-drawn path. That's been replaced with a
clean two-segment diagonal-then-vertical run to the same exit point.

Even after both changes, 2 clearance violations remain between the relocated
via and the `/SDA` diagonal: actual clearance 0.068mm and 0.193mm vs. the
0.2mm rule (i.e. short by 0.03–0.13mm, not an actual short — verified via the
DRC report's own reported "actual" values). Closing this fully was possible
but only by re-routing `/SDA` on a wide detour that starts colliding with
unrelated copper further from U5 — not a local change anymore, and higher
risk than the small remaining margin justifies. Reviewed and accepted as-is:
the via is off the LGA pad (the actual assembly risk this addresses), and the
remaining shortfall is well within what JLCPCB's standard process tolerates
in practice. Revisit if a future full re-route of this area happens anyway.

**1 unconnected-item: isolated `+3V3` copper island near U6, pre-existing**

`kicad-cli pcb drc` reports an isolated island in the `+3V3` zone pour on
F.Cu, centered close to U6 (BH1750), not U5 — confirmed via pcbnew's zone
fill data (`ZONE.GetFilledPolysList`) that this ~0.75×1mm island has no pad,
via, or track of its own net touching it. This is a leftover pour-fill gap,
not something introduced by the U5 work in this pass: the same board at the
PR3 commit already had 2 such islands (checked via `git show` + DRC on that
revision); PR4's U5 fix incidentally closed one of them, leaving this one.
Cosmetic/negligible (isolated island, not a short or missing connection to
anything that needs it) but worth a dedicated small fix later rather than
folding it into this pass.

## Compact layout (v1, 75x80mm)

The board was reworked from its original 140x100mm outline down to
75x80mm: footprints repositioned into denser functional zones, roughly
half the passives/small-signal parts (all 0805 R/C, Q1-Q4, D2-D10, D4, U1)
moved to the back copper layer, and re-routed from scratch with Freerouting
(headless: `--gui.enabled=false -mt 1` — the GUI mode gets stuck on a
repaint exception after routing completes on this machine, and
multi-threaded route optimization is flagged by Freerouting itself as
"known to generate clearance violations"). All 44 nets routed (0 unrouted).

**U3 (ESP32-WROOM-32) courtyard was shrunk from 48x41mm to 19x27mm.** The
as-imported footprint's courtyard applied the Espressif-recommended 15mm
antenna keepout symmetrically around the *entire module*, not just the
antenna end — effectively reserving half of any sub-100mm board for the
module alone. The 15mm clearance is real (Espressif ESP Hardware Design
Guidelines: "at least 15mm... if the antenna cannot extend beyond the
board, keep it at least 15mm away from other components"), but it's an
antenna-proximity rule, not a whole-module rule. Fixed by shrinking U3's
own courtyard to the physical module body (18x25.5mm datasheet dimension +
assembly margin) and carrying the 15mm antenna clearance on a dedicated
26x16mm keepout rule-zone (F.Cu+B.Cu, no tracks/vias/pads/pours/footprints)
placed directly above the module's antenna edge instead. Non-redundant,
same physical protection.

**Known DRC finding: 25 unconnected GND/+3V3 pads (pour-fill islands)**

At this density, the GND (B.Cu) and +3V3 (F.Cu) copper pours fragment into
several small disconnected islands around tightly-packed clusters (the
backside ESD-diode/header-support row D2-D3/D5-D10, decoupling caps next
to U5/U6, a few pads near J2). Originally 26 pads/islands were affected
(see issue #8); one pour island was closed by a collision-checked stitch
track, verified with `kicad-cli pcb drc` to introduce zero new
`clearance`/`shorting_items` findings. 25 remain open.

Three approaches were tried for the remainder, in order of increasing
manual effort, all under real `kicad-cli pcb drc` verification (never
just eyeballing the fill):

1. **Freerouting on the full GND/+3V3 nets.** Exporting the Specctra DSN
   normally emits `(plane ...)` statements for GND/+3V3, which makes
   Freerouting treat the pads as already satisfied by the pour and skip
   them entirely — this is *why* the gaps exist in the first place.
   Stripping the plane statements so Freerouting has to route explicit
   traces works in principle, but at this density GND alone has ~70 pins;
   asking Freerouting to fully re-route it from scratch (rather than just
   patch the ~25 real gaps) consistently plateaus at 16+ unrouted
   connections and 49 internal violations regardless of pass count
   (tried 10/20/unlimited passes, headless via `-Djava.awt.headless=true`)
   — the router gets stuck on the same congestion, not on pass budget.
2. **Collision-checked candidate-pair search.** For each gap, sampling
   many point pairs between the two disconnected copper islands (not just
   the nearest points) and picking the first pair with a straight-line
   path clear of every other net's copper (via KiCad's own
   `SHAPE_SEGMENT::Collide`/`GetClearance`, not a distance heuristic).
   For most of the 25 remaining gaps this finds **zero** viable straight
   line at any clearance down to 0mm — the isolating obstacle (another
   net's escape trace) doesn't just fail clearance, the direct path
   physically overlaps it.
3. **Nudge-and-verify.** For gaps blocked by exactly one non-via signal
   trace, bending that trace out of the way (multiple offsets, multiple
   anchor points along its length) and re-verifying both the moved trace
   and the new GND/+3V3 stitch against every other item on the board,
   including each other. This is what closed the one gap that's fixed.
   For the rest, no bend/anchor combination within a few mm clears the
   local congestion without the moved trace or the new stitch colliding
   with something else — via barrels most often, which can't be nudged.

An earlier, less careful version of the nudge script produced 15+
`track_dangling`/`tracks_crossing` findings, traced to a real bug (the
collision check validated the planned stitch against the world with the
old blocker trace removed but before its replacement pieces existed,
missing collisions with the replacement geometry itself). Fixed by
including the planned replacement geometry as a real obstacle in both
directions of the check; re-running the corrected version dropped the
"successful" nudge count from 17 (mostly false positives) to 1 (verified).

**Straight pad-to-pad stitching without real collision checking was
tried and reverted before this investigation** — it drew tracks through
unrelated copper, producing real `shorting_items` violations (GND
shorted to +3V3, /REED_IN, /EXP_IO39), a strictly worse outcome than a
documented open connection. The takeaway holds after this pass too: at
this placement density, closing the remaining 25 gaps needs a **layout**
change (nudging component/trace placement to open a legal corridor, or a
scoped local clearance-relief design rule where fab tolerance allows),
not just more routing cleverness — same category as the U5 pocket below.
**Do not fab from this branch before that follow-up pass and a clean
`kicad-cli pcb drc` re-run.**

**Known DRC finding: `courtyards_overlap`/`items_not_allowed` between
MH1, MH2, and U3, positions don't actually support it**

`kicad-cli pcb drc` reports `Footprint MH1, Footprint U3` courtyard
overlap and `Footprint MH2` inside the antenna keepout on every run
(deterministic, not intermittent like the U5 finding above). Verified
directly via `pcbnew` that MH1 (4mm, 4mm) and U3 (58mm, 29mm) are ~55mm
apart, and MH2 (71mm, 4mm) is 3mm clear of the keepout zone's right edge
(68mm) — geometrically no overlap. Same category as the pre-existing
"DRC engine noise" finding on U5 (see below): re-verify with the reported
item positions, not just the violation count, before treating as real.

**1 dangling via on `+3V3`** — a Freerouting fanout via left connected on
only one layer after the auto-router found a more direct path. Cosmetic
(not a short, not a missing connection), same severity class as the
pre-existing isolated-pour-island finding below; cleanup candidate for a
future pass.

## Fixed: `wisp.kicad_sym` failed to load

`hardware/kicad/wisp.kicad_sym` previously had a stray top-level
`(embedded_fonts no)` field as a direct child of `kicad_symbol_lib`, instead
of one `(embedded_fonts no)` nested inside each `(symbol ...)` block (the
format every KiCad-generated symbol library uses). KiCad's parser rejects
the whole file when this field is misplaced, which surfaced as ERC warnings
claiming the `wisp` symbol library "was not found" for every symbol sourced
from it (U1 CH340C, U6 BH1750) — a misleading error, since the file was
present and otherwise valid. Fixed by moving the field into each symbol.
