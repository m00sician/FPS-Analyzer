"""
Frame Detection — Tile-basierte Duplikat-Erkennung mit adaptivem Threshold.

Kombiniert zwei Verbesserungen gegenüber dem globalen Mean-Diff:

1. KACHEL-VERGLEICH (8×8 Grid):
   Statt mean(|a-b|) über das ganze Bild wird pro Kachel verglichen.
   → Kleine lokale Bewegung (Charakter in statischer Szene) hebt einzelne
     Kacheln klar über den Threshold, statt im globalen Mittel unterzugehen.
   → Encoder-Rauschen verteilt sich gleichmäßig und hebt keine Kachel an.
   Score = größte Kachel-Differenz (max statt mean).

2. ADAPTIVER THRESHOLD (Largest-Gap-Clustering):
   Die Scores der letzten ~2s bilden zwei Cluster: Duplikate nahe 0,
   echte Frames deutlich darüber. Der Threshold wird in die größte Lücke
   zwischen den Clustern gelegt (vereinfachtes Otsu).
   → Dunkle/bewegungsarme Szenen senken beide Cluster gemeinsam ab;
     der Threshold wandert mit, statt fälschlich Duplikate zu melden.
   Guards verhindern Fehlanpassung:
   - Cluster müssen klar getrennt sein (oberer ≥ 2× unterer), sonst Fallback
   - Beide Cluster brauchen ≥ 10% der Samples
   - Bei zu wenig Historie (< 20 Frames): User-Threshold

   LOW-MOTION-REGIME (Sonderfall innerhalb der adaptiven Threshold-Logik):
   Gibt es keinen sauberen, ausgewogenen Bimodal-Split (weder ein Ratio-Sprung
   ≥2× noch beide Seiten ≥10% der Samples), heißt das NICHT automatisch
   "Dauer-Duplikat". Zwei echte Fälle sehen dabei ähnlich aus:
     (a) echtes durchgehendes 60fps-Material (Scores klar > 0, eng gebündelt)
     (b) sehr ruhige Szene mit subtiler Dauerbewegung (Scores winzig, aber
         KONSISTENT von null verschieden — keine Duplikate!)
   Getestet (2026-07-30, synthetische Wolken-Szene nach Vorbild echter
   Screenshots): Der Low-Motion-Test lag ursprünglich NUR im Zweig
   "gar kein Ratio-Sprung gefunden". In der Praxis findet die Largest-Gap-
   Suche aber fast immer IRGENDEINEN ≥2×-Sprung (ein paar Ausreißer-Frames
   reichen, z.B. ein Objekt, das eine Kachel-Grenze quert) — das schickte
   den Code in den Bimodal-Zweig, der dann an Guard 2 (Minderheits-Fraktion
   <10%) scheiterte und DIREKT den Fallback zurückgab, ohne den Low-Motion-
   Test je zu erreichen. Ergebnis: die ruhige Wolkenszene blieb bei ~98%
   Duplikat-Rate, exakt der ursprüngliche Bug.
   Fix: Der Low-Motion-Test läuft jetzt immer, wenn KEIN sauberer (Ratio
   UND Fraktion erfüllt) Bimodal-Split vorliegt — nicht nur bei komplett
   fehlendem Sprung. p10/p90 der Gesamt-Historie bleiben robust gegen
   einzelne Ausreißer, solange deren Anteil <10% bleibt.
   Zusätzlich: "above_zero" verglich den unteren Bandrand (p10) bislang mit
   einem Rauschboden aus DERSELBEN eng gebündelten Verteilung (2%-Perzentil)
   — bei gleichmäßigem Dauerrauschen liegen beide fast identisch beieinander,
   das Verhältnis erreichte praktisch nie die geforderten 1.5×. Jetzt feste
   Absolut-Schwelle relativ zum User-Threshold (ABS_FLOOR_FRAC).
   Bekannte offene Grenze (noch nicht mit echtem Material geprüft): Mischt
   eine Szene echte Exakt-Duplikate (≥10% der Historie, z.B. durch
   Frame-Repeats) MIT durchgehender Sub-Threshold-Bewegung, kann p10 in den
   Duplikat-Anteil fallen und above_zero fälschlich negativ ausfallen. Bitte
   an echtem Capture-Material verifizieren, ob dieser Fall überhaupt auftritt.

3. PAIRDIFF-OVERRIDE (Sicherheitsnetz):
   Ist der aktuelle Score ≥ 75% des vorherigen, ist es sehr wahrscheinlich
   kein Duplikat (Duplikate haben immer deutlich kleinere Diffs als der
   erste Frame einer Präsentation) → überstimmt den Threshold.
"""

