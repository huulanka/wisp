"""Wisp Rev B floorplan.

Placement is by function, not by arithmetic. Two kinds of entry:

FIXED   explicit (x, y, rotation) for the parts whose position is a design
        decision -- the module, the regulator loop, the connectors on the
        board edges, the sensors on the thermally isolated tab.

ANCHOR  "put this part as close as possible to that pad". Used for every
        decoupling capacitor, pull-up and series resistor. gen_pcb.py runs a
        collision-checked spiral search outwards from the anchor pad, so the
        parts land 1.8-3.0mm from the pin they actually serve instead of
        wherever a global autoplacer felt like putting them. Rev A shipped
        its decoupling on the opposite copper layer 8-20mm away, which is
        what this mechanism exists to prevent.

Board is 60 x 80 mm. Origin is the top-left corner, +y is down.

  y 0.0-7.5    antenna keepout, all four copper layers, full board width
  y 0.75-26.3  U3 ESP32-S3-WROOM-1, antenna flush with the top edge
  y 8-30       left: EN/IO0 support, reset+boot buttons, status LED
               right: J2/J3 headers on the right edge
  y 30-46      USB-C (left edge) -> U8 ESD -> F1 -> U2 buck -> L1
  y 44-48      test point grid
  y 48-62      left: small headers; right: J4/J9; buzzer
  y 63.5-80    sensor tab, milled free on three sides
"""

# ref -> (x, y, rotation_deg)
FIXED = {
    # ---- MCU. Body spans y 0.75..26.25, so the antenna (top 6mm of the
    # module) sits inside the keepout and radiates off the board edge.
    "U3": (30.0, 13.5, 0),

    # ---- buttons and status LED, left of the module
    "SW1": (5.5, 24.0, 0),
    "SW2": (13.0, 24.0, 0),
    "D1": (7.0, 12.0, 0),
    "D12": (14.5, 30.0, 0),

    # ---- right-edge expansion headers
    "J2": (56.5, 14.0, 0),
    "J3": (56.5, 26.0, 0),
    "J4": (56.5, 38.0, 0),
    "J9": (56.5, 52.0, 0),

    # ---- USB-C in, ESD, fuse, buck. Kept on one line so the SW node and
    # the input/output caps stay in one tight loop next to the regulator.
    "J1": (5.5, 40.0, 0),
    "U8": (14.0, 36.5, 0),
    "F1": (22.0, 33.0, 0),
    "U2": (29.0, 33.0, 0),
    "L1": (35.0, 33.0, 0),

    # ---- test point grid. 4.0mm pitch, not 3.2mm: these pads sit in the
    # busiest part of the board and at tighter spacing the router boxes one of
    # them in completely, leaving a net that no amount of post-processing can
    # reach. The extra millimetre buys every pad an escape lane.
    "TP1": (22.0, 43.0, 0), "TP2": (26.0, 43.0, 0), "TP3": (30.0, 43.0, 0),
    "TP4": (34.0, 43.0, 0), "TP5": (38.0, 43.0, 0), "TP6": (42.0, 43.0, 0),
    "TP7": (22.0, 48.0, 0), "TP8": (26.0, 48.0, 0), "TP9": (30.0, 48.0, 0),
    "TP10": (34.0, 48.0, 0), "TP11": (38.0, 48.0, 0), "TP12": (42.0, 48.0, 0),
    "TP13": (46.0, 48.0, 0),

    # ---- left-edge small headers
    # Pin headers are anchored at pin 1, not at their centre, so a 1x08 header
    # placed at y extends ~20mm *downwards* from there. Spacing these by their
    # centres is how J5/J7 and J9/MH4 first ended up overlapping.
    "J5": (4.5, 48.0, 0),
    "J6": (12.0, 48.0, 0),
    "J7": (4.5, 57.0, 0),
    "J8": (12.0, 57.0, 0),

    # ---- buzzer
    "BZ1": (30.0, 55.5, 0),

    # ---- sensor tab (x 21.5..46.5, y 63.5..80). SCD41 is the big one and
    # takes the left half; the three small sensors share the right column.
    # The SGP41 is put at the far end from the SCD41: it runs a hotplate,
    # and the SCD41 is the part whose temperature reading must stay honest.
    "U4": (27.0, 70.5, 0),
    "U7": (44.5, 65.0, 0),
    "U6": (44.5, 70.0, 0),
    "U5": (44.5, 76.5, 0),

    # ---- mounting holes, in the four corners
    "MH1": (3.5, 4.0, 0),
    "MH2": (56.5, 4.0, 0),
    "MH3": (4.0, 76.0, 0),
    "MH4": (56.0, 76.0, 0),
}

