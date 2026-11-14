"""後方コア PCB の部品とネット定義（docs/rear-pcb-design.md 準拠）。

回路図生成（gen_sch.py）と基板生成（gen_pcb.py）の唯一のデータソース。
pins の値は {シンボルのピン番号: ネット名}。記載のないピンは未接続（NC フラグ）。
"""

PROJECT = "rear-core-claude"

R0603 = "Resistor_SMD:R_0603_1608Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
SOD123 = "Diode_SMD:D_SOD-123"


def R(ref, value, n1, n2, lcsc="", group="", near=None):
    return dict(ref=ref, lib="Device:R", value=value, fp=R0603, lcsc=lcsc,
                pins={"1": n1, "2": n2}, group=group, near=near)


def C(ref, value, n1, n2, fp=C0603, lcsc="", group="", near=None):
    return dict(ref=ref, lib="Device:C", value=value, fp=fp, lcsc=lcsc,
                pins={"1": n1, "2": n2}, group=group, near=near)


def schottky(ref, k, a, group="", near=None):
    return dict(ref=ref, lib="Device:D_Schottky", value="B5819W", fp=SOD123,
                lcsc="C8598", pins={"1": k, "2": a}, group=group, near=near)


ESP_GND = ["1", "2", "11", "14"] + [str(n) for n in range(36, 54)]

