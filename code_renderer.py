"""
Code Renderer for FPS Analyzer
Replaces the PNG template renderer completely.

No external PNG files any more - everything is drawn programmatically, with
exactly the same visual result as the templates:
  - Schwarzer semi-transparenter Hintergrund (alpha=128/255 = 50%)
  - Horizontale Grid-Linien (hellgrau, alpha=179/255 = 70%)
  - title "FRAME RATE" / "FRAME TIME" (Bebas Neue with stroke)
  - axis labels on the right (computed automatically from the scale)
  - the dynamic line on top (cv2.polylines)

Advantages over PNG templates:
  - no templates/ dependency
  - scale changes take effect at once, without a new PNG file
  - Neue Graphen / Elemente in wenigen Zeilen Code
  - automatic scaling to any resolution
"""

import time
import collections
import itertools
import numpy as np
import cv2
from typing import Dict, List, Optional, Tuple

# ── Optional dependencies ─────────────────────────────────────────────────────
try:
    # noqa: F401 - Image and ImageFont look unused, but they belong to the
    # check: only when ALL THREE can be imported is Pillow really complete.
    # Remove them and PILLOW is wrongly set to True, so the error only shows
    # up later, while drawing.
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
        """'#RRGGBB' -> (B, G, R) for OpenCV. Fallback when color_manager is missing."""
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


# ── Constants (from the template analysis) ────────────────────────────────────
# Background: black, 50% opacity
BG_COLOR   = (0, 0, 0)
BG_ALPHA   = 128 / 255.0        # 0.502

# Grid lines: light grey, 70% opacity
GRID_COLOR = (145, 145, 145)
GRID_ALPHA = 179 / 255.0        # 0.702

# Title + axes: white, fully opaque
LABEL_COLOR     = (255, 255, 255)
LABEL_STROKE    = (0, 0, 0)

# Graph structure (relative to the template size, extracted from pixel analysis)
# FPS template 1840x580: graph area y=73..557 (4 sections of 121px each)
# Title area: 0..73 (transparent), graph: 73..557, bottom pad: 557..580
TITLE_H_RATIO  = 73  / 580    # ~12.6% of the height for the title area
BOTTOM_RATIO   = 23  / 580    # ~4%  Bottom-Padding
# -> graph area: 12.6% .. 96% of the template height
# 4 evenly spaced grid lines including top and bottom

import threading
# No global text lock needed any more: _FontCache is thread-local, so every
# worker renders with its own font instances -> real text parallelism.

MAX_GRAPH_POINTS = 180


# ═══════════════════════════════════════════════════════════════════════════════
# ##  MANUAL TEXT ADJUSTMENT  ##
# ═══════════════════════════════════════════════════════════════════════════════
# Manual fine-tuning of the text elements. All offset values are PIXELS at 4K
# (2160p height) and are scaled automatically to the output resolution - a
# value of 10 therefore shifts by 5px at 1080p and by 10px at 4K.
#
#   *_DX  : horizontal shift (+ = right, - = left)
#   *_DY  : vertical shift   (+ = down,  - = up)
#   *_SIZE: size MULTIPLIER (1.0 = default, 1.2 = 20% larger, 0.8 = smaller)
#
# "TITLE"  = the text ABOVE the graph ("FRAME RATE" / "FRAME TIME")
# "LABELS" = the axis labels to the RIGHT of the graph (60/30/0, or ms)
# ───────────────────────────────────────────────────────────────────────────────

# ── FRAME RATE ──
FR_TITLE_DX   = 0      # "FRAME RATE" text left/right
FR_TITLE_DY   = 0      # "FRAME RATE" text up/down
FR_TITLE_SIZE = 1.0    # "FRAME RATE" text size (multiplier)
FR_LABELS_DX   = 0     # axis labels (60/30/0) left/right
FR_LABELS_DY   = 0     # axis labels up/down
FR_LABELS_SIZE = 1.0   # axis label text size (multiplier)
FR_LABELS_GAP  = 5     # gap between the FR labels and the graph (4K px, + = further away)

# ── FRAME TIME ──
FT_TITLE_DX   = 0      # "FRAME TIME" Text links/rechts
FT_TITLE_DY   = 0      # "FRAME TIME" text up/down
FT_TITLE_SIZE = 1.0    # "FRAME TIME" text size (multiplier)
FT_LABELS_DX   = 0     # ms labels left/right
FT_LABELS_DY   = 0     # ms labels up/down
FT_LABELS_SIZE = 1.0   # ms label text size (multiplier)
FT_LABELS_GAP  = 5     # gap between the FT labels and the graph (4K px, + = further away)

# ── FPS number, top left ──
FPS_NUM_DX   = 0       # FPS number left/right
FPS_NUM_DY   = 0       # FPS number up/down
FPS_NUM_SIZE = 1.0     # FPS number text size (multiplier)
# ═══════════════════════════════════════════════════════════════════════════════


