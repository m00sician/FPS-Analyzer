"""
Color Manager - colour utilities for FPS Analyzer.

The former ColorSelectionDialog has been removed: colours are now
chosen entirely in the Layout Editor (Tools -> Layout Editor, Ctrl+L).
"""


def hex_to_bgr(hex_color):
    """'#RRGGBB' -> (B, G, R) tuple for OpenCV."""
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
