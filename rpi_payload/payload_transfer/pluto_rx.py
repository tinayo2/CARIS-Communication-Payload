# ============================================================
#  pluto_rx.py  —  QPSK receive via PlutoSDR
#
#  Receives IQ samples from PlutoSDR, demodulates QPSK,
#  and returns raw bytes.
#
#  The demodulation chain:
#    IQ samples → RRC match filter → symbol sync →
#    phase recovery → QPSK decision → bits → bytes
# ============================================================

import numpy as np
import adi
import logging
from pluto_tx import rrc_filter   # reuse same RRC coefficients
from config import (
    PLUTO_URI, PLUTO_RX_FREQ_HZ, PLUTO_SAMPLE_RATE,
    PLUTO_RX_GAIN_DB, SAMPLES_PER_SYMBOL
)

logger = logging.getLogger(__name__)

# ── QPSK decision boundaries ─────────────────────────────────
# Inverse of the Gray-coded map in pluto_tx.py
def decide_symbol(sample: complex) -> int:
    """Hard decision on received QPSK sample → dibit."""
    i = 1 if sample.real >= 0 else 0
    q = 1 if sample.imag >= 0 else 0
    # Gray decode: matches the transmit map
    gray_map = {(0,0): 0b00, (0,1): 0b01, (1,1): 0b11, (1,0): 0b10}
    return gray_map[(i, q)]


def symbols_to_bytes(symbols: list) -> bytes:
    """Convert list of dibits back to bytes."""
    result = []
    for i in range(0, len(symbols) - 3, 4):
        byte = (symbols[i]   << 6) | \
               (symbols[i+1] << 4) | \
               (symbols[i+2] << 2) | \
               (symbols[i+3])
        result.append(byte)
    return bytes(result)


def demodulate(iq_samples: np.ndarray) -> bytes:
    """
    Full demodulation chain:
    IQ samples → RRC match filter → downsample → decisions → bytes
    """
    # Step 1: RRC matched filter
    h = rrc_filter()
    filtered = np.convolve(iq_samples, h, mode='same')

    # Step 2: Downsample — take one sample per symbol
    # Simple timing: take centre sample of each symbol
    sps = SAMPLES_PER_SYMBOL
    offset = sps // 2   # take middle sample
    symbols_complex = filtered[offset::sps]

    # Step 3: Phase correction — remove constant phase offset
    # Simple approach: rotate so first known preamble symbol is correct
    # For now: use decision-directed correction
    symbols_complex = _phase_correct(symbols_complex)

    # Step 4: Hard decisions
    dibits = [decide_symbol(s) for s in symbols_complex]

    # Step 5: Dibits → bytes
    return symbols_to_bytes(dibits)


def _phase_correct(symbols: np.ndarray) -> np.ndarray:
    """
    Simple decision-directed phase correction.
    Estimates average phase error and corrects it.
    """
    # For each symbol, ideal phase is ±45°, ±135°
    # Estimate phase error by comparing received to nearest ideal
    ideal_phases = np.array([
        np.pi/4, 3*np.pi/4, -3*np.pi/4, -np.pi/4  # 45°, 135°, -135°, -45°
    ])

    phase_errors = []
    for s in symbols[:100]:   # use first 100 symbols to estimate
        received_phase = np.angle(s)
        # Find nearest ideal phase
        diffs = [(received_phase - p + np.pi) % (2*np.pi) - np.pi
                 for p in ideal_phases]
        min_idx = np.argmin(np.abs(diffs))
        phase_errors.append(diffs[min_idx])

    mean_error = np.mean(phase_errors)
    correction = np.exp(-1j * mean_error)

    logger.debug(f"Phase correction: {np.degrees(mean_error):.2f}°")
    return symbols * correction


class PlutoRX:
    def __init__(self):
        self._sdr = None
        self._connected = False

    def connect(self):
        """Connect to PlutoSDR for receive."""
        try:
            self._sdr = adi.Pluto(uri=PLUTO_URI)
            self._sdr.sample_rate              = PLUTO_SAMPLE_RATE
            self._sdr.rx_rf_bandwidth          = PLUTO_SAMPLE_RATE
            self._sdr.rx_lo                    = PLUTO_RX_FREQ_HZ
            self._sdr.gain_control_mode_chan0   = 'manual'
            self._sdr.rx_hardwaregain_chan0     = PLUTO_RX_GAIN_DB
            self._sdr.rx_buffer_size           = 1024 * 64  # 64k samples
            self._connected = True
            logger.info(
                f"PlutoSDR RX connected: {PLUTO_RX_FREQ_HZ/1e9:.3f} GHz "
                f"SR={PLUTO_SAMPLE_RATE/1e6:.1f} Msps "
                f"gain={PLUTO_RX_GAIN_DB} dB"
            )
        except Exception as e:
            logger.error(f"PlutoSDR RX connect failed: {e}")
            raise

    def receive_bytes(self, num_samples: int = None) -> bytes:
        """
        Receive IQ samples and demodulate to bytes.
        num_samples: how many IQ samples to capture (None = buffer size)
        """
        if not self._connected:
            raise RuntimeError("Not connected")

        raw = self._sdr.rx()   # returns complex64 array
        if raw is None or len(raw) == 0:
            return b''

        return demodulate(raw.astype(np.complex64))

    def receive_raw(self) -> np.ndarray:
        """Return raw IQ samples as complex64 array."""
        if not self._connected:
            raise RuntimeError("Not connected")
        return self._sdr.rx().astype(np.complex64)

    def disconnect(self):
        if self._sdr:
            self._sdr.rx_destroy_buffer()
        self._connected = False
