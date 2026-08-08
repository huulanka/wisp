#!/usr/bin/env python3
"""Rebuild hardware/kicad/wisp.kicad_pcb from the schematic + floorplan.

Run with KiCad's bundled Python, which is the one that has pcbnew:

  /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/\
Versions/Current/bin/python3 hardware/scripts/gen_pcb.py

What is preserved from the existing board: the 4-layer stackup, the board
outline including the milled sensor-tab slot, the design rules, and the four
copper zones. What is regenerated: every footprint, every net assignment, and
(in later stages) all copper.

Stage 1 only places parts and assigns nets. Routing is a separate stage so
that a placement problem shows up as a placement problem.
"""

import os
import re
import math
import subprocess
import sys
import uuid as _uuid

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PCB = os.path.join(ROOT, "hardware", "kicad", "wisp.kicad_pcb")
SCH = os.path.join(ROOT, "hardware", "kicad", "wisp.kicad_sch")
KICAD_FP = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
LOCAL_FP = os.path.join(ROOT, "hardware", "kicad")

sys.path.insert(0, HERE)
import wisp_netlist as D          # noqa: E402
import wisp_floorplan as FP       # noqa: E402

MM = 1000000


def mm(v):
    return int(round(v * MM))


def vec(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


# --------------------------------------------------------------------------

def export_netlist(tmp):
    out = os.path.join(tmp, "wisp.net")
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format",
                    "kicadsexpr", "-o", out, SCH],
                   check=True, capture_output=True)
    return out


def read_netlist(path):
    """(ref, pad) -> netname, using the netlist KiCad itself produced."""
    t = open(path).read()
    i = t.index("\t(nets")
    out = {}
    for block in re.split(r"\n\t\t\(net\n", t[i:])[1:]:
        name = re.search(r'\(name "([^"]*)"\)', block).group(1)
        if name.startswith("unconnected-"):
            continue
        for m in re.finditer(r'\(ref "([^"]+)"\)\s*\n\s*\(pin "([^"]+)"\)', block):
            out[(m.group(1), m.group(2))] = name
    return out


def load_footprint(fp_id):
    lib, name = fp_id.split(":", 1)
    for base in (LOCAL_FP, KICAD_FP):
        d = os.path.join(base, lib + ".pretty")
        if os.path.isdir(d):
            fp = pcbnew.FootprintLoad(d, name)
            if fp is not None:
                return fp
    raise SystemExit("cannot load footprint %s" % fp_id)


def net_of(board, name, cache):
    if name not in cache:
        ni = board.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
        cache[name] = ni
    return cache[name]


# --------------------------------------------------------------------------
# placement helpers
# --------------------------------------------------------------------------

def fp_box(fp):
    """Courtyard offsets (dx0, dy0, dx1, dy1) relative to the footprint origin.

    Not every courtyard is centred on the origin -- the USB-C receptacle's
    origin sits on a pad, several millimetres off centre. Treating the box as
    centred silently shifts the collision rect and lets parts overlap, which
    is how R1 ended up inside J1's courtyard.
    """
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if bb.GetWidth() == 0:
        bb = fp.GetBoundingBox(False, False)
    return (bb.GetX() / MM, bb.GetY() / MM,
            (bb.GetX() + bb.GetWidth()) / MM, (bb.GetY() + bb.GetHeight()) / MM)


def rect_at(fp, x, y):
    """Collision rect for placing an as-yet-unpositioned footprint at (x, y)."""
    dx0, dy0, dx1, dy1 = fp_box(fp)
    return (x + dx0, y + dy0, x + dx1, y + dy1)


def abs_rect(fp):
    """Courtyard rect of a footprint that has already been positioned.

    fp_box() is only relative while the footprint sits at the origin; once
    SetPosition() has been called the same call returns absolute coordinates.
    Adding the position to that gives a rect roughly twice as far out as the
    part really is, so nothing collides with it and parts land on top of each
    other. Always use this after placing.
    """
    return fp_box(fp)


def rects_overlap(a, b, gap):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or
                a[3] + gap <= b[1] or b[3] + gap <= a[1])


def in_board(rect):
    """Rect must sit on copper: inside the outline and clear of the milled slot."""
    x0, y0, x1, y1 = rect
    if x0 < 0.5 or y0 < 0.5 or x1 > FP.BOARD_W - 0.5 or y1 > FP.BOARD_H - 0.5:
        return False
    tx0, ty0, tx1, ty1 = FP.TAB
    if y1 <= FP.SLOT_TOP_Y:
        return True                                    # wholly above the slot
    on_tab = x0 >= tx0 + 0.5 and x1 <= tx1 - 0.5 and y0 >= ty0 + 0.5
    left_col = x1 <= FP.LEFT_COL_X - 0.5
    right_col = x0 >= FP.RIGHT_COL_X + 0.5
    neck = x0 >= 40.0 and x1 <= tx1 - 0.5
    return on_tab or left_col or right_col or neck


def region_of(x, y):
    """Which contiguous piece of board a point sits on.

    The milled slot splits the board into exactly two regions: the sensor tab
    and everything else (the left and right columns stay joined to the main
    board above the slot). A decoupling cap must land in the same region as
    the pin it serves -- otherwise its only path to that pin is the 8.5mm
    neck, which is the opposite of decoupling. This is how C13 first ended up
    10mm from the SCD41 with a milled slot in between.
    """
    tx0, ty0, tx1, ty1 = FP.TAB
    if tx0 <= x <= tx1 and y >= ty0:
        return "tab"
    return "main"


def keepout_rect():
    xs = [p[0] for p in FP.ANTENNA_KEEPOUT]
    ys = [p[1] for p in FP.ANTENNA_KEEPOUT]
    return (min(xs), min(ys), max(xs), max(ys))


