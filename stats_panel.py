"""
Stats panel - an alternative display mode in the style of classic benchmark
overlays.

A rounded, semi-transparent box with alternating light and dark bands. From
top to bottom:

    1  title (game name)
    2  large FPS number + AVG / MIN / MAX
    3  FPS graph with a centre line
    4  console + version (two fixed fields)
    5  up to three freely assignable rows (1 wide OR 2 narrow fields each)
    6  frame time graph

The bands alternate between BAND_DARK and BAND_LIGHT, starting dark.

PERFORMANCE
By far the largest part of the panel is identical across the whole clip:
bands, rounded corners, title, console, version, extra fields and the
labels. Only the FPS number, AVG/MIN/MAX and the two graphs change. So the
static part is rendered into an RGBA layer ONCE and only blended after
that - the same strategy that took the main overlay from 213 ms to 27 ms.
Per frame, only the few dynamic elements are left to draw.
"""

import threading

import numpy as np
import cv2

try:
    from PIL import Image as PILImage, ImageDraw as PILDraw
    PILLOW = True
except ImportError:  # pragma: no cover
    PILLOW = False

try:
    from code_renderer import _FontCache
except Exception:  # pragma: no cover
    _FontCache = None


# ── Colours & measurements (all pixel values relative to 1080p) ─────────────

BAND_DARK = (0x2b, 0x2b, 0x2b)
BAND_LIGHT = (0x44, 0x44, 0x44)

DEFAULTS = {
    'x': 40, 'y': 40, 'width': 460,
    'opacity': 0.88,
    'corner_radius': 14,
    'pad_x': 14,
    'title_h': 40,
    'fps_h': 76,
    'graph_h': 62,
    'row_h': 34,
    'ft_graph_h': 46,
    'title_size': 26,
    'fps_size': 54,
    'stat_size': 20,
    'row_size': 21,
    'line_thickness': 2,
}

MAX_EXTRA_LINES = 3          # in addition to the fixed console/version row
GRAPH_WINDOW = 180           # frames in the graph window (3 s at 60 fps)


def hex_to_rgb(c, fallback=(255, 255, 255)):
    if isinstance(c, (tuple, list)):
        return tuple(int(v) for v in c[:3])
    h = str(c).lstrip('#')
    if len(h) != 6:
        return fallback
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return fallback


def default_config():
    """A fresh configuration with sensible starting values."""
    return {
        'enabled': False,
        'title': {'text': '', 'color': '#FFFFFF'},
        'console': {'text': '', 'color': '#FFFFFF'},
        'version': {'text': '', 'color': '#FFFFFF'},
        'extra_lines': [],          # list of rows, 1 or 2 fields each
        'fps_color': '#FFFFFF',
        'ft_color': '#FFFFFF',
        'stat_color': '#BBBBBB',
        'geometry': dict(DEFAULTS),
    }


def normalize_config(cfg):
    """
    Bring a configuration into a valid state.

    Enforces the rules of the interface even when the file was edited by
    hand: at most MAX_EXTRA_LINES rows, at most two fields per row, and a
    wide field always sits alone in its row.
    """
    base = default_config()
    if not isinstance(cfg, dict):
        return base
    out = dict(base)
    out.update({k: v for k, v in cfg.items() if k in base})

    for key in ('title', 'console', 'version'):
        f = cfg.get(key) or {}
        out[key] = {'text': str(f.get('text', '')),
                    'color': f.get('color', '#FFFFFF')}

    lines = []
    for line in (cfg.get('extra_lines') or [])[:MAX_EXTRA_LINES]:
        fields = []
        for f in (line or [])[:2]:
            fields.append({'text': str((f or {}).get('text', '')),
                           'color': (f or {}).get('color', '#FFFFFF'),
                           'wide': bool((f or {}).get('wide', False))})
        if not fields:
            continue
        # A wide field occupies the whole row on its own.
        if fields[0]['wide']:
            fields = fields[:1]
        elif len(fields) == 2 and fields[1]['wide']:
            fields[1]['wide'] = False
        lines.append(fields)
    out['extra_lines'] = lines

    geo = dict(DEFAULTS)
    geo.update(cfg.get('geometry') or {})
    out['geometry'] = geo
    return out


# ── Geometry ─────────────────────────────────────────────────────────────────

def _bands(cfg, s):
    """
    Heights and colours of all bands from top to bottom.

    Returns a list of (kind, height, band_color).
    """
    g = cfg['geometry']
    def px(k):
        return max(1, int(round(g.get(k, DEFAULTS[k]) * s)))

    rows = [('title', px('title_h')),
            ('fps', px('fps_h')),
            ('fps_graph', px('graph_h')),
            ('fixed', px('row_h'))]
    for _ in cfg['extra_lines']:
        rows.append(('extra', px('row_h')))
    rows.append(('ft_graph', px('ft_graph_h')))

    out = []
    for i, (kind, h) in enumerate(rows):
        out.append((kind, h, BAND_DARK if i % 2 == 0 else BAND_LIGHT))
    return out


