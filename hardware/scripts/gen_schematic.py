#!/usr/bin/env python3
"""Generate hardware/kicad/wisp.kicad_sch from wisp_netlist.py.

Usage:  python3 hardware/scripts/gen_schematic.py

Connectivity is expressed with labels rather than drawn wires: every pin gets
a short stub and a label carrying its net name. That is electrically identical
to a drawn net and it keeps the generator independent of symbol geometry, so
swapping a part cannot silently disconnect something.

Before writing anything the generator checks that

  * every lib_id resolves in a symbol library,
  * every footprint file actually exists,
  * every (ref, pin) named in NETS exists on that part, and
  * every pin of every part is claimed by exactly one net or by NO_CONNECT.

Any failure aborts without touching the schematic.
"""

import os
import re
import sys
import uuid as _uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
KICAD_SHARE = "/Applications/KiCad/KiCad.app/Contents/SharedSupport"
SYM_DIRS = [os.path.join(KICAD_SHARE, "symbols"), os.path.join(ROOT, "hardware", "kicad")]
FP_DIRS = [os.path.join(KICAD_SHARE, "footprints"), os.path.join(ROOT, "hardware", "kicad")]
OUT = os.path.join(ROOT, "hardware", "kicad", "wisp.kicad_sch")

sys.path.insert(0, HERE)
import wisp_netlist as D  # noqa: E402

SHEET_UUID = "16790539-5274-46cb-b845-34aaaf8d75b9"  # keep stable across regens


# --------------------------------------------------------------------------
# tiny s-expression reader / writer
# --------------------------------------------------------------------------

