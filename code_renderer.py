"""
Code Renderer für FPS Analyzer
Ersetzt den PNG Template Renderer vollständig.

Keine externen PNG-Dateien mehr — alles wird programmatisch gezeichnet.
Exakt dasselbe visuelle Ergebnis wie die Templates:
  - Schwarzer semi-transparenter Hintergrund (alpha=128/255 = 50%)
  - Horizontale Grid-Linien (hellgrau, alpha=179/255 = 70%)
  - Titel "FRAME RATE" / "FRAME TIME" (Bebas Neue mit Stroke)
  - Achsenbeschriftungen rechts (automatisch aus scale berechnet)
  - Dynamische Linie darüber (cv2.polylines)

Vorteile gegenüber PNG Templates:
  - Keine templates/ Abhängigkeit
  - Scale-Änderungen wirken sofort ohne neue PNG-Datei
  - Neue Graphen / Elemente in wenigen Zeilen Code
  - Automatische Skalierung auf jede Auflösung
"""

import time
import collections
import itertools
import numpy as np
import cv2
from typing import Dict, List, Optional, Tuple

# ── Optionale Dependencies ─────────────────────────────────────────────────────
try:
    # noqa: F401 - Image und ImageFont sehen ungenutzt aus, gehoeren aber zur
    # Pruefung: nur wenn ALLE drei importierbar sind, ist Pillow wirklich
    # vollstaendig. Werden sie entfernt, steht PILLOW faelschlich auf True
    # und der Fehler faellt erst spaeter beim Zeichnen auf.
    from PIL import Image, ImageDraw, ImageFont  # noqa: F401
    PILLOW = True
except ImportError:
    PILLOW = False

try:
    from cuda_accelerator import get_blender as _get_blender
    _cuda_blender = _get_blender()
except Exception:
    _cuda_blender = None

try:
    from color_manager import hex_to_bgr
except ImportError:
    def hex_to_bgr(hex_color):
        """'#RRGGBB' → (B, G, R) für OpenCV. Fallback wenn color_manager fehlt."""
        if isinstance(hex_color, (tuple, list)):
            return tuple(hex_color)
        h = str(hex_color).lstrip('#')
        if len(h) != 6:
            return (0, 255, 0)
        try:
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return (b, g, r)   # BGR!
        except ValueError:
            return (0, 255, 0)

try:
    from png_template_renderer import FontSizeConfig
except ImportError:
    class FontSizeConfig:
        @staticmethod
        def get_absolute_size(key, w, h):
            scale = min(w/1920, h/1080)
            sizes = {'fps_number': 120, 'stats_text': 24, 'border_thickness': 2,
                     'graph_title': 36, 'axis_label': 22}
            return max(8, int(sizes.get(key, 24) * scale))
        @staticmethod
        def get_resolution_category(w, h):
            if h >= 2160: return '4K'
            if h >= 1440: return '1440p'
            if h >= 1080: return '1080p'
            return '720p'


# ── Konstanten (aus Template-Analyse) ──────────────────────────────────────────
# Hintergrund: schwarz, 50% Deckkraft
BG_COLOR   = (0, 0, 0)
BG_ALPHA   = 128 / 255.0        # 0.502

# Grid-Linien: hellgrau, 70% Deckkraft
GRID_COLOR = (145, 145, 145)
GRID_ALPHA = 179 / 255.0        # 0.702

# Titel + Achsen: weiß, voll opak
LABEL_COLOR     = (255, 255, 255)
LABEL_STROKE    = (0, 0, 0)

# Graph-Struktur (relativ zur Template-Größe, aus Pixel-Analyse extrahiert)
# FPS Template 1840x580: Graph-Bereich y=73..557 (4 Sections à 121px)
# Titel-Bereich: 0..73 (transparent), Graph: 73..557, Bottom-Pad: 557..580
TITLE_H_RATIO  = 73  / 580    # ~12.6% der Höhe für Titel-Bereich
BOTTOM_RATIO   = 23  / 580    # ~4%  Bottom-Padding
# → Graph-Bereich: 12.6% .. 96% der Template-Höhe
# 4 gleichmäßige Grid-Linien inkl. oben und unten

import threading
# Kein globaler Text-Lock mehr nötig: _FontCache ist thread-lokal, jeder
# Worker rendert mit eigenen Font-Instanzen → echte Text-Parallelität.

MAX_GRAPH_POINTS = 180


# ═══════════════════════════════════════════════════════════════════════════════
# ██  MANUELLE TEXT-JUSTIERUNG  ██
# ═══════════════════════════════════════════════════════════════════════════════
# Feinjustierung der Textelemente per Hand. Alle Offset-Werte sind PIXEL bei
# 4K (2160p Höhe) und werden automatisch auf die Ausgabeauflösung skaliert —
# ein Wert von 10 verschiebt bei 1080p also um 5px, bei 4K um 10px.
#
#   *_DX  : Verschiebung horizontal (+ = nach rechts, - = nach links)
#   *_DY  : Verschiebung vertikal   (+ = nach unten,  - = nach oben)
#   *_SIZE: Größen-MULTIPLIKATOR (1.0 = Standard, 1.2 = 20% größer, 0.8 = kleiner)
#
# "TITLE"  = der Text ÜBER dem Graphen ("FRAME RATE" / "FRAME TIME")
# "LABELS" = die Achsenbeschriftungen RECHTS neben dem Graphen (60/30/0 bzw. ms)
# ───────────────────────────────────────────────────────────────────────────────

# ── FRAME RATE ──
FR_TITLE_DX   = 0      # "FRAME RATE" Text links/rechts
FR_TITLE_DY   = 0      # "FRAME RATE" Text hoch/runter
FR_TITLE_SIZE = 1.0    # "FRAME RATE" Textgröße (Multiplikator)
FR_LABELS_DX   = 0     # Achsenlabels (60/30/0) links/rechts
FR_LABELS_DY   = 0     # Achsenlabels hoch/runter
FR_LABELS_SIZE = 1.0   # Achsenlabels Textgröße (Multiplikator)
FR_LABELS_GAP  = 5     # Abstand der FR-Labels vom Graphen (4K-px, + = weiter weg)

# ── FRAME TIME ──
FT_TITLE_DX   = 0      # "FRAME TIME" Text links/rechts
FT_TITLE_DY   = 0      # "FRAME TIME" Text hoch/runter
FT_TITLE_SIZE = 1.0    # "FRAME TIME" Textgröße (Multiplikator)
FT_LABELS_DX   = 0     # ms-Labels links/rechts
FT_LABELS_DY   = 0     # ms-Labels hoch/runter
FT_LABELS_SIZE = 1.0   # ms-Labels Textgröße (Multiplikator)
FT_LABELS_GAP  = 5     # Abstand der FT-Labels vom Graphen (4K-px, + = weiter weg)

# ── FPS-Zahl oben links ──
FPS_NUM_DX   = 0       # FPS-Zahl links/rechts
FPS_NUM_DY   = 0       # FPS-Zahl hoch/runter
FPS_NUM_SIZE = 1.0     # FPS-Zahl Textgröße (Multiplikator)
# ═══════════════════════════════════════════════════════════════════════════════


def _tweak_for(title):
    """Liefert (title_dx, title_dy, title_size, lbl_dx, lbl_dy, lbl_size, lbl_gap) für einen Graph-Titel."""
    if title == "FRAME RATE":
        return (FR_TITLE_DX, FR_TITLE_DY, FR_TITLE_SIZE,
                FR_LABELS_DX, FR_LABELS_DY, FR_LABELS_SIZE, FR_LABELS_GAP)
    elif title == "FRAME TIME":
        return (FT_TITLE_DX, FT_TITLE_DY, FT_TITLE_SIZE,
                FT_LABELS_DX, FT_LABELS_DY, FT_LABELS_SIZE, FT_LABELS_GAP)
    return (0, 0, 1.0, 0, 0, 1.0, 5)


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _alpha_composite_rect(img: np.ndarray, x1: int, y1: int,
                           x2: int, y2: int, color: tuple, alpha: float):
    """Semi-transparentes Rechteck direkt in img compositen (in-place)."""
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return
    roi = img[y1:y2, x1:x2].astype(np.float32)
    fg  = np.array(color, dtype=np.float32)
    img[y1:y2, x1:x2] = (roi * (1 - alpha) + fg * alpha).astype(np.uint8)


def _alpha_composite_hline(img: np.ndarray, y: int, x1: int, x2: int,
                            color: tuple, alpha: float, thickness: int = 1):
    """Semi-transparente horizontale Linie."""
    half = thickness // 2
    _alpha_composite_rect(img, x1, y - half, x2, y + half + 1, color, alpha)