def panel_size(cfg, s):
    g = cfg['geometry']
    w = max(1, int(round(g.get('width', DEFAULTS['width']) * s)))
    h = sum(b[1] for b in _bands(cfg, s))
    return w, h


def panel_origin(cfg, s):
    g = cfg['geometry']
    return (int(round(g.get('x', DEFAULTS['x']) * s)),
            int(round(g.get('y', DEFAULTS['y']) * s)))


def _rounded_mask(w, h, radius):
    """Alpha mask for rounded corners (0..255)."""
    m = np.zeros((h, w), dtype=np.uint8)
    r = int(max(0, min(radius, min(w, h) // 2)))
    if r <= 0:
        m[:] = 255
        return m
    cv2.rectangle(m, (r, 0), (w - r - 1, h - 1), 255, -1)
    cv2.rectangle(m, (0, r), (w - 1, h - r - 1), 255, -1)
    for cx, cy in ((r, r), (w - r - 1, r), (r, h - r - 1), (w - r - 1, h - r - 1)):
        cv2.circle(m, (cx, cy), r, 255, -1, cv2.LINE_AA)
    return m


# ── Text ─────────────────────────────────────────────────────────────────────

def _font(size):
    if _FontCache is not None:
        return _FontCache.get(max(1, int(size)))
    return None


def _text(draw, xy, s, size, color, anchor=None):
    f = _font(size)
    try:
        draw.text(xy, str(s), font=f, fill=tuple(color) + (255,), anchor=anchor)
    except Exception:
        draw.text(xy, str(s), fill=tuple(color) + (255,))


def _text_w(draw, s, size):
    f = _font(size)
    try:
        return int(draw.textlength(str(s), font=f))
    except Exception:
        return len(str(s)) * size // 2


# ── Static layer ─────────────────────────────────────────────────────────────

_STATIC_CACHE = {}
_STATIC_LOCK = threading.Lock()


def _static_key(cfg, s):
    def fkey(f):
        return (f.get('text', ''), str(f.get('color', '')), bool(f.get('wide', False)))
    return (round(s, 4),
            fkey(cfg['title']), fkey(cfg['console']), fkey(cfg['version']),
            tuple(tuple(fkey(f) for f in line) for line in cfg['extra_lines']),
            str(cfg.get('stat_color')),
            tuple(sorted((k, v) for k, v in cfg['geometry'].items())),
            round(float(cfg['geometry'].get('opacity', DEFAULTS['opacity'])), 3))


def build_static_layer(cfg, s):
    """
    Bands, corners and all unchanging text as an RGBA layer.

    Built once per configuration and reused for every frame after that.
    wiederverwendet.
    """
    key = _static_key(cfg, s)
    with _STATIC_LOCK:
        hit = _STATIC_CACHE.get(key)
    if hit is not None:
        return hit

    w, h = panel_size(cfg, s)
    g = cfg['geometry']
    pad = max(2, int(round(g.get('pad_x', DEFAULTS['pad_x']) * s)))
    opacity = float(g.get('opacity', DEFAULTS['opacity']))

    layer = np.zeros((h, w, 4), dtype=np.uint8)

    # Fill the bands
    geo = {}
    y = 0
    for kind, bh, col in _bands(cfg, s):
        layer[y:y + bh, :, :3] = col[::-1] if False else col
        geo.setdefault(kind, []).append((y, bh))
        y += bh
    layer[:, :, 3] = 255

    # Rounded corners
    radius = int(round(g.get('corner_radius', DEFAULTS['corner_radius']) * s))
    mask = _rounded_mask(w, h, radius)
    layer[:, :, 3] = (mask.astype(np.float32) * opacity).astype(np.uint8)

    # Text
    if PILLOW:
        pil = PILImage.fromarray(layer, 'RGBA')
        draw = PILDraw.Draw(pil)

        def sz(k):
            return max(6, int(round(g.get(k, DEFAULTS[k]) * s)))

        # Title
        ty, th = geo['title'][0]
        _text(draw, (pad, ty + th // 2), cfg['title']['text'],
              sz('title_size'), hex_to_rgb(cfg['title']['color']), anchor='lm')

        # Console + version (fixed row, two columns)
        fy, fh = geo['fixed'][0]
        half = w // 2
        _text(draw, (pad, fy + fh // 2), cfg['console']['text'],
              sz('row_size'), hex_to_rgb(cfg['console']['color']), anchor='lm')
        _text(draw, (half + pad // 2, fy + fh // 2), cfg['version']['text'],
              sz('row_size'), hex_to_rgb(cfg['version']['color']), anchor='lm')

        # Zusatzzeilen
        for (ry, rh), fields in zip(geo.get('extra', []), cfg['extra_lines']):
            if len(fields) == 1 and fields[0].get('wide'):
                _text(draw, (pad, ry + rh // 2), fields[0]['text'],
                      sz('row_size'), hex_to_rgb(fields[0]['color']), anchor='lm')
            else:
                for i, f in enumerate(fields[:2]):
                    fx = pad if i == 0 else half + pad // 2
                    _text(draw, (fx, ry + rh // 2), f['text'],
                          sz('row_size'), hex_to_rgb(f['color']), anchor='lm')

        rgba = np.array(pil)
        # Text is fully opaque; the band transparency applies only to the
        # background, otherwise the type looks washed out.
        layer = rgba

    entry = (layer, geo, _premultiply(layer))
    with _STATIC_LOCK:
        _STATIC_CACHE[key] = entry
    return entry


def _premultiply(layer):
    """
    Prepare the static layer's blend data once.

    Without this, the whole panel would be converted to float32 three times
    per frame (alpha, foreground, background) - at 4K that is 920x652 pixels,
    and the data never changes. Prepared like this, only one multiplication
    plus one addition is left per frame.
    """
    a = layer[:, :, 3:4].astype(np.float32) / 255.0
    return (1.0 - a), layer[:, :, :3].astype(np.float32) * a


def clear_cache():
    with _STATIC_LOCK:
        _STATIC_CACHE.clear()


# ── Graph ────────────────────────────────────────────────────────────────────

def _draw_graph(canvas, x0, y0, gw, gh, seq, idx, vmin, vmax, color,
                thickness, center_line=False, invert=False):
    """
    Draw a compact trend graph into the panel.

    canvas is RGB (uint8). Values outside [vmin, vmax] are clamped, and
    missing values (None) break the line.

    invert=False: large value at the top - correct for FPS (60 top, 0 bottom)
    invert=True:  small value at the top - correct for frame time (16.7 ms at
                  the top, 66.7 ms at the bottom), exactly as in the main
                  overlay. Without it, a hitch pointed upwards in the panel
                  and downwards in the main graph.
    """
    if seq is None or idx is None or gw <= 2 or gh <= 2:
        return
    half = GRAPH_WINDOW // 2
    n = len(seq)
    xs, ys, valid = [], [], []
    for j in range(GRAPH_WINDOW):
        src = idx - half + j
        v = seq[src] if 0 <= src < n else None
        ok = v is not None
        xs.append(x0 + int(j * (gw - 1) / max(1, GRAPH_WINDOW - 1)))
        if ok:
            t = (float(v) - vmin) / max(1e-6, (vmax - vmin))
            t = min(1.0, max(0.0, t))
            if invert:
                t = 1.0 - t
            ys.append(y0 + int((1.0 - t) * (gh - 1 - thickness)) + thickness // 2)
        else:
            ys.append(y0)
        valid.append(ok)

    if center_line:
        cy = y0 + gh // 2
        cv2.line(canvas, (x0, cy), (x0 + gw - 1, cy), (110, 110, 110), 1, cv2.LINE_AA)

    seg = []
    for i in range(GRAPH_WINDOW):
        if valid[i]:
            seg.append((xs[i], ys[i]))
        else:
            if len(seg) > 1:
                cv2.polylines(canvas, [np.array(seg, np.int32)], False,
                              color, thickness, cv2.LINE_AA)
            seg = []
    if len(seg) > 1:
        cv2.polylines(canvas, [np.array(seg, np.int32)], False,
                      color, thickness, cv2.LINE_AA)


# ── Render the panel ─────────────────────────────────────────────────────────

def render_panel(frame_rgb, cfg, fps_seq, ft_seq, idx, stats=None,
                 source_fps=60.0, ft_scale=None):
    """
    Blend the panel into the image. `frame_rgb` is modified in place.

    How it works: the cached static layer is blended ONCE as a whole, after
    which only the three changing bands (FPS number with statistics, FPS
    graph, frame time graph) are drawn straight into the image.

    The obvious approach - rebuilding the complete panel as RGBA every frame
    and then blending it - cost around 31 ms per frame at 4K, because every
    time 920x652 pixels run through PIL and several numpy copies even though
    over 80% of the area stays unchanged.

    cfg      – Konfiguration (siehe default_config / normalize_config)
    fps_seq  - the complete FPS sequence
    ft_seq   - the complete frame time sequence
    idx      – aktueller Frame-Index (Playhead)
    stats    - {'fps': {'avg','min','max'}} for the statistics row
    ft_scale - (min_ms, max_ms) for the frame time graph
    """
    if not cfg or not cfg.get('enabled'):
        return frame_rgb
    cfg = normalize_config(cfg)

    h_img, w_img = frame_rgb.shape[:2]
    s = max(1.0, h_img / 1080.0)

    layer, geo, (inv_a, pre) = build_static_layer(cfg, s)
    ph, pw = layer.shape[:2]
    px, py = panel_origin(cfg, s)

    # Clipping at the image edge
    x1, y1 = max(0, px), max(0, py)
    x2, y2 = min(w_img, px + pw), min(h_img, py + ph)
    if x2 <= x1 or y2 <= y1:
        return frame_rgb
    sx, sy = x1 - px, y1 - py
    cw, ch = x2 - x1, y2 - y1

    # ── 1. Blend the static layer (premultiplied, see _premultiply)
    roi = frame_rgb[y1:y2, x1:x2].astype(np.float32)
    roi *= inv_a[sy:sy + ch, sx:sx + cw]
    roi += pre[sy:sy + ch, sx:sx + cw]
    frame_rgb[y1:y2, x1:x2] = roi.astype(np.uint8)

    # ── 2. Draw the changing bands straight into the image ─────────────
    g = cfg['geometry']

    def sz(k):
        return max(6, int(round(g.get(k, DEFAULTS[k]) * s)))
    pad = max(2, int(round(g.get('pad_x', DEFAULTS['pad_x']) * s)))
    thick = max(1, int(round(g.get('line_thickness', DEFAULTS['line_thickness']) * s)))

    fps_col = hex_to_rgb(cfg.get('fps_color', '#FFFFFF'))
    ft_col = hex_to_rgb(cfg.get('ft_color', '#FFFFFF'))
    stat_col = hex_to_rgb(cfg.get('stat_color', '#BBBBBB'))

    cur = None
    if fps_seq is not None and idx is not None and 0 <= idx < len(fps_seq):
        cur = fps_seq[idx]

    # FPS number + statistics - only this one band goes through PIL
    if PILLOW:
        by, bh = geo['fps'][0]
        ty1 = max(y1, py + by)
        ty2 = min(y2, py + by + bh)
        if ty2 > ty1:
            band = np.ascontiguousarray(frame_rgb[ty1:ty2, x1:x2])
            pil = PILImage.fromarray(band, 'RGB')
            draw = PILDraw.Draw(pil)
            oy = (py + by) - ty1     # band top edge relative to the crop
            _text(draw, (pad, oy + int(bh * 0.42)),
                  '--' if cur is None else f"{cur:.0f}",
                  sz('fps_size'), fps_col, anchor='lm')
            if stats and stats.get('fps'):
                st = stats['fps']
                parts = [('AVG', st.get('avg')), ('MIN', st.get('min')),
                         ('MAX', st.get('max'))]
                txt = '   '.join(f"{k}: {v:.0f}" for k, v in parts
                                 if isinstance(v, (int, float)) and v >= 0)
                if txt:
                    _text(draw, (pad, oy + int(bh * 0.82)), txt,
                          sz('stat_size'), stat_col, anchor='lm')
            frame_rgb[ty1:ty2, x1:x2] = np.array(pil)

    # Graphs - drawn straight onto a contiguous crop of the image.
    # cv2 rejects non-contiguous slices, so each band gets a compact buffer
    # instead of a copy of the whole panel.
    inner_w = cw - 2 * pad
    for kind, seq, lo, hi, col, centre, inv in (
            ('fps_graph', fps_seq, 0.0, float(source_fps) * 1.02, fps_col, True, False),
            ('ft_graph', ft_seq,
             (ft_scale[0] if ft_scale else 0.0),
             (ft_scale[1] if ft_scale else 1000.0 / max(1e-6, source_fps) * 4),
             ft_col, False, True)):
        if kind not in geo or inner_w <= 4:
            continue
        by, bh = geo[kind][0]
        gy1 = max(y1, py + by)
        gy2 = min(y2, py + by + bh)
        if gy2 <= gy1:
            continue
        band = np.ascontiguousarray(frame_rgb[gy1:gy2, x1:x2])
        oy = (py + by) - gy1
        _draw_graph(band, pad, oy + 2, inner_w, bh - 4, seq, idx,
                    float(lo), float(hi), col, thick, center_line=centre,
                    invert=inv)
        frame_rgb[gy1:gy2, x1:x2] = band

    return frame_rgb
