# ============================================================
#  packetiser.py  —  Video file packetisation and reassembly
#
#  Packet format (total = CHUNK_SIZE + 12 bytes header):
#
#  Byte  0      : SOF (start of frame) = 0xAA
#  Bytes 1-2    : sequence number (uint16, 0-65535)
#  Bytes 3-4    : total packets in file (uint16)
#  Bytes 5-6    : payload length in this packet (uint16)
#  Bytes 7-8    : file ID (uint16) — random, identifies this transfer
#  Byte  9      : flags (bit0=last packet, bit1=retransmit)
#  Bytes 10-11  : CRC-16 of header + payload
#  Bytes 12-N   : payload data (up to CHUNK_SIZE bytes)
#
#  Total overhead: 12 bytes per packet
#  At 1024 byte chunks: 1.2% overhead — negligible
# ============================================================

import struct
import os
import random
import logging
from config import CHUNK_SIZE_BYTES, VIDEO_FILE_PATH, RECEIVED_FILE_PATH

logger = logging.getLogger(__name__)

# Constants
SOF         = 0xAA
HEADER_SIZE = 12  # 10 bytes header + 2 bytes CRC


def crc16(data: bytes) -> int:
    """CRC-16/CCITT checksum."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


# ── Transmit side ────────────────────────────────────────────

class FilePacketiser:
    """
    Reads a file and produces a sequence of packets ready to transmit.

    Usage:
        p = FilePacketiser('/home/pi/video.mp4')
        for packet in p.packets():
            transmit(packet)
    """

    def __init__(self, filepath: str = VIDEO_FILE_PATH):
        self.filepath = filepath
        self.file_id  = random.randint(0, 0xFFFF)
        self._data    = None
        self._packets = []
        self._load()

    def _load(self):
        """Read entire file into memory and build packet list."""
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Video file not found: {self.filepath}")

        with open(self.filepath, 'rb') as f:
            self._data = f.read()

        file_size = len(self._data)
        total_packets = math.ceil(file_size / CHUNK_SIZE_BYTES)

        logger.info(
            f"Packetising {self.filepath}: "
            f"{file_size} bytes → {total_packets} packets "
            f"({CHUNK_SIZE_BYTES} bytes/packet)"
        )

        self._packets = []
        for seq in range(total_packets):
            start   = seq * CHUNK_SIZE_BYTES
            end     = min(start + CHUNK_SIZE_BYTES, file_size)
            payload = self._data[start:end]
            is_last = (seq == total_packets - 1)
            pkt     = self._build_packet(seq, total_packets, payload, is_last)
            self._packets.append(pkt)

    def _build_packet(self, seq: int, total: int,
                      payload: bytes, is_last: bool,
                      retransmit: bool = False) -> bytes:
        flags = 0
        if is_last:     flags |= 0x01
        if retransmit:  flags |= 0x02

        # Header without CRC
        header_no_crc = struct.pack('>BHHHHB',
            SOF,
            seq & 0xFFFF,
            total & 0xFFFF,
            len(payload) & 0xFFFF,
            self.file_id,
            flags
        )
        # CRC over header (minus CRC bytes) + payload
        chk = crc16(header_no_crc + payload)
        crc_bytes = struct.pack('>H', chk)

        return header_no_crc + crc_bytes + payload

    def total_packets(self) -> int:
        return len(self._packets)

    def get_packet(self, seq: int, retransmit: bool = False) -> bytes:
        """Get packet by sequence number (for retransmission)."""
        if retransmit:
            # Rebuild with retransmit flag set
            start   = seq * CHUNK_SIZE_BYTES
            end     = min(start + CHUNK_SIZE_BYTES, len(self._data))
            payload = self._data[start:end]
            is_last = (seq == self.total_packets() - 1)
            return self._build_packet(seq, self.total_packets(),
                                      payload, is_last, retransmit=True)
        return self._packets[seq]

    def packets(self):
        """Generator — yields all packets in order."""
        for pkt in self._packets:
            yield pkt


# ── Receive side ─────────────────────────────────────────────

class FileReassembler:
    """
    Receives packets and reassembles the file.

    Usage:
        r = FileReassembler()
        r.receive_packet(raw_bytes)
        if r.is_complete():
            r.save('/home/pi/received.mp4')
    """

    def __init__(self):
        self._chunks       = {}     # seq → payload bytes
        self._total        = None   # total packets expected
        self._file_id      = None
        self._received     = 0
        self._corrupt      = 0

    def receive_packet(self, raw: bytes) -> dict:
        """
        Parse and store one packet.
        Returns dict with parse result.
        """
        result = {'ok': False, 'seq': None, 'duplicate': False, 'error': None}

        if len(raw) < HEADER_SIZE:
            result['error'] = 'too short'
            self._corrupt += 1
            return result

        # Parse header
        sof, seq, total, plen, file_id, flags = struct.unpack(
            '>BHHHHB', raw[:10]
        )
        received_crc = struct.unpack('>H', raw[10:12])[0]
        payload      = raw[12:12 + plen]

        # Validate SOF
        if sof != SOF:
            result['error'] = 'bad SOF'
            self._corrupt += 1
            return result

        # Validate CRC
        header_no_crc = raw[:10]
        computed_crc  = crc16(header_no_crc + payload)
        if computed_crc != received_crc:
            result['error'] = f'CRC mismatch (got {received_crc:04X} expected {computed_crc:04X})'
            self._corrupt += 1
            return result

        # Validate payload length
        if len(payload) != plen:
            result['error'] = 'payload length mismatch'
            self._corrupt += 1
            return result

        # Store
        if seq in self._chunks:
            result['duplicate'] = True
        else:
            self._chunks[seq] = payload
            self._received += 1

        self._total   = total
        self._file_id = file_id
        result.update({'ok': True, 'seq': seq, 'total': total,
                       'is_last': bool(flags & 0x01)})

        logger.debug(f"Packet {seq}/{total} OK "
                     f"({self._received}/{total} received)")
        return result

    def is_complete(self) -> bool:
        if self._total is None:
            return False
        return self._received >= self._total

    def missing_sequences(self) -> list:
        if self._total is None:
            return []
        return [i for i in range(self._total) if i not in self._chunks]

    def progress(self) -> float:
        if self._total is None or self._total == 0:
            return 0.0
        return self._received / self._total * 100.0

    def save(self, filepath: str = RECEIVED_FILE_PATH):
        """Write reassembled file to disk."""
        if not self.is_complete():
            missing = self.missing_sequences()
            raise RuntimeError(
                f"File incomplete — missing {len(missing)} packets: "
                f"{missing[:10]}{'...' if len(missing)>10 else ''}"
            )

        with open(filepath, 'wb') as f:
            for seq in range(self._total):
                f.write(self._chunks[seq])

        size = sum(len(v) for v in self._chunks.values())
        logger.info(f"File saved: {filepath} ({size} bytes, "
                    f"{self._total} packets, {self._corrupt} corrupt dropped)")
        return filepath


import math  # needed for ceil in _load