PARTS = [
    # ---------------- 外部端子 ----------------
    dict(ref="J1", lib="Connector_Generic:Conn_01x04", value="TRUNK 12V/RS485",
         fp="Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical", lcsc="",
         pins={"1": "+12V_IN", "2": "GND", "3": "RS485_A", "4": "RS485_B"}, group="端子"),
    dict(ref="J2", lib="Connector_Generic:Conn_01x03", value="WS2812",
         fp="Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical", lcsc="",
         pins={"1": "+5V", "2": "LED_DATA_5V", "3": "GND"}, group="端子"),
    dict(ref="J3", lib="Connector_Generic:Conn_01x04", value="LASER L/R",
         fp="Connector_JST:JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical", lcsc="",
         pins={"1": "V_LASER", "2": "LASER_L-", "3": "V_LASER", "4": "LASER_R-"}, group="端子"),

    # ---------------- ① 電源: 入力保護 ----------------
    dict(ref="F1", lib="Device:Polyfuse", value="3A", fp="Fuse:Fuse_1812_4532Metric",
         lcsc="", pins={"1": "+12V_IN", "2": "12V_F"}, group="電源 入力保護", near=("J1", "1")),
    dict(ref="D1", lib="Diode:SS34", value="SS34", fp="Diode_SMD:D_SMA", lcsc="C8678",
         pins={"1": "+12V", "2": "12V_F"}, group="電源 入力保護", near=("F1", "2")),
    dict(ref="TVS1", lib="Device:D_Zener", value="SMBJ15A", fp="Diode_SMD:D_SMB",
         lcsc="C73385", pins={"1": "+12V", "2": "GND"}, group="電源 入力保護", near=("D1", "1")),
    C("C1", "22uF/25V", "+12V", "GND", fp=C1206, group="電源 入力保護", near=("U1", "3")),
    C("C2", "22uF/25V", "+12V", "GND", fp=C1206, group="電源 入力保護", near=("U1", "3")),
    C("C3", "100nF/50V", "+12V", "GND", lcsc="C14663", group="電源 入力保護", near=("U1", "3")),

    # ---------------- ① 電源: 12V→5V Buck ----------------
    dict(ref="U1", lib="Regulator_Switching:TPS54302", value="TPS54302DDCR",
         fp="Package_TO_SOT_SMD:SOT-23-6", lcsc="C311038",
         pins={"1": "GND", "2": "SW", "3": "+12V", "4": "FB", "6": "BST"},
         group="電源 12V→5V", near=(9.0, 30.0)),
    C("C4", "100nF", "BST", "SW", lcsc="C14663", group="電源 12V→5V", near=("U1", "6")),
    dict(ref="L1", lib="Device:L", value="4.7uH 4A", fp="Inductor_SMD:L_Bourns_SRN6045TA",
         lcsc="C408412", pins={"1": "SW", "2": "+5V"}, group="電源 12V→5V", near=("U1", "2")),
    R("R1", "75k 1%", "+5V", "FB", lcsc="C23242", group="電源 12V→5V", near=("U1", "4")),
    R("R2", "10k 1%", "FB", "GND", lcsc="C25804", group="電源 12V→5V", near=("U1", "4")),
    C("C5", "22uF/10V", "+5V", "GND", fp=C0805, lcsc="C45783", group="電源 12V→5V", near=("L1", "2")),
    C("C6", "22uF/10V", "+5V", "GND", fp=C0805, lcsc="C45783", group="電源 12V→5V", near=("L1", "2")),
    C("C7", "22uF/10V", "+5V", "GND", fp=C0805, lcsc="C45783", group="電源 12V→5V", near=("L1", "2")),
    dict(ref="C8", lib="Device:C_Polarized", value="220uF/10V", fp="Capacitor_SMD:CP_Elec_6.3x7.7",
         lcsc="", pins={"1": "+5V", "2": "GND"}, group="電源 12V→5V", near=("J2", "1")),

    # ---------------- ① 電源: OR + 3.3V LDO ----------------
    schottky("D2", "V5_LOGIC", "+5V", group="電源 3.3V", near=("U2", "1")),
    schottky("D3", "V5_LOGIC", "VBUS", group="電源 3.3V", near=("U2", "1")),
    dict(ref="U2", lib="Regulator_Linear:AP2112K-3.3", value="AP2112K-3.3",
         fp="Package_TO_SOT_SMD:SOT-23-5", lcsc="C51118",
         pins={"1": "V5_LOGIC", "2": "GND", "3": "V5_LOGIC", "5": "+3V3"},
         group="電源 3.3V", near=(4.0, 9.0)),
    C("C9", "1uF", "V5_LOGIC", "GND", lcsc="C15849", group="電源 3.3V", near=("U2", "1")),
    C("C10", "10uF", "V5_LOGIC", "GND", lcsc="C19702", group="電源 3.3V", near=("U2", "1")),
    C("C11", "1uF", "+3V3", "GND", lcsc="C15849", group="電源 3.3V", near=("U2", "5")),
    C("C12", "10uF", "+3V3", "GND", lcsc="C19702", group="電源 3.3V", near=("U2", "5")),

    # ---------------- ② USB-C ----------------
    dict(ref="USB1", lib="Connector:USB_C_Receptacle_USB2.0_16P", value="TYPE-C-31-M-12",
         fp="Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", lcsc="C165948",
         pins={"A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND",
               "A4": "VBUS", "A9": "VBUS", "B4": "VBUS", "B9": "VBUS",
               "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP",
               "A7": "USB_DN", "B7": "USB_DN", "SH": "GND"}, group="USB"),
    R("R3", "5.1k", "CC1", "GND", lcsc="C23186", group="USB", near=("USB1", "A5")),
    R("R4", "5.1k", "CC2", "GND", lcsc="C23186", group="USB", near=("USB1", "B5")),

    # ---------------- ③ RS-485 ----------------
    dict(ref="U3", lib="Interface_UART:SP3485EN", value="SP3485EN",
         fp="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", lcsc="C9945",
         pins={"1": "LINK_RX", "2": "RS485_DE", "3": "RS485_DE", "4": "LINK_TX",
               "5": "GND", "6": "RS485_A", "7": "RS485_B", "8": "+3V3"},
         group="RS-485", near=(15.0, 27.0)),
    C("C15", "100nF", "+3V3", "GND", lcsc="C14663", group="RS-485", near=("U3", "8")),
    R("R5", "10k", "LINK_RX", "+3V3", lcsc="C25804", group="RS-485", near=("U3", "1")),
    R("R6", "10k", "RS485_DE", "GND", lcsc="C25804", group="RS-485", near=("U3", "3")),
    R("R7", "120", "RS485_A", "TERM", lcsc="C22787", group="RS-485", near=("U3", "6")),
    dict(ref="JP1", lib="Jumper:SolderJumper_2_Bridged", value="TERM",
         fp="Jumper:SolderJumper-2_P1.3mm_Bridged_Pad1.0x1.5mm", lcsc="",
         pins={"1": "TERM", "2": "RS485_B"}, group="RS-485", near=("U3", "7")),
    dict(ref="TVS2", lib="Diode:SM712_SOT23", value="SM712", fp="Package_TO_SOT_SMD:SOT-23",
         lcsc="C15919", pins={"1": "RS485_A", "2": "RS485_B", "3": "GND"},
         group="RS-485", near=("J1", "3")),

    # ---------------- ④ MCU ----------------
    dict(ref="U4", lib="LaserBlinker:ESP32-C3-MINI-1", value="ESP32-C3-MINI-1-N4",
         fp="LaserBlinker:ESP32-C3-MINI-1", lcsc="C2838502",
         pins={**{p: "GND" for p in ESP_GND},
               "3": "+3V3", "8": "EN", "12": "IO0_TP", "13": "IMU_INT1", "5": "G2_STRAP",
               "6": "RS485_DE", "18": "LASER_L", "19": "LASER_R", "20": "I2C_SDA",
               "21": "I2C_SCL", "22": "STATUS_LED", "23": "BOOT_BTN", "16": "WS_DIN",
               "26": "USB_DN", "27": "USB_DP", "30": "LINK_RX", "31": "LINK_TX"},
         group="MCU"),
    C("C13", "10uF", "+3V3", "GND", lcsc="C19702", group="MCU", near=("U4", "3")),
    C("C14", "100nF", "+3V3", "GND", lcsc="C14663", group="MCU", near=("U4", "3")),
    R("R8", "10k", "EN", "+3V3", lcsc="C25804", group="MCU", near=("U4", "8")),
    C("C16", "1uF", "EN", "GND", lcsc="C15849", group="MCU", near=("U4", "8")),
    dict(ref="SW1", lib="Switch:SW_Push", value="RST", fp="Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A",
         lcsc="C318884", pins={"1": "EN", "2": "GND"}, group="MCU", near=("U4", "8")),
    R("R9", "10k", "BOOT_BTN", "+3V3", lcsc="C25804", group="MCU", near=("U4", "23")),
    dict(ref="SW2", lib="Switch:SW_Push", value="BOOT", fp="Button_Switch_SMD:SW_Push_1P1T_XKB_TS-1187A",
         lcsc="C318884", pins={"1": "BOOT_BTN", "2": "GND"}, group="MCU", near=("U4", "23")),
    R("R10", "10k", "G2_STRAP", "+3V3", lcsc="C25804", group="MCU", near=("U4", "5")),
    R("R11", "1k", "+3V3", "LED_A", lcsc="C21190", group="MCU", near=("U4", "22")),
    dict(ref="LED1", lib="Device:LED", value="BLUE", fp="LED_SMD:LED_0603_1608Metric",
         lcsc="C72041", pins={"1": "STATUS_LED", "2": "LED_A"}, group="MCU", near=("U4", "22")),
    dict(ref="TP1", lib="Connector:TestPoint", value="IO0", fp="TestPoint:TestPoint_Pad_D1.0mm",
         lcsc="", pins={"1": "IO0_TP"}, group="MCU", near=("U4", "12")),

    # ---------------- ⑥ 加速度センサ ----------------
    dict(ref="U5", lib="Sensor_Motion:LIS3DH", value="LIS3DHTR",
         fp="Package_LGA:LGA-16_3x3mm_P0.5mm_LayoutBorder3x5y", lcsc="C15134",
         pins={"1": "+3V3", "14": "+3V3", "8": "+3V3", "7": "GND", "6": "I2C_SDA",
               "4": "I2C_SCL", "11": "IMU_INT1", "5": "GND", "10": "GND", "12": "GND"},
         group="IMU", near=(18.0, 20.0)),
    C("C17", "10uF", "+3V3", "GND", lcsc="C19702", group="IMU", near=("U5", "14")),
    C("C18", "100nF", "+3V3", "GND", lcsc="C14663", group="IMU", near=("U5", "14")),
    R("R12", "4.7k", "I2C_SDA", "+3V3", lcsc="C23162", group="IMU", near=("U5", "6")),
    R("R13", "4.7k", "I2C_SCL", "+3V3", lcsc="C23162", group="IMU", near=("U5", "4")),

    # ---------------- ⑤ 出力: WS2812 レベルシフト ----------------
    dict(ref="U6", lib="Logic_LevelTranslator:SN74LV1T34DBV", value="SN74LV1T34DBVR",
         fp="Package_TO_SOT_SMD:SOT-23-5", lcsc="C100022",
         pins={"2": "WS_DIN", "3": "GND", "4": "WS_OUT", "5": "+5V"},
         group="WS2812", near=("J2", "2")),
    C("C19", "100nF", "+5V", "GND", lcsc="C14663", group="WS2812", near=("U6", "5")),
    R("R14", "330", "WS_OUT", "LED_DATA_5V", lcsc="C23138", group="WS2812", near=("J2", "2")),

    # ---------------- ⑤ 出力: レーザー L/R ----------------
    dict(ref="JP2", lib="Jumper:SolderJumper_3_Bridged12", value="V_LASER 5V/12V",
         fp="Jumper:SolderJumper-3_P1.3mm_Bridged12_Pad1.0x1.5mm", lcsc="",
         pins={"1": "+5V", "2": "V_LASER", "3": "+12V"}, group="レーザー", near=("J3", "1")),
    dict(ref="Q1", lib="Transistor_FET:AO3400A", value="AO3400A", fp="Package_TO_SOT_SMD:SOT-23",
         lcsc="C20917", pins={"1": "GATE_L", "2": "GND", "3": "LASER_L-"},
         group="レーザー", near=("J3", "2")),
    dict(ref="Q2", lib="Transistor_FET:AO3400A", value="AO3400A", fp="Package_TO_SOT_SMD:SOT-23",
         lcsc="C20917", pins={"1": "GATE_R", "2": "GND", "3": "LASER_R-"},
         group="レーザー", near=("J3", "4")),
    R("R15", "100", "LASER_L", "GATE_L", lcsc="C22775", group="レーザー", near=("Q1", "1")),
    R("R16", "10k", "GATE_L", "GND", lcsc="C25804", group="レーザー", near=("Q1", "1")),
    R("R17", "100", "LASER_R", "GATE_R", lcsc="C22775", group="レーザー", near=("Q2", "1")),
    R("R18", "10k", "GATE_R", "GND", lcsc="C25804", group="レーザー", near=("Q2", "1")),
    schottky("D4", "V_LASER", "LASER_L-", group="レーザー", near=("Q1", "3")),
    schottky("D5", "V_LASER", "LASER_R-", group="レーザー", near=("Q2", "3")),
]

# ERC 用: power_in ピンしかないネットに駆動元があることを示す
PWR_FLAG_NETS = ["GND", "+12V", "+5V", "V5_LOGIC"]

# 太い配線にするネット（mm）
NET_WIDTH = {
    "+12V_IN": 0.8, "12V_F": 0.8, "+12V": 0.5, "SW": 0.5, "+5V": 0.5,
    "V_LASER": 0.5, "LASER_L-": 0.5, "LASER_R-": 0.5, "VBUS": 0.5, "V5_LOGIC": 0.5,
    "+3V3": 0.3, "GND": 0.3,
}
