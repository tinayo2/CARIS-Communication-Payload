# ============================================================
#  pluto_tx.py  —  QPSK transmit via PlutoSDR using GNU Radio
#
#  Takes raw bytes, QPSK modulates them, and transmits at
#  1.2 GHz via PlutoSDR connected to RPi over USB.
#
#  Modulation: QPSK with RRC pulse shaping (alpha=0.35)
#  Symbol rate: 500 ksps → bitrate: 1 Mbps
#  Sample rate: 2 Msps (4 samples per symbol)
#
#  Dependencies:
#    pip install gnuradio pyadi-iio
#    or use: apt install python3-gnuradio
# ============================================================

import numpy as np
import adi
import logging
import time
from config import (
    PLUTO_URI, PLUTO_TX_FREQ_HZ, PLUTO_SAMPLE_RATE,
    PLUTO_TX_GAIN_DB, SYMBOL_RATE, SAMPLES_PER_SYMBOL
)

logger = logging.getLogger(__name__)

# ── QPSK constellation (Gray coded) ─────────────────────────
# Dibit → complex symbol
QPSK_MAP = {
    0b00: complex(-1, -1) / np.sqrt(2),
    0b01: complex(-1, +1) / np.sqrt(2),
    0b11: complex(+1, +1) / np.sqrt(2),
    0b10: complex(+1, -1) / np.sqrt(2),
}


def bytes_to_symbols(data: bytes) -> np.ndarray:
    """Convert raw bytes to QPSK complex symbols (Gray coded)."""
    symbols = []
    for byte in data:
        for shift in [6, 4, 2, 0]:          # MSB first
            dibit = (byte >> shift) & 0x03
            symbols.append(QPSK_MAP[dibit])
    return np.array(symbols, dtype=np.complex64)


def rrc_filter(alpha: float = 0.35, num_taps: int = 32) -> np.ndarray:
    """
    Root Raised Cosine filter coefficients.
    alpha: roll-off factor (0.35 is standard)
    num_taps: filter length (per side, total = 2*num_taps*sps + 1)
    """
    sps = SAMPLES_PER_SYMBOL
    N   = 2 * num_taps * sps + 1
    t   = np.arange(-(N//2), N//2 + 1) / sps

    h = np.zeros(N)
    for i, ti in enumerate(t):
        if ti == 0:
            h[i] = (1 + alpha * (4/np.pi - 1))
        elif abs(ti) == 1 / (4 * alpha):
            h[i] = (alpha / np.sqrt(2)) * (
                (1 + 2/np.pi) * np.sin(np.pi / (4*alpha)) +
                (1 - 2/np.pi) * np.cos(np.pi / (4*alpha))
            )
        else:
            num = np.sin(np.pi * ti * (1-alpha)) + \
                  4*alpha*ti * np.cos(np.pi * ti * (1+alpha))
            den = np.pi * ti * (1 - (4*alpha*ti)**2)
            h[i] = num / den

    # Normalise
    h /= np.sqrt(np.sum(h**2))
    return h.astype(np.float32)


def modulate(data: bytes) -> np.ndarray:
    """
    Full modulation chain: bytes → QPSK symbols → upsample → RRC filter
    Returns complex64 IQ samples ready for PlutoSDR.
    """
    # Step 1: bytes → symbols
    symbols = bytes_to_symbols(data)

    # Step 2: upsample (insert zeros between symbols)
    sps = SAMPLES_PER_SYMBOL
    upsampled = np.zeros(len(symbols) * sps, dtype=np.complex64)
    upsampled[::sps] = symbols

    # Step 3: RRC pulse shaping
    h = rrc_filter()
    filtered = np.convolve(upsampled, h, mode='same').astype(np.complex64)

    # Step 4: scale to int16 range for PlutoSDR
    max_val = np.max(np.abs(filtered))
    if max_val > 0:
        filtered = filtered / max_val * 0.9   # 90% of full scale

    return filtered


class PlutoTX:
    def __init__(self):
        self._sdr = None
        self._connected = False

    def connect(self):
        """Connect to PlutoSDR."""
        try:
            self._sdr = adi.Pluto(uri=PLUTO_URI)
            self._sdr.sample_rate              = PLUTO_SAMPLE_RATE
            self._sdr.tx_rf_bandwidth          = PLUTO_SAMPLE_RATE
            self._sdr.tx_lo                    = PLUTO_TX_FREQ_HZ
            self._sdr.tx_hardwaregain_chan0     = PLUTO_TX_GAIN_DB
            self._sdr.tx_cyclic_buffer         = False
            self._connected = True
            logger.info(
                f"PlutoSDR TX connected: {PLUTO_TX_FREQ_HZ/1e9:.3f} GHz "
                f"SR={PLUTO_SAMPLE_RATE/1e6:.1f} Msps "
                f"gain={PLUTO_TX_GAIN_DB} dB"
            )
        except Exception as e:
            logger.error(f"PlutoSDR TX connect failed: {e}")
            logger.error("Check: PlutoSDR USB connected, IP 192.168.2.1 reachable")
            raise

    def transmit(self, data: bytes):
        """
        Modulate and transmit raw bytes.
        Blocks until transmission is complete.
        """
        if not self._connected:
            raise RuntimeError("PlutoSDR not connected — call connect() first")

        # Modulate
        iq_samples = modulate(data)

        # PlutoSDR expects int16 interleaved IQ
        # numpy complex64 → interleaved int16
        iq_int16 = np.empty(len(iq_samples) * 2, dtype=np.int16)
        iq_int16[0::2] = (iq_samples.real * 32767).astype(np.int16)
        iq_int16[1::2] = (iq_samples.imag * 32767).astype(np.int16)

        self._sdr.tx(iq_int16)
        logger.debug(f"TX: {len(data)} bytes → {len(iq_samples)} samples")

    def disconnect(self):
        if self._sdr:
            self._sdr.tx_destroy_buffer()
        self._connected = False
