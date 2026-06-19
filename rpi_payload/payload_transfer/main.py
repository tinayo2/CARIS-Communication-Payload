#!/usr/bin/env python3
# ============================================================
#  main.py  —  Payload RPi main coordinator (RF switch version)
#
#  Run: sudo python3 main.py
# ============================================================

import time
import logging
import signal
import sys

from uart_receiver import AzElReceiver
from rf_switch     import RFSwitch
from beamsteering  import BeamSteerer
from pluto_tx      import PlutoTX
from pluto_rx      import PlutoRX
from file_transfer import FileTransfer, State
from config        import RECEIVED_FILE_PATH

logging.basicConfig(
    level    = logging.INFO,
    format   = '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/home/pi/payload.log')
    ]
)
logger = logging.getLogger('main')

_uart_rx   = None
_rf_switch = None
_pluto_tx  = None
_pluto_rx  = None


def cleanup(sig=None, frame=None):
    logger.info("Shutting down...")
    if _uart_rx:   _uart_rx.stop()
    if _rf_switch: _rf_switch.cleanup()
    if _pluto_tx:  _pluto_tx.disconnect()
    if _pluto_rx:  _pluto_rx.disconnect()
    sys.exit(0)


signal.signal(signal.SIGINT,  cleanup)
signal.signal(signal.SIGTERM, cleanup)


def update_beam(az, el, steerer, rf_switch):
    states = steerer.compute_switch_states(az, el)
    rf_switch.set_all(states)


def wait_for_gps(uart_rx, steerer, rf_switch, timeout_s=120.0):
    logger.info("Waiting for GPS fix from FC board...")
    deadline = time.time() + timeout_s
    last_update = 0

    while time.time() < deadline:
        az, el, fresh = uart_rx.get()
        if time.time() - last_update >= 0.1:
            if fresh:
                update_beam(az, el, steerer, rf_switch)
            last_update = time.time()
        if fresh:
            logger.info(f"GPS fix: AZ={az:+.1f}° EL={el:+.1f}°")
            return True
        time.sleep(0.05)

    logger.warning("GPS timeout — continuing without fix")
    return False


def main():
    global _uart_rx, _rf_switch, _pluto_tx, _pluto_rx

    logger.info("=" * 50)
    logger.info("  Payload RPi Boot")
    logger.info("=" * 50)

    logger.info("[1/5] Starting UART receiver...")
    _uart_rx = AzElReceiver()
    _uart_rx.start()

    logger.info("[2/5] Initialising RF switches...")
    _rf_switch = RFSwitch()
    steerer    = BeamSteerer()
    _rf_switch.all_off()   # start at broadside

    logger.info("[3/5] Connecting PlutoSDR...")
    _pluto_tx = PlutoTX()
    _pluto_rx = PlutoRX()
    _pluto_tx.connect()
    _pluto_rx.connect()

    logger.info("[4/5] Waiting for GPS...")
    wait_for_gps(_uart_rx, steerer, _rf_switch, timeout_s=120.0)

    logger.info("[5/5] Starting file transfer...")
    ft = FileTransfer(_pluto_tx, _pluto_rx)

    last_beam   = 0
    last_status = 0

    while True:
        now = time.time()

        # Update beam at 10 Hz
        if now - last_beam >= 0.1:
            az, el, fresh = _uart_rx.get()
            update_beam(az, el, steerer, _rf_switch)
            last_beam = now

        # Status every 5s
        if now - last_status >= 5.0:
            az, el, fresh = _uart_rx.get()
            s = _uart_rx.status()
            phases = _rf_switch.get_active_phases()
            logger.info(
                f"AZ={az:+.1f}° EL={el:+.1f}° fresh={fresh} "
                f"pkts={s['packets_ok']} | "
                f"switches={_rf_switch.get_states()} | "
                f"state={ft.get_state().name}"
            )
            last_status = now

        # File transfer state machine
        if ft.get_state() == State.IDLE:
            logger.info("Receiving from GS1...")
            ft.receive_file(timeout_s=120.0)

        elif ft.get_state() == State.STORING:
            logger.info("Transmitting to GS2...")
            ft.transmit_file(RECEIVED_FILE_PATH)

        elif ft.get_state() == State.COMPLETE:
            time.sleep(1)

        elif ft.get_state() == State.ERROR:
            logger.error("Transfer error — retrying in 10s")
            time.sleep(10)
            ft.state = State.IDLE

        time.sleep(0.01)


if __name__ == '__main__':
    main()
