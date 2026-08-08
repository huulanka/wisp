"""Wisp Rev B — the design, as data.

This module is the single source of truth for what is on the board. It is
consumed by gen_schematic.py, which turns it into hardware/kicad/wisp.kicad_sch.

Editing this file and re-running gen_schematic.py is the supported way to
change the circuit. Do not hand-edit the generated .kicad_sch: it will be
overwritten. (Rev A's schematic was produced by a throwaway script that was
never committed, which is why nobody could tell how it had been built.)

Designator gaps are intentional. C1, C8, C11, C15, C19, R5, R6, R19, Q1, Q2
and U1 belonged to the Rev A CH340C USB-UART bridge and its auto-reset
circuit, or to the BME680. The ESP32-S3 has native USB, so that whole block
is gone; the numbers are left retired rather than reused so that Rev A and
Rev B designators never mean two different things.
"""

# --------------------------------------------------------------------------
# Parts
#
# ref, lib_id, value, footprint, dnp, mpn, manufacturer, rating, group
# --------------------------------------------------------------------------

R0805 = "Resistor_SMD:R_0805_2012Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
SOD882 = "Diode_SMD:D_SOD-882"
SOD123 = "Diode_SMD:D_SOD-123"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOT236 = "Package_TO_SOT_SMD:SOT-23-6"
TP = "TestPoint:TestPoint_Pad_1.5x1.5mm"
HDR = "Connector_PinHeader_2.54mm:PinHeader_1x%02d_P2.54mm_Vertical"

