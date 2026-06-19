#!/usr/bin/env python3
# ============================================================
#  gs_rx.py  —  Ground Station 2: receive video from payload
#
#  Runs on a laptop at GS2.
#  Listens for packets from the payload, ACKs each one,
#  reassembles and saves the video file.
#
#  Usage:
#    python3 gs_rx.py --out received.mp4 --pluto ip:192.168.2.1
# ============================================================

import sys
import time
import logging
import argparse

sys.path.insert(0, '.')

logging.basicConfig(
    level  = logging.INFO,
    format = '%(asctime)s [GS-RX] %(levelname)s: %(message)s'
)
logger = logging.getLogger('gs_rx')

from packetiser    import FileReassembler, HEADER_SIZE
from pluto_tx      import PlutoTX
from pluto_rx      import PlutoRX
from file_transfer import parse_ack, make_ack
import struct


def gs_receive(output_path: str, pluto_uri: str, timeout_s: float = 300.0):
    logger.info(f"GS2 RX starting — output: {output_path}  timeout: {timeout_s}s")

    import config
    config.PLUTO_URI = pluto_uri

    tx = PlutoTX()
    rx = PlutoRX()
    tx.connect()
    rx.connect()

    assembler = FileReassembler()
    deadline  = time.time() + timeout_s
    last_log  = time.time()

    logger.info("Listening for packets from payload...")

    while time.time() < deadline:
        raw = rx.receive_bytes()
        if not raw:
            time.sleep(0.01)
            continue

        # Extract packets from received bytes
        packets = _extract_packets(raw)

        for pkt_raw in packets:
            result = assembler.receive_packet(pkt_raw)

            if result['ok']:
                seq = result['seq']
                # Send ACK back to payload
                tx.transmit(make_ack(seq))

                if assembler.is_complete():
                    logger.info("All packets received!")
                    path = assembler.save(output_path)
                    logger.info(f"File saved: {path}")
                    logger.info(
                        f"Stats: {result['total']} packets, "
                        f"{assembler._corrupt} corrupt dropped"
                    )
                    tx.disconnect()
                    rx.disconnect()
                    return True
            else:
                logger.debug(f"Bad packet: {result['error']}")

        # Progress log every 5 seconds
        if time.time() - last_log >= 5.0:
            last_log = time.time()
            logger.info(
                f"Progress: {assembler.progress():.1f}% "
                f"received={assembler._received} "
                f"corrupt={assembler._corrupt}"
            )

    logger.warning(f"Timeout after {timeout_s}s")
    missing = assembler.missing_sequences()
    logger.warning(f"Missing {len(missing)} packets")

    # Save partial file anyway
    if assembler._received > 0:
        try:
            assembler._total = assembler._received  # force complete
            path = assembler.save(output_path + '.partial')
            logger.info(f"Partial file saved: {path}")
        except Exception as e:
            logger.error(f"Could not save partial: {e}")

    tx.disconnect()
    rx.disconnect()
    return False


def _extract_packets(raw: bytes) -> list:
    """Find packet boundaries by SOF byte (0xAA)."""
    packets = []
    i = 0
    while i < len(raw):
        if raw[i] == 0xAA:
            if i + HEADER_SIZE < len(raw):
                plen = struct.unpack('>H', raw[i+5:i+7])[0]
                end  = i + HEADER_SIZE + plen
                if end <= len(raw):
                    packets.append(raw[i:end])
                    i = end
                    continue
        i += 1
    return packets


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='GS2 Video Receiver')
    parser.add_argument('--out',     default='received.mp4',
                        help='Output file path')
    parser.add_argument('--pluto',   default='ip:192.168.2.1',
                        help='PlutoSDR URI')
    parser.add_argument('--timeout', default=300, type=float,
                        help='Receive timeout in seconds')
    args = parser.parse_args()
    gs_receive(args.out, args.pluto, args.timeout)
