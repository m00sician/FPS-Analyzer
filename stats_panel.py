"""
Stats-Panel — alternativer Anzeigemodus im Stil klassischer Benchmark-Overlays.

Eine abgerundete, halbtransparente Box mit abwechselnd hellen und dunklen
Bändern. Aufbau von oben nach unten:

    1  Titel (Spielname)
    2  große FPS-Zahl + AVG / MIN / MAX
    3  FPS-Graph mit Mittellinie
    4  Konsole + Version (zwei feste Felder)
    5  bis zu drei frei belegbare Zeilen (je 1 breites ODER 2 schmale Felder)
    6  Frametime-Graph

Die Bänder wechseln zwischen BAND_DARK und BAND_LIGHT, beginnend dunkel.

LEISTUNG
Der weitaus größte Teil des Panels ist über den ganzen Clip identisch:
Bänder, abgerundete Ecken, Titel, Konsole, Version, Zusatzfelder und die
Beschriftungen. Nur FPS-Zahl, AVG/MIN/MAX und die beiden Graphen ändern sich.
Deshalb wird der statische Teil EINMAL in einen RGBA-Layer gerendert und
danach nur noch geblendet — dieselbe Strategie, die im Haupt-Overlay aus
213 ms 27 ms gemacht hat. Pro Frame bleibt nur das Zeichnen der wenigen
dynamischen Elemente übrig.
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


# ── Farben & Maße (alle Pixelwerte auf 1080p bezogen) ────────────────────────

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

MAX_EXTRA_LINES = 3          # zusätzlich zur festen Konsole/Version-Zeile
GRAPH_WINDOW = 180           # Frames im Graph-Fenster (3 s bei 60 fps)


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
    """Frische Konfiguration mit sinnvollen Startwerten."""
    return {
        'enabled': False,
        'title': {'text': '', 'color': '#FFFFFF'},
        'console': {'text': '', 'color': '#FFFFFF'},
        'version': {'text': '', 'color': '#FFFFFF'},
        'extra_lines': [],          # Liste von Zeilen, je 1 oder 2 Felder
        'fps_color': '#FFFFFF',
        'ft_color': '#FFFFFF',
        'stat_color': '#BBBBBB',
        'geometry': dict(DEFAULTS),
    }


def normalize_config(cfg):
    """
    Konfiguration auf einen gültigen Stand bringen.

    Erzwingt die Regeln der Oberfläche auch dann, wenn die Datei von Hand
    bearbeitet wurde: höchstens MAX_EXTRA_LINES Zeilen, je Zeile höchstens
    zwei Felder, und ein breites Feld steht immer allein in seiner Zeile.
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
        # Ein breites Feld belegt die ganze Zeile allein.
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


# ── Geometrie ────────────────────────────────────────────────────────────────

def _bands(cfg, s):
    """
    Höhen und Farben aller Bänder von oben nach unten.

    Returns Liste von (kind, height, band_color).
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
    """Alphamaske für abgerundete Ecken (0..255)."""
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


# ── Statischer Layer ─────────────────────────────────────────────────────────

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
    Bänder, Ecken und alle unveränderlichen Texte als RGBA-Layer.

    Wird pro Konfiguration einmal gebaut und danach für jeden Frame
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

    # Bänder füllen
    geo = {}
    y = 0
    for kind, bh, col in _bands(cfg, s):
        layer[y:y + bh, :, :3] = col[::-1] if False else col
        geo.setdefault(kind, []).append((y, bh))
        y += bh
    layer[:, :, 3] = 255

    # Abgerundete Ecken
    radius = int(round(g.get('corner_radius', DEFAULTS['corner_radius']) * s))
    mask = _rounded_mask(w, h, radius)
    layer[:, :, 3] = (mask.astype(np.float32) * opacity).astype(np.uint8)

    # Texte
    if PILLOW:
        pil = PILImage.fromarray(layer, 'RGBA')
        draw = PILDraw.Draw(pil)

        def sz(k):
            return max(6, int(round(g.get(k, DEFAULTS[k]) * s)))

        # Titel
        ty, th = geo['title'][0]
        _text(draw, (pad, ty + th // 2), cfg['title']['text'],
              sz('title_size'), hex_to_rgb(cfg['title']['color']), anchor='lm')

        # Konsole + Version (feste Zeile, zwei Spalten)
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
        # Text hat volle Deckkraft; die Bandtransparenz gilt nur für den
        # Hintergrund, sonst wirkt die Schrift ausgewaschen.
        layer = rgba

    entry = (layer, geo, _premultiply(layer))
    with _STATIC_LOCK:
        _STATIC_CACHE[key] = entry
    return entry


def _premultiply(layer):
    """
    Blend-Daten des statischen Layers einmalig vorbereiten.

    Ohne das würde pro Frame das gesamte Panel dreimal nach float32
    konvertiert (Alpha, Vordergrund, Hintergrund) — bei 4K sind das
    920×652 Pixel, und die Daten ändern sich nie. Vorbereitet bleibt pro
    Frame nur noch eine Multiplikation plus Addition.
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
    Kompakter Verlaufsgraph in das Panel zeichnen.

    canvas ist RGB (uint8). Werte außerhalb [vmin, vmax] werden geklemmt,
    fehlende Werte (None) unterbrechen die Linie.

    invert=False: großer Wert oben  — richtig für FPS (60 oben, 0 unten)
    invert=True:  kleiner Wert oben — richtig für Frametime (16.7 ms oben,
                  66.7 ms unten), genau wie im Haupt-Overlay. Ohne das
                  zeigte ein Ruckler im Panel nach oben und im Hauptgraphen
                  nach unten.
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