PARTS = [
    # ---- USB-C input and protection -------------------------------------
    dict(ref="J1", lib="Connector:USB_C_Receptacle_USB2.0_16P", val="USB-C",
         fp="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
         mpn="TYPE-C-31-M-12", mfr="HRO", lcsc="C165948", group="usb"),
    dict(ref="R1", lib="Device:R", val="5.1k", fp=R0805,
         mpn="RC0805FR-075K1L", mfr="Yageo", lcsc="C84375", rating="1%, 1/8W", group="usb"),
    dict(ref="R2", lib="Device:R", val="5.1k", fp=R0805,
         mpn="RC0805FR-075K1L", mfr="Yageo", lcsc="C84375", rating="1%, 1/8W", group="usb"),
    dict(ref="U8", lib="Power_Protection:USBLC6-2SC6", val="USBLC6-2SC6", fp=SOT236,
         mpn="USBLC6-2SC6", mfr="STMicroelectronics", lcsc="C7519",
         rating="ESD array, D+/D-/VBUS", group="usb"),
    dict(ref="C5", lib="Device:C", val="10uF", fp=C0805,
         mpn="CL21A106KOQNNNE", mfr="Samsung", lcsc="C1713", rating="25V X5R", group="usb"),
    dict(ref="F1", lib="Device:Polyfuse", val="500mA", fp="Fuse:Fuse_1812_4532Metric",
         mpn="MF-MSMF050-2", mfr="Bourns", lcsc="C17313",
         rating="PTC, 500mA hold, 6V", group="usb"),

    # ---- Buck regulator 5V -> 3V3 ---------------------------------------
    dict(ref="U2", lib="Regulator_Switching:AP63203WU", val="AP63203WU-7",
         fp="Package_TO_SOT_SMD:TSOT-23-6",
         mpn="AP63203WU-7", mfr="Diodes Incorporated", lcsc="C780769",
         rating="2A sync buck, fixed 3.3V", group="buck"),
    dict(ref="L1", lib="Device:L", val="2.2uH", fp="Inductor_SMD:L_1210_3225Metric",
         mpn="SRN3015-2R2M", mfr="Bourns", lcsc="C2041716",
         rating="Isat >= 1.5A, DCR < 100mOhm", group="buck"),
    dict(ref="C7", lib="Device:C", val="100nF", fp=C0805,
         mpn="CL21B104KBCNNNC", mfr="Samsung", lcsc="C1711", rating="50V X7R",
         group="buck"),  # BST cap, datasheet-specified value
    dict(ref="C6", lib="Device:C", val="22uF", fp=C0805,
         mpn="CL21A226MOQNNNE", mfr="Samsung", lcsc="C98190", rating="16V X5R", group="buck"),
    dict(ref="C14", lib="Device:C", val="22uF", fp=C0805,
         mpn="CL21A226MOQNNNE", mfr="Samsung", lcsc="C98190", rating="16V X5R", group="buck"),
    dict(ref="C3", lib="Device:C", val="10uF", fp=C0805,
         mpn="CL21A106KOQNNNE", mfr="Samsung", lcsc="C1713", rating="16V X5R", group="buck"),

    # ---- MCU -------------------------------------------------------------
    dict(ref="U3", lib="RF_Module:ESP32-S3-WROOM-1", val="ESP32-S3-WROOM-1-N8",
         fp="wisp:ESP32-S3-WROOM-1",
         mpn="ESP32-S3-WROOM-1-N8", mfr="Espressif", lcsc="C2913198",
         rating="8MB flash, no PSRAM", group="mcu"),
    dict(ref="C2", lib="Device:C", val="100nF", fp=C0805,
         mpn="CL21B104KBCNNNC", mfr="Samsung", lcsc="C1711", rating="50V X7R", group="mcu"),
    dict(ref="C12", lib="Device:C", val="10uF", fp=C0805,
         mpn="CL21A106KOQNNNE", mfr="Samsung", lcsc="C1713", rating="16V X5R", group="mcu"),
    dict(ref="R3", lib="Device:R", val="10k", fp=R0805,
         mpn="RC0805FR-0710KL", mfr="Yageo", lcsc="C84376", rating="1%, 1/8W", group="mcu"),
    dict(ref="C4", lib="Device:C", val="1uF", fp=C0805,
         mpn="CL21A105KBFNNNE", mfr="Samsung", rating="25V X5R", group="mcu"),
    dict(ref="R4", lib="Device:R", val="10k", fp=R0805,
         mpn="RC0805FR-0710KL", mfr="Yageo", lcsc="C84376", rating="1%, 1/8W", group="mcu"),
    dict(ref="SW1", lib="Switch:SW_Push", val="RESET",
         fp="Button_Switch_SMD:SW_SPST_PTS810",
         mpn="PTS810 SJM 250 SMTR LFS", mfr="C&K", lcsc="C116501", group="mcu"),
    dict(ref="SW2", lib="Switch:SW_Push", val="BOOT",
         fp="Button_Switch_SMD:SW_SPST_PTS810",
         mpn="PTS810 SJM 250 SMTR LFS", mfr="C&K", lcsc="C116501", group="mcu"),

    # ---- Status LED ------------------------------------------------------
    dict(ref="D1", lib="LED:WS2812B", val="WS2812B",
         fp="LED_SMD:LED_WS2812B_PLCC4_5.0x5.0mm_P3.2mm",
         mpn="WS2812B", mfr="Worldsemi", rating="VDD 3.5-5.3V", group="led"),
    dict(ref="D11", lib="Diode:1N4148W", val="1N4148W", fp=SOD123,
         mpn="1N4148W-7-F", mfr="Diodes Incorporated", lcsc="C83528",
         rating="drops +5V_EXT to ~4.3V for D1", group="led"),
    dict(ref="C17", lib="Device:C", val="100nF", fp=C0805,
         mpn="CL21B104KBCNNNC", mfr="Samsung", lcsc="C1711", rating="50V X7R", group="led"),
    dict(ref="R7", lib="Device:R", val="330R", fp=R0805,
         mpn="RC0805FR-07330RL", mfr="Yageo", lcsc="C105878", rating="1%, 1/8W", group="led"),
    dict(ref="R20", lib="Device:R", val="10k", fp=R0805,
         mpn="RC0805FR-0710KL", mfr="Yageo", lcsc="C84376", rating="1%, 1/8W", group="led"),
    dict(ref="D12", lib="Device:LED", val="GREEN",
         fp="LED_SMD:LED_0805_2012Metric",
         mpn="150080GS75000", mfr="Wurth", rating="green, power-on indicator",
         group="led"),
    dict(ref="R21", lib="Device:R", val="2.2k", fp=R0805,
         mpn="RC0805FR-072K2L", mfr="Yageo", lcsc="C114561", rating="1%, 1/8W", group="led"),

    # ---- Sensors ---------------------------------------------------------
    dict(ref="U4", lib="Sensor_Gas:SCD41-D-R2", val="SCD41-D-R2",
         fp="Sensor:Sensirion_SCD4x-1EP_10.1x10.1mm_P1.25mm_EP4.8x4.8mm",
         mpn="SCD41-D-R2", mfr="Sensirion", rating="CO2/T/RH, I2C 0x62",
         group="sensor"),
    dict(ref="C9", lib="Device:C", val="100nF", fp=C0805,
         mpn="CL21B104KBCNNNC", mfr="Samsung", lcsc="C1711", rating="50V X7R", group="sensor"),
    dict(ref="C13", lib="Device:C", val="10uF", fp=C0805,
         mpn="CL21A106KOQNNNE", mfr="Samsung", lcsc="C1713", rating="16V X5R", group="sensor"),

    dict(ref="U5", lib="wisp:SGP41", val="SGP41",
         fp="wisp:Sensirion_DFN-6-1EP_2.44x2.44mm_P0.8mm_EP1.25x1.7mm",
         mpn="SGP41-D-R4", mfr="Sensirion", rating="VOC/NOx, I2C 0x59",
         group="sensor"),
    dict(ref="R22", lib="Device:R", val="4.7R", fp=R0805,
         mpn="RC0805FR-074R7L", mfr="Yageo", lcsc="C137513",
         rating="1%, SGP41 VDD RC element", group="sensor"),
    dict(ref="C20", lib="Device:C", val="1uF", fp=C0805,
         mpn="CL21A105KBFNNNE", mfr="Samsung", rating="25V X5R", group="sensor"),
    dict(ref="C21", lib="Device:C", val="1uF", fp=C0805,
         mpn="CL21A105KBFNNNE", mfr="Samsung", rating="25V X5R", group="sensor"),

    dict(ref="U6", lib="wisp:BH1750FVI-TR", val="BH1750FVI-TR",
         fp="wisp:BH1750FVI-TR_WSOF6",
         mpn="BH1750FVI-TR", mfr="ROHM", lcsc="C78960",
         rating="lux, I2C 0x23", group="sensor"),
    dict(ref="C10", lib="Device:C", val="100nF", fp=C0805,
         mpn="CL21B104KBCNNNC", mfr="Samsung", lcsc="C1711", rating="50V X7R", group="sensor"),

    dict(ref="U7", lib="Sensor:BME280", val="BME280",
         fp="Package_LGA:Bosch_LGA-8_2.5x2.5mm_P0.65mm_ClockwisePinNumbering",
         mpn="BME280", mfr="Bosch Sensortec", lcsc="C92489",
         rating="pressure/T/RH, I2C 0x76", group="sensor"),
    dict(ref="C18", lib="Device:C", val="100nF", fp=C0805,
         mpn="CL21B104KBCNNNC", mfr="Samsung", lcsc="C1711", rating="50V X7R", group="sensor"),
    dict(ref="C19", lib="Device:C", val="100nF", fp=C0805,
         mpn="CL21B104KBCNNNC", mfr="Samsung", lcsc="C1711", rating="50V X7R", group="sensor"),

    dict(ref="R8", lib="Device:R", val="4.7k", fp=R0805,
         mpn="RC0805FR-074K7L", mfr="Yageo", lcsc="C60816", rating="1%, I2C pull-up",
         group="sensor"),
    dict(ref="R9", lib="Device:R", val="4.7k", fp=R0805,
         mpn="RC0805FR-074K7L", mfr="Yageo", lcsc="C60816", rating="1%, I2C pull-up",
         group="sensor"),

    # ---- Test points -----------------------------------------------------
    dict(ref="TP1", lib="Connector:TestPoint", val="JTAG_MTDI", fp=TP, group="tp"),
    dict(ref="TP2", lib="Connector:TestPoint", val="JTAG_MTCK", fp=TP, group="tp"),
    dict(ref="TP3", lib="Connector:TestPoint", val="JTAG_MTMS", fp=TP, group="tp"),
    dict(ref="TP4", lib="Connector:TestPoint", val="JTAG_MTDO", fp=TP, group="tp"),
    dict(ref="TP5", lib="Connector:TestPoint", val="+3V3", fp=TP, group="tp"),
    dict(ref="TP6", lib="Connector:TestPoint", val="GND", fp=TP, group="tp"),
    dict(ref="TP7", lib="Connector:TestPoint", val="SDA", fp=TP, group="tp"),
    dict(ref="TP8", lib="Connector:TestPoint", val="SCL", fp=TP, group="tp"),
    dict(ref="TP9", lib="Connector:TestPoint", val="EN", fp=TP, group="tp"),
    dict(ref="TP10", lib="Connector:TestPoint", val="IO0", fp=TP, group="tp"),
    dict(ref="TP11", lib="Connector:TestPoint", val="UART0_TX", fp=TP, group="tp"),
    dict(ref="TP12", lib="Connector:TestPoint", val="UART0_RX", fp=TP, group="tp"),
    dict(ref="TP13", lib="Connector:TestPoint", val="LED_DOUT", fp=TP, group="tp"),

    # ---- Expansion: second I2C ------------------------------------------
    dict(ref="J2", lib="Connector_Generic:Conn_01x04", val="Second I2C Bus",
         fp=HDR % 4, dnp=True, group="exp"),
    dict(ref="R10", lib="Device:R", val="4.7k", fp=R0805, dnp=True,
         mpn="RC0805FR-074K7L", mfr="Yageo", lcsc="C60816", rating="1%", group="exp"),
    dict(ref="R11", lib="Device:R", val="4.7k", fp=R0805, dnp=True,
         mpn="RC0805FR-074K7L", mfr="Yageo", lcsc="C60816", rating="1%", group="exp"),
    dict(ref="D2", lib="Diode:PESD5V0L1UL", val="PESD5V0L1UL", fp=SOD882,
         mpn="PESD5V0L1UL", mfr="Nexperia", lcsc="C552556", group="exp"),
    dict(ref="D3", lib="Diode:PESD5V0L1UL", val="PESD5V0L1UL", fp=SOD882,
         mpn="PESD5V0L1UL", mfr="Nexperia", lcsc="C552556", group="exp"),

    # ---- Expansion: mmWave UART -----------------------------------------
    dict(ref="J3", lib="Connector_Generic:Conn_01x04", val="mmWave UART (LD2410)",
         fp=HDR % 4, dnp=True, group="exp"),

    # ---- Expansion: I2S mic ---------------------------------------------
    dict(ref="J4", lib="Connector_Generic:Conn_01x05", val="I2S Mic (INMP441)",
         fp=HDR % 5, dnp=True, group="exp"),

    # ---- Expansion: switched DC output -----------------------------------
    dict(ref="J5", lib="Connector_Generic:Conn_01x03", val="Switched DC Output",
         fp=HDR % 3, dnp=True, group="exp"),
    dict(ref="Q3", lib="Transistor_FET:AO3400A", val="AO3400A", fp=SOT23, dnp=True,
         mpn="AO3400A", mfr="Alpha & Omega", lcsc="C20917",
         rating="logic-level N-FET, 5.7A, Vgs(th) < 1.4V", group="exp"),
    dict(ref="R12", lib="Device:R", val="100R", fp=R0805, dnp=True,
         mpn="RC0805FR-07100RL", mfr="Yageo", lcsc="C105577", rating="1%, gate series",
         group="exp"),
    dict(ref="R18", lib="Device:R", val="100k", fp=R0805, dnp=True,
         mpn="RC0805FR-07100KL", mfr="Yageo", lcsc="C96346", rating="1%, gate pull-down",
         group="exp"),
    dict(ref="D4", lib="Diode:SS14", val="SS14", fp="Diode_SMD:D_SMA", dnp=True,
         mpn="SS14", mfr="Diodes Incorporated",
         rating="Schottky 1A/40V, flyback for the switched output",
         group="exp"),

    # ---- Expansion: reed / 1-Wire / analog --------------------------------
    dict(ref="J6", lib="Connector_Generic:Conn_01x02", val="Reed/Hall Contact",
         fp=HDR % 2, dnp=True, group="exp"),
    dict(ref="D5", lib="Diode:PESD5V0L1UL", val="PESD5V0L1UL", fp=SOD882,
         mpn="PESD5V0L1UL", mfr="Nexperia", lcsc="C552556", group="exp"),
    dict(ref="R15", lib="Device:R", val="220R", fp=R0805,
         mpn="RC0805FR-07220RL", mfr="Yageo", lcsc="C114519", rating="1%, ESD series",
         group="exp"),

    dict(ref="J7", lib="Connector_Generic:Conn_01x03", val="1-Wire Bus",
         fp=HDR % 3, dnp=True, group="exp"),
    dict(ref="D6", lib="Diode:PESD5V0L1UL", val="PESD5V0L1UL", fp=SOD882,
         mpn="PESD5V0L1UL", mfr="Nexperia", lcsc="C552556", group="exp"),
    dict(ref="R14", lib="Device:R", val="4.7k", fp=R0805, dnp=True,
         mpn="RC0805FR-074K7L", mfr="Yageo", lcsc="C60816", rating="1%, 1-Wire pull-up",
         group="exp"),
    dict(ref="R16", lib="Device:R", val="220R", fp=R0805,
         mpn="RC0805FR-07220RL", mfr="Yageo", lcsc="C114519", rating="1%, ESD series",
         group="exp"),

    dict(ref="J8", lib="Connector_Generic:Conn_01x03", val="Analog Sensor Pad",
         fp=HDR % 3, dnp=True, group="exp"),
    dict(ref="D13", lib="Diode:PESD5V0L1UL", val="PESD5V0L1UL", fp=SOD882,
         mpn="PESD5V0L1UL", mfr="Nexperia", lcsc="C552556", group="exp"),
    dict(ref="R17", lib="Device:R", val="220R", fp=R0805,
         mpn="RC0805FR-07220RL", mfr="Yageo", lcsc="C114519", rating="1%, ESD series",
         group="exp"),
    dict(ref="C16", lib="Device:C", val="100nF", fp=C0805,
         mpn="CL21B104KBCNNNC", mfr="Samsung", lcsc="C1711", rating="50V X7R, ADC filter",
         group="exp"),

    # ---- Expansion: generic header ---------------------------------------
    dict(ref="J9", lib="Connector_Generic:Conn_01x08", val="Expansion Header",
         fp=HDR % 8, dnp=True, group="exp"),
    dict(ref="D7", lib="Diode:PESD5V0L1UL", val="PESD5V0L1UL", fp=SOD882,
         mpn="PESD5V0L1UL", mfr="Nexperia", lcsc="C552556", group="exp"),
    dict(ref="D8", lib="Diode:PESD5V0L1UL", val="PESD5V0L1UL", fp=SOD882,
         mpn="PESD5V0L1UL", mfr="Nexperia", lcsc="C552556", group="exp"),
    dict(ref="D9", lib="Diode:PESD5V0L1UL", val="PESD5V0L1UL", fp=SOD882,
         mpn="PESD5V0L1UL", mfr="Nexperia", lcsc="C552556", group="exp"),
    dict(ref="D10", lib="Diode:PESD5V0L1UL", val="PESD5V0L1UL", fp=SOD882,
         mpn="PESD5V0L1UL", mfr="Nexperia", lcsc="C552556", group="exp"),
    dict(ref="D14", lib="Diode:PESD5V0L1UL", val="PESD5V0L1UL", fp=SOD882,
         mpn="PESD5V0L1UL", mfr="Nexperia", lcsc="C552556", group="exp"),
    dict(ref="D15", lib="Diode:PESD5V0L1UL", val="PESD5V0L1UL", fp=SOD882,
         mpn="PESD5V0L1UL", mfr="Nexperia", lcsc="C552556", group="exp"),

    # ---- Buzzer ----------------------------------------------------------
    dict(ref="BZ1", lib="Device:Buzzer", val="Buzzer",
         fp="Buzzer_Beeper:Buzzer_CUI_CPT-9019S-SMT", dnp=True,
         mpn="CPT-9019S-SMT", mfr="CUI Devices", lcsc="C95163",
         rating="piezo transducer, external drive", group="exp"),
    dict(ref="Q4", lib="Transistor_BJT:MMBT3904", val="MMBT3904", fp=SOT23,
         dnp=True, mpn="MMBT3904", mfr="onsemi", lcsc="C81464", group="exp"),
    dict(ref="R13", lib="Device:R", val="1k", fp=R0805, dnp=True,
         mpn="RC0805FR-071KL", mfr="Yageo", lcsc="C95781", rating="1%, base series",
         group="exp"),

    # ---- Mechanical ------------------------------------------------------
    dict(ref="MH1", lib="Mechanical:MountingHole", val="MountingHole_M3",
         fp="MountingHole:MountingHole_3.2mm_M3", group="mech", exclude_bom=True),
    dict(ref="MH2", lib="Mechanical:MountingHole", val="MountingHole_M3",
         fp="MountingHole:MountingHole_3.2mm_M3", group="mech", exclude_bom=True),
    dict(ref="MH3", lib="Mechanical:MountingHole", val="MountingHole_M3",
         fp="MountingHole:MountingHole_3.2mm_M3", group="mech", exclude_bom=True),
    dict(ref="MH4", lib="Mechanical:MountingHole", val="MountingHole_M3",
         fp="MountingHole:MountingHole_3.2mm_M3", group="mech", exclude_bom=True),
]

