# ============================================================
#  config.py  —  All hardware and system constants for RPi
#
#  Hardware wiring:
#
#  FC Board UART → RPi:
#    FC Board Teensy Pin 8 (TX2) → RPi GPIO 15 (RX / Pin 10)
#    FC Board Teensy Pin 7 (RX2) → RPi GPIO 14 (TX / Pin 8)
#    FC Board GND                → RPi GND (Pin 6)
#
#  RF Switch GPIO (SKY13418-485LF, 3-bit binary, with resistor divider):
#
#    Switch 0 (Face 1, Patch 2):  V1=GPIO17, V2=GPIO27, V3=GPIO22
#    Switch 1 (Face 1, Patch 3):  V1=GPIO5,  V2=GPIO6,  V3=GPIO13
#    Switch 2 (Face 2, Patch 2):  V1=GPIO19, V2=GPIO26, V3=GPIO21
#    Switch 3 (Face 2, Patch 3):  V1=GPIO20, V2=GPIO16, V3=GPIO12
#
#  Each V1/V2/V3 pin goes through a 10kΩ/12kΩ resistor divider
#  to bring RPi 3.3V down to ~1.8V for SKY13418 control pins.
#
#  PlutoSDR: USB → RPi any USB-A port
#
# ============================================================

# ── UART (FC Board → RPi) ────────────────────────────────────
UART_PORT        = '/dev/serial0'
UART_BAUD        = 115200
UART_TIMEOUT_S   = 0.5
AZEL_TIMEOUT_S   = 1.0

# ── RF Switch GPIO pins ──────────────────────────────────────
# Each switch has 3 control pins (V1, V2, V3) for 3-bit binary
# Format: (V1_pin, V2_pin, V3_pin)
SWITCH_PINS = [
    (17, 27, 22),   # Switch 0: Face 1, Patch 2
    ( 5,  6, 13),   # Switch 1: Face 1, Patch 3
    (19, 26, 21),   # Switch 2: Face 2, Patch 2
    (20, 16, 12),   # Switch 3: Face 2, Patch 3
]
NUM_SWITCHES     = 4
ELEMENTS_PER_FACE = 2   # non-reference elements per face (Patch 2 and 3)

# ── SP8T branch → beam angle mapping ────────────────────────
# 4 branches used out of 8.
# Branch index 0-3 maps to SKY13418 RF1-RF4 (3-bit codes 000-011)
# Beam angles designed for your flight geometry (35°-70°)
BRANCH_ANGLES_DEG = [35.0, 45.0, 55.0, 70.0]

# ── Antenna / Array geometry ─────────────────────────────────
ELEMENT_SPACING_MM  = 34.0
FREQUENCY_HZ        = 1.2e9
WAVELENGTH_MM       = 250.0       # free space at 1.2 GHz
WAVELENGTH_EFF_MM   = 134.0       # Rogers 4350B (εr_eff=3.48)

# ── PlutoSDR ─────────────────────────────────────────────────
PLUTO_URI           = 'ip:192.168.2.1'
PLUTO_TX_FREQ_HZ    = 1_200_000_000
PLUTO_RX_FREQ_HZ    = 1_200_000_000
PLUTO_SAMPLE_RATE   = 2_000_000
PLUTO_TX_GAIN_DB    = -10
PLUTO_RX_GAIN_DB    = 30

# ── QPSK / Modulation ────────────────────────────────────────
SYMBOL_RATE         = 500_000
SAMPLES_PER_SYMBOL  = PLUTO_SAMPLE_RATE // SYMBOL_RATE
BITS_PER_SYMBOL     = 2

# ── File Transfer ────────────────────────────────────────────
CHUNK_SIZE_BYTES    = 1024
MAX_RETRIES         = 5
ACK_TIMEOUT_S       = 2.0
VIDEO_FILE_PATH     = '/home/pi/video.mp4'
RECEIVED_FILE_PATH  = '/home/pi/received_video.mp4'

# ── Ground Station coordinates (update at launch site) ───────
GS1_LAT             = 32.9395
GS1_LON             = -106.9195
GS1_ALT_M           = 1401.0

GS2_LAT             = 32.9380
GS2_LON             = -106.9180
GS2_ALT_M           = 1401.0
