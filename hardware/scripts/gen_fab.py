#!/usr/bin/env python3
"""Export fab outputs: Gerbers, drill files, BOM and CPL.

    python3 hardware/scripts/gen_fab.py

Gerbers and drill come from kicad-cli. The BOM is built from wisp_netlist.py
rather than from KiCad's BOM exporter, so it carries the MPN / Manufacturer /
Rating columns that the design actually specifies.

Only the layers a fab needs are exported. Documentation layers (Courtyard,
Fab, Adhesive, Margin, User_*) are deliberately left out: shipping them in the
fab folder risks the fab's layer auto-detection counting them as copper, and
on a 4-layer board that is an expensive mistake.
"""

import csv
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PCB = os.path.join(ROOT, "hardware", "kicad", "wisp.kicad_pcb")
FAB = os.path.join(ROOT, "hardware", "fab")
GERB = os.path.join(FAB, "gerbers")

sys.path.insert(0, HERE)
import wisp_netlist as D  # noqa: E402

LAYERS = ("F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,"
          "F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts")


def run(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit("failed: %s" % " ".join(args))
    return r


def collapse(refs):
    """C1,C2,C3,C8 -> 'C1-C3,C8'"""
    import re
    def key(r):
        m = re.match(r"([A-Za-z]+)(\d+)", r)
        return (m.group(1), int(m.group(2)))
    refs = sorted(refs, key=key)
    out, run_ = [], []

    def flush():
        if not run_:
            return
        if len(run_) >= 3:
            out.append("%s-%s" % (run_[0], run_[-1]))
        else:
            out.extend(run_)
        run_.clear()

    for r in refs:
        if run_ and key(r)[0] == key(run_[-1])[0] and key(r)[1] == key(run_[-1])[1] + 1:
            run_.append(r)
        else:
            flush()
            run_.append(r)
    flush()
    return ",".join(out)


def write_bom(path, parts, with_dnp):
    groups = {}
    for p in parts:
        if not with_dnp and p.get("dnp"):
            continue
        if p.get("exclude_bom"):
            continue
        k = (p["val"], p["fp"], p.get("mpn", ""), p.get("mfr", ""),
             p.get("rating", ""), p.get("lcsc", ""), bool(p.get("dnp")))
        groups.setdefault(k, []).append(p["ref"])
    rows = []
    for (val, fp, mpn, mfr, rating, lcsc, dnp), refs in groups.items():
        rows.append({
            "Designator": collapse(refs),
            "Qty": len(refs),
            "Value": val,
            "Footprint": fp,
            "MPN": mpn,
            "Manufacturer": mfr,
            "Rating": rating,
            "LCSC": lcsc,
            "DNP": "DNP" if dnp else "",
        })
    rows.sort(key=lambda r: r["Designator"])
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(rows)
    return len(rows), sum(r["Qty"] for r in rows)


def main():
    os.makedirs(GERB, exist_ok=True)
    for f in os.listdir(GERB):
        os.remove(os.path.join(GERB, f))

    run("kicad-cli", "pcb", "export", "gerbers", "--layers", LAYERS,
        "-o", GERB + os.sep, PCB)
    run("kicad-cli", "pcb", "export", "drill", "--format", "excellon",
        "--excellon-separate-th", "--generate-map", "--map-format", "gerberx2",
        "-o", GERB + os.sep, PCB)
    run("kicad-cli", "pcb", "export", "pos", "--format", "csv", "--units", "mm",
        "--side", "front", "--exclude-dnp",
        "-o", os.path.join(FAB, "wisp-cpl-prototype.csv"), PCB)

    n_full, q_full = write_bom(os.path.join(FAB, "wisp-bom-full.csv"),
                               D.PARTS, with_dnp=True)
    n_proto, q_proto = write_bom(os.path.join(FAB, "wisp-bom-prototype.csv"),
                                 D.PARTS, with_dnp=False)

    with open(os.path.join(FAB, "wisp-cpl-prototype.csv")) as f:
        cpl = sum(1 for _ in f) - 1

    print("gerbers + drill: %d files" % len(os.listdir(GERB)))
    print("BOM full:      %d lines / %d parts" % (n_full, q_full))
    print("BOM prototype: %d lines / %d parts" % (n_proto, q_proto))
    print("CPL:           %d placements" % cpl)

    job = os.path.join(GERB, "wisp-job.gbrjob")
    if os.path.exists(job):
        import json
        j = json.load(open(job))
        gp = j.get("GeneralSpecs", {})
        print("gbrjob LayerNumber: %s" % gp.get("LayerNumber"))
        for fl in j.get("FilesAttributes", []):
            fn = fl.get("FileFunction", "")
            if fn.startswith("Copper"):
                print("   %s" % fn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