# --------------------------------------------------------------------------
# Nets
#
# Power nets (GND / +3V3 / +5V) are additionally anchored by one power symbol
# each, so KiCad names them globally without a sheet-path prefix. The PCB's
# copper planes are bound to the names "GND" and "+3V3" -- renaming them here
# would silently orphan both planes.
# --------------------------------------------------------------------------

NETS = {
    "GND": [
        ("C2", "2"), ("C3", "2"), ("C4", "2"), ("C5", "2"), ("C6", "2"),
        ("C9", "2"), ("C10", "2"), ("C12", "2"), ("C13", "2"), ("C14", "2"),
        ("C16", "2"), ("C17", "2"), ("C18", "2"), ("C19", "2"), ("C20", "2"),
        ("C21", "2"),
        ("D1", "3"), ("D12", "1"),
        ("D2", "2"), ("D3", "2"), ("D5", "2"), ("D6", "2"), ("D7", "2"),
        ("D8", "2"), ("D9", "2"), ("D10", "2"), ("D13", "2"), ("D14", "2"),
        ("D15", "2"),
        ("J1", "A1"), ("J1", "A12"), ("J1", "B1"), ("J1", "B12"), ("J1", "SH"),
        ("J2", "4"), ("J3", "2"), ("J4", "2"), ("J5", "3"), ("J6", "2"),
        ("J7", "2"), ("J8", "2"), ("J9", "1"),
        ("Q3", "2"), ("Q4", "2"),
        ("R1", "2"), ("R2", "2"), ("R18", "2"), ("R20", "2"),
        ("SW1", "2"), ("SW2", "2"),
        ("TP6", "1"),
        ("U2", "4"),
        ("U3", "1"), ("U3", "40"), ("U3", "41"),
        ("U4", "6"), ("U4", "20"), ("U4", "21"),
        ("U5", "2"), ("U5", "4"), ("U5", "7"),
        ("U6", "2"), ("U6", "3"),
        ("U7", "1"), ("U7", "5"), ("U7", "7"),
        ("U8", "2"),
    ],
    "+3V3": [
        ("C2", "1"), ("C3", "1"), ("C6", "1"), ("C9", "1"), ("C10", "1"),
        ("C12", "1"), ("C13", "1"), ("C14", "1"), ("C18", "1"), ("C19", "1"),
        ("C21", "1"),
        ("L1", "2"),
        ("R3", "1"), ("R4", "1"), ("R8", "1"), ("R9", "1"), ("R10", "1"),
        ("R11", "1"), ("R14", "1"), ("R21", "1"), ("R22", "1"),
        ("J2", "1"), ("J4", "1"), ("J7", "1"), ("J8", "1"), ("J9", "2"),
        ("TP5", "1"),
        ("U2", "1"),
        ("U3", "2"),
        ("U4", "7"), ("U4", "19"),
        ("U5", "5"),
        ("U6", "1"), ("U6", "5"),
        ("U7", "2"), ("U7", "6"), ("U7", "8"),
        ("BZ1", "1"),
    ],
    "+5V": [
        ("C5", "1"), ("F1", "1"),
        ("J1", "A4"), ("J1", "A9"), ("J1", "B4"), ("J1", "B9"),
        ("U2", "2"), ("U2", "3"), ("U8", "5"),
    ],

    # ---- local nets ------------------------------------------------------
    "+5V_EXT": [("F1", "2"), ("J3", "1"), ("J5", "1"), ("D4", "1"), ("D11", "2")],
    "LED_VCC": [("D11", "1"), ("D1", "1"), ("C17", "1")],
    "SGP_VDD": [("R22", "2"), ("U5", "1"), ("C20", "1")],

    "CC1": [("J1", "A5"), ("R1", "1")],
    "CC2": [("J1", "B5"), ("R2", "1")],
    "USB_DP": [("J1", "A6"), ("J1", "B6"), ("U8", "3"), ("U8", "4"), ("U3", "14")],
    "USB_DM": [("J1", "A7"), ("J1", "B7"), ("U8", "1"), ("U8", "6"), ("U3", "13")],

    "BUCK_SW": [("U2", "5"), ("L1", "1"), ("C7", "2")],
    "BUCK_BST": [("U2", "6"), ("C7", "1")],

    "EN": [("C4", "1"), ("R3", "2"), ("SW1", "1"), ("TP9", "1"), ("U3", "3")],
    "IO0": [("R4", "2"), ("SW2", "1"), ("TP10", "1"), ("U3", "27")],

    "SDA": [("R8", "2"), ("TP7", "1"), ("U3", "12"), ("U4", "10"), ("U5", "3"),
            ("U6", "4"), ("U7", "3")],
    "SCL": [("R9", "2"), ("TP8", "1"), ("U3", "17"), ("U4", "9"), ("U5", "6"),
            ("U6", "6"), ("U7", "4")],

    "LED_CTRL": [("U3", "7"), ("R7", "1"), ("R20", "1")],
    "LED_A": [("R7", "2"), ("D1", "4")],
    "LED_DOUT": [("D1", "2"), ("TP13", "1")],
    "PWR_LED": [("R21", "2"), ("D12", "2")],

    "BUZZER_CTRL": [("U3", "8"), ("R13", "1")],
    "BUZZER_BASE": [("R13", "2"), ("Q4", "1")],
    "BUZZER_COLLECTOR": [("Q4", "3"), ("BZ1", "2")],

    "SW_OUT_CTRL": [("U3", "9"), ("R12", "1")],
    "SW_OUT_GATE": [("R12", "2"), ("Q3", "1"), ("R18", "1")],
    "SW_GND": [("Q3", "3"), ("J5", "2"), ("D4", "2")],

    "SDA2": [("U3", "10"), ("R10", "2"), ("J2", "2"), ("D2", "1")],
    "SCL2": [("U3", "11"), ("R11", "2"), ("J2", "3"), ("D3", "1")],

    "MMWAVE_RX": [("U3", "18"), ("J3", "4")],
    "MMWAVE_TX": [("U3", "19"), ("J3", "3")],

    "MIC_SCK": [("U3", "20"), ("J4", "4")],
    "MIC_WS": [("U3", "21"), ("J4", "3")],
    "MIC_SD": [("U3", "22"), ("J4", "5")],

    "REED_EXT": [("J6", "1"), ("D5", "1"), ("R15", "1")],
    "REED_IN": [("R15", "2"), ("U3", "6")],

    "ONEWIRE_EXT": [("J7", "3"), ("D6", "1"), ("R14", "2"), ("R16", "1")],
    "ONEWIRE_DATA": [("R16", "2"), ("U3", "5")],

    "ADC_PAD_EXT": [("J8", "3"), ("D13", "1"), ("R17", "1")],
    "ADC_PAD": [("R17", "2"), ("U3", "4"), ("C16", "1")],

    "EXP_IO1": [("U3", "39"), ("J9", "3"), ("D7", "1")],
    "EXP_IO2": [("U3", "38"), ("J9", "4"), ("D8", "1")],
    "EXP_IO21": [("U3", "23"), ("J9", "5"), ("D9", "1")],
    "EXP_IO38": [("U3", "31"), ("J9", "6"), ("D10", "1")],
    "EXP_IO47": [("U3", "24"), ("J9", "7"), ("D14", "1")],
    "EXP_IO48": [("U3", "25"), ("J9", "8"), ("D15", "1")],

    "JTAG_MTCK": [("U3", "32"), ("TP2", "1")],
    "JTAG_MTDO": [("U3", "33"), ("TP4", "1")],
    "JTAG_MTDI": [("U3", "34"), ("TP1", "1")],
    "JTAG_MTMS": [("U3", "35"), ("TP3", "1")],

    "UART0_RX": [("U3", "36"), ("TP12", "1")],
    "UART0_TX": [("U3", "37"), ("TP11", "1")],
}

# Pins deliberately left open. Every pin of every part must appear either in
# NETS or here, or gen_schematic.py refuses to emit -- that check is what
# stops a forgotten pin from silently becoming an unrouted net later.
NO_CONNECT = [
    ("J1", "A8"), ("J1", "B8"),          # SBU1/SBU2, no alternate mode
    ("U3", "15"),                        # IO3   strapping (JTAG source select)
    ("U3", "16"),                        # IO46  strapping (ROM log), int. pull-down
    ("U3", "26"),                        # IO45  strapping (VDD_SPI), int. pull-down
    ("U3", "28"), ("U3", "29"), ("U3", "30"),  # IO35/36/37: octal PSRAM on -R8 parts
]

# Power-net anchors and ERC drivers.
POWER_ANCHORS = ["GND", "+3V3", "+5V"]
# Nets whose only source sits behind a passive element need an explicit ERC
# driver: LED_VCC is behind D11, SGP_VDD behind the SGP41's 4.7R RC element.
PWR_FLAGS = ["GND", "+3V3", "+5V", "LED_VCC", "SGP_VDD"]

PROTOTYPE_DNP_NOTE = (
    "Prototype build populates everything except the expansion headers and "
    "the parts that only serve them."
)