# ref -> (anchor_ref, anchor_pad, preferred_direction)
# direction is a hint for the search: "any", "left", "right", "up", "down".
ANCHOR = {
    # ESP32-S3 supply. Espressif wants 10uF + 100nF at the 3V3 pin; Rev A had
    # the 100nF right but the nearest bulk was 26mm away at the regulator.
    "C2":  ("U3", "2", "left"),
    "C12": ("U3", "2", "left"),
    "R3":  ("U3", "3", "left"),
    "C4":  ("U3", "3", "left"),
    "R4":  ("U3", "27", "right"),

    # buck loop
    "C5":  ("U2", "3", "up"),
    "C7":  ("U2", "6", "up"),
    "C6":  ("L1", "2", "down"),
    "C14": ("L1", "2", "down"),
    "C3":  ("L1", "2", "right"),

    # status LED
    "R7":  ("D1", "4", "right"),
    "R20": ("D1", "4", "right"),
    "C17": ("D1", "1", "left"),
    "D11": ("D1", "1", "up"),
    "R21": ("D12", "2", "left"),

    # USB-C
    "R1":  ("J1", "A5", "right"),
    "R2":  ("J1", "B5", "right"),

    # I2C pull-ups, kept near the bus master end
    "R8":  ("U3", "12", "right"),
    "R9":  ("U3", "17", "right"),

    # sensors
    "C9":  ("U4", "7", "down"),
    "C13": ("U4", "7", "down"),
    "R22": ("U5", "1", "any"),
    "C20": ("U5", "1", "any"),
    "C21": ("U5", "5", "any"),
    "C10": ("U6", "1", "any"),
    "C18": ("U7", "8", "any"),
    "C19": ("U7", "6", "any"),

    # expansion support parts, each next to the header it belongs to
    "R10": ("J2", "2", "left"),
    "R11": ("J2", "3", "left"),
    "D2":  ("J2", "2", "left"),
    "D3":  ("J2", "3", "left"),
    "Q3":  ("J5", "2", "right"),
    "R12": ("J5", "2", "right"),
    "R18": ("J5", "2", "right"),
    "D4":  ("J5", "1", "right"),   # SMA, needs the open area mid-board
    "D5":  ("J6", "1", "right"),
    "R15": ("J6", "1", "right"),
    "D6":  ("J7", "3", "right"),
    "R14": ("J7", "3", "right"),
    "R16": ("J7", "3", "right"),
    "D13": ("J8", "3", "right"),
    "R17": ("J8", "3", "right"),
    "C16": ("J8", "3", "right"),
    "D7":  ("J9", "3", "left"),
    "D8":  ("J9", "4", "left"),
    "D9":  ("J9", "5", "left"),
    "D10": ("J9", "6", "left"),
    "D14": ("J9", "7", "left"),
    "D15": ("J9", "8", "left"),
    "Q4":  ("BZ1", "2", "left"),
    "R13": ("BZ1", "2", "left"),
}

# Antenna keepout, all four copper layers. Rev A cleared exactly the module
# width (x 18..42), leaving GND pour flush with the antenna on both sides.
# This clears ~9mm either side instead. It stops short of the board corners so
# the mounting holes still have somewhere to live -- the keepout forbids pads,
# and an M3 hole is a pad.
ANTENNA_KEEPOUT = [(8.0, 0.0), (52.0, 0.0), (52.0, 7.5), (8.0, 7.5)]

BOARD_W, BOARD_H = 60.0, 80.0

# ---------------------------------------------------------------------------
# Board outline, as one closed loop of segments.
#
# The sensor tab is milled free on three sides by a 1.5mm slot and hangs off a
# 9mm neck. Rev A's tab was 25 x 16.5mm, which the SCD41 alone fills to 40%;
# there was no room left to put that sensor's own 100nF and 10uF next to it,
# and the placer pushed them 9mm away across the slot. The tab is 29.5 x 18mm
# here so every sensor keeps its decoupling on its own side of the slot.
#
#   left slot   x 18.0 .. 19.5, y 60.5 .. 80
#   right slot  x 49.0 .. 50.5, y 62.0 .. 80
#   top slot    y 60.5 .. 62.0, x 18.0 .. 40.0
#   neck        x 40.0 .. 49.0
OUTLINE = [
    (0.0, 0.0), (60.0, 0.0), (60.0, 80.0),
    (50.5, 80.0), (50.5, 62.0), (49.0, 62.0), (49.0, 80.0),
    (19.5, 80.0), (19.5, 62.0), (40.0, 62.0), (40.0, 60.5),
    (18.0, 60.5), (18.0, 80.0), (0.0, 80.0),
]

# Sensor tab, for the placement checker.
TAB = (19.5, 62.0, 49.0, 80.0)

# Left and right main-board columns beside the slot.
LEFT_COL_X = 18.0
RIGHT_COL_X = 50.5
SLOT_TOP_Y = 60.5