def parse(text, start=0):
    """Parse one s-expression starting at `start`. Returns (node, next_index)."""
    i = start
    n = len(text)
    while i < n and text[i] in " \t\r\n":
        i += 1
    if text[i] != "(":
        raise ValueError("expected ( at %d" % i)
    i += 1
    out = []
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "(":
            node, i = parse(text, i)
            out.append(node)
        elif c == ")":
            return out, i + 1
        elif c == '"':
            j = i + 1
            buf = []
            while text[j] != '"' or text[j - 1] == "\\":
                buf.append(text[j])
                j += 1
            out.append(('"', "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in " \t\r\n()":
                j += 1
            out.append(text[i:j])
            i = j
    raise ValueError("unterminated s-expression")


def ser(node, indent=0):
    pad = "\t" * indent
    if isinstance(node, tuple):
        return '"%s"' % node[1]
    if isinstance(node, str):
        return node
    if not node:
        return "()"
    head = node[0]
    simple = all(not isinstance(x, list) for x in node)
    if simple:
        return "(" + " ".join(ser(x) for x in node) + ")"
    parts = ["(" + (ser(head) if not isinstance(head, list) else "")]
    body = node[1:] if not isinstance(head, list) else node
    inline = []
    rest = []
    for x in body:
        (rest if isinstance(x, list) else inline).append(x)
    if inline:
        parts[0] += " " + " ".join(ser(x) for x in inline)
    chunks = [parts[0]]
    for x in rest:
        chunks.append("\n" + pad + "\t" + ser(x, indent + 1))
    chunks.append("\n" + pad + ")")
    return "".join(chunks)


def find(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def first(node, key):
    f = find(node, key)
    return f[0] if f else None


def sval(x):
    return x[1] if isinstance(x, tuple) else x


# --------------------------------------------------------------------------
# symbol libraries
# --------------------------------------------------------------------------

_libcache = {}


def load_lib(libname):
    if libname in _libcache:
        return _libcache[libname]
    for d in SYM_DIRS:
        p = os.path.join(d, libname + ".kicad_sym")
        if os.path.exists(p):
            root, _ = parse(open(p).read())
            syms = {}
            for s in find(root, "symbol"):
                syms[sval(s[1])] = s
            _libcache[libname] = syms
            return syms
    raise SystemExit("symbol library not found: %s" % libname)


def get_symbol(lib_id):
    libname, name = lib_id.split(":", 1)
    syms = load_lib(libname)
    if name not in syms:
        raise SystemExit("symbol %s not in library %s" % (name, libname))
    sym = syms[name]
    ext = first(sym, "extends")
    if ext is None:
        return sym, name, syms
    parent = sval(ext[1])
    if parent not in syms:
        raise SystemExit("parent symbol %s missing for %s" % (parent, lib_id))
    return sym, parent, syms


def symbol_pins(lib_id):
    """Return [(number, name, x, y, angle, ptype)] in symbol coordinates."""
    sym, geom_name, syms = get_symbol(lib_id)
    geom = syms[geom_name]
    pins = []
    units = set()
    for sub in find(geom, "symbol"):
        subname = sval(sub[1])
        m = re.match(r".*_(\d+)_(\d+)$", subname)
        if m:
            units.add(int(m.group(1)))
        for p in find(sub, "pin"):
            ptype = p[1]
            at = first(p, "at")
            x, y = float(at[1]), float(at[2])
            ang = float(at[3]) if len(at) > 3 else 0.0
            nm = sval(first(p, "name")[1])
            num = sval(first(p, "number")[1])
            pins.append((num, nm, x, y, ang, ptype))
    real_units = {u for u in units if u > 0}
    if len(real_units) > 1:
        raise SystemExit("%s has %d units; generator handles single-unit symbols only"
                         % (lib_id, len(real_units)))
    return pins


def flattened_symbol(lib_id):
    """Build the lib_symbols entry: parent geometry carrying child properties.

    Everything that is not a property or a unit sub-symbol is copied verbatim
    and in order. That matters for markers like (power) on the power-rail
    symbols: dropping it makes KiCad stop treating them as power sources, which
    surfaces later as a bogus "power pin not driven" ERC error rather than as
    anything that points at this function.
    """
    sym, geom_name, syms = get_symbol(lib_id)
    geom = syms[geom_name]

    child_props = {sval(p[1]): p for p in find(sym, "property")}
    child_base = lib_id.split(":", 1)[1]

    out = ["symbol", ('"', lib_id)]
    emitted = set()
    for node in geom[2:]:
        if not isinstance(node, list):
            continue
        key = node[0]
        if key == "extends":
            continue
        if key == "property":
            pname = sval(node[1])
            out.append(child_props.get(pname, node))
            emitted.add(pname)
        elif key == "symbol":
            sub = list(node)
            sub[1] = ('"', sval(sub[1]).replace(geom_name, child_base, 1))
            out.append(sub)
        else:
            out.append(node)
    for pname, prop in child_props.items():
        if pname not in emitted:
            out.insert(2, prop)
    return out


def find_footprint(fp_id):
    libname, name = fp_id.split(":", 1)
    for d in FP_DIRS:
        p = os.path.join(d, libname + ".pretty", name + ".kicad_mod")
        if os.path.exists(p):
            return p
    return None


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def pin_endpoint(sx, sy, px, py):
    """Symbol-local pin position -> absolute schematic position (Y is flipped)."""
    return (round(sx + px, 4), round(sy - py, 4))


def outward(angle):
    """Unit vector pointing away from the symbol body, in schematic coords."""
    a = int(angle) % 360
    return {0: (-1.0, 0.0), 90: (0.0, 1.0), 180: (1.0, 0.0), 270: (0.0, -1.0)}[a]


def uid():
    return str(_uuid.uuid4())


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def main():
    parts = {p["ref"]: p for p in D.PARTS}
    if len(parts) != len(D.PARTS):
        raise SystemExit("duplicate designator in PARTS")

    pinmap = {}
    for ref, p in parts.items():
        pins = symbol_pins(p["lib"])
        pinmap[ref] = pins
        fp = find_footprint(p["fp"])
        if fp is None:
            raise SystemExit("footprint not found: %s (%s)" % (p["fp"], ref))

    # ---- validation ------------------------------------------------------
    errors = []
    claimed = {}
    for net, conns in D.NETS.items():
        for ref, pin in conns:
            if ref not in parts:
                errors.append("net %s references unknown part %s" % (net, ref))
                continue
            nums = {n for n, *_ in pinmap[ref]}
            if pin not in nums:
                errors.append("net %s: %s has no pin %r (has %s)"
                              % (net, ref, pin, ",".join(sorted(nums))))
                continue
            key = (ref, pin)
            if key in claimed:
                errors.append("%s.%s is on both %s and %s"
                              % (ref, pin, claimed[key], net))
            claimed[key] = net
    for ref, pin in D.NO_CONNECT:
        if ref not in parts:
            errors.append("NO_CONNECT references unknown part %s" % ref)
            continue
        if (ref, pin) in claimed:
            errors.append("%s.%s is both wired and NO_CONNECT" % (ref, pin))
        claimed[(ref, pin)] = None
    for ref, pins in pinmap.items():
        for num, nm, *_ in pins:
            if (ref, num) not in claimed:
                errors.append("unclaimed pin %s.%s (%s) -- add to NETS or NO_CONNECT"
                              % (ref, num, nm))
    if errors:
        print("REFUSING TO GENERATE -- %d problem(s):" % len(errors))
        for e in sorted(set(errors)):
            print("  " + e)
        return 1

    # ---- layout ----------------------------------------------------------
    GROUP_ORDER = ["usb", "buck", "mcu", "led", "sensor", "tp", "exp", "mech"]
    GROUP_TITLE = {
        "usb": "USB-C input, ESD protection, PTC fuse",
        "buck": "5V -> 3V3 buck regulator",
        "mcu": "ESP32-S3-WROOM-1 (native USB, no UART bridge)",
        "led": "Status LED (WS2812B on ~4.3V) + power-on LED",
        "sensor": "Sensors: SCD41 CO2/T/RH, SGP41 VOC/NOx, BME280 pressure, BH1750 lux",
        "tp": "Test points",
        "exp": "DNP expansion footprints (see docs/hardware-expandability.md)",
        "mech": "Mounting holes",
    }
    COL_W, X0, Y0, YMAX, GAP = 57.0, 25.0, 30.0, 540.0, 6.0

    placed, col, ycur = {}, 0, Y0
    colgroup = {}
    for g in GROUP_ORDER:
        members = [p for p in D.PARTS if p.get("group") == g]
        if not members:
            continue
        if ycur > Y0:
            col += 1
            ycur = Y0
        colgroup.setdefault(col, g)
        for p in members:
            pins = pinmap[p["ref"]]
            ys = [py for _, _, _, py, _, _ in pins] or [0]
            h = (max(ys) - min(ys)) + 14.0
            if ycur + h > YMAX:
                col += 1
                ycur = Y0
                colgroup.setdefault(col, g)
            # Snap the placement origin to the 1.27mm connection grid. Library
            # pin coordinates are all multiples of 1.27, so a snapped origin
            # puts every pin -- and therefore every stub end and label -- on
            # grid. Without this KiCad reports one endpoint_off_grid warning
            # per pin, which buries every real finding.
            cx = round((X0 + col * COL_W) / 1.27) * 1.27
            cy = round((ycur + h / 2.0) / 1.27) * 1.27
            placed[p["ref"]] = (round(cx, 4), round(cy, 4))
            ycur += h + GAP

    # ---- emit ------------------------------------------------------------
    L = []
    L.append("(kicad_sch (version 20251024) (generator wisp)")
    L.append("")
    L.append("  (uuid %s)" % SHEET_UUID)
    L.append("")
    L.append('  (paper "A1")')
    L.append("")

    lib_ids = sorted({p["lib"] for p in D.PARTS})
    for n in D.POWER_ANCHORS:
        lib_ids.append("power:" + n)
    lib_ids.append("power:PWR_FLAG")
    lib_ids = sorted(set(lib_ids))

    L.append("  (lib_symbols")
    for lid in lib_ids:
        L.append(re.sub(r"^", "    ", ser(flattened_symbol(lid), 2), flags=re.M))
    L.append("  )")
    L.append("")

    def emit_symbol(lib_id, ref, val, x, y, props, dnp=False, in_bom=True,
                    hide_ref=False, hide_val=False):
        pins = symbol_pins(lib_id)
        s = []
        s.append('  (symbol (lib_id "%s") (at %g %g 0) (unit 1)' % (lib_id, x, y))
        s.append("    (in_bom %s) (on_board yes) (dnp %s)"
                 % ("yes" if in_bom else "no", "yes" if dnp else "no"))
        s.append("    (uuid %s)" % uid())
        ys = [py for _, _, _, py, _, _ in pins] or [0]
        top = y - (max(ys) + 3.0)
        bot = y - (min(ys) - 3.0)
        s.append('    (property "Reference" "%s" (at %g %g 0)' % (ref, x - 1.5, top))
        s.append("      (effects (font (size 1.27 1.27))%s)"
                 % (" hide" if hide_ref else ""))
        s.append("    )")
        s.append('    (property "Value" "%s" (at %g %g 0)' % (val, x - 1.5, bot))
        s.append("      (effects (font (size 1.27 1.27))%s)"
                 % (" hide" if hide_val else ""))
        s.append("    )")
        for k, v in props:
            s.append('    (property "%s" "%s" (at %g %g 0)' % (k, v, x, y))
            s.append("      (effects (font (size 1.27 1.27)) hide)")
            s.append("    )")
        for num, *_ in pins:
            s.append('    (pin "%s" (uuid %s))' % (num, uid()))
        s.append("    (instances")
        s.append('      (project "wisp"')
        s.append('        (path "/%s"' % SHEET_UUID)
        s.append('          (reference "%s") (unit 1)' % ref)
        s.append("        )")
        s.append("      )")
        s.append("    )")
        s.append("  )")
        return "\n".join(s)

    def emit_stub(px, py, ox, oy, net):
        ex, ey = round(px + ox * 2.54, 4), round(py + oy * 2.54, 4)
        w = []
        w.append("  (wire (pts (xy %g %g) (xy %g %g))" % (px, py, ex, ey))
        w.append("    (stroke (width 0) (type default))")
        w.append("    (uuid %s)" % uid())
        w.append("  )")
        just = "right" if ox < 0 else "left"
        rot = 0 if ox != 0 else 90
        w.append('  (label "%s" (at %g %g %d)' % (net, ex, ey, rot))
        w.append("    (effects (font (size 1.27 1.27)) (justify %s bottom))" % just)
        w.append("    (uuid %s)" % uid())
        w.append("  )")
        return "\n".join(w)

    # group captions
    for c, g in sorted(colgroup.items()):
        L.append('  (text "%s" (at %g %g 0)' % (GROUP_TITLE[g], X0 + c * COL_W - 12, 20))
        L.append("    (effects (font (size 1.6 1.6) (thickness 0.3) bold) (justify left))")
        L.append("    (uuid %s)" % uid())
        L.append("  )")
    L.append("")

    # parts
    for p in D.PARTS:
        ref = p["ref"]
        x, y = placed[ref]
        props = [("Footprint", p["fp"])]
        for key, name in (("mpn", "MPN"), ("mfr", "Manufacturer"),
                          ("rating", "Rating"), ("lcsc", "LCSC")):
            if p.get(key):
                props.append((name, p[key]))
        L.append(emit_symbol(p["lib"], ref, p["val"], x, y, props,
                             dnp=p.get("dnp", False),
                             in_bom=not p.get("exclude_bom", False)))
        for num, nm, px, py, ang, _ in pinmap[ref]:
            net = claimed.get((ref, num))
            ax, ay = pin_endpoint(x, y, px, py)
            ox, oy = outward(ang)
            if net is None:
                L.append("  (no_connect (at %g %g) (uuid %s))" % (ax, ay, uid()))
            else:
                L.append(emit_stub(ax, ay, ox, oy, net))
    L.append("")

    # power anchors + PWR_FLAGs, parked in their own column
    anchor_x = round((X0 + (max(colgroup) + 1) * COL_W) / 1.27) * 1.27
    ay = round(Y0 / 1.27) * 1.27
    for n in D.POWER_ANCHORS:
        lib_id = "power:" + n
        pins = symbol_pins(lib_id)
        L.append(emit_symbol(lib_id, "#PWR%03d" % (D.POWER_ANCHORS.index(n) + 1),
                             n, anchor_x, ay, [("Footprint", "")],
                             in_bom=False, hide_ref=True, hide_val=True))
        for num, nm, px, py, ang, _ in pins:
            px_, py_ = pin_endpoint(anchor_x, ay, px, py)
            ox, oy = outward(ang)
            L.append(emit_stub(px_, py_, ox, oy, n))
        ay += 30.48
    for i, n in enumerate(D.PWR_FLAGS):
        pins = symbol_pins("power:PWR_FLAG")
        L.append(emit_symbol("power:PWR_FLAG", "#FLG%03d" % (i + 1), "PWR_FLAG",
                             anchor_x, ay, [("Footprint", "")],
                             in_bom=False, hide_ref=True, hide_val=True))
        for num, nm, px, py, ang, _ in pins:
            px_, py_ = pin_endpoint(anchor_x, ay, px, py)
            ox, oy = outward(ang)
            L.append(emit_stub(px_, py_, ox, oy, n))
        ay += 30.48

    L.append("")
    L.append("  (sheet_instances")
    L.append('    (path "/" (page "1"))')
    L.append("  )")
    L.append(")")

    text = "\n".join(L) + "\n"
    open(OUT, "w").write(text)

    nets = len(D.NETS)
    npins = sum(len(v) for v in pinmap.values())
    print("wrote %s" % os.path.relpath(OUT, ROOT))
    print("  %d parts, %d pins, %d nets, %d no-connects"
          % (len(D.PARTS), npins, nets, len(D.NO_CONNECT)))
    print("  parens balanced: %s" % (text.count("(") == text.count(")")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
