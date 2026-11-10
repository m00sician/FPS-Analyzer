"""
Fade Detection - finds uniform transition frames (fade to white/black/colour).

Problem:
A fade transition (the camera pulls back, the image briefly turns a single
colour) has almost no spatial variance. The duplicate detector sees identical
frames and reports 0 FPS and 500ms+ frame time spikes, which distorts
min/max/avg and the graph.

Solution:
Frames with very low spatial variance (standard deviation of the greyscale
image) are marked as fades. A buffer (2s by default) is placed around every
fade block, and its frames are excluded from the statistics. The gap stays
visible in the graph as a break in the line.

The buffer AFTER a fade is not yet known while the analysis runs, so the
detector works in two stages:
  1. Live, per frame: is_fade(gray) marks uniform frames immediately.
  2. Post-processing: finalize_excluded() expands every fade block by the
     buffer and returns the final set of excluded indices.
"""

import numpy as np


class FadeDetector:
    def __init__(self, source_fps: float,
                 std_threshold: float = 8.0,
                 buffer_seconds: float = 2.0,
                 min_fade_frames: int = 2):
        """
        std_threshold:  greyscale standard deviation below which a frame counts
                        as uniform (0..255 scale). ~8 catches fades reliably
                        without hitting dark-but-detailed scenes.
        buffer_seconds: buffer before and after every fade block.
        min_fade_frames: minimum length of a fade block (guards against single
                        frame false alarms from e.g. full-screen effects).
        """
        self.source_fps    = max(1.0, source_fps)
        self.std_threshold = float(std_threshold)
        self.buffer_frames = int(round(buffer_seconds * self.source_fps))
        self.min_fade_frames = int(min_fade_frames)

        self._is_fade_frame: list[bool] = []   # one entry per frame index

    def process(self, gray: np.ndarray) -> bool:
        """
        Per-frame live check. gray = greyscale image (0..255 or 0..1).
        Returns True when the frame is uniform (a fade candidate).
        """
        g = gray
        if g.dtype != np.float32 and g.dtype != np.float64:
            g = g.astype(np.float32)
        # Normalise to the 0..255 scale so the threshold stays consistent
        if float(g.max()) <= 1.5:
            g = g * 255.0

        std = float(g.std())
        is_fade = std < self.std_threshold
        self._is_fade_frame.append(is_fade)
        return is_fade

    def finalize_excluded(self) -> set:
        """
        Call this after the analysis. Expands every contiguous fade block
        (>= min_fade_frames) by buffer_frames in both directions and returns
        the set of all excluded frame indices.
        """
        flags = self._is_fade_frame
        n = len(flags)
        excluded: set = set()

        i = 0
        while i < n:
            if not flags[i]:
                i += 1
                continue
            # Find the fade block [start, end)
            start = i
            while i < n and flags[i]:
                i += 1
            end = i
            if (end - start) >= self.min_fade_frames:
                lo = max(0, start - self.buffer_frames)
                hi = min(n, end + self.buffer_frames)
                excluded.update(range(lo, hi))

        return excluded

    def fade_blocks(self) -> list:
        """
        Returns the raw fade blocks as [(start, end), ...] (without the
        buffer) - useful for logging and diagnostics.
        """
        flags = self._is_fade_frame
        n = len(flags)
        blocks = []
        i = 0
        while i < n:
            if not flags[i]:
                i += 1
                continue
            start = i
            while i < n and flags[i]:
                i += 1
            if (i - start) >= self.min_fade_frames:
                blocks.append((start, i))
        return blocks