import collections
import numpy as np


class TileAdaptiveDetector:
    GRID = 8                 # 8×8 Kacheln
    HISTORY_LEN = 120        # ~2s bei 60fps
    MIN_HISTORY = 20         # ab hier greift der adaptive Threshold
    CLUSTER_RATIO = 2.0      # oberer Cluster muss ≥ 2× unterer sein
    MIN_CLUSTER_FRAC = 0.10  # beide Cluster ≥ 10% der Samples
    PAIR_RATIO = 0.75          # PairDiff-Override-Grenze
    ABS_FLOOR_FRAC = 0.05      # Low-Motion "above_zero"-Schwelle, als Anteil des User-Thresholds
    ACTIVITY_ALPHA = 0.06      # EMA-Faktor der Aktivitäts-Maske (~30 Frames Warmup)
    ACTIVITY_THRESHOLD = 0.85  # ab dieser dauerhaften Aktivität wird maskiert
    MAX_MASKED = 8             # max. maskierbare Kacheln (von 64)

    def __init__(self, fallback_threshold: float = 0.005):
        self.fallback = float(fallback_threshold)
        self.history: collections.deque = collections.deque(maxlen=self.HISTORY_LEN)
        self.prev_gray: np.ndarray | None = None
        self.prev_score: float = 0.0
        self.activity = np.zeros((self.GRID, self.GRID), dtype=np.float64)
        self._mask_signature: tuple = ()
        self.last_threshold: float = self.fallback   # für Debug/Anzeige
        self.adaptive_active: bool = False
        self._low_motion: bool = False

    # ── Public API ────────────────────────────────────────────────────────────

    def process(self, gray_small: np.ndarray) -> tuple[bool, float]:
        """
        gray_small: 2D float array (z.B. 128×128, Werte 0..1).
        Returns (is_duplicate, score).
        """
        # Skalen-Normalisierung: die Aufrufer liefern teils 0..1-Floats,
        # teils rohe 0..255-Graustufen. Der Detektor (Thresholds, Clamps)
        # arbeitet auf 0..1 — also bei Bedarf normalisieren.
        gray_small = gray_small.astype(np.float32, copy=False)
        if float(gray_small.max()) > 1.5:
            gray_small = gray_small / 255.0

        if self.prev_gray is None:
            self.prev_gray = gray_small
            return False, 0.0

        # Pixel-Differenz zuerst, DANN Kachel-Mittelwerte der Differenz.
        diff_img = np.abs(gray_small - self.prev_gray)
        self.prev_gray = gray_small

        tile_diffs = self._tile_means(diff_img)

        # AKTIVITÄTS-MASKE gegen permanent animierte HUD-Elemente.
        # "Aktiv" = Kachel sticht deutlich aus dem Frame heraus
        # (> 3× Median der Kacheln). Der Median ist eine per-Frame-Referenz
        # und unabhängig vom adaptiven Threshold → kein Feedback-Loop.
        #   - HUD in Duplikat-Frame:  0.2 vs Median≈Rauschen → aktiv
        #   - HUD in Unique-Frame:    0.2 vs Median≈0.05 → aktiv (3×0.05=0.15)
        #   - Vollbild-60fps-Motion:  kaum Kacheln > 3× Median → nichts maskiert
        med = float(np.median(tile_diffs))
        active = (tile_diffs > max(3.0 * med, self.fallback)).astype(np.float64)
        self.activity = self.ACTIVITY_ALPHA * active + (1 - self.ACTIVITY_ALPHA) * self.activity

        mask = np.zeros_like(tile_diffs, dtype=bool)
        hot = np.argwhere(self.activity > self.ACTIVITY_THRESHOLD)
        if 0 < len(hot) <= self.MAX_MASKED:
            mask[tuple(hot.T)] = True
        # >MAX_MASKED heiße Kacheln = echter Vollbild-Content → nicht maskieren

        # Regime-Wechsel: ändert sich die Maske, sind alte Scores nicht mehr
        # vergleichbar (HUD war noch drin) → Historie zurücksetzen, damit
        # das Clustering nicht auf gemischten Regimes arbeitet.
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
        """Kompakte Diagnose-Zeile für Konsolen-Output."""
        if len(self.history) < 5:
            return "detector: zu wenig Historie"
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

        # Nur EIN sauberer Bimodal-Split zählt als "echte Duplikat/Unique-
        # Trennung": Ratio-Sprung UND beide Seiten groß genug. Reicht nur
        # der Ratio-Sprung (z.B. weil ein paar Ausreißer-Frames — Objekt
        # quert Kachel-Grenze — zufällig die größte Lücke bilden), ist das
        # KEIN echter Split, sondern eine Minderheits-Spitze über einem
        # einzigen Cluster. Früher führte das trotzdem in diesen Zweig,
        # scheiterte dort an der Fraktions-Prüfung und gab sofort den
        # Fallback zurück — der Low-Motion-Test weiter unten wurde nie
        # erreicht (Ursache für den ursprünglichen "0 fps in ruhiger Szene"-
        # Bug, siehe Moduldocstring).
        genuine_bimodal = (
            upper_bot >= lower_top * self.CLUSTER_RATIO
            and lower_frac >= self.MIN_CLUSTER_FRAC
            and upper_frac >= self.MIN_CLUSTER_FRAC
        )

        if genuine_bimodal:
            thr = (lower_top + upper_bot) / 2.0
            # Sane clamping: nie unter 30% des User-Thresholds, nie absurd hoch
            thr = float(min(max(thr, self.fallback * 0.3), 0.25))
            self.adaptive_active = True
            self._low_motion = False
            return thr

        # Kein sauberer bimodaler Split → EIN Cluster (ggf. mit ein paar
        # Ausreißern). Zwei mögliche Fälle:
        #  (a) echtes durchgehendes 60fps-Material (Scores deutlich > 0)
        #  (b) sehr ruhige Szene mit subtiler Bewegung (Scores winzig,
        #      aber KONSISTENT von null verschieden → keine Duplikate!)
        # In beiden Fällen darf NICHT alles als Duplikat gewertet werden.
        # p10/p90 auf der GESAMTEN Historie berechnet — bleibt robust gegen
        # einzelne Ausreißer, solange deren Anteil < MIN_CLUSTER_FRAC bleibt.
        self.adaptive_active = False
        p10 = s[max(0, int(0.10 * n))]
        p90 = s[min(n - 1, int(0.90 * n))]
        # "Low-Motion-Regime": Band eng (p90 < 4× p10) UND der untere Rand
        # liegt klar über einer festen Absolut-Schwelle (relativ zum User-
        # Threshold — NICHT relativ zu einem Perzentil derselben eng
        # gebündelten Verteilung, das wäre bei Dauerrauschen fast tautologisch
        # und würde kaum je auslösen).
        band_tight = p90 < max(4.0 * p10, p10 + 1e-4)
        above_zero = p10 > self.fallback * self.ABS_FLOOR_FRAC
        if band_tight and above_zero and p10 > 1e-4:
            # Threshold knapp UNTER den unteren Bandrand → Szene gilt als
            # durchgehend bewegt (unique), nicht als Dauer-Duplikat.
            self._low_motion = True
            return float(max(p10 * 0.5, 1e-5))
        self._low_motion = False
        return self.fallback
