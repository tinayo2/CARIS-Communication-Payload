#!/usr/bin/env python3
# ============================================================
#  gs_tx.py  —  Ground Station 1: transmit video to payload
#
#  Runs on a laptop at GS1.
#  Transmits the video file to the payload over PlutoSDR.
#  Listens for ACKs from the payload and retransmits on NAK
#  or timeout.
#
#  Usage:
#    python3 gs_tx.py --file video.mp4 --pluto ip:192.168.2.1
#
#  Dependencies:
#    pip install pyadi-iio numpy
# ============================================================

import sys
import time
import logging
import argparse
import struct
import numpy as np

# Add parent dir for shared modules
sys.path.insert(0, '.')

logging.basicConfig(
    level  = logging.INFO,
    format = '%(asctime)s [GS-TX] %(levelname)s: %(message)s'
)
logger = logging.getLogger('gs_tx')


# ── Inline config (GS1 side) ─────────────────────────────────
TX_FREQ_HZ    = 1_200_000_000   # 1.2 GHz
SAMPLE_RATE   = 2_000_000       # 2 Msps
TX_GAIN_DB    = -10             # PlutoSDR attenuation
CHUNK_SIZE    = 1024            # bytes per packet
MAX_RETRIES   = 5
ACK_TIMEOUT_S = 2.0

# Reuse packet builder from packetiser
from packetiser import FilePacketiser, crc16, SOF, HEADER_SIZE
from pluto_tx   import PlutoTX, modulate
from pluto_rx   import PlutoRX
from file_transfer import parse_ack, make_ack


def gs_transmit(filepath: str, pluto_uri: str):
    logger.info(f"GS1 TX starting — file: {filepath}  PlutoSDR: {pluto_uri}")

    # Override URI in config
    import config
    config.PLUTO_URI = pluto_uri

    # Init PlutoSDR
    tx = PlutoTX()
    rx = PlutoRX()
    tx.connect()
    rx.connect()

    # Packetise file
    packetiser = FilePacketiser(filepath)
    total = packetiser.total_packets()
    logger.info(f"File packetised: {total} packets of {CHUNK_SIZE} bytes")

    # Transmit with stop-and-wait ARQ
    start_time  = time.time()
    total_retx  = 0

    for seq in range(total):
        pkt     = packetiser.get_packet(seq)
        retries = 0
        acked   = False

        while retries <= MAX_RETRIES and not acked:
            # Transmit packet
            tx.transmit(pkt)

            # Wait for ACK
            deadline = time.time() + ACK_TIMEOUT_S
            while time.time() < deadline:
                resp = rx.receive_bytes()
                if resp:
                    parsed = parse_ack(resp)
                    if parsed:
                        kind, ack_seq = parsed
                        if kind == 'ACK' and ack_seq == seq:
                            acked = True
                            break
                        elif kind == 'NAK' and ack_seq == seq:
                            logger.debug(f"NAK seq {seq}")
                            break

            if not acked:
                retries += 1
                total_retx += 1
                logger.warning(f"Seq {seq}: retry {retries}")
                pkt = packetiser.get_packet(seq, retransmit=True)

        if not acked:
            logger.error(f"Seq {seq} FAILED after {MAX_RETRIES} retries")

        # Progress
        if seq % 20 == 0 or seq == total - 1:
            elapsed  = time.time() - start_time
            rate_kbps = (seq * CHUNK_SIZE * 8) / elapsed / 1000 if elapsed > 0 else 0
            logger.info(
                f"Progress: {seq+1}/{total} ({(seq+1)/total*100:.1f}%) "
                f"retx={total_retx} rate={rate_kbps:.1f} kbps"
            )

    elapsed = time.time() - start_time
    logger.info(
        f"TX complete: {total} packets in {elapsed:.1f}s "
        f"retransmits={total_retx}"
    )

    tx.disconnect()
    rx.disconnect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='GS1 Video Transmitter')
    parser.add_argument('--file',  default='video.mp4',
                        help='Video file to transmit')
    parser.add_argument('--pluto', default='ip:192.168.2.1',
                        help='PlutoSDR URI')
    args = parser.parse_args()
    gs_transmit(args.file, args.pluto)
