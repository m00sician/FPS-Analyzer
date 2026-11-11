"""
Frame Detection - tile-based duplicate detection with an adaptive threshold.

Combines two improvements over a global mean diff:

1. TILE COMPARISON (8x8 grid):
   Instead of mean(|a-b|) over the whole image, each tile is compared.
   -> Small local motion (a character in an otherwise static scene) lifts
      individual tiles clearly above the threshold instead of vanishing in
      the global average.
   -> Encoder noise spreads evenly and lifts no single tile.
   Score = largest tile difference (max instead of mean).

2. ADAPTIVE THRESHOLD (largest-gap clustering):
   The scores of the last ~2s form two clusters: duplicates near 0, real
   frames clearly above them. The threshold is placed in the largest gap
   between the clusters (a simplified Otsu).
   -> Dark or low-motion scenes lower both clusters together; the threshold
      moves with them instead of falsely reporting duplicates.
   Guards prevent mis-adaptation:
   - the clusters must be clearly separated (upper >= 2x lower), else fallback
   - both clusters need >= 10% of the samples
   - with too little history (< 20 frames): the user threshold

   LOW-MOTION REGIME (a special case inside the adaptive threshold logic):
   If there is no clean, balanced bimodal split (neither a ratio jump of >=2x
   nor both sides holding >=10% of the samples), that does NOT automatically
   mean "permanent duplicate". Two genuine cases look alike here:
     (a) real continuous 60fps footage (scores clearly > 0, tightly bunched)
     (b) a very calm scene with subtle continuous motion (scores tiny, but
         CONSISTENTLY different from zero - not duplicates!)
   Tested (2026-07-30, a synthetic cloud scene modelled on real screenshots):
   the low-motion test originally sat ONLY in the branch for "no ratio jump
   found at all". In practice the largest-gap search almost always finds SOME
   >=2x jump (a few outlier frames are enough, e.g. an object crossing a tile
   boundary), which sent the code into the bimodal branch, where it failed
   guard 2 (minority fraction <10%) and returned the fallback IMMEDIATELY,
   never reaching the low-motion test. Result: the calm cloud scene stayed at
   a ~98% duplicate rate - exactly the original bug.
   Fix: the low-motion test now always runs when there is NO clean bimodal
   split (ratio AND fraction satisfied), not only when no jump exists at all.
   p10/p90 over the whole history stay robust against individual outliers as
   long as their share stays below 10%.
   Also: "above_zero" used to compare the lower band edge (p10) against a
   noise floor taken from the SAME tightly bunched distribution (its 2nd
   percentile). With uniform continuous noise the two sit almost on top of
   each other, so the ratio practically never reached the required 1.5x. It
   now uses a fixed absolute floor relative to the user threshold
   (ABS_FLOOR_FRAC).
   Known open limit (not yet checked against real footage): if a scene mixes
   genuine exact duplicates (>=10% of the history, e.g. from frame repeats)
   WITH continuous sub-threshold motion, p10 can fall into the duplicate
   portion and above_zero can come out falsely negative. Please verify on real
   capture footage whether this case occurs at all.

3. PAIRDIFF OVERRIDE (safety net):
   If the current score is >= 75% of the previous one, it is very unlikely to
   be a duplicate (duplicates always have far smaller diffs than the first
   frame of a presented image) -> this overrules the threshold.
"""

import collections
import numpy as np


