"""
Color Manager — Farb-Utilities für FPS Analyzer.

Der frühere ColorSelectionDialog wurde entfernt: Farben werden jetzt
vollständig im Layout Editor gewählt (Tools → Layout Editor, Ctrl+L).
"""


def hex_to_bgr(hex_color):
    """'#RRGGBB' → (B, G, R) Tupel für OpenCV."""
    if isinstance(hex_color, (tuple, list)):
        return tuple(hex_color)
    h = str(hex_color).lstrip('#')
    if len(h) != 6:
        return (0, 255, 0)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (b, g, r)
    except ValueError:
        return (0, 255, 0)
