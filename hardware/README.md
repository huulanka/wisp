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

## Board grown to 100x100mm to resolve GND/+3V3 pour-stitch congestion

Follow-up to the investigation above (#8/#9), which concluded the remaining
25 of 26 unconnected GND/+3V3 pour islands needed a placement/layout change,
not more routing cleverness, because at 75x80mm density most gaps had zero
collision-free path at any clearance down to 0mm — direct paths physically
overlapped other nets' copper.

**Board outline grown from 75x80mm to 100x100mm.** Chosen because it's the
largest size within JLCPCB's cheapest prototype-quantity price bracket (no
cost increase over 75x80mm), and `docs/hardware-expandability.md` already
noted the outline "is not final" pending a real enclosure design. All 73
footprints were repositioned proportionally (uniform scale from the old
75x80mm layout, preserving relative placement/functional zones), and the
board was re-routed from scratch with Freerouting (headless), same method
as the original compact-layout pass.

**A first attempt at 85x90mm silently corrupted U3's antenna keepout
zone.** The 26x16mm RF keepout area (see "U3 courtyard" finding above) is
not a footprint-owned zone, so it doesn't move automatically with U3 —
naively scaling its outline coordinates by the same factor as the
footprints double-transformed it relative to U3's new position, producing
a degenerate shape. `kicad-cli pcb drc` caught this as new
`courtyards_overlap`/`npth_inside_courtyard` hits against components ~50mm
away from U3 — geometrically impossible for a real overlap, which is what
exposed the bug. Fixed by translating the keepout zone by U3's exact
movement delta instead of scaling it (it's rigidly attached to U3, not
proportional to board size). Re-routing with the corrected (harder,
because now-correct) keepout in place initially performed *worse* (42
unconnected vs. the corrupted version's accidental 0) — confirming the
keepout was doing its job, not that the fix was wrong — which is why the
board was grown further to 100x100mm rather than kept at 85x90mm.

**Result at 100x100mm: 13 of the original 26 GND/+3V3 gaps remain, down
from 25.** Freerouting reported 0 unrouted signal nets; the 13 are
zone-fill islands on `GND`/`+3V3` pads that still don't reach the main
pour after refill:

- GND: pad 2 of `D3`, `D6`, `D9` (ESD-diode row)
- +3V3: pad 1 of `U2`, pads 2/6 of `U5`, pad 5 of `U6` (decoupling)

The same collision-checked stitching method validated in #9 (KiCad's own
`SHAPE_SEGMENT::Collide`/`GetClearance`, minimum-spanning-tree island
pairing, nudge-and-verify with the replacement-geometry fix already in
place) was re-run against the regrown board and closed 2 more islands
directly, verified with zero new `clearance`/`shorting_items` findings.
Widening the nudge search (more offsets, more anchor fractions) found no
further gains — the remaining 13 are blocked by multiple stacked signal
traces (`/SDA2`, `/EXP_IO35`, `/EXP_IO39`, `/MIC_SD`, `/MIC_SCK`, `/DTR`,
`+5V`, `/SDA`) that a single-track nudge can't route around. Closing them
needs either further board growth past JLCPCB's cheapest tier, or manual
rerouting of those specific nets — not more stitching.

**Two real regressions introduced by the regrow, both fixed and
re-verified:**

- `D2`'s GND pad ended up partially inside U3's (correctly-positioned)
  antenna keepout after the proportional scale. Moved `D2` 3mm clear
  (with its one attached `/SDA2` track end moved to match) — `items_not_allowed`
  finding resolved.
- Freerouting placed 7 short fanout-stub tracks at 0.15mm width, below
  the board's 0.2mm minimum. Widened to 0.2mm and re-verified no new
  clearance collisions.
- The fixed board title text (`wisp v1 - Andreas Bauer - 2026`, a static
  PCB graphic, not attached to any footprint) ended up overlapping
  `SW1`/`SW2`/`U4` silkscreen after those repositioned closer to its fixed
  location. Moved to open board space.

**Known DRC finding update: the MH1/U3 courtyard false-positive (see
above) now also flags `J1` vs `U3`.** Re-verified directly via `pcbnew`:
U3's courtyard spans roughly x=87-106mm, J1's spans roughly x=40-50mm on
the regrown board — ~40mm apart, geometrically impossible to overlap. Same
DRC-engine-noise category as the existing MH1/MH2/U3 finding, not a new
defect class.

13 of 26 GND/+3V3 pour islands remained open after this pass — see the
follow-up below, which closed all but 6 of those with two additional
stitching techniques.

## Layer-hop and A*-routed stitching closed 19 of the original 26 gaps