def _tweak_for(title):
    """Returns (title_dx, title_dy, title_size, lbl_dx, lbl_dy, lbl_size, lbl_gap) for a graph title."""
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
    """Composite a semi-transparent rectangle straight into img (in place)."""
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
    if x2 <= x1 or y2 <= y1:
        return
    roi = img[y1:y2, x1:x2].astype(np.float32)
    fg  = np.array(color, dtype=np.float32)
    img[y1:y2, x1:x2] = (roi * (1 - alpha) + fg * alpha).astype(np.uint8)


def _alpha_composite_hline(img: np.ndarray, y: int, x1: int, x2: int,
                            color: tuple, alpha: float, thickness: int = 1):
    """Semi-transparent horizontal line."""
    half = thickness // 2
    _alpha_composite_rect(img, x1, y - half, x2, y + half + 1, color, alpha)


def _find_font(size: int):
    """Load Bebas Neue, falling back to any available TTF."""
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
    Keeps loaded Pillow fonts THREAD-LOCAL in a cache (size as the key).

    FreeType (behind Pillow) is not thread-safe when the SAME font object is
    shared across threads. With thread-local instances every worker thread
    renders with its own font -> no global lock needed, and real parallelism
    while rendering text.
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
    Frosted glass: blur and darken the image area BEHIND the panel
    (gx,gy,gw,gh), writing straight into the overlay.

    Performance-Trick: Downscale → Blur (klein) → Upscale. Das Hochskalieren
    adds extra softness, and the blur runs on a fraction of the pixels.

    blur_strength: 0..100 (higher = blurrier)
    darken:        0..1  (0 = no darkening, 1 = black)
    """
    h, w = overlay.shape[:2]
    x1, y1 = max(0, gx), max(0, gy)
    x2, y2 = min(w, gx + gw), min(h, gy + gh)
    if x2 <= x1 or y2 <= y1:
        return

    roi = overlay[y1:y2, x1:x2]
    rh, rw = roi.shape[:2]

    # Always downscale heavily (a fixed small target area) -> the blur is cheap
    # and consistently fast, independent of the panel size. The blur strength
    # mainly controls the kernel on the small image plus how far it is scaled.
    target = max(60, int(200 - blur_strength))   # stronger = smaller = softer
    scale = min(1.0, target / max(rw, rh))
    small_w = max(1, int(rw * scale))
    small_h = max(1, int(rh * scale))

    small = cv2.resize(roi, (small_w, small_h), interpolation=cv2.INTER_AREA)
    k = max(1, int(blur_strength / 12) * 2 + 1)   # small kernel on a small image
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
    Renders the title and axis labels with real anti-aliasing onto a
    transparent RGBA overlay and composites it into the canvas with correct
    alpha. Keeps the soft edges (no mask threshold).
    Style: Hard Outline (Pillow-Stroke) / Drop Shadow (versetzte Kopie) / None.
    """
    if not PILLOW:
        return
    try:
        from PIL import Image as PILImage, ImageDraw as PILDraw
    except Exception:
        return

    # Transparent RGBA image at canvas size
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
            continue   # x prefix: no label
        label = item[0]
        lby = grid_y - vis_h_fn(label) // 2
        lby = max(0, min(canvas_h - label_fs, lby))
        _draw_one(label, label_x, lby, label_fs, sw_label)

    # Title
    _draw_one(title, title_x, title_y, title_fs, sw_title)

    # Composite into the RGBA canvas with correct alpha (over the existing BG/grid)
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
    Draw text with Pillow TrueType onto an ROI.
    Only the minimal ROI is converted (fast).
    """
    if not PILLOW:
        return _draw_text_opencv(img, text, x, y, font_size, color, stroke_color, stroke_width)

    font = _FontCache.get(font_size)
    if font is None:
        return _draw_text_opencv(img, text, x, y, font_size, color, stroke_color, stroke_width)

    # Determine the bounding box
    try:
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        y_off = -bbox[1]
    except Exception:
        tw, th, y_off = font_size * len(text), font_size, 0

    pad = stroke_width + 4
    # Unclipped layer geometry - the blend does the clipping.
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


# ── Graph drawing ─────────────────────────────────────────────────────────────

def draw_graph_background(img: np.ndarray,
                           gx: int, gy: int, gw: int, gh: int,
                           title: str,
                           grid_labels: List[str],
                           label_font_size: int,
                           title_font_size: int):
    """
    Draws the graph background exactly like the PNG template:
      - a transparent title area at the top
      - a semi-transparent black background (50%)
      - 5 horizontal grid lines (light grey 70%), evenly spaced
      - the title at the top left (Bebas Neue)
      - axis labels outside on the right
    """
    # Height of the title area (proportional, as in the template)
    title_h = int(gh * TITLE_H_RATIO / (1 - TITLE_H_RATIO - BOTTOM_RATIO))
    # Alternatively, directly: the graph area without the title is passed in
    # already. The caller provides gy such that the title sits above it.

    # 1. Black background (50% opacity)
    _alpha_composite_rect(img, gx, gy, gx + gw, gy + gh, BG_COLOR, BG_ALPHA)

    # 2. Grid lines (5 of them: top, 3 in the middle, bottom)
    n_lines = len(grid_labels)   # typically 3 (top, mid, bottom) -> but we have 5 lines
    # 5 evenly spaced lines matching the template (4 sections)
    n_sections = 4
    line_thickness = max(1, int(gh / 150))
    for i in range(n_sections + 1):
        ly = gy + int(i * gh / n_sections)
        _alpha_composite_hline(img, ly, gx, gx + gw, GRID_COLOR, GRID_ALPHA, line_thickness)

    # 3. Axis labels on the right (outside the graph area)
    label_x = gx + gw + max(4, int(gw * 0.008))
    for i, label in enumerate(grid_labels):
        # grid_labels[0] = top (max), grid_labels[-1] = bottom (min)
        if len(grid_labels) == 3:
            positions = [0, 2, 4]   # top, middle, bottom
        else:
            positions = list(range(len(grid_labels)))

        pos_idx = positions[i] if i < len(positions) else i
        label_y = gy + int(pos_idx * gh / n_sections) - label_font_size // 2
        label_y = max(gy, min(gy + gh - label_font_size, label_y))
        _draw_text_pillow(img, label, label_x, label_y,
                          label_font_size, LABEL_COLOR, LABEL_STROKE,
                          stroke_width=max(1, label_font_size // 12))

    # 4. Title at the top left (above the graph area)
    title_y = gy - title_font_size - max(4, int(gh * 0.02))
    title_y = max(0, title_y)
    _draw_text_pillow(img, title, gx, title_y,
                      title_font_size, LABEL_COLOR, LABEL_STROKE,
                      stroke_width=max(2, title_font_size // 10))


LINE_Y_PAD_EXTRA_4K = 0    # extra inner padding beyond the line thickness (4K reference)


def _line_y_bounds(gy, gh, s4k, line_thickness):
    """
    Top/bottom edge of the area in which the graph line is drawn.

    Used by all FOUR drawing paths (FPS and frame time, each with and without
    a playhead). The formula used to sit in the code four separate times -
    exactly the kind of duplication where a change lands in three places and
    not in the fourth.

    The inner padding is made up of two parts:
      • the border thickness `ot` - the border layer is blended AFTER the
        line. Without this part the upper half of the line disappears under
        the border, and the line looks thinner at the best value than at
        middling ones (measured at 4K: only 3 of 6 px visible).
      • half the line thickness - cv2 draws the line around its centre.

    With that, at the best value (60 fps or 16.7 ms) the line sits at full
    thickness right against the inner edge of the border, at any output
    resolution:

        Output    Border  Line    Gap old       new
        4K            3      6              8     6   (= 2 px gained)
        1080p         3      3              4     4   (was already flush)

    That also explains why the gap only showed at 4K - the old fixed formula
    happened to hit exactly the right value at 1080p.
    """
    ot = max(2, int(gh / 150)) + 1          # as in _get_border_layer
    pad = max(0, ot + line_thickness // 2
              + int(round(LINE_Y_PAD_EXTRA_4K * s4k)))
    return gy + pad, gy + gh - pad


def _draw_polyline_with_gaps(img, px_arr, py_arr, valid, color, line_thickness):
    """
    Draws the coloured measurement line for valid segments. Across invalid
    zones (fades, single-colour frames) a STRAIGHT WHITE line is drawn
    instead, connecting the last measured value with the next one - signalling
    'nothing is measured here' rather than leaving a gap.
    """
    n = len(px_arr)
    # 1. White bridges across gaps. Connects the last valid point with the
    #    next valid one. If the gap reaches the window edge (no valid
    #    neighbour on one side), the white line continues horizontally to that
    #    edge - so it stays visible throughout while the fade zone scrolls
    #    through the window (in from the right, out to the left).
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
            # The gap reaches the right edge -> horizontal from the last value
            p1 = (int(px_arr[left]), int(py_arr[left]))
            p2 = (int(px_arr[n - 1]), int(py_arr[left]))
        elif has_right:
            # The gap reaches the left edge -> horizontal to the next value
            p1 = (int(px_arr[0]), int(py_arr[right]))
            p2 = (int(px_arr[right]), int(py_arr[right]))
        else:
            p1 = p2 = None
        if p1 is not None:
            cv2.line(img, p1, p2, (255, 255, 255), line_thickness, cv2.LINE_AA)
        i = right

    # 2. Coloured measurement line for the valid segments (drawn over the bridge)
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
    """Thin vertical centre line (the current frame)."""
    cx = gx + gw // 2
    th = max(1, int(2 * s4k))
    y1, y2 = gy, gy + gh
    roi = img[y1:y2, max(0, cx - th//2):cx + th//2 + 1].astype(np.float32)
    white = np.full_like(roi, 255)
    img[y1:y2, max(0, cx - th//2):cx + th//2 + 1] = (roi * 0.25 + white * 0.75).astype(np.uint8)


def _prepare_window(seq, center_idx, half):
    """
    Returns a centred window [center-half, center+half] of fixed length
    2*half+1. Missing edges (start/end of the video) and None/NaN are marked
    invalid. Returns (values[], valid[]).
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
    Dynamic FPS line; value_scale=(map_x, map_f) for a piecewise linear scale.
    playhead=(full_seq, center_idx): DF style - the window is centred on
    center_idx, the left half is the past, the right half the future, and the
    centre line is marked.
    """
    s4k = img.shape[0] / 2160.0
    x_off = max(1, int(3 * s4k))
    x_r3  = max(1, int(3 * s4k))   # trim 3px on the right

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
        # 3px (at 4K) padding top and bottom: at 60fps the line sits just below
        # the top border and at 0fps just above the bottom one, not exactly on them.
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
    """Dynamic frame time line; playhead=(full_seq, center_idx) for DF style."""
    s4k = img.shape[0] / 2160.0
    x_l = max(1, int(4 * s4k))
    x_r = max(1, int(2 * s4k)) + max(1, int(3 * s4k))   # trim 2px + 3px
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




# ── Main renderer ─────────────────────────────────────────────────────────────

class CodeRenderer:
    """
    A fully code-based renderer - no PNG template needed any more.
    A drop-in replacement for PNGTemplateRenderer.render_overlay().
    """

    def __init__(self):
        self.render_times: collections.deque = collections.deque(maxlen=300)
        self._frame_count = 0
        self._current_layout_config = None
        # Cache for pre-rendered backgrounds (key = (gx,gy,gw,gh,title,labels_tuple)).
        # Rendered once, then blended via CUDA - just as fast as PNG templates.
        self._bg_cache: Dict[tuple, np.ndarray] = {}
        print("✅ CodeRenderer initialized — no PNG templates needed")

    def _blend_prep(self, layer):
        """
        Prepare the blend data for a CACHED layer ONCE.

        Background (measured on the real layers, 2021x474 on a 4K canvas):
        the previous CPU blend converted three full arrays to float32 per
        frame (alpha, fg, roi) - even though alpha and fg never change,
        because the layer comes from the cache. That is expensive per frame
        and per layer:

            Variant                                     bg layer   Border
            A  as before (3x float32 conversion)          19.95ms   19.41ms
            B  premultiplied (cached)                      5.78ms    7.02ms
            C  uint16 integers                             7.63ms    9.68ms
            D  only pixels with alpha>0                   16.92ms    0.76ms

        Which variant wins depends on the layer's alpha occupancy:
            bg layer:     76.7% partly transparent -> B is optimal (3.45x)
            border layer: 98.6% FULLY transparent  -> D is optimal (25.4x)

        So the choice is made per layer automatically here, and the result is
        cached together with the layer.
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
            # Sparsely occupied (borders, text) -> touch only the pixels with
            # alpha>0. IMPORTANT: row/column indices, NOT flat indices onto a
            # reshape(-1,3). A slice of the overlay is not contiguous, and
            # reshape on it silently returns a COPY, so the blend lands
            # nowhere (in testing: the border was not drawn at all).
            rows, cols = np.nonzero(a8)
            af = (a8[rows, cols].astype(np.float32) / 255.0)[:, None]
            fg = layer[rows, cols, :3].astype(np.float32)
            prep = {'mode': 'sparse', 'shape': layer.shape,
                    'rows': rows, 'cols': cols,
                    'inv': 1.0 - af, 'pre': fg * af}
        else:
            # Densely occupied (graph backgrounds) -> premultiplied
            a = a8[:, :, None].astype(np.float32) / 255.0
            prep = {'mode': 'dense', 'shape': layer.shape,
                    'inv': 1.0 - a,
                    'pre': layer[:, :, :3].astype(np.float32) * a}
        cache[key] = prep
        # Keep a reference so id() is not recycled by the GC and assigned to
        # a different array
        prep['_ref'] = layer
        return prep

    def _blend_rgba(self, overlay, layer, blend_x, blend_y, w, h):
        """Composite an RGBA layer at (blend_x, blend_y) into the overlay (CUDA or CPU)."""
        if _cuda_blender is not None and not getattr(self, 'force_cpu_blend', False):
            _cuda_blender.blend(overlay, layer, blend_x, blend_y)
            return
        self._blend_rgba_cpu(overlay, layer, blend_x, blend_y, w, h)

    def _blend_rgba_cpu(self, overlay, layer, blend_x, blend_y, w, h):
        """Optimised CPU blend, see _blend_prep for the measurements."""
        bh, bw = layer.shape[:2]
        y2 = min(h, blend_y + bh)
        x2 = min(w, blend_x + bw)
        th, tw = y2 - blend_y, x2 - blend_x
        if th <= 0 or tw <= 0:
            return

        prep = self._blend_prep(layer)

        # The fast sparse path works on flat indices of the FULL layer - it is
        # only valid while the layer is not clipped.
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
            # Clipped sparse layer -> recompute it densely, once
            a = layer[:th, :tw, 3:4].astype(np.float32) / 255.0
            inv = 1.0 - a
            pre = layer[:th, :tw, :3].astype(np.float32) * a

        roi = overlay[blend_y:y2, blend_x:x2].astype(np.float32)
        overlay[blend_y:y2, blend_x:x2] = (roi * inv + pre).astype(np.uint8)

    def _get_border_layer(self, gx, gy, gw, gh, title, label_font_size, title_font_size, frame_w, frame_h):
        """
        Separate border layer (white outline / soft glow only), cached.
        Blended AFTER the FPS/FT line so its overshoot at the graph edge is
        hidden. Same canvas geometry as _get_bg_layer.
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

        ot = max(2, int(gh / 150)) + 1   # 1px thicker
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
        Returns a pre-rendered RGBA template.
        grid_items: a list of (label, fraction) - fraction 0.0 = top, 1.0 = bottom.
        One grid line plus label is drawn per entry (any number of values).
        Overlay styles (text_style / graph_border / bg_opacity) come from
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

        # 1. Background fill: SKIPPED with frosted glass (the blurred frame
        #    then provides the background). Otherwise a black fill with the
        #    opacity from the Layout Editor.
        frosted = bool(style.get('frosted_glass', False))
        if not frosted:
            _rect_rgba(cx, cy, cx + gw, cy + gh, BG_COLOR, bg_opacity)

        # 2. Graph border: NOT drawn here - it comes as a separate layer AFTER
        #    the FPS/FT line, so the line's overshoot at the edge is hidden.
        #    (see _get_border_layer + the blend order in render_overlay)

        # 3. Grid lines - one per grid_item at its fraction
        line_thickness = max(1, int(gh / 150))
        grid_ys = [cy + int(item[1] * gh) for item in grid_items]
        for item, ly in zip(grid_items, grid_ys):
            hidden = len(item) > 2 and item[2]
            if hidden:
                # x prefix: a grey, more subtle line
                _hline_rgba(ly, cx, cx + gw, (128, 128, 128),
                            GRID_ALPHA * 0.55, line_thickness)
            else:
                _hline_rgba(ly, cx, cx + gw, GRID_COLOR, GRID_ALPHA, line_thickness)

        # 4. Text - stroke width from overlay_style (outline_width), scaled.
        #    IMPORTANT: scale to frame_h (like the FPS number + stats), NOT to
        #    canvas_h (the small template height) - otherwise the title and
        #    labels would get a far thinner outline than the other text.
        style = getattr(self, '_overlay_style', {}) or {}
        ow_base = style.get('outline_width', None)
        if ow_base is not None:
            sw_val = max(0, int(round(float(ow_base) * max(1.0, frame_h / 1080.0))))
        else:
            sw_val = max(2, label_font_size // 8)
        sw_label = sw_title = sw_val
        if text_style == 'None':
            sw_label = sw_title = 0

        # ── Manual adjustment (the tweak block at the top of the file) ──
        s4k_lbl = canvas_h / 2160.0
        t_tdx, t_tdy, t_tsize, l_ldx, l_ldy, l_lsize, l_gap = _tweak_for(title)
        # 4K-Offsets → Ausgabepixel
        title_dx  = int(t_tdx * s4k_lbl)
        title_dy  = int(t_tdy * s4k_lbl)
        lbl_dx    = int(l_ldx * s4k_lbl)
        lbl_dy    = int(l_ldy * s4k_lbl)
        # Size multipliers
        title_fs  = max(6, int(title_font_size * t_tsize))
        label_fs  = max(6, int(label_font_size * l_lsize))

        # Base label position: per-graph gap + individual tweak
        label_x  = cx + gw + max(3, int(gw * 0.012) - int(l_gap * s4k_lbl)) + lbl_dx
        title_y  = max(0, cy - title_font_size - max(2, int(gh * 0.01))) + title_dy
        title_x  = cx + title_dx

        # Glyph height for vertical centring (with the tweaked label size)
        _f = _FontCache.get(label_fs)
        def _vis_h(t):
            try:
                bb = _f.getbbox(t)
                return bb[3] - bb[1]
            except Exception:
                return label_fs

        # Render the text into the RGBA canvas with REAL anti-aliasing.
        # Instead of a mask threshold (which destroys AA edges), the text is
        # drawn onto a transparent RGBA Pillow image and composited into the
        # canvas with correct alpha - keeping soft edges like the FPS number.
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
        """Default layout for 1080p, scaled to the target resolution."""
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
        Main rendering function.
        The same signature as PNGTemplateRenderer.render_overlay()
        -> a drop-in replacement, no changes needed in the calling code.
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

        # Read the FPS/FT scale from template_config - any number of grid values
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

        # EQUIDISTANT grid labels: all values evenly spaced, independent of
        # their numeric distance (e.g. 16.7,25,33.3,100). The lines are mapped
        # onto the same positions through a piecewise linear scale (np.interp),
        # so line and labels line up.
        fps_sorted_desc = sorted(set(fps_grid_values), reverse=True)
        n_fps = max(1, len(fps_sorted_desc) - 1)
        fps_grid_items = [
            (f"{v:g}", i / n_fps, v in fps_hidden)
            for i, v in enumerate(fps_sorted_desc)
        ]
        # Mapping arrays for np.interp (x ascending)
        # x ascending; frac: smallest value at the bottom (1.0), largest at the top (0.0)
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

        # Font sizes
        scale = min(w / 1920, h / 1080)
        # Text boost (e.g. comparison mode: larger title/labels for legibility)
        _tb = float((getattr(self, '_overlay_style', {}) or {}).get('text_boost', 1.0))
        title_size    = max(8, int(36 * scale * _tb))
        label_size_ft = max(8, int(19 * scale * _tb))
        label_size_fr = max(8, int(24 * scale * _tb))
        label_size    = label_size_ft
        # Line thickness: base @1080p from the Layout Editor (default 2px), scaled
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

            # Frosted glass: ONLY the graph box area (not the title/labels)
            _st = getattr(self, '_overlay_style', {}) or {}
            if _st.get('frosted_glass', False):
                _apply_frosted_glass(overlay, gx, gy, gw, gh,
                                     blur_strength=int(_st.get('frost_blur', 25)),
                                     darken=float(_st.get('frost_darken', 0.35)))

            # Fetch the background from the cache and blend it via CUDA (small, like a PNG template)
            bg = self._get_bg_layer(gx, gy, gw, gh, "FRAME RATE", fps_grid_items,
                                    label_size_fr, title_size, w, h)
            # Canvas-Ursprung = gx, gy minus title_margin
            title_margin = title_size + max(6, int(gh * 0.02)) + 8
            left_m   = max(3, int(gw * 0.003))
            blend_x  = max(0, gx - left_m)
            blend_y  = max(0, gy - title_margin)
            # Centrally through _blend_rgba - uses the optimised CPU path with
            # prepared, cached alpha data (see _blend_prep).
            self._blend_rgba(overlay, bg, blend_x, blend_y, w, h)

            _ph_fps = (full_fps_seq, playhead_index) if (playhead_index is not None and full_fps_seq is not None) else None
            draw_fps_line(overlay, fps_history, gx, gy, gw, gh,
                          framerate_color, fps_max, line_thick,
                          value_scale=getattr(self, '_fps_scale', None),
                          playhead=_ph_fps)

            # Blend the border layer ON TOP of the line (hides the line overshoot)
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

            # Frosted glass: ONLY the graph box area (not the title/labels)
            _st = getattr(self, '_overlay_style', {}) or {}
            if _st.get('frosted_glass', False):
                _apply_frosted_glass(overlay, gx, gy, gw, gh,
                                     blur_strength=int(_st.get('frost_blur', 25)),
                                     darken=float(_st.get('frost_darken', 0.35)))

            # Fetch the background from the cache and blend it via CUDA
            bg = self._get_bg_layer(gx, gy, gw, gh, "FRAME TIME", ft_grid_items,
                                    label_size_ft, title_size, w, h)
            title_margin = title_size + max(6, int(gh * 0.02)) + 8
            left_m   = max(3, int(gw * 0.003))
            blend_x  = max(0, gx - left_m)
            blend_y  = max(0, gy - title_margin)
            # Centrally through _blend_rgba - uses the optimised CPU path with
            # prepared, cached alpha data (see _blend_prep).
            self._blend_rgba(overlay, bg, blend_x, blend_y, w, h)

            _ph_ft = (full_ft_seq, playhead_index) if (playhead_index is not None and full_ft_seq is not None) else None
            draw_frametime_line(overlay, frame_times, gx, gy, gw, gh,
                                frametime_color, ft_min, ft_max_val, line_thick,
                                value_scale=getattr(self, '_ft_scale', None),
                                playhead=_ph_ft)

            # Blend the border layer ON TOP of the line
            border = self._get_border_layer(gx, gy, gw, gh, "FRAME TIME",
                                             label_size_ft, title_size, w, h)
            self._blend_rgba(overlay, border, blend_x, blend_y, w, h)
        t_debug['ft_graph'] = time.perf_counter() - t0

        # ── 3. FPS number ──────────────────────────────────────────────────────
        t0 = time.perf_counter()
        fpsd = layout_config.get('fps_display', {})
        if fpsd.get('visible', True):
            fps_font_size = FontSizeConfig.get_absolute_size('fps_number', w, h)
            multiplier    = fpsd.get('font_scale_multiplier', 1.0)
            if multiplier != 1.0:
                fps_font_size = int(fps_font_size * multiplier)
            # Manual FPS number adjustment (tweak block)
            _s4k_fps = h / 2160.0
            fps_font_size = max(6, int(fps_font_size * FPS_NUM_SIZE))
            _fps_dx = int(FPS_NUM_DX * _s4k_fps)
            _fps_dy = int(FPS_NUM_DY * _s4k_fps)
            # The FPS number sits exactly on its layout position (no legacy
            # offset any more) - so the Layout Editor and the video agree and
            # the number can be positioned freely.
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
            # Render the FPS number through the thread-local font cache (no shared
            # font object is mutated -> thread-safe without a lock).
            _pf = _FontCache.get(fps_font_size)

            _fx = fpsd['x'] + _fps_dx
            # Style-bewusster Pillow-Pfad (Hard Outline / Drop Shadow / None),
            # uses the thread-local font.
            overlay = _draw_text_styled(
                overlay, fps_text,
                _fx, fpsd['y'] + y_offset,
                fps_font_size, _style_mode, _sw, pil_font=_pf)
        t_debug['fps_number'] = time.perf_counter() - t0

        # ── 4. Statistics ──────────────────────────────────────────────────────
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

        # FPS statistics
        fps_stat_data = None
        if precomputed_stats and 'fps' in precomputed_stats:
            fps_stat_data = precomputed_stats['fps']
        elif global_fps_values and len(global_fps_values) > 60:
            rec = list(global_fps_values)[-300:]
            fps_stat_data = {'avg': sum(rec)/len(rec),
                             'min': min(rec), 'max': max(rec)}
        _draw_stats('fps_statistics', fps_stat_data)

        # Frame time statistics
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
        # ── Stats panel (alternative display mode) ──────────────────────────
        # Drawn after the graphs so it sits on top. When it is active the
        # classic graphs are normally switched off - but that is decided by
        # the layout, not by the renderer.
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
                    print(f"⚠️ Could not draw the stats panel: {_e}")
                    self._panel_err_logged = True

        # ── Deviation marker ────────────────────────────────────────────────
        # A red block in the top right corner for as long as the footage
        # deviates from the baseline value. Deliberately drawn at the very
        # end, so it sits above everything else.
        if full_dev_seq is not None and playhead_index is not None:
            if 0 <= playhead_index < len(full_dev_seq) and full_dev_seq[playhead_index]:
                _st = getattr(self, '_overlay_style', {}) or {}
                # Size in 1080p pixels, like every other layout value, scaled
                # with the output height - otherwise the block would be only a
                # quarter of the intended size at 4K.
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

        # ── Accumulate the stage timings thread-safely ──────────────────
        # This used to print per frame and was suppressed entirely in parallel
        # mode, which meant the 6-worker run produced no breakdown at all.
        # Now it is accumulated and reported once at the end.
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
        Breakdown of the overlay time, summed across all worker threads.
        Returns None when nothing was measured.
        """
        acc = getattr(self, '_stage_acc', None)
        if not acc or not acc['n']:
            return None
        n = acc['n']
        parts = [(k, acc.get(k, 0.0)) for k in
                 ('copy', 'fps_graph', 'ft_graph', 'fps_number', 'statistics')]
        total = acc['total'] or 1e-9
        lines = [f"🔬 Overlay breakdown ({n} frames, "
                 f"{total:.1f}s Worker-Zeit gesamt):"]
        named = {'copy': 'Copy frame',
                 'fps_graph': 'FPS graph (frosted glass+blend+line)',
                 'ft_graph': 'Frametime-Graph',
                 'fps_number': 'FPS number (text)',
                 'statistics': 'Statistics text'}
        acc_sum = 0.0
        for k, v in parts:
            acc_sum += v
            lines.append(f"     {named[k]:34s} {v*1000/n:7.2f} ms/Frame "
                         f"({100*v/total:5.1f}%)")
        rest = total - acc_sum
        lines.append(f"     {'other (setup/layout)':34s} {rest*1000/n:7.2f} ms/frame "
                     f"({100*rest/total:5.1f}%)")
        _tc = text_cache_stats()
        if _tc:
            lines.append(f"     {_tc}")
        return "\n".join(lines)