DIR_ORDER = {
    "left":  [(-1, 0), (-1, -1), (-1, 1), (0, -1), (0, 1), (1, 0)],
    "right": [(1, 0), (1, -1), (1, 1), (0, -1), (0, 1), (-1, 0)],
    "up":    [(0, -1), (-1, -1), (1, -1), (-1, 0), (1, 0), (0, 1)],
    "down":  [(0, 1), (-1, 1), (1, 1), (-1, 0), (1, 0), (0, -1)],
    "any":   [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)],
}


def place_anchored(fp, anchor_xy, direction, occupied, gap=0.3):
    """Spiral outwards from the anchor pad until the courtyard fits."""
    ax, ay = anchor_xy
    want = region_of(ax, ay)
    ko = keepout_rect()
    best = None
    for r in [x * 0.1 for x in range(18, 221)]:          # 1.8mm .. 22.0mm
        for dx, dy in DIR_ORDER[direction]:
            n = (dx * dx + dy * dy) ** 0.5
            cx, cy = ax + dx / n * r, ay + dy / n * r
            rect = rect_at(fp, cx, cy)
            if region_of(cx, cy) != want:
                continue
            if region_of(rect[0], rect[1]) != want or region_of(rect[2], rect[3]) != want:
                continue
            if not in_board(rect):
                continue
            if rects_overlap(rect, ko, 0.0):
                continue
            if any(rects_overlap(rect, o, gap) for o in occupied):
                continue
            best = (cx, cy, rect, r)
            break
        if best:
            break
    return best


# --------------------------------------------------------------------------

def stage_strip():
    """Reset the board: keepout, zone outlines, then delete copper + footprints.

    Order matters and is not cosmetic. pcbnew's SWIG bindings stop resolving
    types for the rest of the process once anything has been Remove()d --
    zones come back as raw SwigPyObjects, GetTracks() stops being iterable,
    and FootprintLoad() breaks. So every read/modify happens first, the
    deletions happen last, and anything that needs to construct new objects
    lives in a different stage.
    """
    board = pcbnew.LoadBoard(PCB)

    # SHAPE_POLY_SET objects must outlive the SetOutline() call; letting them
    # be collected inside the loop segfaults the interpreter.
    keepalive = []

    for i in range(board.GetAreaCount()):
        z = board.GetArea(i)
        if z.GetIsRuleArea():
            # Antenna keepout, widened to the full board width.
            poly = pcbnew.SHAPE_POLY_SET()
            poly.NewOutline()
            for x, y in FP.ANTENNA_KEEPOUT:
                poly.Append(mm(x), mm(y))
            keepalive.append(poly)
            z.SetOutline(poly)
            ls = pcbnew.LSET()
            for lay in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
                ls.addLayer(lay)
            z.SetLayerSet(ls)
        else:
            # Copper pours: give every zone the whole board rectangle as its
            # outline. KiCad clips the fill to the board edge anyway, so the
            # pours follow the outline automatically instead of carrying a
            # hand-traced copy of it that silently goes stale the moment the
            # sensor tab moves -- which is exactly what Rev A's zones did.
            poly = pcbnew.SHAPE_POLY_SET()
            poly.NewOutline()
            for x, y in ((0, 0), (FP.BOARD_W, 0),
                         (FP.BOARD_W, FP.BOARD_H), (0, FP.BOARD_H)):
                poly.Append(mm(x), mm(y))
            keepalive.append(poly)
            z.SetOutline(poly)

    for t in list(board.GetTracks()):
        board.Remove(t)
    for f in list(board.GetFootprints()):
        board.Remove(f)
    pcbnew.SaveBoard(PCB, board)
    print("stage strip: copper cleared, keepout + zone outlines reset")
    sys.stdout.flush()
    # The zones now share ownership of the SHAPE_POLY_SETs in `keepalive`, so
    # normal interpreter teardown double-frees them and segfaults *after* a
    # perfectly good save. Leave without running teardown.
    os._exit(0)


def stage_outline():
    """Rewrite Edge.Cuts from wisp_floorplan.OUTLINE.

    Plain text on purpose: this has to delete existing drawings and create new
    ones, which cannot be done in the same pcbnew process (see stage_strip).
    """
    src = open(PCB).read()
    out = []
    i = 0
    removed = 0
    while True:
        k = src.find("\n\t(gr_line", i)
        if k < 0:
            out.append(src[i:])
            break
        depth = 0
        j = k + 1
        while j < len(src):
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
                if depth == 0:
                    j += 1
                    break
            j += 1
        block = src[k:j]
        if '(layer "Edge.Cuts")' in block:
            out.append(src[i:k])
            removed += 1
        else:
            out.append(src[i:j])
        i = j
    src = "".join(out)

    pts = FP.OUTLINE
    segs = []
    for n in range(len(pts)):
        a, b = pts[n], pts[(n + 1) % len(pts)]
        segs.append(
            '\t(gr_line\n\t\t(start %g %g)\n\t\t(end %g %g)\n'
            '\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type default)\n\t\t)\n'
            '\t\t(layer "Edge.Cuts")\n\t\t(uuid "%s")\n\t)\n'
            % (a[0], a[1], b[0], b[1], _uuid.uuid4()))
    m = src.rindex("\n)")
    src = src[:m + 1] + "".join(segs) + src[m + 1:]
    open(PCB, "w").write(src)
    print("stage outline: replaced %d Edge.Cuts segments with %d new ones"
          % (removed, len(segs)))
    return 0


