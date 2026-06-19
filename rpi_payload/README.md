# ============================================================
#  README.md  —  RPi Payload Software Setup
# ============================================================

# RPi Payload — Setup & Run Guide

## Install dependencies (run on RPi)

```bash
# System packages
sudo apt update
sudo apt install -y python3-pip python3-numpy python3-scipy \
                   python3-spidev python3-rpi.gpio \
                   libad9361-dev libiio-dev

# Python packages
pip3 install pyadi-iio pyserial

# Enable SPI and UART on RPi
sudo raspi-config
# → Interface Options → SPI → Enable
# → Interface Options → Serial Port → Enable (disable login shell, enable hardware)
sudo reboot
```

## File structure on RPi

```
/home/pi/
├── payload/
│   ├── config.py
│   ├── uart_receiver.py
│   ├── phase_shifter.py
│   ├── beamsteering.py
│   ├── pluto_tx.py
│   ├── pluto_rx.py
│   ├── packetiser.py
│   ├── file_transfer.py
│   ├── main.py
│   └── ground_station/
│       ├── gs_tx.py
│       └── gs_rx.py
├── video.mp4          ← for TX test
└── payload.log        ← auto-created
```

## Wiring

### FC Board → RPi UART
```
FC Board Teensy Pin 8 (TX2)  →  RPi GPIO 15 / Pin 10 (RX)
FC Board Teensy Pin 7 (RX2)  →  RPi GPIO 14 / Pin 8  (TX)
FC Board GND                 →  RPi GND / Pin 6
```

### RPi → Phase Shifter PCB (SPI)
```
RPi GPIO 10 / Pin 19 (MOSI)  →  MOSI
RPi GPIO 11 / Pin 23 (CLK)   →  CLK
RPi GPIO  8 / Pin 24 (CE0)   →  CS Element 0 (Face 1, El 1)
RPi GPIO  7 / Pin 26 (CE1)   →  CS Element 1 (Face 1, El 2)
RPi GPIO 25 / Pin 22          →  CS Element 2 (Face 1, El 3)
RPi GPIO 24 / Pin 18          →  CS Element 3 (Face 2, El 1)
RPi GPIO 23 / Pin 16          →  CS Element 4 (Face 2, El 2)
RPi GPIO 18 / Pin 12          →  CS Element 5 (Face 2, El 3)
RPi 3.3V   / Pin  1           →  Phase shifter PCB VCC
RPi GND    / Pin  6           →  Phase shifter PCB GND
```

### PlutoSDR
```
PlutoSDR USB → RPi any USB-A port
PlutoSDR SMA (TX/RX) → Phase Shifter PCB SMA input
```

## Run

### On RPi (payload):
```bash
cd /home/pi/payload
sudo python3 main.py
```

### On GS1 laptop (transmit video to payload):
```bash
python3 ground_station/gs_tx.py --file video.mp4 --pluto ip:192.168.2.1
```

### On GS2 laptop (receive video from payload):
```bash
python3 ground_station/gs_rx.py --out received.mp4 --pluto ip:192.168.2.1
```

## Before launch — update config.py

```python
GS1_LAT = 32.XXXX   # measure at launch site
GS1_LON = -106.XXXX
GS1_ALT_M = XXXX

GS2_LAT = 32.XXXX
GS2_LON = -106.XXXX
GS2_ALT_M = XXXX
```

## Bench test (no RF hardware needed)

Test packetiser and reassembler:
```bash
python3 -c "
from packetiser import FilePacketiser, FileReassembler
p = FilePacketiser('video.mp4')
r = FileReassembler()
for pkt in p.packets():
    r.receive_packet(pkt)
print(f'Complete: {r.is_complete()}')
r.save('test_output.mp4')
"
```

Test beam steering math:
```bash
python3 -c "
from beamsteering import BeamSteerer
s = BeamSteerer()
s.print_scan_table()
print(s.compute_phases(45.0, 15.0))
"
```
