# ============================================================
#  beamsteering.py  —  Converts az/el → SP8T branch selection
#
#  Logic:
#    1. Determine which face is pointing toward the target
#       (from azimuth in payload body frame)
#    2. Find which of the 4 branches gives a beam angle
#       closest to the target elevation angle
#    3. Set both switches on the active face to that branch
#    4. Set both switches on the inactive face to idle
#
#  Branch → beam angle mapping (from config):
#    Branch 0 → RF1 → 35°
#    Branch 1 → RF2 → 45°
#    Branch 2 → RF3 → 55°
#    Branch 3 → RF4 → 70°
#
#  These are the 4 delay line options on the RF PCB.
#  The RF team designs delay line lengths to hit these angles.
# ============================================================

import logging
from config import BRANCH_ANGLES_DEG

logger = logging.getLogger(__name__)


class BeamSteerer:
    def __init__(self):
        logger.info("BeamSteerer init")
        logger.info(f"Available beam angles: {BRANCH_ANGLES_DEG}")
        self._print_branch_table()

    def compute(self, azimuth_deg: float,
                elevation_deg: float) -> dict:
        """
        Main function — call at 10 Hz from main.py.

        Takes az/el from FC board (payload body frame).
        Returns dict with:
            'active_face': 0 or 1 (Face 1 or Face 2)
            'branch':      0-3 (which delay line to use)
            'beam_angle':  actual steering angle of chosen branch
            'error_deg':   difference between target and chosen angle
        """

        # ── Step 1: Face selection ────────────────────────────
        # Azimuth in body frame:
        #   0°    = forward (Face 1 direction)
        #   ±180° = backward (Face 2 direction)
        # Face 1 covers forward hemisphere: az within ±90°
        # Face 2 covers rear hemisphere: az beyond ±90°
        face = 0 if abs(azimuth_deg) <= 90.0 else 1

        # ── Step 2: Best branch selection ────────────────────
        # Find which branch angle is closest to target elevation
        target = abs(elevation_deg)
        branch, beam_angle = self._best_branch(target)
        error = abs(beam_angle - target)

        result = {
            'active_face': face,
            'branch':      branch,
            'beam_angle':  beam_angle,
            'error_deg':   error,
        }

        logger.debug(
            f"AZ={azimuth_deg:+.1f}° EL={elevation_deg:+.1f}° → "
            f"Face {face+1} active, "
            f"branch {branch} ({beam_angle}°), "
            f"error={error:.1f}°"
        )

        return result

    def apply(self, azimuth_deg: float,
              elevation_deg: float,
              rf_switch) -> dict:
        """
        Compute and immediately apply to hardware.
        Convenience function used by main.py.

        Returns the same dict as compute().
        """
        result = self.compute(azimuth_deg, elevation_deg)

        active_face   = result['active_face']
        inactive_face = 1 - active_face
        branch        = result['branch']

        # Set active face to best branch
        rf_switch.set_face(active_face, branch)

        # Set inactive face to idle (branch 0)
        rf_switch.set_face_idle(inactive_face)

        return result

    def _best_branch(self, target_angle_deg: float) -> tuple:
        """
        Find the branch whose steering angle is closest to target.
        Returns (branch_index, beam_angle_deg).
        """
        best_branch = 0
        best_error  = float('inf')

        for i, angle in enumerate(BRANCH_ANGLES_DEG):
            error = abs(angle - target_angle_deg)
            if error < best_error:
                best_error  = error
                best_branch = i

        return best_branch, BRANCH_ANGLES_DEG[best_branch]

    def _print_branch_table(self):
        """Print branch lookup table at startup for verification."""
        logger.info("Branch table:")
        logger.info(f"  {'Branch':8s} {'RF port':8s} {'Beam angle':12s} {'3-bit code'}")
        codes = [(0,0,0),(0,0,1),(0,1,0),(0,1,1)]
        for i, angle in enumerate(BRANCH_ANGLES_DEG):
            v1,v2,v3 = codes[i]
            logger.info(
                f"  {i:8d} {'RF'+str(i+1):8s} {angle:8.1f}°     "
                f"V1={v1} V2={v2} V3={v3}"
            )
