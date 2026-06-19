# ============================================================
#  uart_receiver.py  —  Reads az/el packets from FC board
#
#  Runs in a background thread. Parses $AZEL packets sent
#  by the FC board Teensy over UART at 10 Hz.
#
#  Packet format: $AZEL,+045.30,-012.70,1*3F\n
#
#  Usage:
#    receiver = AzElReceiver()
#    receiver.start()
#    az, el, valid = receiver.get()
# ============================================================

import serial
import threading
import time
import logging
from config import UART_PORT, UART_BAUD, UART_TIMEOUT_S, AZEL_TIMEOUT_S

logger = logging.getLogger(__name__)


class AzElReceiver:
    def __init__(self):
        self._az          = 0.0
        self._el          = 0.0
        self._gps_valid   = False
        self._data_fresh  = False
        self._last_rx     = 0.0
        self._packet_count = 0
        self._error_count  = 0
        self._lock        = threading.Lock()
        self._running     = False
        self._thread      = None
        self._serial      = None

    # ── Public API ───────────────────────────────────────────

    def start(self):
        """Open serial port and start background receive thread."""
        try:
            self._serial = serial.Serial(
                port      = UART_PORT,
                baudrate  = UART_BAUD,
                timeout   = UART_TIMEOUT_S
            )
            self._running = True
            self._thread  = threading.Thread(
                target = self._receive_loop,
                daemon = True,        # dies when main program exits
                name   = 'AzElRX'
            )
            self._thread.start()
            logger.info(f"UART receiver started on {UART_PORT} at {UART_BAUD} baud")
        except serial.SerialException as e:
            logger.error(f"Failed to open {UART_PORT}: {e}")
            raise

    def stop(self):
        self._running = False
        if self._serial:
            self._serial.close()

    def get(self):
        """
        Returns (azimuth_deg, elevation_deg, is_fresh).
        is_fresh = False if no packet received within AZEL_TIMEOUT_S.
        """
        with self._lock:
            fresh = self._data_fresh and \
                    (time.time() - self._last_rx) < AZEL_TIMEOUT_S
            return self._az, self._el, fresh

    def status(self):
        with self._lock:
            return {
                'packets_ok'  : self._packet_count,
                'errors'      : self._error_count,
                'fresh'       : self._data_fresh,
                'az'          : self._az,
                'el'          : self._el,
                'gps_valid'   : self._gps_valid,
                'last_rx_ago' : time.time() - self._last_rx
            }

    # ── Internal ─────────────────────────────────────────────

    def _receive_loop(self):
        logger.info("UART receive loop running")
        while self._running:
            try:
                line = self._serial.readline().decode('ascii', errors='ignore').strip()
                if line:
                    self._parse(line)
            except serial.SerialException as e:
                logger.error(f"Serial read error: {e}")
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"Unexpected error in receive loop: {e}")

    def _checksum(self, sentence):
        """XOR checksum of chars between $ and * (exclusive)."""
        chk = 0
        for c in sentence:
            if c == '$':
                continue
            if c == '*':
                break
            chk ^= ord(c)
        return chk

    def _parse(self, line):
        """Parse $AZEL,+045.30,-012.70,1*3F"""
        try:
            if not line.startswith('$AZEL,'):
                return

            # Split checksum
            if '*' not in line:
                self._error_count += 1
                return

            body, chk_str = line.rsplit('*', 1)
            received_chk  = int(chk_str[:2], 16)
            computed_chk  = self._checksum(line)

            if received_chk != computed_chk:
                self._error_count += 1
                logger.warning(
                    f"Checksum mismatch: got {received_chk:02X} "
                    f"expected {computed_chk:02X}"
                )
                return

            # Parse fields: $AZEL,az,el,gps_valid
            fields = body[6:].split(',')   # skip '$AZEL,'
            if len(fields) != 3:
                self._error_count += 1
                return

            az        = float(fields[0])
            el        = float(fields[1])
            gps_valid = int(fields[2]) == 1

            # Bounds check
            if not (-180 <= az <= 180) or not (-90 <= el <= 90):
                self._error_count += 1
                logger.warning(f"Out of range: az={az} el={el}")
                return

            with self._lock:
                self._az          = az
                self._el          = el
                self._gps_valid   = gps_valid
                self._data_fresh  = True
                self._last_rx     = time.time()
                self._packet_count += 1

        except (ValueError, IndexError) as e:
            self._error_count += 1
            logger.debug(f"Parse error: {e} on line: {line}")