def stage_build():
    tmp = os.environ.get("CLAUDE_JOB_DIR", "/tmp")
    tmp = os.path.join(tmp, "tmp") if os.path.isdir(os.path.join(tmp, "tmp")) else "/tmp"
    netmap = read_netlist(export_netlist(tmp))

    board = pcbnew.LoadBoard(PCB)
    parts = {p["ref"]: p for p in D.PARTS}
    fps = {ref: load_footprint(p["fp"]) for ref, p in parts.items()}

    cache = {}
    occupied = []
    placed = {}
    fixed_rects = []
    fixed_clashes = []

    # ---- fixed placements ---------------------------------------------
    order = [r for r in FP.FIXED] + [r for r in FP.ANCHOR]
    missing = set(parts) - set(order)
    if missing:
        raise SystemExit("no floorplan entry for: %s" % sorted(missing))
    unknown = set(order) - set(parts)
    if unknown:
        raise SystemExit("floorplan references unknown parts: %s" % sorted(unknown))

    for ref in FP.FIXED:
        p = parts[ref]
        fp = fps[ref]
        board.Add(fp)
        x, y, rot = FP.FIXED[ref]
        fp.SetPosition(vec(x, y))
        fp.SetOrientationDegrees(rot)
        fp.SetReference(ref)
        fp.SetValue(p["val"])
        if p.get("dnp"):
            fp.SetDNP(True)
        if p.get("exclude_bom"):
            fp.SetExcludedFromBOM(True)
        for key, name in (("mpn", "MPN"), ("mfr", "Manufacturer"),
                          ("rating", "Rating"), ("lcsc", "LCSC")):
            if p.get(key):
                fp.SetField(name, p[key])
        rect = abs_rect(fp)
        for oref, orect in fixed_rects:
            if rects_overlap(rect, orect, 0.0):
                fixed_clashes.append("%s overlaps %s" % (ref, oref))
        fixed_rects.append((ref, rect))
        occupied.append(rect)
        placed[ref] = (x, y)

    # ---- anchored placements -------------------------------------------
    failures = []
    for ref, (aref, apad, direction) in FP.ANCHOR.items():
        p = parts[ref]
        fp = fps[ref]
        board.Add(fp)
        fp.SetReference(ref)
        fp.SetValue(p["val"])
        if p.get("dnp"):
            fp.SetDNP(True)
        for key, name in (("mpn", "MPN"), ("mfr", "Manufacturer"),
                          ("rating", "Rating"), ("lcsc", "LCSC")):
            if p.get(key):
                fp.SetField(name, p[key])
        host = board.FindFootprintByReference(aref)
        if host is None:
            failures.append("%s: anchor part %s not placed" % (ref, aref))
            continue
        pad = host.FindPadByNumber(apad)
        if pad is None:
            failures.append("%s: anchor pad %s.%s not found" % (ref, aref, apad))
            continue
        pos = pad.GetPosition()
        got = place_anchored(fp, (pos.x / MM, pos.y / MM), direction, occupied)
        if got is None:
            failures.append("%s: no free spot near %s.%s" % (ref, aref, apad))
            continue
        cx, cy, rect, dist = got
        fp.SetPosition(vec(cx, cy))
        occupied.append(abs_rect(fp))
        placed[ref] = (cx, cy)

    if fixed_clashes:
        print("FIXED PLACEMENTS OVERLAP:")
        for c in sorted(set(fixed_clashes)):
            print("  " + c)
        return 1
    if failures:
        print("PLACEMENT FAILED:")
        for f in failures:
            print("  " + f)
        return 1

    # ---- nets -----------------------------------------------------------
    unassigned = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            num = pad.GetNumber()
            if not num:
                continue
            name = netmap.get((ref, num))
            if name is None:
                if not pad.IsOnCopperLayer():
                    continue
                unassigned.append("%s.%s" % (ref, num))
                continue
            pad.SetNet(net_of(board, name, cache))

    board.BuildListOfNets()
    pcbnew.SaveBoard(PCB, board)

    print("stage 1 complete")
    print("  footprints placed: %d" % len(board.GetFootprints()))
    print("  nets on board:     %d" % (board.GetNetCount() - 1))
    if unassigned:
        print("  pads with no net (expected: NO_CONNECT + mech): %d" % len(unassigned))
        print("   ", ", ".join(sorted(unassigned)[:16]))
    dists = []
    for ref, (aref, apad, _) in FP.ANCHOR.items():
        host = board.FindFootprintByReference(aref)
        pad = host.FindPadByNumber(apad)
        px, py = pad.GetPosition().x / MM, pad.GetPosition().y / MM
        cx, cy = placed[ref]
        dists.append((((cx - px) ** 2 + (cy - py) ** 2) ** 0.5, ref, aref, apad))
    dists.sort()
    print("  anchored parts: %d, distance to their pin %.2f..%.2f mm"
          % (len(dists), dists[0][0], dists[-1][0]))
    far = [d for d in dists if d[0] > 5.0]
    if far:
        print("  further than 5mm from their pin:")
        for d, ref, aref, apad in far:
            print("    %-5s %5.2f mm from %s.%s" % (ref, d, aref, apad))
    return 0


# --------------------------------------------------------------------------

VIA_D, VIA_DRILL, CLEAR, STUB_W = 0.6, 0.3, 0.2, 0.3
HOLE_GAP = 0.3          # fab hole-to-hole minimum, with margin over 0.2495