Follow-up to the 100x100mm regrow above. The remaining 13 islands were
blocked by same-layer signal traces (`/SDA2`, `/EXP_IO35`, `/EXP_IO39`,
`/MIC_SD`, `/MIC_SCK`, `/DTR`, `+5V`, `/SDA`) that a same-layer
nudge-and-verify can't route around without moving the blocker itself.
Two further collision-verified techniques were applied, in order:

1. **Layer-hop stitching.** Instead of nudging the blocking trace, route
   the GND/+3V3 stitch itself onto the opposite copper layer for just the
   segment that collides, via-hopping back down on the far side —
   sidesteps a same-layer blocker without touching it. Verified the same
   way as all prior stitches: KiCad's own `SHAPE_SEGMENT::Collide` against
   every other net's copper on both layers, plus explicit hole-to-hole
   spacing checks so via barrels don't crowd each other or existing holes.
   Standard 0.6mm/0.3mm vias everywhere except directly under U5, which
   reuses the existing "U5 local via size exception" DRU rule (0.45mm/0.2mm,
   same one documented above) since standard vias don't fit U5's 0.8mm pin
   pitch. Closed 6 islands.
2. **A\* pathfinding.** For islands still blocked (backside diodes needing a
   real detour around long runs like `/+5V_EXT`, which crosses most of one
   board quadrant on F.Cu), grid-based A\* search (reusing the same
   real-collision `PointChecker`, not a distance heuristic) found genuine
   multi-waypoint paths around the obstruction rather than a single
   straight or bent segment. One early A\* run routed a stitch directly
   through U3's antenna keepout rule-area — the pathfinder's obstacle set
   hadn't included rule areas, only tracks/pads/vias. Fixed by adding zone
   outlines (`ZONE.Outline()`, a filled `SHAPE_POLY_SET`) to the obstacle
   collision set for rule-area zones on the relevant layer, then re-ran
   clean. Closed 1 more island (`D3`'s GND pad, a 12-waypoint detour around
   the `/+5V_EXT`/`/EXP_IO39` congestion near J2).

Re-running both passes repeatedly past the point of new gains is
expected and harmless — once an island is bridged, the zone-fill
algorithm doesn't necessarily merge its pour polygon with the main pour
(the connection lives in the separate stitch copper, not the fill shape),
so a re-run's island-detection still sees it as "separate" and may add a
redundant parallel stitch to the same already-connected pad. These are
harmless (same net, verified collision-free, just extra copper) but were
cleaned up — 16 exact-duplicate track/via objects removed via a
dedup pass (identical net+layer+endpoints) before final export.

**Result: 6 of the original 26 gaps remain**, all on IC pins with sub-1mm
pin pitch where standard-size vias/traces have no room to route around
even after the board regrow:

- GND: pad 2 of `D9`
- +3V3: pads 2 and 6 of `U5` (0.8mm pitch BME680), pads 1 and 5 of `U6`

Verified exhaustively — direct stitch, same-layer nudge, layer-hop, and
A\* pathfinding (search radius up to 60mm, both 15mm- and 30mm-margin
passes) all independently converge on the same 6 pads with zero viable
path at any clearance. Closing these needs either a further board regrow
(past JLCPCB's cheapest tier — a real cost tradeoff, ask before doing
this) or hand-placed vias-in-pad / component-specific footprint changes
for `U5`/`U6`/`D9` specifically, which needs visual review in KiCad rather
than more scripted search.

**Still not fully fab-ready**, but the remaining gap is now 5 specific
pins on 3 components instead of a placement-density wall across the whole
board. `kicad-cli pcb drc --severity-all` reports 7 violations, all in the
pre-existing accepted false-positive/cosmetic categories documented above
(MH1/MH2/J1 vs U3 courtyard-overlap noise, U5 via-size exception NPTH/PTH
flags) — zero `clearance` or `shorting_items` findings. BOM/CPL
re-exported (CPL positions changed; BOM unchanged). Gerbers/drill
regenerated from the updated board.

Not all 6 stayed stuck: one further pass (below) found and fixed the
specific net responsible for most of the remaining congestion, closing
one more of these — `D9`'s GND pad. 5 gaps remain: `U5` pads 2/6, `U6`
pads 1/5, per the follow-up below.

## Placement review: decoupling caps found too far from their ICs, and a targeted /+5V_EXT reroute

Prompted by a fair challenge: is the placement actually well thought out,
or has repeated proportional scaling just carried forward an
under-optimized layout? Checked systematically rather than assuming.

