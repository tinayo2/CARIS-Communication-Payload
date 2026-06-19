# ============================================================
#  rf_switch.py  —  SKY13418-485LF SP8T switch control
#
#  4 switches total:
#    Switch 0: Face 1, Patch 2 (non-reference element)
#    Switch 1: Face 1, Patch 3 (non-reference element)
#    Switch 2: Face 2, Patch 2 (non-reference element)
#    Switch 3: Face 2, Patch 3 (non-reference element)
#
#  Patch 1 on each face = reference element (0° phase, no switch)
#
#  Each switch is controlled by 3 GPIO pins (V1, V2, V3).
#  3-bit binary selects which of 8 branches is active.
#  We use branches 0-3 (RF1-RF4), each connected to a different
#  delay line giving a different beam steering angle.
#
#  SKY13418 truth table (branches 0-3):
#    V1  V2  V3  → Branch → Delay line → Beam angle
#     0   0   0  → RF1    → delay A    → 35°
#     0   0   1  → RF2    → delay B    → 45°
#     0   1   0  → RF3    → delay C    → 55°
#     0   1   1  → RF4    → delay D    → 70°
#
#  Note: GPIO pins go through 10kΩ/12kΩ resistor divider
#  to bring 3.3V → 1.8V for SKY13418 control pins.
# ============================================================

import RPi.GPIO as GPIO
import logging
from config import SWITCH_PINS, NUM_SWITCHES, BRANCH_ANGLES_DEG

logger = logging.getLogger(__name__)

# 3-bit codes for each branch (V1, V2, V3)
BRANCH_CODES = {
    0: (0, 0, 0),   # RF1 → 35°
    1: (0, 0, 1),   # RF2 → 45°
    2: (0, 1, 0),   # RF3 → 55°
    3: (0, 1, 1),   # RF4 → 70°
}

# Default safe branch when face is inactive
IDLE_BRANCH = 0   # RF1 (lowest steering angle, or could use unused RF5+)


class RFSwitch:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Set up all GPIO pins as outputs, default LOW
        for v1, v2, v3 in SWITCH_PINS:
            GPIO.setup(v1, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(v2, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(v3, GPIO.OUT, initial=GPIO.LOW)

        self._branches = [IDLE_BRANCH] * NUM_SWITCHES

        logger.info(f"RFSwitch init: {NUM_SWITCHES} switches")
        logger.info(f"Branch angles: {BRANCH_ANGLES_DEG}")
        logger.info("All switches set to idle branch (RF1)")

        # Apply idle state to all switches
        for i in range(NUM_SWITCHES):
            self._apply(i, IDLE_BRANCH)

    # ── Public API ───────────────────────────────────────────

    def set_branch(self, switch_idx: int, branch: int):
        """
        Set a switch to a specific branch (0-3).
        branch 0 → RF1 → 35°
        branch 1 → RF2 → 45°
        branch 2 → RF3 → 55°
        branch 3 → RF4 → 70°
        """
        if not 0 <= switch_idx < NUM_SWITCHES:
            raise ValueError(f"Switch index must be 0-{NUM_SWITCHES-1}")
        if not 0 <= branch <= 3:
            raise ValueError(f"Branch must be 0-3, got {branch}")

        self._apply(switch_idx, branch)
        self._branches[switch_idx] = branch

        logger.debug(
            f"Switch {switch_idx} → branch {branch} "
            f"({BRANCH_ANGLES_DEG[branch]}°) "
            f"GPIO{SWITCH_PINS[switch_idx]} = {BRANCH_CODES[branch]}"
        )

    def set_face(self, face: int, branch: int):
        """
        Set both switches on a face to the same branch.
        face 0 = Face 1 (switches 0 and 1)
        face 1 = Face 2 (switches 2 and 3)
        """
        base = face * 2
        self.set_branch(base,     branch)
        self.set_branch(base + 1, branch)
        logger.info(
            f"Face {face+1} → branch {branch} "
            f"({BRANCH_ANGLES_DEG[branch]}°)"
        )

    def set_idle(self, switch_idx: int):
        """Set a switch to the idle/safe branch."""
        self.set_branch(switch_idx, IDLE_BRANCH)

    def set_face_idle(self, face: int):
        """Set both switches on a face to idle."""
        self.set_face(face, IDLE_BRANCH)

    def get_branches(self) -> list:
        """Return current branch index for each switch."""
        return list(self._branches)

    def get_beam_angles(self) -> dict:
        """Return current beam angle for each switch."""
        return {
            f'Face1_Patch2': BRANCH_ANGLES_DEG[self._branches[0]],
            f'Face1_Patch3': BRANCH_ANGLES_DEG[self._branches[1]],
            f'Face2_Patch2': BRANCH_ANGLES_DEG[self._branches[2]],
            f'Face2_Patch3': BRANCH_ANGLES_DEG[self._branches[3]],
        }

    def cleanup(self):
        """Reset all switches to idle and release GPIO."""
        for i in range(NUM_SWITCHES):
            self._apply(i, IDLE_BRANCH)
        GPIO.cleanup([pin for pins in SWITCH_PINS for pin in pins])

    # ── Internal ─────────────────────────────────────────────

    def _apply(self, switch_idx: int, branch: int):
        """Write V1/V2/V3 GPIO levels for given switch and branch."""
        v1_pin, v2_pin, v3_pin = SWITCH_PINS[switch_idx]
        v1, v2, v3 = BRANCH_CODES[branch]
        GPIO.output(v1_pin, GPIO.HIGH if v1 else GPIO.LOW)
        GPIO.output(v2_pin, GPIO.HIGH if v2 else GPIO.LOW)
        GPIO.output(v3_pin, GPIO.HIGH if v3 else GPIO.LOW)