# ── Panel rendern ────────────────────────────────────────────────────────────

def render_panel(frame_rgb, cfg, fps_seq, ft_seq, idx, stats=None,
                 source_fps=60.0, ft_scale=None):
    """
    Panel in das Bild einblenden. `frame_rgb` wird an Ort und Stelle verändert.

    Ablauf: der gecachte statische Layer wird EINMAL als Ganzes geblendet,
    danach werden nur die drei veränderlichen Bänder (FPS-Zahl mit Statistik,
    FPS-Graph, Frametime-Graph) direkt in das Bild gezeichnet.

    Der naheliegende Weg — das komplette Panel pro Frame als RGBA neu
    aufbauen und dann blenden — kostete bei 4K rund 31 ms pro Frame, weil
    dabei jedes Mal 920×652 Pixel durch PIL und mehrere numpy-Kopien laufen,
    obwohl über 80% der Fläche unverändert bleibt.

    cfg      – Konfiguration (siehe default_config / normalize_config)
    fps_seq  – vollständige FPS-Sequenz
    ft_seq   – vollständige Frametime-Sequenz
    idx      – aktueller Frame-Index (Playhead)
    stats    – {'fps': {'avg','min','max'}} für die Statistikzeile
    ft_scale – (min_ms, max_ms) für den Frametime-Graphen
    """
    if not cfg or not cfg.get('enabled'):
        return frame_rgb
    cfg = normalize_config(cfg)

    h_img, w_img = frame_rgb.shape[:2]
    s = max(1.0, h_img / 1080.0)

    layer, geo, (inv_a, pre) = build_static_layer(cfg, s)
    ph, pw = layer.shape[:2]
    px, py = panel_origin(cfg, s)

    # Beschnitt am Bildrand
    x1, y1 = max(0, px), max(0, py)
    x2, y2 = min(w_img, px + pw), min(h_img, py + ph)
    if x2 <= x1 or y2 <= y1:
        return frame_rgb
    sx, sy = x1 - px, y1 - py
    cw, ch = x2 - x1, y2 - y1

    # ── 1. Statischen Layer blenden (premultipliziert, siehe _premultiply)
    roi = frame_rgb[y1:y2, x1:x2].astype(np.float32)
    roi *= inv_a[sy:sy + ch, sx:sx + cw]
    roi += pre[sy:sy + ch, sx:sx + cw]
    frame_rgb[y1:y2, x1:x2] = roi.astype(np.uint8)

    # ── 2. Veränderliche Bänder direkt ins Bild zeichnen ────────────────
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

    # FPS-Zahl + Statistik — nur dieses eine Band durch PIL schicken
    if PILLOW:
        by, bh = geo['fps'][0]
        ty1 = max(y1, py + by)
        ty2 = min(y2, py + by + bh)
        if ty2 > ty1:
            band = np.ascontiguousarray(frame_rgb[ty1:ty2, x1:x2])
            pil = PILImage.fromarray(band, 'RGB')
            draw = PILDraw.Draw(pil)
            oy = (py + by) - ty1     # Bandoberkante relativ zum Ausschnitt
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

    # Graphen — direkt auf einen zusammenhängenden Ausschnitt des Bildes.
    # cv2 lehnt nicht zusammenhängende Slices ab, deshalb pro Band ein
    # kompakter Puffer statt einer Kopie des ganzen Panels.
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