_TEXT_LAYER_CACHE: "collections.OrderedDict[tuple, tuple]" = collections.OrderedDict()
_TEXT_LAYER_LOCK = threading.Lock()
_TEXT_LAYER_BUDGET = 192 * 1024 * 1024   # bytes, LRU eviction
_TEXT_LAYER_BYTES = [0]
_TEXT_LAYER_STATS = {'hit': 0, 'miss': 0}


def _text_layer(key, size_wh, draw_fn):
    """
    Returns a cached RGBA text layer, rendering it on first use.

    Why: the statistics and FPS text were redrawn completely every frame -
    convert the ROI to RGB, copy it into a PIL image, render the text WITH a
    stroke (which draws the glyph several times), copy it back, convert it
    back.

    The cache has to avoid three traps, all three of which hit on the first
    attempt (measured on the 4K run, 1659 statistics frames):

      1. Do NOT cache the whole statistics block as one layer. AVG, MIN and
         MAX change independently -> 243 different combinations. Cached per
         line it is 92 / 31 / 131 layers, i.e. hit rates of
         94.5% / 98.1% / 92.1%.
      2. Do NOT key on id(pil_font). _FontCache is thread-local, so each of
         the 6 workers would get its own entries for identical content -> a
         sixfold multiplication. The font size in the key is enough, because
         _FontCache.get(size) deterministically returns the same font.
         After rendering, the layers are read-only -> shareable.
      3. Do NOT clear the whole cache on overflow. 243 x 6 threads x 2 blocks
         became 2916 entries against a limit of 512 - the cache kept clearing
         itself and was practically useless (21.88 ms -> 20.55 ms instead of
         the expected ~2 ms). Now it is LRU with a memory budget.

    draw_fn(pil_image) draws the text onto a transparent RGBA image.
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
    # The drawing routines used to work on an ROI swapped by cvtColor and
    # swapped it back afterwards. So the layer can be blended straight into
    # the image, the swap is done once here instead of twice per frame on the
    # whole ROI.
    layer = np.ascontiguousarray(layer[:, :, [2, 1, 0, 3]])

    # Prepare the blend data at the same time. Text layers are >85%
    # transparent, so the sparse path pays off especially well here.
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
            # LRU eviction instead of clearing everything
            while _TEXT_LAYER_BYTES[0] > _TEXT_LAYER_BUDGET and len(_TEXT_LAYER_CACHE) > 1:
                _k, _v = _TEXT_LAYER_CACHE.popitem(last=False)
                _l, _p = _v
                _TEXT_LAYER_BYTES[0] -= (_l.nbytes + _p['rows'].nbytes
                                         + _p['cols'].nbytes
                                         + _p['inv'].nbytes * 2
                                         + _p['pre'].nbytes)
    return entry


def text_cache_stats():
    """Hit rate of the text layer cache (for runtime diagnostics)."""
    h, m = _TEXT_LAYER_STATS['hit'], _TEXT_LAYER_STATS['miss']
    if h + m == 0:
        return None
    return (f"Textlayer-Cache: {100*h/(h+m):.1f}% Treffer "
            f"({h} Treffer / {m} Misses), {len(_TEXT_LAYER_CACHE)} Layer, "
            f"{_TEXT_LAYER_BYTES[0]/1024**2:.0f} MB")


_TEXT_WIDTH_CACHE: Dict[tuple, int] = {}


def _text_width(draw, text, font, font_size):
    """Measure text width - cached, because the font layout ran every frame."""
    k = (text, font_size)
    w = _TEXT_WIDTH_CACHE.get(k)
    if w is None:
        w = int(draw.textlength(text, font=font)) if font else len(text) * font_size // 2
        _TEXT_WIDTH_CACHE[k] = w
    return w


def _blend_text_layer(img, entry, ox, oy):
    """
    Blend a text layer at (ox, oy) into img, including clipping at the image
    edges (also with a negative origin).
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

    # Handle clipping in the sparse path too. Previously every clipped layer
    # falls back to the dense path - and that is the normal case, not the
    # exception: the FPS number sits so high up that the layer origin becomes
    # negative (y=88 with pad=96). That made the cached path even SLOWER than
    # the original redraw.
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
    """Draw text with an overlay style: Hard Outline / Drop Shadow / None."""
    try:
        from PIL import ImageDraw as PILDraw
        if pil_font is None:
            pil_font = _FontCache.get(size)
        h, w = img.shape[:2]
        pad = size + stroke_w + 8
        # Unclipped layer geometry (the blend does the clipping)
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
                    # Shadow and text as SEPARATE layers, blended one after
                    # the other. Drawing both into one layer gives different
                    # alpha values along the overlap edge than the original
                    # direct drawing onto the background (measured: up to 65
                    # levels of deviation across 146 pixels).
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

        # NO id(pil_font) in the key: _FontCache is thread-local, which would
        # give every worker its own entries for identical content. The size is
        # enough, because _FontCache.get(size) is deterministic.
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
    """Draw the stats in a single Pillow ROI (fast).
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

        # Load the font thread-locally (do not mutate a shared object) - the
        # stats size is taken straight from the thread-local cache.
        pil_font = _FontCache.get(font_size)

        # Spacing from the measured text width instead of a fixed spacing -
        # prevents overlap at any resolution and font size.
        gap = max(12, font_size)
        probe = PILDraw.Draw(PILImage.new('RGB', (8, 8)))
        # Widths cached - the font layout used to run per frame and per line
        widths = [_text_width(probe, t, pil_font, font_size) for t in texts]
        x_offsets = [0,
                     widths[0] + gap,
                     widths[0] + gap + widths[1] + gap]
        total_w = x_offsets[2] + widths[2] + border_thickness * 2 + 16
        total_h = font_size + border_thickness * 2 + int(font_size * 0.4) + 20

        ih, iw = img.shape[:2]
        # Unclipped layer geometry - the blend takes care of the clipping
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

        # EVERY line as its own layer: AVG, MIN and MAX change independently
        # of each other. As one shared layer there would be the product of all
        # combinations (measured: 243 instead of 92/31/131).
        def _mk(text, lx, ly, which):
            def _draw(pil):
                draw = PILDraw.Draw(pil)
                if not pil_font:
                    draw.text((lx, ly), text, fill=(255, 255, 255, 255))
                    return
                if text_style == 'Drop Shadow':
                    # separate layers, see _draw_text_styled
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
