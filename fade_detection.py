"""
Fade Detection — erkennt uniforme Übergangs-Frames (Fade to white/black/color).

Problem:
  Ein Fade-Übergang (Kamera zoomt raus, Bild wird kurz einfarbig) hat quasi
  keine räumliche Varianz. Der Duplikat-Detektor sieht identische Frames und
  meldet 0 FPS / 500ms+ Frametime-Spikes — was Min/Max/Avg und den Graphen
  verfälscht.

Lösung:
  Frames mit sehr niedriger räumlicher Varianz (Standardabweichung der
  Graustufen) werden als Fade markiert. Um jeden Fade-Block wird ein
  Puffer (Default 2s) gelegt, dessen Frames aus den Statistiken
  ausgeschlossen werden. Im Graphen bleibt die Lücke sichtbar (Unterbrechung).

  Der Puffer NACH dem Fade ist zum Analyse-Zeitpunkt noch nicht bekannt,
  daher arbeitet der Detektor in zwei Stufen:
    1. Live pro Frame: is_fade(gray) markiert uniforme Frames sofort.
    2. Nachbearbeitung: finalize_excluded() expandiert alle Fade-Blöcke
       um den Puffer und liefert das finale Set ausgeschlossener Indizes.
"""

import numpy as np


class FadeDetector:
    def __init__(self, source_fps: float,
                 std_threshold: float = 8.0,
                 buffer_seconds: float = 2.0,
                 min_fade_frames: int = 2):
        """
        std_threshold:  Graustufen-Standardabweichung unter der ein Frame als
                        uniform gilt (0..255-Skala). ~8 fängt Fades sicher,
                        ohne dunkle-aber-strukturierte Szenen zu treffen.
        buffer_seconds: Puffer vor und nach jedem Fade-Block.
        min_fade_frames: Mindestlänge eines Fade-Blocks (gegen Einzelframe-
                        Fehlalarme durch z.B. Vollbild-Effekte).
        """
        self.source_fps    = max(1.0, source_fps)
        self.std_threshold = float(std_threshold)
        self.buffer_frames = int(round(buffer_seconds * self.source_fps))
        self.min_fade_frames = int(min_fade_frames)

        self._is_fade_frame: list[bool] = []   # pro Frame-Index

    def process(self, gray: np.ndarray) -> bool:
        """
        Live-Check pro Frame. gray = Graustufenbild (0..255 oder 0..1).
        Returns True wenn der Frame uniform (Fade-Kandidat) ist.
        """
        g = gray
        if g.dtype != np.float32 and g.dtype != np.float64:
            g = g.astype(np.float32)
        # Normalisierung auf 0..255-Skala für konsistenten Threshold
        if float(g.max()) <= 1.5:
            g = g * 255.0

        std = float(g.std())
        is_fade = std < self.std_threshold
        self._is_fade_frame.append(is_fade)
        return is_fade

    def finalize_excluded(self) -> set:
        """
        Nach der Analyse aufrufen. Expandiert jeden zusammenhängenden
        Fade-Block (>= min_fade_frames) um buffer_frames in beide Richtungen
        und liefert das Set aller ausgeschlossenen Frame-Indizes.
        """
        flags = self._is_fade_frame
        n = len(flags)
        excluded: set = set()

        i = 0
        while i < n:
            if not flags[i]:
                i += 1
                continue
            # Fade-Block finden [start, end)
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
        Liefert die reinen Fade-Blöcke als [(start, end), ...] (ohne Puffer)
        — nützlich für Logging/Diagnose.
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