def _find_font(size: int):
    """Bebas Neue laden, Fallback auf verfügbare TTF."""
    if not PILLOW:
        return None
    import glob, platform, os
    dirs = (["C:/Windows/Fonts/",
             os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/")]
            if platform.system() == "Windows"
            else ["/usr/share/fonts/", "/usr/local/share/fonts/",
                  os.path.expanduser("~/.fonts/")])
    candidates = []
    for d in dirs:
        candidates += glob.glob(d + "**/*.ttf", recursive=True)
        candidates += glob.glob(d + "**/*.otf", recursive=True)
    bebas = [f for f in candidates if 'bebas' in f.lower()]
    path  = bebas[0] if bebas else (candidates[0] if candidates else None)
    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None


class _FontCache:
    """
    Hält geladene Pillow-Fonts THREAD-LOKAL im Cache (Größe als Key).

    FreeType (hinter Pillow) ist nicht thread-safe wenn sich DASSELBE
    Font-Objekt über Threads teilt. Durch thread-lokale Instanzen rendert
    jeder Worker-Thread mit seinem eigenen Font → kein globaler Lock nötig,
    echte Parallelität beim Text-Rendering.
    """
    _local = threading.local()

    @classmethod
    def get(cls, size: int):
        cache = getattr(cls._local, 'cache', None)
        if cache is None:
            cache = {}
            cls._local.cache = cache
        if size not in cache:
            cache[size] = _find_font(size)
        return cache[size]


def _apply_frosted_glass(overlay, gx, gy, gw, gh, blur_strength=25, darken=0.35):
    """
    Milchglas-Effekt: Bildbereich HINTER dem Panel (gx,gy,gw,gh) weichzeichnen
    und abdunkeln, direkt ins overlay schreiben.

    Performance-Trick: Downscale → Blur (klein) → Upscale. Das Hochskalieren
    erzeugt zusätzliche Weichheit, der Blur läuft auf einem Bruchteil der Pixel.

    blur_strength: 0..100 (höher = verschwommener)
    darken:        0..1  (0 = keine Abdunklung, 1 = schwarz)
    """
    h, w = overlay.shape[:2]
    x1, y1 = max(0, gx), max(0, gy)
    x2, y2 = min(w, gx + gw), min(h, gy + gh)
    if x2 <= x1 or y2 <= y1:
        return

    roi = overlay[y1:y2, x1:x2]
    rh, rw = roi.shape[:2]

    # Immer stark downscalen (fixer kleiner Zielbereich) → Blur ist billig und
    # konsistent schnell, unabhängig von der Panelgröße. Die Blur-Stärke steuert
    # primär den Kernel auf dem kleinen Bild + wie klein skaliert wird.
    target = max(60, int(200 - blur_strength))   # stärker = kleiner = weicher
    scale = min(1.0, target / max(rw, rh))
    small_w = max(1, int(rw * scale))
    small_h = max(1, int(rh * scale))

    small = cv2.resize(roi, (small_w, small_h), interpolation=cv2.INTER_AREA)
    k = max(1, int(blur_strength / 12) * 2 + 1)   # kleiner Kernel auf kleinem Bild
    small = cv2.GaussianBlur(small, (k, k), 0)
    blurred = cv2.resize(small, (rw, rh), interpolation=cv2.INTER_LINEAR)

    if darken > 0:
        blurred = (blurred.astype(np.float32) * (1.0 - darken)).astype(np.uint8)

    overlay[y1:y2, x1:x2] = blurred


def _composite_text_rgba(canvas, cx, cy, canvas_w, canvas_h,
                         grid_items, grid_ys, title, title_x, title_y,
                         label_x, label_fs, title_fs, vis_h_fn,
                         text_style, sw_label, sw_title):
    """
    Rendert Titel + Achsenlabels mit echtem Anti-Aliasing auf ein
    transparentes RGBA-Overlay und komponiert es alpha-korrekt in den Canvas.
    Erhält weiche Kanten (kein Masken-Threshold).
    Style: Hard Outline (Pillow-Stroke) / Drop Shadow (versetzte Kopie) / None.
    """
    if not PILLOW:
        return
    try:
        from PIL import Image as PILImage, ImageDraw as PILDraw
    except Exception:
        return

    # Transparentes RGBA-Bild in Canvas-Größe
    layer = PILImage.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    draw  = PILDraw.Draw(layer)

    def _draw_one(text, x, y, size, sw):
        font = _FontCache.get(size)
        if font is None:
            return
        try:
            bb = font.getbbox(text)
            y_off = -bb[1]
        except Exception:
            y_off = 0
        yy = y + y_off
        if text_style == 'Drop Shadow':
            off = max(2, sw)
            draw.text((x + off, yy + off), text, font=font, fill=(0, 0, 0, 255))
            draw.text((x, yy), text, font=font, fill=(255, 255, 255, 255))
        elif text_style == 'None':
            draw.text((x, yy), text, font=font, fill=(255, 255, 255, 255))
        else:   # Hard Outline
            draw.text((x, yy), text, font=font, fill=(255, 255, 255, 255),
                      stroke_width=max(1, sw), stroke_fill=(0, 0, 0, 255))

    # Achsenlabels
    for item, grid_y in zip(grid_items, grid_ys):
        if len(item) > 2 and item[2]:
            continue   # x-Präfix: kein Label
        label = item[0]
        lby = grid_y - vis_h_fn(label) // 2
        lby = max(0, min(canvas_h - label_fs, lby))
        _draw_one(label, label_x, lby, label_fs, sw_label)

    # Titel
    _draw_one(title, title_x, title_y, title_fs, sw_title)

    # Alpha-korrekt in den RGBA-Canvas kompositen (über bestehende BG/Grid)
    layer_np = np.array(layer)   # (H, W, 4) RGBA
    la = layer_np[:, :, 3:4].astype(np.float32) / 255.0
    lc = layer_np[:, :, :3].astype(np.float32)
    ca = canvas[:, :, 3:4].astype(np.float32) / 255.0
    cc = canvas[:, :, :3].astype(np.float32)
    # Standard "over"-Kompositing
    out_a = la + ca * (1 - la)
    safe_a = np.where(out_a > 1e-6, out_a, 1.0)
    out_c = (lc * la + cc * ca * (1 - la)) / safe_a
    canvas[:, :, :3] = np.clip(out_c, 0, 255).astype(np.uint8)
    canvas[:, :, 3]  = np.clip(out_a[:, :, 0] * 255, 0, 255).astype(np.uint8)


def _draw_text_pillow(img: np.ndarray, text: str, x: int, y: int,
                      font_size: int, color=(255,255,255),
                      stroke_color=(0,0,0), stroke_width=3) -> np.ndarray:
    """
    Text mit Pillow TrueType auf ROI zeichnen.
    Nur das minimale ROI wird konvertiert (schnell).
    """
    if not PILLOW:
        return _draw_text_opencv(img, text, x, y, font_size, color, stroke_color, stroke_width)

    font = _FontCache.get(font_size)
    if font is None:
        return _draw_text_opencv(img, text, x, y, font_size, color, stroke_color, stroke_width)

    # Bounding Box ermitteln
    try:
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        y_off = -bbox[1]
    except Exception:
        tw, th, y_off = font_size * len(text), font_size, 0

    pad = stroke_width + 4
    # Unbeschnittene Layer-Geometrie — den Beschnitt macht der Blend.
    ox = x - pad
    oy = y - pad
    lw = (x + tw + pad * 2) - ox
    lh = (y + th + pad * 2 + int(th * 0.25)) - oy
    if lw <= 0 or lh <= 0:
        return img

    lx = x - ox
    ly = y - oy + y_off
    fill_rgb   = (color[2],        color[1],        color[0])
    stroke_rgb = (stroke_color[2], stroke_color[1], stroke_color[0])

    def _draw(pil):
        ImageDraw.Draw(pil).text(
            (lx, ly), text, font=font,
            fill=(fill_rgb[0], fill_rgb[1], fill_rgb[2], 255),
            stroke_width=stroke_width,
            stroke_fill=(stroke_rgb[0], stroke_rgb[1], stroke_rgb[2], 255))

    key = ('pillow', text, font_size, color, stroke_color, stroke_width,
           lw, lh, lx, ly)
    _blend_text_layer(img, _text_layer(key, (lw, lh), _draw), ox, oy)
    return img


def _draw_text_opencv(img, text, x, y, font_size,
                      color=(255,255,255), stroke_color=(0,0,0), stroke_width=2):
    scale = font_size / 40.0
    thick = max(1, font_size // 20)
    cv2.putText(img, text, (x, y + font_size),
                cv2.FONT_HERSHEY_SIMPLEX, scale, stroke_color, thick + stroke_width, cv2.LINE_AA)
    cv2.putText(img, text, (x, y + font_size),
                cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)
    return img


# ── Graph-Zeichner ─────────────────────────────────────────────────────────────

def draw_graph_background(img: np.ndarray,
                           gx: int, gy: int, gw: int, gh: int,
                           title: str,
                           grid_labels: List[str],
                           label_font_size: int,
                           title_font_size: int):
    """
    Zeichnet den Graph-Hintergrund exakt wie das PNG-Template:
      - Transparenter Titel-Bereich oben
      - Semi-transparenter schwarzer Hintergrund (50%)
      - 5 horizontale Grid-Linien (hellgrau 70%), gleichmäßig verteilt
      - Titel oben links (Bebas Neue)
      - Achsenbeschriftungen rechts außen
    """
    # Titel-Bereich Höhe (proportional wie im Template)
    title_h = int(gh * TITLE_H_RATIO / (1 - TITLE_H_RATIO - BOTTOM_RATIO))
    # Alternativ direkt: wir übergeben bereits den Graph-Bereich ohne Titel.
    # Der Aufrufer gibt gy so, dass Titel darüber liegt.

    # 1. Schwarzer Hintergrund (50% Deckkraft)
    _alpha_composite_rect(img, gx, gy, gx + gw, gy + gh, BG_COLOR, BG_ALPHA)

    # 2. Grid-Linien (5 Stück: oben, 3 Mitte, unten)
    n_lines = len(grid_labels)   # typisch 3 (top, mid, bottom) → aber wir haben 5 Linien
    # 5 gleichmäßige Linien entsprechend dem Template (4 Sektionen)
    n_sections = 4
    line_thickness = max(1, int(gh / 150))
    for i in range(n_sections + 1):
        ly = gy + int(i * gh / n_sections)
        _alpha_composite_hline(img, ly, gx, gx + gw, GRID_COLOR, GRID_ALPHA, line_thickness)

    # 3. Achsenbeschriftungen rechts (außerhalb des Graph-Bereichs)
    label_x = gx + gw + max(4, int(gw * 0.008))
    for i, label in enumerate(grid_labels):
        # grid_labels[0] = oben (max), grid_labels[-1] = unten (min)
        if len(grid_labels) == 3:
            positions = [0, 2, 4]   # oben, mitte, unten
        else:
            positions = list(range(len(grid_labels)))

        pos_idx = positions[i] if i < len(positions) else i
        label_y = gy + int(pos_idx * gh / n_sections) - label_font_size // 2
        label_y = max(gy, min(gy + gh - label_font_size, label_y))
        _draw_text_pillow(img, label, label_x, label_y,
                          label_font_size, LABEL_COLOR, LABEL_STROKE,
                          stroke_width=max(1, label_font_size // 12))

    # 4. Titel oben links (über dem Graph-Bereich)
    title_y = gy - title_font_size - max(4, int(gh * 0.02))
    title_y = max(0, title_y)
    _draw_text_pillow(img, title, gx, title_y,
                      title_font_size, LABEL_COLOR, LABEL_STROKE,
                      stroke_width=max(2, title_font_size // 10))


LINE_Y_PAD_EXTRA_4K = 0    # zusätzlicher Innenabstand über die Linienstärke hinaus (4K-Bezug)


def _line_y_bounds(gy, gh, s4k, line_thickness):
    """
    Oberer/unterer Rand des Bereichs, in dem die Graph-Linie gezeichnet wird.

    Wird von allen VIER Zeichenpfaden benutzt (FPS und Frametime, jeweils mit
    und ohne Playhead). Vorher stand die Formel viermal einzeln im Code —
    genau die Art Duplikat, bei der eine Änderung an drei Stellen ankommt und
    an der vierten nicht.

    Der Innenabstand setzt sich aus zwei Anteilen zusammen:
      • Rahmenstärke `ot` — der Border-Layer wird NACH der Linie geblendet.
        Ohne diesen Anteil verschwindet die obere Hälfte der Linie unter dem
        Rahmen, und die Linie wirkt beim Bestwert dünner als bei mittleren
        Werten (gemessen bei 4K: nur 3 von 6 px sichtbar).
      • halbe Linienstärke — cv2 zeichnet die Linie um ihre Mitte.

    Damit liegt die Linie beim Bestwert (60 fps bzw. 16.7 ms) mit voller
    Stärke direkt an der Rahmen-Innenkante, auf jeder Ausgabeauflösung:

        Ausgabe   Rahmen  Linie   Abstand alt   neu
        4K            3      6              8     6   (= 2 px Gewinn)
        1080p         3      3              4     4   (war schon bündig)

    Das erklärt auch, warum der Spalt nur bei 4K auffiel — die alte feste
    Formel traf bei 1080p zufällig genau den richtigen Wert.
    """
    ot = max(2, int(gh / 150)) + 1          # wie in _get_border_layer
    pad = max(0, ot + line_thickness // 2
              + int(round(LINE_Y_PAD_EXTRA_4K * s4k)))
    return gy + pad, gy + gh - pad


def _draw_polyline_with_gaps(img, px_arr, py_arr, valid, color, line_thickness):
    """
    Zeichnet die farbige Messlinie für gültige Segmente. Über ungültige
    Zonen (Fade/einfarbige Frames) wird stattdessen eine GERADE WEISSE Linie
    gezogen, die den letzten gemessenen Wert mit dem nächsten verbindet —
    signalisiert 'hier wird nicht gemessen', statt eine Lücke zu lassen.
    """
    n = len(px_arr)
    # 1. Weiße Brücken über Lücken. Verbindet den letzten gültigen mit dem
    #    nächsten gültigen Punkt. Reicht die Lücke bis an den Fensterrand
    #    (kein gültiger Nachbar auf einer Seite), wird die weiße Linie waagerecht
    #    bis zum Rand fortgesetzt — so bleibt sie durchgehend sichtbar, während
    #    die Fade-Zone durchs Fenster scrollt (rein von rechts, raus nach links).
    i = 0
    while i < n:
        if valid[i]:
            i += 1
            continue
        left = i - 1
        while left >= 0 and not valid[left]:
            left -= 1
        right = i
        while right < n and not valid[right]:
            right += 1

        has_left = left >= 0
        has_right = right < n
        if has_left and has_right:
            p1 = (int(px_arr[left]),  int(py_arr[left]))
            p2 = (int(px_arr[right]), int(py_arr[right]))
        elif has_left:
            # Lücke reicht bis zum rechten Rand → waagerecht vom letzten Wert
            p1 = (int(px_arr[left]), int(py_arr[left]))
            p2 = (int(px_arr[n - 1]), int(py_arr[left]))
        elif has_right:
            # Lücke reicht bis zum linken Rand → waagerecht zum nächsten Wert
            p1 = (int(px_arr[0]), int(py_arr[right]))
            p2 = (int(px_arr[right]), int(py_arr[right]))
        else:
            p1 = p2 = None
        if p1 is not None:
            cv2.line(img, p1, p2, (255, 255, 255), line_thickness, cv2.LINE_AA)
        i = right

    # 2. Farbige Messlinie für die gültigen Segmente (über die Brücke gezeichnet)
    seg_x, seg_y = [], []
    for i in range(n):
        if valid[i]:
            seg_x.append(px_arr[i])
            seg_y.append(py_arr[i])
        else:
            if len(seg_x) >= 2:
                arr = np.stack([seg_x, seg_y], axis=1).reshape((-1, 1, 2)).astype(np.int32)
                cv2.polylines(img, [arr], False, color, line_thickness, cv2.LINE_AA)
            seg_x, seg_y = [], []
    if len(seg_x) >= 2:
        arr = np.stack([seg_x, seg_y], axis=1).reshape((-1, 1, 2)).astype(np.int32)
        cv2.polylines(img, [arr], False, color, line_thickness, cv2.LINE_AA)


def _draw_playhead(img, gx, gy, gw, gh, s4k):
    """Dünne vertikale Mittellinie (aktueller Frame)."""
    cx = gx + gw // 2
    th = max(1, int(2 * s4k))
    y1, y2 = gy, gy + gh
    roi = img[y1:y2, max(0, cx - th//2):cx + th//2 + 1].astype(np.float32)
    white = np.full_like(roi, 255)
    img[y1:y2, max(0, cx - th//2):cx + th//2 + 1] = (roi * 0.25 + white * 0.75).astype(np.uint8)


def _prepare_window(seq, center_idx, half):
    """
    Liefert ein zentriertes Fenster [center-half, center+half] mit fester Länge
    2*half+1. Fehlende Ränder (Videoanfang/-ende) und None/NaN werden als
    ungültig markiert. Returns (values[], valid[]).
    """
    total = 2 * half + 1
    vals = np.full(total, np.nan, dtype=np.float32)
    valid = np.zeros(total, dtype=bool)
    n = len(seq)
    for j in range(total):
        src = center_idx - half + j
        if 0 <= src < n:
            v = seq[src]
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                vals[j] = v
                valid[j] = True
    return vals, valid


def draw_fps_line(img: np.ndarray,
                  fps_history,
                  gx: int, gy: int, gw: int, gh: int,
                  color: Tuple[int,int,int],
                  max_fps: float,
                  line_thickness: int = 2,
                  value_scale=None,
                  playhead=None) -> np.ndarray:
    """
    Dynamische FPS-Linie; value_scale=(map_x, map_f) für stückweise-lineare Skala.
    playhead=(full_seq, center_idx): DF-Stil — Fenster zentriert auf center_idx,
    linke Hälfte Vergangenheit, rechte Hälfte Zukunft, Mittellinie markiert.
    """
    s4k = img.shape[0] / 2160.0
    x_off = max(1, int(3 * s4k))
    x_r3  = max(1, int(3 * s4k))   # rechts 3px kürzen

    if playhead is not None:
        full_seq, center_idx = playhead
        half = MAX_GRAPH_POINTS // 2
        raw, valid = _prepare_window(full_seq, center_idx, half)
        n_pts = len(raw)
        indices = np.arange(n_pts, dtype=np.float32)
        px_arr = (gx + x_off + indices * (gw - x_off - x_r3) / (n_pts - 1)).astype(np.int32)
        safe = np.where(valid, raw, 0.0)
        if value_scale is not None:
            map_x, map_f = value_scale
            fracs = np.interp(safe, map_x, map_f).astype(np.float32)
        else:
            fracs = 1.0 - np.clip(safe / max_fps, 0.0, 1.0)
        # 3px (4K) oben+unten Padding: Linie liegt bei 60fps knapp unter dem
        # oberen und bei 0fps knapp über dem unteren Rahmen statt exakt drauf.
        y_top, y_bot = _line_y_bounds(gy, gh, s4k, line_thickness)
        py_arr = np.clip((y_top + fracs * (y_bot - y_top)).astype(np.int32), y_top, y_bot)
        _draw_polyline_with_gaps(img, px_arr, py_arr, valid, color, line_thickness)
        _draw_playhead(img, gx, gy, gw, gh, s4k)
        return img

    n = len(fps_history)
    if n < 2:
        return img
    if n > MAX_GRAPH_POINTS:
        hist = list(itertools.islice(fps_history, n - MAX_GRAPH_POINTS, n))
    else:
        hist = list(fps_history)
    n_pts = len(hist)
    indices = np.arange(n_pts, dtype=np.float32)
    px_arr  = (gx + x_off + indices * (gw - x_off - x_r3) / MAX_GRAPH_POINTS).astype(np.int32)
    raw = np.array(hist, dtype=np.float32)
    if value_scale is not None:
        map_x, map_f = value_scale
        fracs = np.interp(raw, map_x, map_f).astype(np.float32)
    else:
        fracs = 1.0 - np.clip(raw / max_fps, 0.0, 1.0)
    y_top, y_bot = _line_y_bounds(gy, gh, s4k, line_thickness)
    py_arr  = np.clip((y_top + fracs * (y_bot - y_top)).astype(np.int32), y_top, y_bot)
    arr = np.stack([px_arr, py_arr], axis=1).reshape((-1, 1, 2))
    cv2.polylines(img, [arr], False, color, line_thickness, cv2.LINE_AA)
    return img


def draw_frametime_line(img: np.ndarray,
                        frame_times: List[float],
                        gx: int, gy: int, gw: int, gh: int,
                        color: Tuple[int,int,int],
                        ft_min: float, ft_max: float,
                        line_thickness: int = 2,
                        value_scale=None,
                        playhead=None) -> np.ndarray:
    """Dynamische Frametime-Linie; playhead=(full_seq, center_idx) für DF-Stil."""
    s4k = img.shape[0] / 2160.0
    x_l = max(1, int(4 * s4k))
    x_r = max(1, int(2 * s4k)) + max(1, int(3 * s4k))   # 2px + 3px kürzen
    scale = ft_max - ft_min if ft_max > ft_min else 1.0

    if playhead is not None:
        full_seq, center_idx = playhead
        half = MAX_GRAPH_POINTS // 2
        raw, valid = _prepare_window(full_seq, center_idx, half)
        n_pts = len(raw)
        indices = np.arange(n_pts, dtype=np.float32)
        px_arr = (gx + x_l + indices * (gw - x_l - x_r) / (n_pts - 1)).astype(np.int32)
        safe = np.where(valid, raw, ft_min)
        if value_scale is not None:
            map_x, map_f = value_scale
            fracs = np.interp(safe, map_x, map_f).astype(np.float32)
        else:
            fracs = np.clip((safe - ft_min) / scale, 0.0, 1.0)
        y_top, y_bot = _line_y_bounds(gy, gh, s4k, line_thickness)
        py_arr = np.clip((y_top + fracs * (y_bot - y_top)).astype(np.int32), y_top, y_bot)
        _draw_polyline_with_gaps(img, px_arr, py_arr, valid, color, line_thickness)
        _draw_playhead(img, gx, gy, gw, gh, s4k)
        return img

    n = len(frame_times)
    if n < 2:
        return img
    if n > MAX_GRAPH_POINTS:
        hist = list(itertools.islice(frame_times, n - MAX_GRAPH_POINTS, n))
    else:
        hist = list(frame_times)
    n_pts = len(hist)
    indices = np.arange(n_pts, dtype=np.float32)
    px_arr  = (gx + x_l + indices * (gw - x_l - x_r) / MAX_GRAPH_POINTS).astype(np.int32)
    raw = np.array(hist, dtype=np.float32)
    if value_scale is not None:
        map_x, map_f = value_scale
        fracs = np.interp(raw, map_x, map_f).astype(np.float32)
    else:
        fracs = np.clip((raw - ft_min) / scale, 0.0, 1.0)
    y_top, y_bot = _line_y_bounds(gy, gh, s4k, line_thickness)
    py_arr  = np.clip((y_top + fracs * (y_bot - y_top)).astype(np.int32), y_top, y_bot)
    arr = np.stack([px_arr, py_arr], axis=1).reshape((-1, 1, 2))
    cv2.polylines(img, [arr], False, color, line_thickness, cv2.LINE_AA)
    return img




# ── Haupt-Renderer ─────────────────────────────────────────────────────────────

class CodeRenderer:
    """
    Komplett code-basierter Renderer — kein PNG-Template mehr benötigt.
    Drop-in Ersatz für PNGTemplateRenderer.render_overlay().
    """

    def __init__(self):
        self.render_times: collections.deque = collections.deque(maxlen=300)
        self._frame_count = 0
        self._current_layout_config = None
        # Cache für vorgerenderte Hintergründe (key = (gx,gy,gw,gh,title,labels_tuple))
        # Wird einmalig gerendert, dann per CUDA geblendet — identisch schnell wie PNG-Templates
        self._bg_cache: Dict[tuple, np.ndarray] = {}
        print("✅ CodeRenderer initialized — no PNG templates needed")

    def _blend_prep(self, layer):
        """
        Bereitet die Blend-Daten für einen GECACHTEN Layer EINMALIG vor.

        Hintergrund (gemessen an den echten Layern, 2021×474 auf 4K-Canvas):
        Der bisherige CPU-Blend konvertierte pro Frame drei volle Arrays nach
        float32 (alpha, fg, roi) — obwohl alpha und fg sich nie ändern, weil
        der Layer aus dem Cache kommt. Das ist pro Frame und pro Layer teuer:

            Variante                                    bg-Layer   Border
            A  bisher (3× float32-Konvertierung)          19.95ms   19.41ms
            B  premultipliziert (Cache)                    5.78ms    7.02ms
            C  uint16-Integer                              7.63ms    9.68ms
            D  nur Pixel mit alpha>0                      16.92ms    0.76ms

        Welche Variante gewinnt, hängt an der Alpha-Belegung des Layers:
            bg-Layer:     76.7% teiltransparent →  B ist optimal (3.45×)
            Border-Layer: 98.6% VOLL transparent → D ist optimal (25.4×)

        Deshalb wird hier pro Layer automatisch entschieden und das Ergebnis
        zusammen mit dem Layer gecacht.
        """
        key = id(layer)
        cache = getattr(self, '_blend_prep_cache', None)
        if cache is None:
            cache = self._blend_prep_cache = {}
        hit = cache.get(key)
        if hit is not None and hit['shape'] == layer.shape:
            return hit

        a8 = layer[:, :, 3]
        nonzero_frac = float(np.count_nonzero(a8)) / max(a8.size, 1)

        if nonzero_frac < 0.30:
            # Dünn belegt (Borders, Text) → nur die Pixel mit alpha>0 anfassen.
            # WICHTIG: Zeilen/Spalten-Indizes, KEINE flachen Indizes auf einem
            # reshape(-1,3). Ein Slice des Overlays ist nicht zusammenhängend;
            # reshape darauf liefert stillschweigend eine KOPIE, und der Blend
            # landet im Nichts (im Test: Border wurde gar nicht gezeichnet).
            rows, cols = np.nonzero(a8)
            af = (a8[rows, cols].astype(np.float32) / 255.0)[:, None]
            fg = layer[rows, cols, :3].astype(np.float32)
            prep = {'mode': 'sparse', 'shape': layer.shape,
                    'rows': rows, 'cols': cols,
                    'inv': 1.0 - af, 'pre': fg * af}
        else:
            # Flächig belegt (Graph-Hintergründe) → premultipliziert
            a = a8[:, :, None].astype(np.float32) / 255.0
            prep = {'mode': 'dense', 'shape': layer.shape,
                    'inv': 1.0 - a,
                    'pre': layer[:, :, :3].astype(np.float32) * a}
        cache[key] = prep
        # Referenz halten, damit id() nicht durch GC recycelt und einem
        # anderen Array zugeordnet wird
        prep['_ref'] = layer
        return prep

    def _blend_rgba(self, overlay, layer, blend_x, blend_y, w, h):
        """RGBA-Layer an (blend_x, blend_y) in overlay compositen (CUDA oder CPU)."""
        if _cuda_blender is not None and not getattr(self, 'force_cpu_blend', False):
            _cuda_blender.blend(overlay, layer, blend_x, blend_y)
            return
        self._blend_rgba_cpu(overlay, layer, blend_x, blend_y, w, h)

    def _blend_rgba_cpu(self, overlay, layer, blend_x, blend_y, w, h):
        """Optimierter CPU-Blend, siehe _blend_prep für die Messwerte."""
        bh, bw = layer.shape[:2]
        y2 = min(h, blend_y + bh)
        x2 = min(w, blend_x + bw)
        th, tw = y2 - blend_y, x2 - blend_x
        if th <= 0 or tw <= 0:
            return

        prep = self._blend_prep(layer)

        # Der schnelle Sparse-Pfad arbeitet auf flachen Indizes des VOLLEN
        # Layers — er ist nur gültig, wenn der Layer nicht beschnitten wird.
        if prep['mode'] == 'sparse' and th == bh and tw == bw:
            sub = overlay[blend_y:y2, blend_x:x2]
            rows, cols = prep['rows'], prep['cols']
            sel = sub[rows, cols].astype(np.float32)
            sub[rows, cols] = (sel * prep['inv'] + prep['pre']).astype(np.uint8)
            return

        if prep['mode'] == 'dense':
            inv = prep['inv'][:th, :tw]
            pre = prep['pre'][:th, :tw]
        else:
            # Beschnittener Sparse-Layer → einmalig dicht nachrechnen
            a = layer[:th, :tw, 3:4].astype(np.float32) / 255.0
            inv = 1.0 - a
            pre = layer[:th, :tw, :3].astype(np.float32) * a

        roi = overlay[blend_y:y2, blend_x:x2].astype(np.float32)
        overlay[blend_y:y2, blend_x:x2] = (roi * inv + pre).astype(np.uint8)

    def _get_border_layer(self, gx, gy, gw, gh, title, label_font_size, title_font_size, frame_w, frame_h):
        """
        Separater Border-Layer (nur weiße Umrandung / Soft Glow), gecacht.
        Wird NACH der FPS/FT-Linie geblendet, damit deren Überstand am
        Graph-Rand kaschiert wird. Gleiche Canvas-Geometrie wie _get_bg_layer.
        """
        style = getattr(self, '_overlay_style', {}) or {}
        border_style = style.get('graph_border', 'White Outline')
        bkey = (gw, gh, title, label_font_size, title_font_size, border_style)
        if not hasattr(self, '_border_cache'):
            self._border_cache = {}
        if bkey in self._border_cache:
            return self._border_cache[bkey]

        left_margin  = max(3, int(gw * 0.003))
        label_margin = label_font_size * 7
        title_margin = title_font_size + max(6, int(gh * 0.02)) + 8
        canvas_w = min(left_margin + gw + label_margin, frame_w)
        canvas_h = min(gh + title_margin + label_font_size // 2 + 4, frame_h)
        canvas = np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)
        cx, cy = left_margin, title_margin

        def _rect_rgba(cx1, cy1, cx2, cy2, color, alpha_val):
            cx1, cy1 = max(0, cx1), max(0, cy1)
            cx2, cy2 = min(canvas_w, cx2), min(canvas_h, cy2)
            if cx2 <= cx1 or cy2 <= cy1:
                return
            a = int(alpha_val * 255)
            existing_a = canvas[cy1:cy2, cx1:cx2, 3:4].astype(np.float32) / 255.0
            new_a = alpha_val + (existing_a[..., 0] * (1 - alpha_val))
            canvas[cy1:cy2, cx1:cx2, :3] = color
            canvas[cy1:cy2, cx1:cx2, 3]  = np.clip(new_a * 255, 0, 255).astype(np.uint8)

        ot = max(2, int(gh / 150)) + 1   # 1px dicker
        if border_style == 'White Outline':
            _rect_rgba(cx,           cy,           cx + gw,     cy + ot,     (255,255,255), 0.9)
            _rect_rgba(cx,           cy + gh - ot, cx + gw,     cy + gh,     (255,255,255), 0.9)
            _rect_rgba(cx,           cy,           cx + ot,     cy + gh,     (255,255,255), 0.9)
            _rect_rgba(cx + gw - ot, cy,           cx + gw,     cy + gh,     (255,255,255), 0.9)
        elif border_style == 'Soft Glow':
            for ring, a in enumerate((0.55, 0.30, 0.12)):
                o = ot * (ring + 1)
                _rect_rgba(cx - o,          cy - o,          cx + gw + o, cy - o + ot,  (255,255,255), a)
                _rect_rgba(cx - o,          cy + gh + o - ot, cx + gw + o, cy + gh + o, (255,255,255), a)
                _rect_rgba(cx - o,          cy - o,          cx - o + ot, cy + gh + o,  (255,255,255), a)
                _rect_rgba(cx + gw + o - ot, cy - o,         cx + gw + o, cy + gh + o,  (255,255,255), a)
        # 'None' → leerer Layer

        self._border_cache[bkey] = canvas
        return canvas

    def _get_bg_layer(self, gx: int, gy: int, gw: int, gh: int,
                      title: str, grid_items,
                      label_font_size: int, title_font_size: int,
                      frame_w: int, frame_h: int) -> np.ndarray:
        """
        Gibt ein vorgerendertes RGBA-Template zurück.
        grid_items: Liste von (label, fraction) — fraction 0.0 = oben, 1.0 = unten.
        Pro Eintrag wird eine Gridlinie + Label gezeichnet (beliebig viele Werte).
        Overlay-Styles (text_style / graph_border / bg_opacity) kommen aus
        self._overlay_style (Layout Editor).
        """
        style = getattr(self, '_overlay_style', {}) or {}
        text_style   = style.get('text_style', 'Hard Outline')
        border_style = style.get('graph_border', 'White Outline')
        bg_opacity   = float(style.get('bg_opacity', BG_ALPHA))
        cache_key = (gw, gh, title, tuple(grid_items),
                     label_font_size, title_font_size,
                     text_style, border_style, round(bg_opacity, 2),
                     _tweak_for(title), bool(style.get('frosted_glass', False)))
        if cache_key in self._bg_cache:
            return self._bg_cache[cache_key]

        left_margin  = max(3, int(gw * 0.003))
        label_margin = label_font_size * 7
        title_margin = title_font_size + max(6, int(gh * 0.02)) + 8
        canvas_w = min(left_margin + gw + label_margin, frame_w)
        canvas_h = min(gh + title_margin + label_font_size // 2 + 4, frame_h)

        canvas = np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)
        cx, cy = left_margin, title_margin

        def _rect_rgba(cx1, cy1, cx2, cy2, color, alpha_val):
            cx1, cy1 = max(0, cx1), max(0, cy1)
            cx2, cy2 = min(canvas_w, cx2), min(canvas_h, cy2)
            if cx2 <= cx1 or cy2 <= cy1:
                return
            canvas[cy1:cy2, cx1:cx2, :3] = color
            canvas[cy1:cy2, cx1:cx2,  3] = int(alpha_val * 255)

        def _hline_rgba(y, x1, x2, color, alpha_val, thickness=1):
            half = thickness // 2
            _rect_rgba(x1, y - half, x2, y + half + 1, color, alpha_val)

        # 1. Hintergrund-Fill: bei Milchglas-Effekt WEGLASSEN (der geblurrte
        #    Frame liefert dann den Hintergrund). Sonst schwarzer Fill mit
        #    Deckkraft aus dem Layout Editor.
        frosted = bool(style.get('frosted_glass', False))
        if not frosted:
            _rect_rgba(cx, cy, cx + gw, cy + gh, BG_COLOR, bg_opacity)

        # 2. Graph-Rand: NICHT hier zeichnen — kommt als separater Layer NACH
        #    der FPS/FT-Linie, damit der Linienüberstand am Rand kaschiert wird.
        #    (siehe _get_border_layer + Blend-Reihenfolge in render_overlay)

        # 3. Grid-Linien — eine pro grid_item an dessen Fraktion
        line_thickness = max(1, int(gh / 150))
        grid_ys = [cy + int(item[1] * gh) for item in grid_items]
        for item, ly in zip(grid_items, grid_ys):
            hidden = len(item) > 2 and item[2]
            if hidden:
                # x-Präfix: graue, dezentere Linie
                _hline_rgba(ly, cx, cx + gw, (128, 128, 128),
                            GRID_ALPHA * 0.55, line_thickness)
            else:
                _hline_rgba(ly, cx, cx + gw, GRID_COLOR, GRID_ALPHA, line_thickness)

        # 4. Text — Stroke-Stärke aus overlay_style (outline_width), skaliert.
        #    WICHTIG: auf frame_h skalieren (wie FPS-Zahl + Stats), NICHT auf
        #    canvas_h (die kleine Template-Höhe) — sonst wären Titel/Labels
        #    viel dünner umrandet als die anderen Texte.
        style = getattr(self, '_overlay_style', {}) or {}
        ow_base = style.get('outline_width', None)
        if ow_base is not None:
            sw_val = max(0, int(round(float(ow_base) * max(1.0, frame_h / 1080.0))))
        else:
            sw_val = max(2, label_font_size // 8)
        sw_label = sw_title = sw_val
        if text_style == 'None':
            sw_label = sw_title = 0

        # ── Manuelle Justierung (Tweak-Block oben in der Datei) ──
        s4k_lbl = canvas_h / 2160.0
        t_tdx, t_tdy, t_tsize, l_ldx, l_ldy, l_lsize, l_gap = _tweak_for(title)
        # 4K-Offsets → Ausgabepixel
        title_dx  = int(t_tdx * s4k_lbl)
        title_dy  = int(t_tdy * s4k_lbl)
        lbl_dx    = int(l_ldx * s4k_lbl)
        lbl_dy    = int(l_ldy * s4k_lbl)
        # Größen-Multiplikatoren
        title_fs  = max(6, int(title_font_size * t_tsize))
        label_fs  = max(6, int(label_font_size * l_lsize))

        # Basis-Position Labels: per-Graph Gap + individueller Tweak
        label_x  = cx + gw + max(3, int(gw * 0.012) - int(l_gap * s4k_lbl)) + lbl_dx
        title_y  = max(0, cy - title_font_size - max(2, int(gh * 0.01))) + title_dy
        title_x  = cx + title_dx

        # Glyphenhöhe für vertikale Zentrierung (mit getweakter Labelgröße)
        _f = _FontCache.get(label_fs)
        def _vis_h(t):
            try:
                bb = _f.getbbox(t)
                return bb[3] - bb[1]
            except Exception:
                return label_fs

        # Text mit ECHTEM Anti-Aliasing in den RGBA-Canvas rendern.
        # Statt Masken-Threshold (der AA-Kanten zerstört) wird der Text auf
        # einem transparenten RGBA-Pillow-Bild gezeichnet und alpha-korrekt
        # in den Canvas komponiert — erhält weiche Kanten wie FPS-Zahl/Stats.
        _composite_text_rgba(
            canvas, cx, cy, canvas_w, canvas_h,
            grid_items, grid_ys, title, title_x, title_y,
            label_x, label_fs, title_fs, _vis_h,
            text_style, sw_label, sw_title,
        )

        self._bg_cache[cache_key] = canvas
        print(f"🖼️  CodeRenderer: cached '{title}' template ({canvas_w}x{canvas_h})")
        return canvas

    def get_default_layout(self, w: int, h: int) -> Dict:
        """Standard-Layout für 1080p, skaliert auf Zielauflösung."""
        sx = w / 1920
        sy = h / 1080
        s  = min(sx, sy)
        return {
            'fps_display': {
                'x': int(50 * sx), 'y': int(0 * sy),
                'visible': True, 'font_scale_multiplier': 1.0
            },
            'frame_rate_graph': {
                'x': int(50 * sx),  'y': int(736 * sy),
                'width': int(920 * sx), 'height': int(290 * sy),
                'visible': True
            },
            'frame_time_graph': {
                'x': int(50 * sx),  'y': int(510 * sy),
                'width': int(400 * sx), 'height': int(180 * sy),
                'visible': True
            },
            'fps_statistics': {
                'x': int(50 * sx), 'y': int(1050 * sy), 'visible': True
            },
            'frametime_statistics': {
                'x': int(50 * sx), 'y': int(710 * sy), 'visible': True
            },
        }

    def render_overlay(self,
                       frame: np.ndarray,
                       fps_history: List[float],
                       current_fps: float,
                       frame_times: Optional[List[float]] = None,
                       show_frame_time_graph: bool = True,
                       layout_config: Optional[Dict] = None,
                       color_settings: Optional[Dict] = None,
                       template_config: Optional[Dict] = None,
                       font_settings: Optional[Dict] = None,
                       global_fps_values=None,
                       global_frame_times=None,
                       precomputed_stats: Optional[Dict] = None,
                       playhead_index: Optional[int] = None,
                       full_fps_seq=None,
                       full_ft_seq=None,
                       full_dev_seq=None,
                       stats_panel_config=None) -> np.ndarray:
        """
        Haupt-Rendering-Funktion.
        Identische Signatur wie PNGTemplateRenderer.render_overlay()
        → Drop-in Ersatz, keine Änderungen am aufrufenden Code nötig.
        """
        t_start = time.perf_counter()
        t_debug = {}

        # ── Setup ──────────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        overlay = frame.copy()
        t_debug['copy'] = time.perf_counter() - t0

        h, w = frame.shape[:2]
        self._current_layout_config = layout_config
        position_scale = max(w / 1920, h / 1080)

        if color_settings is None:
            color_settings = {'framerate_color': '#00FF00', 'frametime_color': '#00FF00'}
        framerate_color = hex_to_bgr(color_settings.get('framerate_color', '#00FF00'))
        frametime_color = hex_to_bgr(color_settings.get('frametime_color', '#00FF00'))

        if layout_config is None:
            layout_config = self.get_default_layout(w, h)

        # FPS/FT scale aus template_config lesen — beliebig viele Grid-Werte
        fps_max = 60
        fps_grid_values = [60, 30, 0]
        fps_hidden: set = set()
        ft_hidden: set = set()
        ft_min, ft_max_val = 16.7, 33.3
        ft_grid_values = [16.7, 25.0, 33.3]
        self._overlay_style = {}
        if template_config:
            self._overlay_style = template_config.get('overlay_style', {}) or {}
            fps_data = template_config.get('fps_graph_template')
            if fps_data and isinstance(fps_data, dict):
                gl = fps_data.get('values') or fps_data.get('grid_lines')
                if gl:
                    fps_grid_values = [float(v) for v in gl]
                fps_hidden = set(float(v) for v in fps_data.get('hidden', []))
                fps_max = fps_data.get('max_fps') or max(fps_grid_values)
            ft_data = template_config.get('frametime_template')
            if ft_data and isinstance(ft_data, dict):
                vals = ft_data.get('values')
                if not vals:
                    sc = ft_data.get('scale', {})
                    vals = sorted({sc.get('min', 16.7), sc.get('mid', 25.0), sc.get('max', 33.3)})
                ft_grid_values = [float(v) for v in vals]
                ft_hidden = set(float(v) for v in ft_data.get('hidden', []))
                ft_min, ft_max_val = min(ft_grid_values), max(ft_grid_values)

        # ÄQUIDISTANTE Grid-Labels: alle Werte mit gleichem Abstand,
        # unabhängig von ihrer numerischen Distanz (z.B. 16.7,25,33.3,100).
        # Die Linien werden über eine stückweise-lineare Skala (np.interp)
        # auf dieselben Positionen gemappt, damit Linie und Labels passen.
        fps_sorted_desc = sorted(set(fps_grid_values), reverse=True)
        n_fps = max(1, len(fps_sorted_desc) - 1)
        fps_grid_items = [
            (f"{v:g}", i / n_fps, v in fps_hidden)
            for i, v in enumerate(fps_sorted_desc)
        ]
        # Mapping-Arrays für np.interp (x aufsteigend)
        # x aufsteigend; frac: kleinster Wert unten (1.0), größter oben (0.0)
        fps_map_x = np.array(sorted(set(fps_grid_values)), dtype=np.float32)
        fps_map_f = np.array([1.0 - j / n_fps for j in range(len(fps_map_x))],
                             dtype=np.float32)

        ft_sorted_asc = sorted(set(ft_grid_values))
        n_ft = max(1, len(ft_sorted_asc) - 1)
        ft_grid_items = [
            (f"{v:g}MS", i / n_ft, v in ft_hidden)
            for i, v in enumerate(ft_sorted_asc)
        ]
        ft_map_x = np.array(ft_sorted_asc, dtype=np.float32)
        ft_map_f = np.array([i / n_ft for i in range(len(ft_map_x))], dtype=np.float32)
        self._fps_scale = (fps_map_x, fps_map_f)
        self._ft_scale  = (ft_map_x, ft_map_f)

        # Font-Größen
        scale = min(w / 1920, h / 1080)
        # Text-Boost (z.B. Comparison-Modus: Titel/Labels größer für Lesbarkeit)
        _tb = float((getattr(self, '_overlay_style', {}) or {}).get('text_boost', 1.0))
        title_size    = max(8, int(36 * scale * _tb))
        label_size_ft = max(8, int(19 * scale * _tb))
        label_size_fr = max(8, int(24 * scale * _tb))
        label_size    = label_size_ft
        # Liniendicke: Basis @1080p aus Layout Editor (default 2px), skaliert
        base_thick = 2
        if template_config and template_config.get('fps_line_thickness'):
            try:
                base_thick = max(1, int(template_config['fps_line_thickness']))
            except Exception:
                pass
        line_thick = max(1, int(base_thick * h / 1080))

        # ── 1. FPS-Graph ───────────────────────────────────────────────────────
        t0 = time.perf_counter()
        frg = layout_config.get('frame_rate_graph', {})
        if frg.get('visible', True):
            gx = frg['x'];  gy = frg['y']
            gw = frg['width']; gh = frg['height']

            # Milchglas-Effekt: NUR der Graph-Box-Bereich (nicht Titel/Labels)
            _st = getattr(self, '_overlay_style', {}) or {}
            if _st.get('frosted_glass', False):
                _apply_frosted_glass(overlay, gx, gy, gw, gh,
                                     blur_strength=int(_st.get('frost_blur', 25)),
                                     darken=float(_st.get('frost_darken', 0.35)))

            # Hintergrund aus Cache holen und per CUDA blenden (klein, wie PNG-Template)
            bg = self._get_bg_layer(gx, gy, gw, gh, "FRAME RATE", fps_grid_items,
                                    label_size_fr, title_size, w, h)
            # Canvas-Ursprung = gx, gy minus title_margin
            title_margin = title_size + max(6, int(gh * 0.02)) + 8
            left_m   = max(3, int(gw * 0.003))
            blend_x  = max(0, gx - left_m)
            blend_y  = max(0, gy - title_margin)
            # Zentral über _blend_rgba — nutzt den optimierten CPU-Pfad mit
            # vorbereiteten, gecachten Alpha-Daten (siehe _blend_prep).
            self._blend_rgba(overlay, bg, blend_x, blend_y, w, h)

            _ph_fps = (full_fps_seq, playhead_index) if (playhead_index is not None and full_fps_seq is not None) else None
            draw_fps_line(overlay, fps_history, gx, gy, gw, gh,
                          framerate_color, fps_max, line_thick,
                          value_scale=getattr(self, '_fps_scale', None),
                          playhead=_ph_fps)

            # Border-Layer ÜBER der Linie blenden (kaschiert Linienüberstand)
            border = self._get_border_layer(gx, gy, gw, gh, "FRAME RATE",
                                             label_size_fr, title_size, w, h)
            self._blend_rgba(overlay, border, blend_x, blend_y, w, h)
        t_debug['fps_graph'] = time.perf_counter() - t0

        # ── 2. Frametime-Graph ─────────────────────────────────────────────────
        t0 = time.perf_counter()
        ftg = layout_config.get('frame_time_graph', {})
        if show_frame_time_graph and frame_times and ftg.get('visible', True):
            gx = ftg['x'];  gy = ftg['y']
            gw = ftg['width']; gh = ftg['height']

            # Milchglas-Effekt: NUR der Graph-Box-Bereich (nicht Titel/Labels)
            _st = getattr(self, '_overlay_style', {}) or {}
            if _st.get('frosted_glass', False):
                _apply_frosted_glass(overlay, gx, gy, gw, gh,
                                     blur_strength=int(_st.get('frost_blur', 25)),
                                     darken=float(_st.get('frost_darken', 0.35)))

            # Hintergrund aus Cache holen und per CUDA blenden
            bg = self._get_bg_layer(gx, gy, gw, gh, "FRAME TIME", ft_grid_items,
                                    label_size_ft, title_size, w, h)
            title_margin = title_size + max(6, int(gh * 0.02)) + 8
            left_m   = max(3, int(gw * 0.003))
            blend_x  = max(0, gx - left_m)
            blend_y  = max(0, gy - title_margin)
            # Zentral über _blend_rgba — nutzt den optimierten CPU-Pfad mit
            # vorbereiteten, gecachten Alpha-Daten (siehe _blend_prep).
            self._blend_rgba(overlay, bg, blend_x, blend_y, w, h)

            _ph_ft = (full_ft_seq, playhead_index) if (playhead_index is not None and full_ft_seq is not None) else None
            draw_frametime_line(overlay, frame_times, gx, gy, gw, gh,
                                frametime_color, ft_min, ft_max_val, line_thick,
                                value_scale=getattr(self, '_ft_scale', None),
                                playhead=_ph_ft)

            # Border-Layer ÜBER der Linie blenden
            border = self._get_border_layer(gx, gy, gw, gh, "FRAME TIME",
                                             label_size_ft, title_size, w, h)
            self._blend_rgba(overlay, border, blend_x, blend_y, w, h)
        t_debug['ft_graph'] = time.perf_counter() - t0

        # ── 3. FPS-Zahl ────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        fpsd = layout_config.get('fps_display', {})
        if fpsd.get('visible', True):
            fps_font_size = FontSizeConfig.get_absolute_size('fps_number', w, h)
            multiplier    = fpsd.get('font_scale_multiplier', 1.0)
            if multiplier != 1.0:
                fps_font_size = int(fps_font_size * multiplier)
            # Manuelle FPS-Zahl-Justierung (Tweak-Block)
            _s4k_fps = h / 2160.0
            fps_font_size = max(6, int(fps_font_size * FPS_NUM_SIZE))
            _fps_dx = int(FPS_NUM_DX * _s4k_fps)
            _fps_dy = int(FPS_NUM_DY * _s4k_fps)
            # FPS-Zahl sitzt exakt auf ihrer Layout-Position (kein Legacy-
            # Offset mehr) — damit stimmen Layout Editor und Video überein und
            # die Zahl lässt sich frei positionieren.
            y_offset = _fps_dy
            fps_text = "---" if current_fps < 0 else str(int(current_fps))

            fps_font_obj = font_settings.get('fps_font') if font_settings else None
            _style = getattr(self, '_overlay_style', {}) or {}
            _style_mode = _style.get('text_style', 'Hard Outline')
            _ow_base = _style.get('outline_width', None)
            if _ow_base is not None:
                _sw = max(0, int(round(float(_ow_base) * max(1.0, h / 1080.0))))
            else:
                _sw = max(3, fps_font_size // 15)

            _pf = None
            # FPS-Zahl über thread-lokalen Font-Cache rendern (kein geteiltes
            # Font-Objekt mutieren → thread-sicher ohne Lock).
            _pf = _FontCache.get(fps_font_size)

            _fx = fpsd['x'] + _fps_dx
            # Style-bewusster Pillow-Pfad (Hard Outline / Drop Shadow / None),
            # nutzt den thread-lokalen Font.
            overlay = _draw_text_styled(
                overlay, fps_text,
                _fx, fpsd['y'] + y_offset,
                fps_font_size, _style_mode, _sw, pil_font=_pf)
        t_debug['fps_number'] = time.perf_counter() - t0

        # ── 4. Statistiken ─────────────────────────────────────────────────────
        t0 = time.perf_counter()
        stats_font_size   = FontSizeConfig.get_absolute_size('stats_text', w, h)
        _style_stats = getattr(self, '_overlay_style', {}) or {}
        _ow_stats = _style_stats.get('outline_width', None)
        if _ow_stats is not None:
            border_thickness = max(1, int(round(float(_ow_stats) * max(1.0, h / 1080.0))))
        else:
            border_thickness = max(2, int(2 * min(w/1920, h/1080)))
        spacing = int(100 * min(w / 1920, h / 1080))

        def _draw_stats(cfg_key, stat_data, suffix=''):
            cfg = layout_config.get(cfg_key, {})
            if not cfg.get('visible', True):
                return
            if not stat_data or stat_data.get('avg', -1) < 0:
                return
            sx0, sy0 = cfg['x'] + 4, cfg['y']
            framerate_font = (font_settings.get('framerate_font')
                              if font_settings else None)
            if framerate_font and hasattr(framerate_font, 'render_text'):
                # Shared ROI path (fast)
                _draw_stats_pillow_shared(overlay, stat_data, sx0, sy0,
                                          spacing, stats_font_size,
                                          border_thickness, suffix,
                                          framerate_font,
                                          text_style=getattr(self, '_overlay_style', {}).get('text_style', 'Hard Outline'))
            else:
                items = [
                    (f"AVG: {stat_data['avg']:.1f}{suffix}", 0),
                    (f"MIN: {stat_data['min']:.1f}{suffix}", spacing),
                    (f"MAX: {stat_data['max']:.1f}{suffix}", spacing * 2),
                ]
                for text, xrel in items:
                    _draw_text_pillow(overlay, text, sx0 + xrel, sy0,
                                      stats_font_size,
                                      stroke_width=border_thickness)

        # FPS-Statistiken
        fps_stat_data = None
        if precomputed_stats and 'fps' in precomputed_stats:
            fps_stat_data = precomputed_stats['fps']
        elif global_fps_values and len(global_fps_values) > 60:
            rec = list(global_fps_values)[-300:]
            fps_stat_data = {'avg': sum(rec)/len(rec),
                             'min': min(rec), 'max': max(rec)}
        _draw_stats('fps_statistics', fps_stat_data)

        # Frametime-Statistiken
        ft_stat_data = None
        if precomputed_stats and 'frametime' in precomputed_stats:
            ft_stat_data = precomputed_stats['frametime']
        elif global_frame_times and len(global_frame_times) > 60:
            rec = list(global_frame_times)[-300:]
            ft_stat_data = {'avg': sum(rec)/len(rec),
                            'min': min(rec), 'max': max(rec)}
        _draw_stats('frametime_statistics', ft_stat_data, suffix='ms')

        t_debug['statistics'] = time.perf_counter() - t0

        # ── Timing ─────────────────────────────────────────────────────────────
        # ── Stats-Panel (alternativer Anzeigemodus) ─────────────────────────
        # Wird nach den Graphen gezeichnet, damit es darüber liegt. Ist es
        # aktiv, sind die klassischen Graphen normalerweise abgeschaltet —
        # das entscheidet aber das Layout, nicht der Renderer.
        if stats_panel_config and stats_panel_config.get('enabled'):
            try:
                from stats_panel import render_panel as _render_panel
                _src_fps = float((template_config or {}).get('source_fps', 60.0) or 60.0)
                _render_panel(overlay, stats_panel_config,
                              full_fps_seq, full_ft_seq, playhead_index,
                              stats=precomputed_stats, source_fps=_src_fps,
                              ft_scale=getattr(self, '_ft_panel_scale', None))
            except Exception as _e:
                if not getattr(self, '_panel_err_logged', False):
                    print(f"⚠️ Stats-Panel konnte nicht gezeichnet werden: {_e}")
                    self._panel_err_logged = True

        # ── Abweichungs-Marker ──────────────────────────────────────────────
        # Roter Block oben rechts, solange das Material vom Baseline-Wert
        # abweicht. Bewusst ganz am Ende gezeichnet, also über allem anderen.
        if full_dev_seq is not None and playhead_index is not None:
            if 0 <= playhead_index < len(full_dev_seq) and full_dev_seq[playhead_index]:
                _st = getattr(self, '_overlay_style', {}) or {}
                # Größe in 1080p-Pixeln, wie alle anderen Layout-Angaben,
                # und mit der Ausgabehöhe skaliert — sonst wäre der Block
                # bei 4K nur ein Viertel so groß wie im Editor gedacht.
                _sz = int(round(float(_st.get('deviation_marker_size', 50))
                                * max(1.0, h / 1080.0)))
                _mg = int(round(float(_st.get('deviation_marker_margin', 20))
                                * max(1.0, h / 1080.0)))
                _col = _st.get('deviation_marker_color', '#FF0000')
                _rgb = hex_to_bgr(_col)[::-1] if isinstance(_col, str) else (255, 0, 0)
                x2 = max(0, w - _mg)
                x1 = max(0, x2 - _sz)
                y1 = min(h, _mg)
                y2 = min(h, y1 + _sz)
                if x2 > x1 and y2 > y1:
                    overlay[y1:y2, x1:x2] = _rgb

        render_time = (time.perf_counter() - t_start) * 1000
        self.render_times.append(render_time)
        self._frame_count += 1

        # ── Stufen-Zeiten thread-sicher aufsummieren ────────────────────
        # Vorher wurde hier pro Frame geprintet und im Parallel-Modus ganz
        # unterdrückt — dadurch gab es für den 6-Worker-Lauf gar keine
        # Aufschlüsselung. Jetzt wird summiert und am Ende einmal berichtet.
        acc = getattr(self, '_stage_acc', None)
        if acc is None:
            import threading
            acc = self._stage_acc = {'n': 0, 'total': 0.0,
                                     'lock': threading.Lock()}
        with acc['lock']:
            acc['n'] += 1
            acc['total'] += render_time / 1000.0
            for _k, _v in t_debug.items():
                acc[_k] = acc.get(_k, 0.0) + _v

        return overlay

    def get_stage_summary(self):
        """
        Aufschlüsselung der Overlay-Zeit, summiert über alle Worker-Threads.
        Gibt None zurück, wenn nichts gemessen wurde.
        """
        acc = getattr(self, '_stage_acc', None)
        if not acc or not acc['n']:
            return None
        n = acc['n']
        parts = [(k, acc.get(k, 0.0)) for k in
                 ('copy', 'fps_graph', 'ft_graph', 'fps_number', 'statistics')]
        total = acc['total'] or 1e-9
        lines = [f"🔬 Overlay-Aufschlüsselung ({n} Frames, "
                 f"{total:.1f}s Worker-Zeit gesamt):"]
        named = {'copy': 'Frame kopieren',
                 'fps_graph': 'FPS-Graph (Milchglas+Blend+Linie)',
                 'ft_graph': 'Frametime-Graph',
                 'fps_number': 'FPS-Zahl (Text)',
                 'statistics': 'Statistik-Text'}
        acc_sum = 0.0
        for k, v in parts:
            acc_sum += v
            lines.append(f"     {named[k]:34s} {v*1000/n:7.2f} ms/Frame "
                         f"({100*v/total:5.1f}%)")
        rest = total - acc_sum
        lines.append(f"     {'sonstiges (Setup/Layout)':34s} {rest*1000/n:7.2f} ms/Frame "
                     f"({100*rest/total:5.1f}%)")
        _tc = text_cache_stats()
        if _tc:
            lines.append(f"     {_tc}")
        return "\n".join(lines)


_TEXT_LAYER_CACHE: "collections.OrderedDict[tuple, tuple]" = collections.OrderedDict()
_TEXT_LAYER_LOCK = threading.Lock()
_TEXT_LAYER_BUDGET = 192 * 1024 * 1024   # Bytes, LRU-Verdrängung
_TEXT_LAYER_BYTES = [0]
_TEXT_LAYER_STATS = {'hit': 0, 'miss': 0}


def _text_layer(key, size_wh, draw_fn):
    """
    Gibt einen gecachten RGBA-Textlayer zurück; rendert ihn beim ersten Mal.

    Warum: Statistik- und FPS-Text wurden pro Frame komplett neu gezeichnet —
    ROI nach RGB konvertieren, in ein PIL-Bild kopieren, Text MIT Stroke
    rendern (der Stroke zeichnet die Glyphe mehrfach), zurückkopieren,
    zurückkonvertieren.

    Der Cache muss dabei drei Fallen vermeiden, die beim ersten Anlauf alle
    drei zugeschlagen haben (gemessen am 4K-Lauf, 1659 Statistik-Frames):

      1. NICHT den ganzen Statistik-Block als einen Layer cachen. AVG, MIN
         und MAX ändern sich unabhängig → 243 verschiedene Kombinationen.
         Pro Zeile gecacht sind es 92 / 31 / 131 Layer, also Trefferquoten
         von 94.5% / 98.1% / 92.1%.
      2. NICHT nach id(pil_font) schlüsseln. _FontCache ist thread-lokal,
         jeder der 6 Worker hätte eigene Einträge für identischen Inhalt →
         6-fache Vervielfachung. Die Schriftgröße im Schlüssel genügt, weil
         _FontCache.get(size) deterministisch dieselbe Schrift liefert.
         Die Layer sind nach dem Rendern nur noch lesend → teilbar.
      3. Beim Überlauf NICHT den ganzen Cache leeren. Aus 243 × 6 Threads
         × 2 Blöcken wurden 2916 Einträge gegen ein Limit von 512 — der
         Cache hat sich dauernd selbst geleert und war praktisch wirkungslos
         (21.88 ms → 20.55 ms statt der erwarteten ~2 ms). Jetzt LRU mit
         Speicherbudget.

    draw_fn(pil_image) zeichnet den Text auf ein transparentes RGBA-Bild.
    """
    with _TEXT_LAYER_LOCK:
        hit = _TEXT_LAYER_CACHE.get(key)
        if hit is not None:
            _TEXT_LAYER_CACHE.move_to_end(key)
            _TEXT_LAYER_STATS['hit'] += 1
            return hit
        _TEXT_LAYER_STATS['miss'] += 1

    from PIL import Image as PILImage
    lw, lh = size_wh
    pil = PILImage.new('RGBA', (max(1, lw), max(1, lh)), (0, 0, 0, 0))
    draw_fn(pil)
    layer = np.array(pil)                      # RGBA in PIL-Kanalordnung
    # Die Zeichenroutinen arbeiteten bisher auf einem per cvtColor
    # getauschten ROI und tauschten danach zurück. Damit der Layer direkt
    # in das Bild geblendet werden kann, wird der Tausch einmalig hier
    # vorgenommen statt pro Frame zweimal auf dem ganzen ROI.
    layer = np.ascontiguousarray(layer[:, :, [2, 1, 0, 3]])

    # Blend-Daten gleich mitvorbereiten. Textlayer sind zu >85% transparent,
    # deshalb lohnt der Sparse-Pfad hier besonders.
    a8 = layer[:, :, 3]
    rows, cols = np.nonzero(a8)
    af = (a8[rows, cols].astype(np.float32) / 255.0)[:, None]
    fg = layer[rows, cols, :3].astype(np.float32)
    prep = {'rows': rows, 'cols': cols, 'inv': 1.0 - af, 'pre': fg * af}
    entry = (layer, prep)
    nbytes = (layer.nbytes + rows.nbytes + cols.nbytes
              + af.nbytes * 2 + fg.nbytes)

    with _TEXT_LAYER_LOCK:
        if key not in _TEXT_LAYER_CACHE:
            _TEXT_LAYER_CACHE[key] = entry
            _TEXT_LAYER_BYTES[0] += nbytes
            _TEXT_LAYER_CACHE[key] = entry
            # LRU-Verdrängung statt Komplettlöschung
            while _TEXT_LAYER_BYTES[0] > _TEXT_LAYER_BUDGET and len(_TEXT_LAYER_CACHE) > 1:
                _k, _v = _TEXT_LAYER_CACHE.popitem(last=False)
                _l, _p = _v
                _TEXT_LAYER_BYTES[0] -= (_l.nbytes + _p['rows'].nbytes
                                         + _p['cols'].nbytes
                                         + _p['inv'].nbytes * 2
                                         + _p['pre'].nbytes)
    return entry


def text_cache_stats():
    """Trefferquote des Textlayer-Caches (für die Laufzeit-Diagnose)."""
    h, m = _TEXT_LAYER_STATS['hit'], _TEXT_LAYER_STATS['miss']
    if h + m == 0:
        return None
    return (f"Textlayer-Cache: {100*h/(h+m):.1f}% Treffer "
            f"({h} Treffer / {m} Misses), {len(_TEXT_LAYER_CACHE)} Layer, "
            f"{_TEXT_LAYER_BYTES[0]/1024**2:.0f} MB")


_TEXT_WIDTH_CACHE: Dict[tuple, int] = {}


def _text_width(draw, text, font, font_size):
    """Textbreite messen — gecacht, weil das Font-Layout pro Frame lief."""
    k = (text, font_size)
    w = _TEXT_WIDTH_CACHE.get(k)
    if w is None:
        w = int(draw.textlength(text, font=font)) if font else len(text) * font_size // 2
        _TEXT_WIDTH_CACHE[k] = w
    return w


def _blend_text_layer(img, entry, ox, oy):
    """
    Textlayer an (ox, oy) in img blenden, inklusive Beschnitt an den
    Bildrändern (auch bei negativem Ursprung).
    """
    layer, prep = entry
    ih, iw = img.shape[:2]
    lh, lw = layer.shape[:2]
    sx = max(0, -ox); sy = max(0, -oy)
    dx = max(0, ox);  dy = max(0, oy)
    cw = min(lw - sx, iw - dx)
    ch = min(lh - sy, ih - dy)
    if cw <= 0 or ch <= 0:
        return

    rows, cols = prep['rows'], prep['cols']
    if rows.size == 0:
        return
    inv, pre = prep['inv'], prep['pre']

    # Beschnitt auch im Sparse-Pfad behandeln. Vorher fiel jeder beschnittene
    # Fall auf den dichten Pfad zurück — und das ist der Normalfall, nicht die
    # Ausnahme: die FPS-Zahl sitzt so weit oben, dass der Layer-Ursprung
    # negativ wird (y=88 bei pad=96). Dadurch war der gecachte Pfad sogar
    # LANGSAMER als das ursprüngliche Neuzeichnen.
    if sx or sy or cw != lw or ch != lh:
        m = ((rows >= sy) & (rows < sy + ch) &
             (cols >= sx) & (cols < sx + cw))
        if not m.all():
            rows = rows[m]; cols = cols[m]
            inv = inv[m];   pre = pre[m]
            if rows.size == 0:
                return
        rows = rows - sy
        cols = cols - sx

    sub = img[dy:dy+ch, dx:dx+cw]
    sel = sub[rows, cols].astype(np.float32)
    sub[rows, cols] = (sel * inv + pre).astype(np.uint8)


def _draw_text_styled(img, text, x, y, size, text_style, stroke_w, pil_font=None):
    """Text mit Overlay-Style zeichnen: Hard Outline / Drop Shadow / None."""
    try:
        from PIL import ImageDraw as PILDraw
        if pil_font is None:
            pil_font = _FontCache.get(size)
        h, w = img.shape[:2]
        pad = size + stroke_w + 8
        # Unbeschnittene Layer-Geometrie (Beschnitt macht der Blend)
        ox = x - pad; oy = y - pad
        lw = size * max(1, len(text)) + pad * 2
        lh = size + pad * 2
        if lw <= 0 or lh <= 0:
            return img
        lx, ly = x - ox, y - oy

        def _mk(which):
            def _draw(pil):
                draw = PILDraw.Draw(pil)
                if pil_font is None:
                    draw.text((lx, ly), text, fill=(255, 255, 255, 255))
                elif text_style == 'Drop Shadow':
                    # Schatten und Text als GETRENNTE Layer, nacheinander
                    # geblendet. Beides in einen Layer zu zeichnen ergibt an
                    # der Überlappungskante andere Alphawerte als das
                    # ursprüngliche direkte Zeichnen auf den Hintergrund
                    # (gemessen: bis zu 65 Stufen Abweichung auf 146 Pixeln).
                    off = max(2, stroke_w)
                    if which == 'shadow':
                        draw.text((lx + off, ly + off), text, font=pil_font,
                                  fill=(0, 0, 0, 255))
                    else:
                        draw.text((lx, ly), text, font=pil_font,
                                  fill=(255, 255, 255, 255))
                elif text_style == 'None':
                    draw.text((lx, ly), text, font=pil_font, fill=(255, 255, 255, 255))
                else:   # Hard Outline
                    draw.text((lx, ly), text, font=pil_font, fill=(255, 255, 255, 255),
                              stroke_width=max(1, stroke_w), stroke_fill=(0, 0, 0, 255))
            return _draw

        # KEIN id(pil_font) im Schlüssel: _FontCache ist thread-lokal, das
        # ergäbe pro Worker eigene Einträge für identischen Inhalt. Die
        # Größe genügt, weil _FontCache.get(size) deterministisch ist.
        parts = ('shadow', 'text') if text_style == 'Drop Shadow' else ('all',)
        for which in parts:
            key = ('styled', which, text, size, text_style, stroke_w,
                   lw, lh, lx, ly)
            _blend_text_layer(img, _text_layer(key, (lw, lh), _mk(which)), ox, oy)
        return img
    except Exception as e:
        print(f"⚠️ _draw_text_styled fallback ({text_style}): {e}")
        return _draw_text_pillow(img, text, x, y, size, stroke_width=stroke_w)


def _draw_stats_pillow_shared(img, stats, x0, y0, spacing,
                               font_size, border_thickness, suffix, font_obj,
                               text_style='Hard Outline'):
    """Stats in einem einzigen Pillow-ROI zeichnen (schnell).
    text_style: 'Hard Outline' | 'Drop Shadow' | 'Soft Glow' | 'None'."""
    if not PILLOW:
        return
    try:
        from PIL import Image as PILImage, ImageDraw as PILDraw
        texts = [
            f"AVG: {stats['avg']:.1f}{suffix}",
            f"MIN: {stats['min']:.1f}{suffix}",
            f"MAX: {stats['max']:.1f}{suffix}",
        ]

        # Font thread-lokal laden (kein geteiltes Objekt mutieren) — die
        # Stats-Größe wird direkt aus dem thread-lokalen Cache geholt.
        pil_font = _FontCache.get(font_size)

        # Abstände aus gemessener Textbreite statt fixem spacing —
        # verhindert Überlappung bei jeder Auflösung/Fontgröße.
        gap = max(12, font_size)
        probe = PILDraw.Draw(PILImage.new('RGB', (8, 8)))
        # Breiten gecacht — das Font-Layout lief bisher pro Frame und Zeile
        widths = [_text_width(probe, t, pil_font, font_size) for t in texts]
        x_offsets = [0,
                     widths[0] + gap,
                     widths[0] + gap + widths[1] + gap]
        total_w = x_offsets[2] + widths[2] + border_thickness * 2 + 16
        total_h = font_size + border_thickness * 2 + int(font_size * 0.4) + 20

        ih, iw = img.shape[:2]
        # Unbeschnittene Layer-Geometrie — der Blend übernimmt den Beschnitt
        ox = x0 - border_thickness - 4
        oy = y0 - font_size - border_thickness - 4
        lw = (x0 + total_w) - ox
        lh = (y0 + total_h) - oy
        if lw <= 0 or lh <= 0:
            return

        bc = getattr(font_obj, 'border_color', (0, 0, 0))
        stroke_rgb = (bc[2], bc[1], bc[0]) if bc else (0, 0, 0)
        y_off = -int(font_size * 0.25)
        sw = max(1, border_thickness)
        oy = y0 - font_size - border_thickness - 4
        lh = (y0 + total_h) - oy
        if lh <= 0:
            return

        # JEDE Zeile als eigener Layer: AVG, MIN und MAX ändern sich
        # unabhängig voneinander. Als ein gemeinsamer Layer gäbe es das
        # Produkt aller Kombinationen (gemessen 243 statt 92/31/131).
        def _mk(text, lx, ly, which):
            def _draw(pil):
                draw = PILDraw.Draw(pil)
                if not pil_font:
                    draw.text((lx, ly), text, fill=(255, 255, 255, 255))
                    return
                if text_style == 'Drop Shadow':
                    # getrennte Layer, siehe _draw_text_styled
                    off = max(2, sw)
                    if which == 'shadow':
                        draw.text((lx + off, ly + off), text, font=pil_font,
                                  fill=(0, 0, 0, 255))
                    else:
                        draw.text((lx, ly), text, font=pil_font,
                                  fill=(255, 255, 255, 255))
                elif text_style == 'None':
                    draw.text((lx, ly), text, font=pil_font,
                              fill=(255, 255, 255, 255))
                else:   # Hard Outline
                    draw.text((lx, ly), text, font=pil_font,
                              fill=(255, 255, 255, 255),
                              stroke_width=sw,
                              stroke_fill=(stroke_rgb[0], stroke_rgb[1],
                                           stroke_rgb[2], 255))
            return _draw

        parts = ('shadow', 'text') if text_style == 'Drop Shadow' else ('all',)
        for text, xrel, tw_ in zip(texts, x_offsets, widths):
            ox = (x0 + xrel) - border_thickness - 4
            lw = tw_ + border_thickness * 2 + 16
            if lw <= 0:
                continue
            lx = (x0 + xrel) - ox
            ly = y0 - oy + y_off
            for which in parts:
                key = ('statline', which, text, font_size, sw, text_style,
                       stroke_rgb, lw, lh, lx, ly)
                _blend_text_layer(img, _text_layer(key, (lw, lh),
                                                   _mk(text, lx, ly, which)),
                                  ox, oy)
    except Exception as e:
        print(f"⚠️ _draw_stats_pillow_shared: {e}")
