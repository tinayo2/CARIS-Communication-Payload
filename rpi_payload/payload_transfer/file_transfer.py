# ============================================================
#  file_transfer.py  —  File transfer state machine
#
#  Payload is a RELAY — it receives from GS1, then retransmits
#  to GS2. Half-duplex (one direction at a time).
#
#  State machine:
#
#    IDLE
#      ↓  GS1 starts transmitting
#    RECEIVING  (payload RX on, beam pointed at GS1)
#      ↓  all packets received (or timeout)
#    STORING    (save to disk, verify integrity)
#      ↓  complete
#    TRANSMITTING  (payload TX on, beam pointed at GS2)
#      ↓  all packets sent and ACKd
#    COMPLETE
# ============================================================

import time
import logging
import threading
from enum import Enum, auto
from packetiser import FilePacketiser, FileReassembler, HEADER_SIZE
from config import (
    CHUNK_SIZE_BYTES, MAX_RETRIES, ACK_TIMEOUT_S,
    VIDEO_FILE_PATH, RECEIVED_FILE_PATH
)

logger = logging.getLogger(__name__)


class State(Enum):
    IDLE         = auto()
    RECEIVING    = auto()
    STORING      = auto()
    TRANSMITTING = auto()
    COMPLETE     = auto()
    ERROR        = auto()


# Simple ACK packet: b'ACK' + 2-byte seq number
ACK_MAGIC = b'ACK'
NAK_MAGIC = b'NAK'


def make_ack(seq: int) -> bytes:
    import struct
    return ACK_MAGIC + struct.pack('>H', seq)


def make_nak(seq: int) -> bytes:
    import struct
    return NAK_MAGIC + struct.pack('>H', seq)


def parse_ack(data: bytes):
    """Returns ('ACK'|'NAK', seq) or None if not a valid ACK/NAK."""
    import struct
    if len(data) < 5:
        return None
    magic = data[:3]
    if magic == ACK_MAGIC:
        seq = struct.unpack('>H', data[3:5])[0]
        return ('ACK', seq)
    if magic == NAK_MAGIC:
        seq = struct.unpack('>H', data[3:5])[0]
        return ('NAK', seq)
    return None


class FileTransfer:
    """
    Manages the full receive → store → transmit cycle.

    The TX and RX transport (PlutoTX/PlutoRX) are injected so
    this class stays testable without hardware.
    """

    def __init__(self, pluto_tx, pluto_rx):
        self._tx     = pluto_tx
        self._rx     = pluto_rx
        self.state   = State.IDLE
        self._assembler = FileReassembler()
        self._lock   = threading.Lock()

    # ── Receive side (payload ← GS1) ─────────────────────────

    def receive_file(self, timeout_s: float = 120.0) -> bool:
        """
        Listen for incoming packets from GS1.
        Sends ACK for each good packet, NAK for corrupted ones.
        Returns True if file received completely.
        """
        logger.info("File transfer: entering RECEIVE mode")
        self.state      = State.RECEIVING
        self._assembler = FileReassembler()
        deadline        = time.time() + timeout_s

        while time.time() < deadline:
            # Receive a chunk of data
            try:
                raw_bytes = self._rx.receive_bytes()
            except Exception as e:
                logger.error(f"RX error: {e}")
                time.sleep(0.01)
                continue

            if not raw_bytes:
                continue

            # Try to find packet boundaries in the received bytes
            packets = self._extract_packets(raw_bytes)

            for pkt_raw in packets:
                result = self._assembler.receive_packet(pkt_raw)

                if result['ok']:
                    seq = result['seq']
                    # Send ACK
                    try:
                        self._tx.transmit(make_ack(seq))
                    except Exception as e:
                        logger.warning(f"ACK TX failed: {e}")

                    progress = self._assembler.progress()
                    if seq % 10 == 0:
                        logger.info(f"RX progress: {progress:.1f}% "
                                    f"({seq}/{result['total']})")

                    if self._assembler.is_complete():
                        logger.info("All packets received!")
                        self.state = State.STORING
                        return self._store()
                else:
                    # Send NAK — request retransmit
                    logger.warning(f"Bad packet: {result['error']}")

        logger.warning(f"RX timeout after {timeout_s}s. "
                       f"Progress: {self._assembler.progress():.1f}%")
        missing = self._assembler.missing_sequences()
        logger.warning(f"Missing {len(missing)} packets")
        self.state = State.ERROR
        return False

    def _store(self) -> bool:
        """Save received file to disk."""
        try:
            path = self._assembler.save(RECEIVED_FILE_PATH)
            logger.info(f"File stored: {path}")
            self.state = State.STORING
            return True
        except Exception as e:
            logger.error(f"Store failed: {e}")
            self.state = State.ERROR
            return False

    def _extract_packets(self, raw: bytes) -> list:
        """
        Find packet boundaries in a raw byte stream.
        Looks for SOF byte (0xAA) to find packet starts.
        """
        packets = []
        i = 0
        while i < len(raw):
            if raw[i] == 0xAA:   # SOF
                # Estimate packet end — header says payload length
                if i + HEADER_SIZE < len(raw):
                    import struct
                    plen = struct.unpack('>H', raw[i+5:i+7])[0]
                    end  = i + HEADER_SIZE + plen
                    if end <= len(raw):
                        packets.append(raw[i:end])
                        i = end
                        continue
            i += 1
        return packets

    # ── Transmit side (payload → GS2) ────────────────────────

    def transmit_file(self, filepath: str = RECEIVED_FILE_PATH) -> bool:
        """
        Transmit a file to GS2 with stop-and-wait ARQ.
        Waits for ACK after each packet. Retransmits on NAK or timeout.
        Returns True if all packets acknowledged.
        """
        logger.info(f"File transfer: entering TRANSMIT mode — {filepath}")
        self.state = State.TRANSMITTING

        try:
            packetiser = FilePacketiser(filepath)
        except FileNotFoundError as e:
            logger.error(e)
            self.state = State.ERROR
            return False

        total = packetiser.total_packets()
        logger.info(f"Transmitting {total} packets")

        for seq in range(total):
            pkt        = packetiser.get_packet(seq)
            retries    = 0
            acked      = False

            while retries < MAX_RETRIES and not acked:
                # Transmit
                try:
                    self._tx.transmit(pkt)
                except Exception as e:
                    logger.error(f"TX error seq {seq}: {e}")
                    break

                # Wait for ACK
                ack_deadline = time.time() + ACK_TIMEOUT_S
                while time.time() < ack_deadline:
                    try:
                        resp = self._rx.receive_bytes()
                        parsed = parse_ack(resp)
                        if parsed:
                            kind, ack_seq = parsed
                            if kind == 'ACK' and ack_seq == seq:
                                acked = True
                                break
                            elif kind == 'NAK' and ack_seq == seq:
                                logger.info(f"NAK for seq {seq} — retransmitting")
                                break
                    except Exception:
                        pass

                if not acked:
                    retries += 1
                    logger.warning(f"Seq {seq}: retry {retries}/{MAX_RETRIES}")
                    pkt = packetiser.get_packet(seq, retransmit=True)

            if not acked:
                logger.error(f"Seq {seq} failed after {MAX_RETRIES} retries")
                self.state = State.ERROR
                return False

            if seq % 10 == 0:
                logger.info(f"TX progress: {seq+1}/{total} "
                            f"({(seq+1)/total*100:.1f}%)")

        logger.info("File transmission complete")
        self.state = State.COMPLETE
        return True

    def get_state(self) -> State:
        return self.state