def _index(items, cell=2.0):
    """Bucket rects into a coarse grid so proximity queries stay cheap."""
    grid = {}
    for it in items:
        x0, y0, x1, y1 = it[0], it[1], it[2], it[3]
        for gx in range(int(x0 // cell), int(x1 // cell) + 1):
            for gy in range(int(y0 // cell), int(y1 // cell) + 1):
                grid.setdefault((gx, gy), []).append(it)
    return grid, cell


def _near(index, x, y, pad=1.0):
    grid, cell = index
    out = []
    for gx in range(int((x - pad) // cell), int((x + pad) // cell) + 1):
        for gy in range(int((y - pad) // cell), int((y + pad) // cell) + 1):
            out.extend(grid.get((gx, gy), ()))
    return out


def stage_bond():
    """Give every GND / +3V3 pad its own via straight down to its plane.

    Power connectivity must not depend on a pour reaching a pad. Rev A's 26
    unconnected pour islands were all that failure. With a via per pad, a
    power pad can only be unconnected if its via is missing, which DRC
    reports directly.

    A through via on GND touches the In1 GND plane and is held off In2 by the
    +3V3 zone's own clearance, and vice versa, so one via type serves both
    planes without shorting them.

    Both the via *and the stub track leading to it* are collision-checked.
    Checking only the via is not enough: the stub then cuts straight across
    whatever pad happens to lie between the pad and its via, which is where
    61 GND/+3V3 shorts came from on the first attempt.
    """
    board = pcbnew.LoadBoard(PCB)

    pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            pads.append((bb.GetX() / MM, bb.GetY() / MM,
                         (bb.GetX() + bb.GetWidth()) / MM,
                         (bb.GetY() + bb.GetHeight()) / MM,
                         pad.GetNetname(), fp.GetReference(), pad.GetNumber()))
    pad_index = _index(pads)
    drills = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            d = pad.GetDrillSize()
            if d.x > 0:
                drills[(fp.GetReference(), pad.GetNumber())] = d.x / MM
    obstacles = []          # (x, y, radius, net) for vias and stub samples
    obs_index = {}

    def obs_near(x, y, reach):
        out = []
        cell = 2.0
        for gx in range(int((x - reach) // cell), int((x + reach) // cell) + 1):
            for gy in range(int((y - reach) // cell), int((y + reach) // cell) + 1):
                out.extend(obs_index.get((gx, gy), ()))
        return out

    def add_obs(x, y, r, net):
        obstacles.append((x, y, r, net))
        cell = 2.0
        for gx in range(int((x - r) // cell), int((x + r) // cell) + 1):
            for gy in range(int((y - r) // cell), int((y + r) // cell) + 1):
                obs_index.setdefault((gx, gy), []).append((x, y, r, net))

    def disc_ok(cx, cy, r, net, own=None):
        rect = (cx - r, cy - r, cx + r, cy + r)
        if not in_board(rect) or rects_overlap(rect, keepout_rect(), 0.0):
            return False
        for x0, y0, x1, y1, pnet, pref, pnum in _near(pad_index, cx, cy, r + CLEAR):
            if pnet == net or (pref, pnum) == own:
                continue
            dx = max(x0 - cx, 0, cx - x1)
            dy = max(y0 - cy, 0, cy - y1)
            if (dx * dx + dy * dy) ** 0.5 < r + CLEAR:
                return False
        for x0, y0, x1, y1, pnet, pref, pnum in _near(pad_index, cx, cy, 2.5):
            # Deliberately not skipping `own` here: a hole is a hole, and a via
            # drilled 0.4mm from its own pad's drill is still a fab violation.
            hx, hy = (x0 + x1) / 2, (y0 + y1) / 2
            hr = drills.get((pref, pnum), 0.0) / 2
            if hr and ((cx - hx) ** 2 + (cy - hy) ** 2) ** 0.5 < hr + VIA_DRILL / 2 + HOLE_GAP:
                return False
        for ox, oy, orad, onet in obs_near(cx, cy, r + CLEAR + 0.6):
            dist = ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5
            # Same-net copper may touch, but two drilled holes may never sit
            # closer than the fab's hole-to-hole minimum however they are
            # wired. Skipping same-net items here put GND vias 0.48mm apart.
            if dist < VIA_DRILL + HOLE_GAP:
                return False
            if onet == net:
                continue
            if dist < r + orad + CLEAR:
                return False
        return True

    def stub_ok(x0, y0, x1, y1, net, own):
        n = max(2, int((((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5) / 0.15) + 1)
        for k in range(n + 1):
            f = k / n
            if not disc_ok(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f,
                           STUB_W / 2, net, own):
                return False
        return True

    targets = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() not in ("GND", "+3V3"):
                continue
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                # A plated through-hole pad already spans F.Cu..B.Cu and meets
                # its plane on the way through. Adding a bond via next to it
                # buys nothing and puts a second drill 0.4mm from the first.
                continue
            targets.append((fp.GetReference(), pad))

    def add_via(cx, cy, net, netname):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(vec(cx, cy))
        via.SetDrill(mm(VIA_DRILL))
        via.SetWidth(mm(VIA_D))
        via.SetNet(net)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(via)
        add_obs(cx, cy, VIA_D / 2, netname)

    placed, failed = 0, []
    for ref, pad in targets:
        p = pad.GetPosition()
        px, py = p.x / MM, p.y / MM
        netname = pad.GetNetname()
        want = region_of(px, py)
        bb = pad.GetBoundingBox()
        pw, ph = bb.GetWidth() / MM, bb.GetHeight() / MM

        # Large exposed pads get a via array inside the pad, which is what a
        # thermal pad wants anyway; no stub is involved.
        if pw >= 2.0 and ph >= 2.0:
            for ox in (-pw / 4, pw / 4):
                for oy in (-ph / 4, ph / 4):
                    add_via(px + ox, py + oy, pad.GetNet(), netname)
            placed += 1
            continue

        # Pads that already sit within 2mm of a same-net via do not need one
        # of their own: the local pour reaches them over a distance where it
        # cannot be pinched off. This covers the twelve 0.6mm GND pads packed
        # at 0.7mm pitch around the module's thermal pad, where no via fits at
        # all. DRC's connectivity check is the arbiter, not this heuristic.
        if any(onet == netname and ((px - ox) ** 2 + (py - oy) ** 2) ** 0.5 < 2.0
               for ox, oy, orad, onet in obs_near(px, py, 2.5)):
            placed += 1
            continue

        spot = None
        for r in [x * 0.05 for x in range(8, 101)]:     # 0.4 .. 5.0mm
            for k in range(36):
                a = 2 * math.pi * k / 36
                cx, cy = px + r * math.cos(a), py + r * math.sin(a)
                if region_of(cx, cy) != want:
                    continue
                if not disc_ok(cx, cy, VIA_D / 2, netname, (ref, pad.GetNumber())):
                    continue
                if not stub_ok(px, py, cx, cy, netname, (ref, pad.GetNumber())):
                    continue
                spot = (cx, cy)
                break
            if spot:
                break
        if spot is None:
            failed.append("%s.%s (%s)" % (ref, pad.GetNumber(), netname))
            continue
        cx, cy = spot
        add_via(cx, cy, pad.GetNet(), netname)
        trk = pcbnew.PCB_TRACK(board)
        trk.SetStart(p)
        trk.SetEnd(vec(cx, cy))
        trk.SetWidth(mm(STUB_W))
        trk.SetLayer(pcbnew.F_Cu)
        trk.SetNet(pad.GetNet())
        board.Add(trk)
        n = max(2, int((((cx - px) ** 2 + (cy - py) ** 2) ** 0.5) / 0.3) + 1)
        for k in range(n + 1):
            f = k / n
            add_obs(px + (cx - px) * f, py + (cy - py) * f, STUB_W / 2, netname)
        placed += 1

    # GND stitching grid tying the F.Cu/B.Cu pours to the In1 plane.
    gnd = board.FindNet("GND")
    stitched = 0
    x = 2.0
    while x < FP.BOARD_W:
        y = 2.0
        while y < FP.BOARD_H:
            if disc_ok(x, y, VIA_D / 2, "GND"):
                add_via(x, y, gnd, "GND")
                stitched += 1
            y += 4.0
        x += 4.0

    pcbnew.SaveBoard(PCB, board)
    print("stage bond: %d/%d power pads bonded, %d GND stitching vias"
          % (placed, len(targets), stitched))
    if failed:
        print("  UNBONDED (%d): %s" % (len(failed), ", ".join(failed[:20])))
    return 1 if failed else 0


def stage_fill():
    """Refill every copper zone.

    Must run after any change to zone outlines, placement or copper. An
    unfilled zone makes DRC compare against the zone *outline* instead of the
    poured copper, which reports every via on the board as shorting the
    opposite plane.
    """
    board = pcbnew.LoadBoard(PCB)
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)
    print("stage fill: %d zones refilled" % board.GetAreaCount())
    return 0


def stage_polish():
    """Widen sub-minimum tracks left behind by the autorouter.

    The fine-pitch escapes under U5/U6/U7 legitimately need 0.15mm, which is
    the board minimum and comfortably inside JLCPCB's 4-layer capability
    (0.127mm). Anything thinner than that is a router artefact and gets
    widened; nothing else is touched. Blanket-widening every 0.15mm stub to
    0.20mm is what produced clearance violations against neighbouring pads.
    """
    board = pcbnew.LoadBoard(PCB)
    minw = mm(0.15)
    fixed = 0
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetWidth() < minw:
            t.SetWidth(minw)
            fixed += 1
    pcbnew.SaveBoard(PCB, board)
    print("stage polish: widened %d tracks to 0.20mm" % fixed)
    return 0



def stage_silk():
    """Make the silkscreen manufacturable, keeping as much of it as fits.

    91 parts on 60x80mm means a footprint's own silk outline routinely lands on
    the neighbouring part's pads. Rather than delete silkscreen wholesale, each
    item is tested and only the ones that actually collide are demoted to
    F.Fab, where they still show up in the assembly drawing.

    Reference designators get a spiral search for a legible spot first, because
    on a hand-assembled board they are worth keeping wherever possible; only
    those with nowhere to go are demoted.

    Everything here uses SetLayer rather than Remove: pcbnew's SWIG bindings
    stop resolving types for the rest of the process after any Remove().
    """
    board = pcbnew.LoadBoard(PCB)
    SILK_GAP = 0.16

    pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            pads.append((bb.GetX() / MM - SILK_GAP, bb.GetY() / MM - SILK_GAP,
                         (bb.GetX() + bb.GetWidth()) / MM + SILK_GAP,
                         (bb.GetY() + bb.GetHeight()) / MM + SILK_GAP))
    pad_index = _index(pads)

    edges = []
    pts = FP.OUTLINE
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        edges.append((min(a[0], b[0]) - 0.3, min(a[1], b[1]) - 0.3,
                      max(a[0], b[0]) + 0.3, max(a[1], b[1]) + 0.3))
    edge_index = _index(edges)

    def hits(rect):
        cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
        reach = max(rect[2] - rect[0], rect[3] - rect[1]) / 2 + 1.0
        for o in _near(pad_index, cx, cy, reach):
            if rects_overlap(rect, o, 0.0):
                return True
        for o in _near(edge_index, cx, cy, reach):
            if rects_overlap(rect, o, 0.0):
                return True
        return False

    # Custom footprint fields (MPN, Manufacturer, Rating, LCSC) are created on
    # F.SilkS by default and parked at the footprint origin, stacked on top of
    # each other and on the pads. They are not returned by GraphicalItems(), so
    # they are invisible to every other pass -- and they were the entire source
    # of the ~440 silkscreen violations: 91 footprints x 4 fields of text
    # nobody ever intended to print. They belong on F.Fab, hidden.
    hidden_fields = 0
    for fp in board.GetFootprints():
        for fld in fp.GetFields():
            if fld.GetName() in ("Reference", "Value"):
                continue
            fld.SetLayer(pcbnew.F_Fab)
            fld.SetVisible(False)
            hidden_fields += 1

    placed_text = []
    demoted_gfx = 0
    demoted_ref = 0
    kept_ref = 0

    # 1. Move every footprint silk graphic to F.Fab.
    #    At this density a part's own outline lands on its neighbour's pads far
    #    more often than not -- demoting only the colliding ones still left 199
    #    hits, because the survivors then collided with the designators. The
    #    outlines stay fully available on the fab layer for the assembly
    #    drawing; what a hand-assembler actually needs on the board is the
    #    designator, and that is what gets placed below.
    for fp in board.GetFootprints():
        for g in fp.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS:
                g.SetLayer(pcbnew.F_Fab)
                demoted_gfx += 1

    # 2. place reference designators, biggest parts first so the ones that
    #    matter most for orientation win the good spots
    def area(fp):
        r = abs_rect(fp)
        return (r[2] - r[0]) * (r[3] - r[1])

    for fp in sorted(board.GetFootprints(), key=area, reverse=True):
        ref = fp.Reference()
        if fp.GetReference().startswith("MH"):
            ref.SetLayer(pcbnew.F_Fab)
            continue
        ref.SetLayer(pcbnew.F_SilkS)
        ref.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
        ref.SetTextThickness(mm(0.12))
        w = len(fp.GetReference()) * 0.62 + 0.3
        h = 1.0
        r = abs_rect(fp)
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        spot = None
        for dist in [x * 0.25 for x in range(2, 25)]:
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0),
                           (-1, -1), (1, -1), (-1, 1), (1, 1)):
                n = (dx * dx + dy * dy) ** 0.5
                tx = cx + dx / n * (dist + (r[2] - r[0]) / 2)
                ty = cy + dy / n * (dist + (r[3] - r[1]) / 2)
                rect = (tx - w / 2, ty - h / 2, tx + w / 2, ty + h / 2)
                if rect[0] < 0.3 or rect[1] < 0.3:
                    continue
                if rect[2] > FP.BOARD_W - 0.3 or rect[3] > FP.BOARD_H - 0.3:
                    continue
                if hits(rect):
                    continue
                if any(rects_overlap(rect, o, 0.1) for o in placed_text):
                    continue
                spot = (tx, ty, rect)
                break
            if spot:
                break
        if spot is None:
            ref.SetLayer(pcbnew.F_Fab)
            demoted_ref += 1
        else:
            tx, ty, rect = spot
            ref.SetPosition(vec(tx, ty))
            placed_text.append(rect)
            kept_ref += 1

    # 3. values never go on silkscreen; they belong on the fab layer
    for fp in board.GetFootprints():
        fp.Value().SetLayer(pcbnew.F_Fab)

    pcbnew.SaveBoard(PCB, board)
    print("stage silk: %d refs on silkscreen, %d moved to F.Fab, %d graphics "
          "moved to F.Fab, %d metadata fields hidden onto F.Fab"
          % (kept_ref, demoted_ref, demoted_gfx, hidden_fields))
    return 0


def stage_close():
    """Delete dangling vias, then close whatever the autorouter left open.

    Freerouting reliably gets to within a couple of connections and leaves a
    few vias with copper on only one side. Both are finished here with a
    collision-checked A* over F.Cu/B.Cu with via transitions, which is
    deterministic -- re-running the stochastic autorouter until it happens to
    converge is not a repeatable build step.
    """
    import heapq
    board = pcbnew.LoadBoard(PCB)

    GRID = 0.1
    TRACK_W = 0.2
    NX = int(FP.BOARD_W / GRID) + 1
    NY = int(FP.BOARD_H / GRID) + 1
    LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]

    conn = board.GetConnectivity()
    # Both vias and the stubs that fed them: removing a via orphans its track,
    # so this runs until a pass finds nothing left to remove.
    doomed = [t for t in board.GetTracks()
              if conn.TestTrackEndpointDangling(t, False)]

    def blocked_map(netcode):
        """bytearray per layer: 1 = may not place copper of `netcode` here."""
        maps = [bytearray(NX * NY) for _ in LAYERS]
        margin = TRACK_W / 2 + CLEAR

        def mark(li, x0, y0, x1, y1):
            gx0 = max(0, int((x0) / GRID)); gx1 = min(NX - 1, int((x1) / GRID) + 1)
            gy0 = max(0, int((y0) / GRID)); gy1 = min(NY - 1, int((y1) / GRID) + 1)
            m = maps[li]
            for gy in range(gy0, gy1 + 1):
                base = gy * NX
                for gx in range(gx0, gx1 + 1):
                    m[base + gx] = 1

        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetCode() == netcode:
                    continue
                bb = pad.GetBoundingBox()
                x0, y0 = bb.GetX() / MM - margin, bb.GetY() / MM - margin
                x1 = (bb.GetX() + bb.GetWidth()) / MM + margin
                y1 = (bb.GetY() + bb.GetHeight()) / MM + margin
                for li, lay in enumerate(LAYERS):
                    if pad.IsOnLayer(lay):
                        mark(li, x0, y0, x1, y1)
        for tr in board.GetTracks():
            if tr in doomed or tr.GetNetCode() == netcode:
                continue
            if tr.GetClass() == "PCB_VIA":
                c = tr.GetPosition()
                r = tr.GetWidth() / 2 / MM + margin
                for li in range(len(LAYERS)):
                    mark(li, c.x / MM - r, c.y / MM - r, c.x / MM + r, c.y / MM + r)
            else:
                li = LAYERS.index(tr.GetLayer()) if tr.GetLayer() in LAYERS else None
                if li is None:
                    continue
                a, b = tr.GetStart(), tr.GetEnd()
                r = tr.GetWidth() / 2 / MM + margin
                n = max(2, int(((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5 / MM / GRID) + 1)
                for k in range(n + 1):
                    f = k / n
                    px = (a.x + (b.x - a.x) * f) / MM
                    py = (a.y + (b.y - a.y) * f) / MM
                    mark(li, px - r, py - r, px + r, py + r)
        # keep off the board edge and out of the antenna keepout
        kx0, ky0, kx1, ky1 = keepout_rect()
        for li in range(len(LAYERS)):
            mark(li, kx0, ky0, kx1, ky1)
        for gy in range(NY):
            for gx in range(NX):
                x, y = gx * GRID, gy * GRID
                if not in_board((x - 0.35, y - 0.35, x + 0.35, y + 0.35)):
                    for li in range(len(LAYERS)):
                        maps[li][gy * NX + gx] = 1
        return maps

    def astar(maps, starts, goals):
        goalset = set(goals)
        pq = []
        came = {}
        best = {}
        gx1, gy1, _ = goals[0]
        for s in starts:
            h = abs(s[0] - gx1) + abs(s[1] - gy1)
            heapq.heappush(pq, (h, 0, s))
            best[s] = 0
        while pq:
            f, g, cur = heapq.heappop(pq)
            if cur in goalset:
                path = [cur]
                while cur in came:
                    cur = came[cur]
                    path.append(cur)
                return path[::-1]
            if g > best.get(cur, 1 << 30):
                continue
            cx, cy, cl = cur
            for dx, dy, dl, cost in ((1, 0, 0, 10), (-1, 0, 0, 10), (0, 1, 0, 10),
                                     (0, -1, 0, 10), (0, 0, 1, 120)):
                nx_, ny_, nl = cx + dx, cy + dy, (cl ^ 1) if dl else cl
                if not (0 <= nx_ < NX and 0 <= ny_ < NY):
                    continue
                if maps[nl][ny_ * NX + nx_]:
                    continue
                ng = g + cost
                key = (nx_, ny_, nl)
                if ng < best.get(key, 1 << 30):
                    best[key] = ng
                    came[key] = cur
                    heapq.heappush(pq, (ng + abs(nx_ - gx1) + abs(ny_ - gy1), ng, key))
        return None

    def cells_of(item, netcode, maps):
        """Grid cells that already carry this net and are usable as endpoints."""
        out = []
        if hasattr(item, "GetBoundingBox") and item.GetClass() == "PAD":
            c = item.GetPosition()
            for li, lay in enumerate(LAYERS):
                if item.IsOnLayer(lay):
                    out.append((int(c.x / MM / GRID), int(c.y / MM / GRID), li))
        return out

    added = 0
    closed = 0
    for tr in doomed:
        board.Remove(tr)
    if doomed:
        pcbnew.SaveBoard(PCB, board)
        print("stage close: removed %d dangling vias" % len(doomed))
        sys.stdout.flush()
        os._exit(0)

    print("stage close: no dangling vias")
    return 0



def stage_join():
    """Close whatever connections the autorouter left open, with A*.

    Reads the current DRC report to find the unconnected items, then routes
    each one on a 0.1mm grid over F.Cu/B.Cu with via transitions, checked
    against every pad, track and via that is not on the target net. Vias are
    charged heavily so the result prefers staying on one layer.

    Deterministic by construction, which re-running a stochastic autorouter
    until it happens to converge is not.
    """
    import heapq
    import json as _json

    board = pcbnew.LoadBoard(PCB)
    rpt = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp", "drc.json")
    if not os.path.exists(rpt):
        rpt = "/tmp/drc.json"
    data = _json.load(open(rpt))

    GRID, TRACK_W, VIA_COST = 0.1, 0.2, 140
    NX = int(FP.BOARD_W / GRID) + 1
    NY = int(FP.BOARD_H / GRID) + 1
    LAYERS = [pcbnew.F_Cu, pcbnew.B_Cu]
    margin = TRACK_W / 2 + CLEAR

    def build_maps(netcode):
        maps = [bytearray(NX * NY) for _ in LAYERS]

        def mark(li, x0, y0, x1, y1):
            gx0 = max(0, int(x0 / GRID)); gx1 = min(NX - 1, int(x1 / GRID) + 1)
            gy0 = max(0, int(y0 / GRID)); gy1 = min(NY - 1, int(y1 / GRID) + 1)
            m = maps[li]
            for gy in range(gy0, gy1 + 1):
                base = gy * NX
                for gx in range(gx0, gx1 + 1):
                    m[base + gx] = 1

        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetCode() == netcode:
                    continue
                bb = pad.GetBoundingBox()
                for li, lay in enumerate(LAYERS):
                    if pad.IsOnLayer(lay):
                        mark(li, bb.GetX() / MM - margin, bb.GetY() / MM - margin,
                             (bb.GetX() + bb.GetWidth()) / MM + margin,
                             (bb.GetY() + bb.GetHeight()) / MM + margin)
        for tr in board.GetTracks():
            if tr.GetNetCode() == netcode:
                continue
            if tr.GetClass() == "PCB_VIA":
                c = tr.GetPosition(); r = tr.GetWidth() / 2 / MM + margin
                for li in range(len(LAYERS)):
                    mark(li, c.x / MM - r, c.y / MM - r, c.x / MM + r, c.y / MM + r)
            else:
                if tr.GetLayer() not in LAYERS:
                    continue
                li = LAYERS.index(tr.GetLayer())
                a, b = tr.GetStart(), tr.GetEnd()
                r = tr.GetWidth() / 2 / MM + margin
                n = max(2, int((((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5) / MM / GRID) + 1)
                for k in range(n + 1):
                    f = k / n
                    px = (a.x + (b.x - a.x) * f) / MM
                    py = (a.y + (b.y - a.y) * f) / MM
                    mark(li, px - r, py - r, px + r, py + r)
        kx0, ky0, kx1, ky1 = keepout_rect()
        for li in range(len(LAYERS)):
            mark(li, kx0, ky0, kx1, ky1)
        for gy in range(NY):
            y = gy * GRID
            for gx in range(NX):
                x = gx * GRID
                if not in_board((x - 0.3, y - 0.3, x + 0.3, y + 0.3)):
                    for li in range(len(LAYERS)):
                        maps[li][gy * NX + gx] = 1
        return maps

    def astar(maps, start, goals):
        gset = set(goals)
        pq = [(0, 0, start)]
        came, best = {}, {start: 0}
        while pq:
            f, g, cur = heapq.heappop(pq)
            if cur in gset:
                path = [cur]
                while cur in came:
                    cur = came[cur]; path.append(cur)
                return path[::-1]
            if g > best.get(cur, 1 << 30):
                continue
            cx, cy, cl = cur
            for dx, dy, dl, cost in ((1, 0, 0, 10), (-1, 0, 0, 10), (0, 1, 0, 10),
                                     (0, -1, 0, 10), (0, 0, 1, VIA_COST)):
                nx_, ny_, nl = cx + dx, cy + dy, (cl ^ 1) if dl else cl
                if not (0 <= nx_ < NX and 0 <= ny_ < NY):
                    continue
                if maps[nl][ny_ * NX + nx_]:
                    continue
                ng = g + cost
                key = (nx_, ny_, nl)
                if ng < best.get(key, 1 << 30):
                    best[key] = ng; came[key] = cur
                    heapq.heappush(pq, (ng, ng, key))
        return None

    def cell(x, y, li):
        return (int(round(x / GRID)), int(round(y / GRID)), li)

    # Collect the open connections the DRC report named.
    jobs = []
    for v in data.get("unconnected_items", []):
        its = v.get("items", [])
        if len(its) < 2:
            continue
        a, b = its[0], its[1]
        jobs.append((a, b))

    done = 0
    for a, b in jobs:
        # find the net from the pad description "... [NETNAME] of REF ..."
        m = re.search(r"\[([^\]]+)\]", a.get("description", ""))
        if not m:
            continue
        netname = m.group(1)
        net = board.FindNet(netname)
        if net is None:
            continue
        netcode = net.GetNetCode()
        ax, ay = a["pos"]["x"], a["pos"]["y"]

        maps = build_maps(netcode)

        # Goal = every grid cell already carrying this net. Aiming at a single
        # reported coordinate is fragile: a track's GetPosition() is one end of
        # it, not the nearest point, so a perfectly reachable net looks
        # unreachable. Rasterise the whole net instead.
        goals = set()

        def add_goal_rect(li, x0, y0, x1, y1):
            for gy in range(max(0, int(y0 / GRID)), min(NY - 1, int(y1 / GRID) + 1) + 1):
                for gx in range(max(0, int(x0 / GRID)), min(NX - 1, int(x1 / GRID) + 1) + 1):
                    goals.add((gx, gy, li))

        for tr in board.GetTracks():
            if tr.GetNetCode() != netcode:
                continue
            if tr.GetClass() == "PCB_VIA":
                c = tr.GetPosition(); r = tr.GetWidth() / 2 / MM
                for li in range(len(LAYERS)):
                    add_goal_rect(li, c.x / MM - r, c.y / MM - r, c.x / MM + r, c.y / MM + r)
            elif tr.GetLayer() in LAYERS:
                li = LAYERS.index(tr.GetLayer())
                a2, b2 = tr.GetStart(), tr.GetEnd()
                r = tr.GetWidth() / 2 / MM
                n = max(2, int((((a2.x - b2.x) ** 2 + (a2.y - b2.y) ** 2) ** 0.5) / MM / GRID) + 1)
                for k in range(n + 1):
                    f = k / n
                    px = (a2.x + (b2.x - a2.x) * f) / MM
                    py = (a2.y + (b2.y - a2.y) * f) / MM
                    add_goal_rect(li, px - r, py - r, px + r, py + r)
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetCode() != netcode:
                    continue
                if abs(pad.GetPosition().x / MM - ax) < 0.05 and abs(pad.GetPosition().y / MM - ay) < 0.05:
                    continue
                bb = pad.GetBoundingBox()
                for li, lay in enumerate(LAYERS):
                    if pad.IsOnLayer(lay):
                        add_goal_rect(li, bb.GetX() / MM, bb.GetY() / MM,
                                      (bb.GetX() + bb.GetWidth()) / MM,
                                      (bb.GetY() + bb.GetHeight()) / MM)
        goals = [g for g in goals if 0 <= g[0] < NX and 0 <= g[1] < NY]
        start = cell(ax, ay, 0)
        for li in range(len(LAYERS)):
            maps[li][start[1] * NX + start[0]] = 0
        for g in goals:
            if 0 <= g[0] < NX and 0 <= g[1] < NY:
                maps[g[2]][g[1] * NX + g[0]] = 0

        gs = set(goals)
        free_start = not maps[0][start[1] * NX + start[0]]
        free_goals = sum(1 for g in gs if not maps[g[2]][g[1] * NX + g[0]])
        path = astar(maps, start, list(gs))
        if path is None:
            print("  A* failed for %s: start=%s free=%s, %d goal cells (%d free)"
                  % (netname, start, free_start, len(gs), free_goals))
            continue

        # emit tracks + vias
        run = [path[0]]
        for node in path[1:]:
            if node[2] != run[-1][2]:
                _emit_run(board, run, net, GRID, LAYERS, TRACK_W)
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(vec(node[0] * GRID, node[1] * GRID))
                via.SetDrill(mm(VIA_DRILL)); via.SetWidth(mm(VIA_D))
                via.SetNet(net); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                board.Add(via)
                run = [node]
            else:
                run.append(node)
        _emit_run(board, run, net, GRID, LAYERS, TRACK_W)
        done += 1
        print("  closed %s with %d grid steps" % (netname, len(path)))

    pcbnew.SaveBoard(PCB, board)
    print("stage join: closed %d/%d open connections" % (done, len(jobs)))
    return 0


def _emit_run(board, run, net, GRID, LAYERS, TRACK_W):
    """Collapse a same-layer cell run into straight track segments."""
    if len(run) < 2:
        return
    pts = [run[0]]
    for i in range(1, len(run) - 1):
        ax, ay, _ = run[i - 1]; bx, by, _ = run[i]; cx, cy, _ = run[i + 1]
        if (bx - ax, by - ay) != (cx - bx, cy - by):
            pts.append(run[i])
    pts.append(run[-1])
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(vec(a[0] * GRID, a[1] * GRID))
        tr.SetEnd(vec(b[0] * GRID, b[1] * GRID))
        tr.SetWidth(mm(TRACK_W))
        tr.SetLayer(LAYERS[a[2]])
        tr.SetNet(net)
        board.Add(tr)


STAGES = {"strip": stage_strip, "silk": stage_silk, "close": stage_close, "join": stage_join, "outline": stage_outline, "polish": stage_polish,
          "build": stage_build, "bond": stage_bond, "fill": stage_fill}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "build"
    if which not in STAGES:
        raise SystemExit("usage: gen_pcb.py {%s}" % "|".join(STAGES))
    sys.exit(STAGES[which]())