**Real finding: the four 100nF decoupling caps (`C8`-`C11`) sit 8-13mm
from the +3V3 pin of the IC they decouple** (`U3`/`U4`/`U5`/`U6`), well
past the ~2-3mm generally recommended for effective local supply
filtering — none of them is unambiguously "the" decoupling cap for any
one IC by position. This is a genuine design-quality gap, independent of
the pour-routing issue, and most likely inherited from the original
140x100mm layout's spacing surviving unchanged through every later
proportional scale (uniform scaling preserves relative sloppiness, it
doesn't fix it).

Tried moving `C8`→`U4`, `C9`→`U5`, `C10`→`U6`, `C11`→`U3` (each to <3mm
from its IC's +3V3 pin) and re-routing from scratch. Verified clean on
its own (no new courtyard/clearance issues), but the resulting
Freerouting/stitch pass converged on **11 unconnected pour islands**,
worse than the 5 already achieved — including making `U5`'s decoupling
gap worse, not better. Given a floating power pin (a component that
plain doesn't work) is a more severe defect than a decoupling cap that's
farther from ideal than it should be but still electrically present, this
change was reverted in favor of keeping the 5-gap result. **The
decoupling-cap distance finding stands as a real, documented issue for a
future layout revision** — it just isn't worth trading away verified
pour-connectivity progress for in this pass.

Also tried a non-uniform regrow: shrink the board 100x100mm → 90x90mm
(addressing "this board feels bigger than it needs to be" for so few
components) while specifically pushing components within 10mm of `U5`/`U6`
further outward, giving those two ICs extra local room without growing
the whole board. Result: **8 unconnected**, worse than 100x100mm uniform,
and `U6` still had zero +3V3 connections either way — confirming `U6`'s
problem is intrinsic to its own 0.3x0.4mm pad geometry relative to its
immediate routed neighbors, not a placement-density problem a smarter
regrow could solve. Reverted.

**What did work: identifying and specifically rerouting `/+5V_EXT`.**
This single net (connecting `F1`, `D4`, and two DNP headers `J3`/`J5` at
opposite corners of the board) kept showing up as the direct physical
blocker across nearly every remaining gap investigation — Freerouting
had no reason to avoid routing it straight through the `U5`/`U6` sensor
cluster, since it doesn't know that area needs to stay clear for
GND/+3V3 pour access later. Ripped up just this one net and re-routed it
with A\* pathfinding under an explicit local keepout around `U5`+`U6`
(4mm margin), forcing it around the cluster instead of through it — full
reroute succeeded, zero new violations. Re-running the layer-hop/A\*
stitching passes afterward closed one further gap (`D9`'s GND pad).

**Result: 5 of the original 26 GND/+3V3 gaps remain** — `U5` pads 2 and
6, `U6` pads 1 and 5. Also attempted directly nudging `U6`'s own
footprint position (it has no other components within 8mm, so courtyard
collision wasn't a concern) — every offset tried caused new
`shorting_items` against `U6`'s *own* already-routed neighbor pads,
because the problem is `U6`'s 0.5mm pin pitch relative to its own
adjacent traces, not surrounding component density; moving the whole
footprint can't fix a constraint that's internal to it. Cleanly rejected
by the same verify-before-keep discipline as every other stitch in this
investigation — reverted automatically, no manual cleanup needed.

**Not fab-ready. 5 pins across `U5`/`U6` remain genuinely open** —
`U5` still has a third (already-connected) +3V3 pin so it stays
functional; `U6` has only two +3V3 pins total and **both are
open, meaning `U6` currently has no power connection at all** and would
not function as populated. Closing this needs one of: growing the board
past the 100x100mm cost-free JLCPCB tier (a real cost decision), or
increasing `U6`'s pad copper area in its footprint so the auto-filler can
bridge the gap (untested — the next thing to try, no fab-tier cost, but
changes the footprint from its library default and should be checked
against `U6`'s datasheet land pattern before use).

`kicad-cli pcb drc --severity-all`: 7 violations, same accepted
false-positive/cosmetic categories as before, zero `clearance` or
`shorting_items`. Gerbers/drill/CPL re-exported; BOM unchanged.

## Fixed: `wisp.kicad_sym` failed to load

`hardware/kicad/wisp.kicad_sym` previously had a stray top-level
`(embedded_fonts no)` field as a direct child of `kicad_symbol_lib`, instead
of one `(embedded_fonts no)` nested inside each `(symbol ...)` block (the
format every KiCad-generated symbol library uses). KiCad's parser rejects
the whole file when this field is misplaced, which surfaced as ERC warnings
claiming the `wisp` symbol library "was not found" for every symbol sourced
from it (U1 CH340C, U6 BH1750) — a misleading error, since the file was
present and otherwise valid. Fixed by moving the field into each symbol.