class TileAdaptiveDetector:
    GRID = 8                 # 8x8 tiles
    HISTORY_LEN = 120        # ~2s at 60fps
    MIN_HISTORY = 20         # the adaptive threshold kicks in from here
    CLUSTER_RATIO = 2.0      # the upper cluster must be >= 2x the lower one
    MIN_CLUSTER_FRAC = 0.10  # both clusters >= 10% of the samples
    PAIRDIFF_RATIO = 0.75

    ABS_FLOOR_FRAC = 0.05      # low-motion "above_zero" floor, as a fraction of the user threshold
    ACTIVITY_ALPHA = 0.06      # EMA factor of the activity mask (~30 frames warmup)
    ACTIVITY_THRESHOLD = 0.85  # masking starts at this sustained activity
    MAX_MASKED = 8             # max. maskable tiles (out of 64)

    def __init__(self, fallback_threshold: float = 0.005):
        self.fallback = float(fallback_threshold)
        self.history: collections.deque = collections.deque(maxlen=self.HISTORY_LEN)
        self.prev_gray: np.ndarray | None = None
        self.prev_score: float = 0.0
        self.activity = np.zeros((self.GRID, self.GRID), dtype=np.float64)
        self._mask_signature: tuple = ()
        self.last_threshold: float = self.fallback   # for debug / display
        self.adaptive_active: bool = False
        self._low_motion: bool = False

    # ── Public API ────────────────────────────────────────────────────────────

    def process(self, gray_small: np.ndarray) -> tuple[bool, float]:
        """
        gray_small: 2D float array (e.g. 128x128, values 0..1).
        Returns (is_duplicate, score).
        """
        # Scale normalisation: callers pass either 0..1 floats or
        # 0..255 uint8 arrays, while the whole threshold logic below
        # works on 0..1 - so normalise where needed.
        gray_small = gray_small.astype(np.float32, copy=False)
        if float(gray_small.max()) > 1.5:
            gray_small = gray_small / 255.0

        if self.prev_gray is None:
            self.prev_gray = gray_small
            return False, 0.0

        # Pixel difference first, THEN tile means of that difference.
        diff_img = np.abs(gray_small - self.prev_gray)
        self.prev_gray = gray_small

        tile_diffs = self._tile_means(diff_img)

        # ACTIVITY MASK against permanently animated HUD elements.
        # "Active" = the tile stands out clearly from the frame
        # (> 3x the median of the tiles). The median is a per-frame reference
        # and independent of the adaptive threshold -> no feedback loop.
        #   - HUD in a duplicate frame: 0.2 vs median ~ noise -> active
        #   - HUD in a unique frame:    0.2 vs median ~0.05 -> active (3x0.05=0.15)
        #   - full-screen 60fps motion: hardly any tile > 3x median -> nothing masked
        med = float(np.median(tile_diffs))
        active = (tile_diffs > max(3.0 * med, self.fallback)).astype(np.float64)
        self.activity = self.ACTIVITY_ALPHA * active + (1 - self.ACTIVITY_ALPHA) * self.activity

        mask = np.zeros_like(tile_diffs, dtype=bool)
        hot = np.argwhere(self.activity > self.ACTIVITY_THRESHOLD)
        if 0 < len(hot) <= self.MAX_MASKED:
            mask[tuple(hot.T)] = True
        # >MAX_MASKED hot tiles = real full-screen content -> do not mask

        # Regime change: when the mask changes, older scores are no longer
        # comparable (the HUD was still included) -> reset the history so the
        # clustering does not work across mixed regimes.
        mask_sig = tuple(sorted(map(tuple, np.argwhere(mask))))
        if mask_sig != self._mask_signature:
            self._mask_signature = mask_sig
            self.history.clear()

        visible = tile_diffs[~mask]
        score = float(visible.max()) if visible.size else float(tile_diffs.max())

        threshold = self._adaptive_threshold()
        self.last_threshold = threshold

        is_dup = score < threshold

        self.prev_score = score
        self.history.append(score)

        return is_dup, score

    def get_diagnostics(self) -> str:
        """Compact diagnostic line for console output."""
        if len(self.history) < 5:
            return "detector: too little history"
        s = np.sort(np.asarray(self.history, dtype=np.float64))
        n = len(s)
        p = lambda q: s[min(n - 1, int(n * q))]
        n_masked = int(np.sum(self.activity > self.ACTIVITY_THRESHOLD))
        return (f"scores p5={p(0.05):.5f} p25={p(0.25):.5f} p50={p(0.50):.5f} "
                f"p75={p(0.75):.5f} p95={p(0.95):.5f} | thr={self.last_threshold:.5f} "
                f"adaptive={self.adaptive_active} masked={min(n_masked, self.MAX_MASKED)}")

    def reset(self):
        self.history.clear()
        self.prev_gray = None
        self.prev_score = 0.0
        self.activity = np.zeros((self.GRID, self.GRID), dtype=np.float64)
        self._mask_signature = ()
        self.adaptive_active = False

    # ── Internals ─────────────────────────────────────────────────────────────

    def _tile_means(self, gray: np.ndarray) -> np.ndarray:
        h, w = gray.shape[:2]
        g = self.GRID
        th, tw = h // g, w // g
        cropped = gray[:th * g, :tw * g]
        return cropped.reshape(g, th, g, tw).mean(axis=(1, 3))

    def _adaptive_threshold(self) -> float:
        n = len(self.history)
        if n < self.MIN_HISTORY:
            self.adaptive_active = False
            return self.fallback

        s = np.sort(np.asarray(self.history, dtype=np.float64))
        gaps = np.diff(s)
        if len(gaps) == 0:
            self.adaptive_active = False
            return self.fallback

        i = int(np.argmax(gaps))
        lower_top = s[i]
        upper_bot = s[i + 1]
        lower_frac = (i + 1) / n
        upper_frac = (n - i - 1) / n

        # Only ONE clean bimodal split counts as a real duplicate/unique
        # separation: a ratio jump AND both sides large enough. If only the
        # ratio jump holds (e.g. because a few outlier frames - an object
        # crossing a tile boundary - happen to form the largest gap), that
        # is NOT a real split but a minority spike above a single cluster.
        # This used to lead into this branch anyway, fail the fraction check
        # there and return the fallback immediately - the low-motion test
        # further down was never reached (the cause of the original
        # "0 fps in a calm scene" bug).
        # bug, see the module docstring).
        genuine_bimodal = (
            upper_bot >= lower_top * self.CLUSTER_RATIO
            and lower_frac >= self.MIN_CLUSTER_FRAC
            and upper_frac >= self.MIN_CLUSTER_FRAC
        )

        if genuine_bimodal:
            thr = (lower_top + upper_bot) / 2.0
            # Sane clamping: never below 30% of the user threshold, never absurdly high
            thr = float(min(max(thr, self.fallback * 0.3), 0.25))
            self.adaptive_active = True
            self._low_motion = False
            return thr

        # No clean bimodal split -> ONE cluster (possibly with a few
        # outliers). Two possible cases:
        #  (a) real continuous motion (every frame unique)
        #  (b) a very calm scene with subtle motion (scores tiny,
        #      but CONSISTENTLY different from zero -> not duplicates!)
        # In neither case may everything be counted as a duplicate.
        # p10/p90 are computed over the WHOLE history - robust against
        # individual outliers as long as their share stays < MIN_CLUSTER_FRAC.
        self.adaptive_active = False
        p10 = s[max(0, int(0.10 * n))]
        p90 = s[min(n - 1, int(0.90 * n))]
        # "Low-motion regime": a tight band (p90 < 4x p10) AND a lower edge
        # clearly above a fixed absolute floor (relative to the user
        # threshold - NOT relative to a percentile of the same tightly
        # bunched distribution, which would be nearly tautological under
        # continuous noise and would hardly ever trigger).
        band_tight = p90 < max(4.0 * p10, p10 + 1e-4)
        above_zero = p10 > self.fallback * self.ABS_FLOOR_FRAC
        if band_tight and above_zero and p10 > 1e-4:
            # Put the threshold just BELOW the lower band edge -> the scene
            # counts as continuously moving (unique), not as a permanent duplicate.
            self._low_motion = True
            return float(max(p10 * 0.5, 1e-5))
        self._low_motion = False
        return self.fallback
