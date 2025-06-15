"""
Font Renderer - Spezialisierte Rendering-Funktionen für TrueType-Fonts
Bietet optimierte Text-Rendering-Funktionen für FPS Analyzer

VERWENDUNG: Aus dem Overlay-Renderer importieren

Features:
- Hochwertige Textdarstellung mit Anti-Aliasing
- Unterstützung für Umrandung und Schatten
- Optimierte Alpha-Blending-Methoden
- Debug-Funktionalität für Testbilder
"""

import cv2
import numpy as np
from typing import Dict, List, Tuple, Optional, Union, Any
import os
from datetime import datetime

# TrueType-Support mit Pillow prüfen
try:
    from PIL import Image, ImageDraw, ImageFont, ImageColor
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

# TrueType-Support mit OpenCV prüfen
try:
    # Versuche eine FreeType Font-Instanz zu erstellen
    cv2.freetype.createFreeType2()
    FREETYPE_AVAILABLE = True
except:
    FREETYPE_AVAILABLE = False

# Debug-Optionen
DEBUG_MODE = False
EXPORT_DEBUG_IMAGES = False
DEBUG_IMAGE_DIR = "debug_images"

def enable_debug_mode(export_images=False, debug_dir="debug_images"):
    """Debug-Modus aktivieren"""
    global DEBUG_MODE, EXPORT_DEBUG_IMAGES, DEBUG_IMAGE_DIR
    DEBUG_MODE = True
    EXPORT_DEBUG_IMAGES = export_images
    DEBUG_IMAGE_DIR = debug_dir
    
    if EXPORT_DEBUG_IMAGES and not os.path.exists(DEBUG_IMAGE_DIR):
        os.makedirs(DEBUG_IMAGE_DIR)
    
    print(f"🔍 Font-Renderer-Debug-Modus aktiviert" + 
          (f" mit Bildexport nach '{DEBUG_IMAGE_DIR}'" if export_images else ""))

def debug_log(message):
    """Debug-Nachricht ausgeben"""
    if DEBUG_MODE:
        print(f"🔍 [Font-Renderer] {message}")

def save_debug_image(image, name_prefix="debug"):
    """Debug-Bild speichern"""
    if not EXPORT_DEBUG_IMAGES:
        return
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name_prefix}_{timestamp}.png"
        path = os.path.join(DEBUG_IMAGE_DIR, filename)
        cv2.imwrite(path, image)
        debug_log(f"Debug-Bild gespeichert: {path}")
    except Exception as e:
        debug_log(f"Fehler beim Speichern des Debug-Bildes: {e}")

def render_truetype_text(image: np.ndarray, text: str, position: Tuple[int, int], 
                        font_settings: Any, scale_factor: float = 1.0) -> np.ndarray:
    """
    Rendert Text mit TrueType-Font auf ein Bild
    
    Args:
        image: OpenCV-Bild (numpy.ndarray)
        text: Zu rendernder Text
        position: (x, y) Position des Texts
        font_settings: Font-Einstellungen-Objekt
        scale_factor: Größenskalierungsfaktor
        
    Returns:
        OpenCV-Bild mit gerendertem Text
    """
    # Wenn font_settings die render_text-Methode hat, nutze diese
    if hasattr(font_settings, 'render_text'):
        try:
            result = font_settings.render_text(image, text, position, scale_factor)
            if DEBUG_MODE and EXPORT_DEBUG_IMAGES:
                save_debug_image(result, "text_render")
            return result
        except Exception as e:
            debug_log(f"Fehler beim Text-Rendering mit font_settings.render_text: {e}")
            # Fallback unten
    
    # Fallback auf direkte Methode, wenn render_text nicht verfügbar oder fehlgeschlagen
    return render_text_with_pillow(image, text, position, font_settings, scale_factor)

def render_text_with_pillow(image: np.ndarray, text: str, position: Tuple[int, int],
                           font_settings: Any, scale_factor: float = 1.0) -> np.ndarray:
    """
    Rendert Text direkt mit Pillow auf ein OpenCV-Bild
    
    Args:
        image: OpenCV-Bild (numpy.ndarray)
        text: Zu rendernder Text
        position: (x, y) Position des Texts
        font_settings: Font-Einstellungen-Objekt
        scale_factor: Größenskalierungsfaktor
        
    Returns:
        OpenCV-Bild mit gerendertem Text
    """
    if not PILLOW_AVAILABLE:
        # Wenn Pillow nicht verfügbar ist, Fallback auf OpenCV
        return render_text_with_opencv(image, text, position, font_settings, scale_factor)
    
    try:
        # Eigenschaften aus font_settings extrahieren
        font_name = getattr(font_settings, 'font_name', 'Arial')
        font_path = getattr(font_settings, 'font_path', None)
        font_size = getattr(font_settings, 'size', 24)
        bold = getattr(font_settings, 'bold', False)
        italic = getattr(font_settings, 'italic', False)
        text_color = getattr(font_settings, 'text_color', (255, 255, 255))
        border_color = getattr(font_settings, 'border_color', (0, 0, 0))
        border_thickness = getattr(font_settings, 'border_thickness', 2)
        
        # ✅ FIXED: Verbesserte Größenskalierung für konsistente Darstellung
        # Bei Font-Größe 1.0 in OpenCV entspricht etwa 24 Pixeln
        base_scale = 24.0
        # ✅ FIXED: Skalierungsfaktor von 0.75 auf 0.3 reduziert
        pil_size = int(font_size * base_scale * 0.3 * scale_factor)
        
        # Erstelle ein Pillow-Image mit dem Text
        h, w = image.shape[:2]
        pil_img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(pil_img)
        
        # Versuche den Font zu laden
        try:
            if font_path and os.path.exists(font_path):
                font = ImageFont.truetype(font_path, size=pil_size)
            else:
                # Versuche nach Namen zu laden (einfacher Ansatz)
                font = ImageFont.truetype(font_name, size=pil_size)
        except:
            # Fallback auf Standardfont
            font = ImageFont.load_default()
            pil_size = max(12, pil_size // 2)  # Standardfont benötigt Anpassung
        
        # Position extrahieren
        x, y = position
        
        # Umrandung zeichnen wenn gewünscht
        if border_thickness > 0:
            # Konvertiere OpenCV BGR zu Pillow RGB
            border_rgb = (border_color[2], border_color[1], border_color[0], 255)
            
            # Zeichne den Text in mehreren Versätzen für die Umrandung
            border_size = max(1, int(border_thickness * scale_factor))
            for dx in range(-border_size, border_size + 1):
                for dy in range(-border_size, border_size + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), text, fill=border_rgb, font=font)
        
        # Konvertiere OpenCV BGR zu Pillow RGBA für den Haupttext
        text_rgba = (text_color[2], text_color[1], text_color[0], 255)
        
        # Haupttext zeichnen
        draw.text((x, y), text, fill=text_rgba, font=font)
        
        # Konvertiere zurück zu OpenCV
        pil_img_np = np.array(pil_img)
        
        # Nur wenn das Pillow-Bild einen Alpha-Kanal hat
        if pil_img_np.shape[2] == 4:
            # ✅ FIXED: Verbesserte Alpha-Komposition
            # Erstelle eine Kopie des ursprünglichen Bildes
            result = image.copy()
            
            # Extrahiere die Alpha-Maske aus dem Pillow-Bild
            alpha_mask = pil_img_np[:, :, 3] > 0
            
            # Direkte Pixel-Manipulation statt addWeighted
            if np.any(alpha_mask):
                # Extrahiere die RGB-Werte aus dem Pillow-Bild
                # Konvertiere von RGBA zu BGR (für OpenCV)
                overlay_bgr = pil_img_np[alpha_mask, [2, 1, 0]]
                
                # Alpha-Werte extrahieren und normalisieren
                alpha_values = pil_img_np[alpha_mask, 3].astype(float) / 255.0
                
                # Originalpixel holen
                original_pixels = result[alpha_mask]
                
                # Alpha-Blending durchführen: result = (1-alpha)*original + alpha*overlay
                blended_pixels = (1.0 - alpha_values[:, np.newaxis]) * original_pixels + \
                                  alpha_values[:, np.newaxis] * overlay_bgr
                
                # Zurück ins Ergebnis-Bild schreiben
                result[alpha_mask] = blended_pixels.astype(np.uint8)
            
            if DEBUG_MODE and EXPORT_DEBUG_IMAGES:
                save_debug_image(result, "pillow_text")
            
            return result
        else:
            # Bei Problemen mit dem Alpha-Kanal: Fallback auf OpenCV
            debug_log("Alpha-Kanal fehlt, Fallback auf OpenCV")
            return render_text_with_opencv(image, text, position, font_settings, scale_factor)
            
    except Exception as e:
        debug_log(f"Fehler beim Text-Rendering mit Pillow: {e}")
        import traceback
        debug_log(traceback.format_exc())
        # Fallback auf OpenCV
        return render_text_with_opencv(image, text, position, font_settings, scale_factor)

def render_text_with_opencv(image: np.ndarray, text: str, position: Tuple[int, int],
                           font_settings: Any, scale_factor: float = 1.0) -> np.ndarray:
    """
    Rendert Text mit OpenCV auf ein Bild
    
    Args:
        image: OpenCV-Bild (numpy.ndarray)
        text: Zu rendernder Text
        position: (x, y) Position des Texts
        font_settings: Font-Einstellungen-Objekt
        scale_factor: Größenskalierungsfaktor
        
    Returns:
        OpenCV-Bild mit gerendertem Text
    """
    result = image.copy()
    x, y = position
    
    # Eigenschaften aus font_settings extrahieren
    font_size = getattr(font_settings, 'size', 1.0)
    thickness = getattr(font_settings, 'thickness', 2)
    bold = getattr(font_settings, 'bold', False)
    text_color = getattr(font_settings, 'text_color', (255, 255, 255))
    border_color = getattr(font_settings, 'border_color', (0, 0, 0))
    border_thickness = getattr(font_settings, 'border_thickness', 2)
    
    # Font ermitteln
    if hasattr(font_settings, 'get_opencv_font'):
        font = font_settings.get_opencv_font()
        # ✅ FIXED: Verbesserte Größenskalierung
        font_scale = font_size * scale_factor / 24.0
        thickness = max(1, int(thickness * (1 + (0.5 if bold else 0)) * scale_factor))
    else:
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = font_size * scale_factor * 0.04  # 0.04 Faktor für bessere Skalierung
        thickness = max(1, int(thickness * scale_factor))
    
    # Rahmen zeichnen
    if border_thickness > 0:
        scaled_border = max(1, int(border_thickness * scale_factor))
        for dx in range(-scaled_border, scaled_border + 1):
            for dy in range(-scaled_border, scaled_border + 1):
                if dx != 0 or dy != 0:
                    cv2.putText(result, text, (x + dx, y + dy), font, font_scale,
                              border_color, thickness + 1, cv2.LINE_AA)
    
    # Haupttext zeichnen
    cv2.putText(result, text, (x, y), font, font_scale,
               text_color, thickness, cv2.LINE_AA)
    
    if DEBUG_MODE and EXPORT_DEBUG_IMAGES:
        save_debug_image(result, "opencv_text")
    
    return result

def create_test_image(width: int = 800, height: int = 600, 
                     text: str = "Test TrueType Font Rendering",
                     font_settings=None,
                     bg_color: Tuple[int, int, int] = (30, 30, 30)) -> np.ndarray:
    """
    Erstellt ein Test-Bild mit Text für Debug-Zwecke
    
    Args:
        width: Bildbreite
        height: Bildhöhe
        text: Zu rendernder Text
        font_settings: Font-Einstellungen oder None für Standard
        bg_color: Hintergrundfarbe
        
    Returns:
        OpenCV-Bild mit gerendertem Text
    """
    # Leeres Bild erstellen
    image = np.full((height, width, 3), bg_color, dtype=np.uint8)
    
    # Hintergrund-Gradient für bessere Sichtbarkeit
    for y in range(height):
        # Vertikaler Gradient
        intensity = int(15 + (y / height) * 35)
        color = (intensity, intensity, intensity + 10)
        image[y, :] = color
    
    # Grid-Linien für Referenz
    grid_spacing = 50
    grid_color = (60, 60, 60)
    for x in range(0, width, grid_spacing):
        cv2.line(image, (x, 0), (x, height), grid_color, 1)
    for y in range(0, height, grid_spacing):
        cv2.line(image, (0, y), (width, y), grid_color, 1)
    
    # Text-Positionen
    positions = [
        (50, 50),   # Oben links
        (width // 2, 50),  # Oben mitte
        (50, height // 2),  # Mitte links
        (width // 2, height // 2),  # Mitte
        (50, height - 50)   # Unten links
    ]
    
    # Teste verschiedene Skalierungsfaktoren
    scale_factors = [0.5, 1.0, 1.5, 2.0]
    
    # Font-Einstellungen erstellen wenn nicht übergeben
    if font_settings is None:
        from font_manager import OpenCVFontSettings
        font_settings = OpenCVFontSettings(
            font_name='Arial',
            size=24,
            thickness=2,
            bold=False,
            border_thickness=2,
            text_color=(255, 255, 255),
            border_color=(0, 0, 0)
        )
    
    # Verschiedene Text-Varianten rendern
    for i, position in enumerate(positions):
        pos_text = f"{text} at {position}"
        y_offset = 0
        
        for scale in scale_factors:
            # Position anpassen
            pos = (position[0], position[1] + y_offset)
            
            # Text rendern
            scale_text = f"{pos_text} (scale {scale:.1f})"
            
            # ✅ FIXED: Text-Farbe für bessere Sichtbarkeit
            if hasattr(font_settings, 'text_color'):
                if i % 2 == 0:
                    font_settings.text_color = (255, 255, 255)  # Weiß
                else:
                    font_settings.text_color = (0, 255, 255)    # Gelb
            
            image = render_truetype_text(image, scale_text, pos, font_settings, scale)
            
            # Offset für nächste Zeile
            if hasattr(font_settings, 'get_text_size'):
                text_size = font_settings.get_text_size(scale_text, scale)
                y_offset += text_size[1] + 10
            else:
                y_offset += int(30 * scale)
    
    # Info-Text hinzufügen
    cv2.putText(image, "TrueType Test Image", (width - 200, height - 40),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(image, f"Pillow: {'Yes' if PILLOW_AVAILABLE else 'No'}, FreeType: {'Yes' if FREETYPE_AVAILABLE else 'No'}", 
               (width - 200, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)
    
    # Bild speichern wenn Debug-Modus aktiv
    if DEBUG_MODE and EXPORT_DEBUG_IMAGES:
        save_debug_image(image, "test_image_complete")
    
    return image

def create_comparison_image(font_settings_list=None, 
                          width: int = 1000, height: int = 800,
                          sample_text: str = "The quick brown fox jumps over the lazy dog") -> np.ndarray:
    """
    Erstellt ein Vergleichsbild verschiedener Font-Einstellungen
    
    Args:
        font_settings_list: Liste von Font-Einstellungen-Objekten
        width: Bildbreite
        height: Bildhöhe
        sample_text: Beispieltext
        
    Returns:
        OpenCV-Bild mit Font-Vergleich
    """
    # Leeres Bild erstellen
    image = np.full((height, width, 3), (20, 20, 30), dtype=np.uint8)
    
    # Hintergrund mit Gradient
    for y in range(height):
        intensity = int(15 + (y / height) * 25)
        image[y, :] = (intensity, intensity, intensity + 10)
    
    # Titel
    cv2.putText(image, "Font Rendering Comparison", (30, 40),
               cv2.FONT_HERSHEY_SIMPLEX, 1.2, (220, 220, 220), 2, cv2.LINE_AA)
    
    # Beschreibung
    cv2.putText(image, f"Sample: \"{sample_text}\"", (30, 80),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180), 1, cv2.LINE_AA)
    
    # Standard-Fonts erstellen, wenn keine Liste übergeben wurde
    if font_settings_list is None:
        try:
            from font_manager import OpenCVFontSettings
            font_settings_list = [
                OpenCVFontSettings(font_name='HERSHEY_SIMPLEX', size=24, thickness=2, 
                                 border_thickness=2, text_color=(255, 255, 255)),
                OpenCVFontSettings(font_name='Arial', size=24, thickness=2, 
                                 border_thickness=2, text_color=(255, 255, 0)),
                OpenCVFontSettings(font_name='Times New Roman', size=24, thickness=2, 
                                 border_thickness=2, text_color=(0, 255, 255))
            ]
        except ImportError:
            # Minimale Fallback-Implementierung
            class MinimalFontSettings:
                def __init__(self, name, size=24, color=(255, 255, 255)):
                    self.font_name = name
                    self.size = size
                    self.thickness = 2
                    self.text_color = color
                    self.border_thickness = 2
                    self.border_color = (0, 0, 0)
            
            font_settings_list = [
                MinimalFontSettings("HERSHEY_SIMPLEX"),
                MinimalFontSettings("Arial", color=(255, 255, 0)),
                MinimalFontSettings("Default", color=(0, 255, 255))
            ]
    
    # Fonts rendern
    y_pos = 150
    for i, font_settings in enumerate(font_settings_list):
        # Beschreibungstext
        font_name = getattr(font_settings, 'font_name', 'Unknown')
        font_path = getattr(font_settings, 'font_path', 'N/A')
        font_size = getattr(font_settings, 'size', 0)
        
        if hasattr(font_settings, 'is_freetype_available'):
            is_truetype = font_settings.is_freetype_available()
            renderer = "TrueType" if is_truetype else "OpenCV"
        else:
            renderer = "Unknown"
        
        # Beschreibung
        desc_text = f"Font {i+1}: {font_name} (Size: {font_size}, Renderer: {renderer})"
        cv2.putText(image, desc_text, (50, y_pos - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
        
        # Beispieltext rendern
        image = render_truetype_text(image, sample_text, (50, y_pos), font_settings, 1.0)
        
        # Skalierte Version
        image = render_truetype_text(image, sample_text, (50, y_pos + 50), font_settings, 1.5)
        cv2.putText(image, "(Scale: 1.5x)", (width - 150, y_pos + 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
        
        # Nächste Position
        y_pos += 120
    
    # Informationen
    info_text = [
        f"Pillow Available: {'Yes' if PILLOW_AVAILABLE else 'No'}",
        f"FreeType Available: {'Yes' if FREETYPE_AVAILABLE else 'No'}",
        f"OpenCV Version: {cv2.__version__}",
        "Debug Mode: " + ("Active" if DEBUG_MODE else "Inactive")
    ]
    
    for i, text in enumerate(info_text):
        cv2.putText(image, text, (width - 300, height - 80 + i*20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
    
    # Bild speichern wenn Debug-Modus aktiv
    if DEBUG_MODE and EXPORT_DEBUG_IMAGES:
        save_debug_image(image, "font_comparison")
    
    return image

# ===============================================
# 🎨 DEBUGGING UND TESTS
# ===============================================

def run_rendering_test(font_settings=None, export=True):
    """
    Führt einen Rendering-Test durch und erstellt Test-Bilder
    
    Args:
        font_settings: Zu testende Font-Einstellungen oder None für Standard
        export: Ob Test-Bilder exportiert werden sollen
    """
    # Debug-Modus aktivieren
    enable_debug_mode(export_images=export)
    
    try:
        # Font-Einstellungen erstellen wenn nicht übergeben
        if font_settings is None:
            from font_manager import OpenCVFontSettings, get_font_manager
            
            # Font-Manager holen
            font_manager = get_font_manager()
            
            # Beliebte Fonts suchen
            popular_fonts = font_manager.get_popular_fonts()
            font_name = "Arial"  # Standardwert
            font_path = None
            
            # Ersten gefundenen Font verwenden
            if popular_fonts:
                font_name = popular_fonts[0]['name']
                font_path = popular_fonts[0]['path']
            
            font_settings = OpenCVFontSettings(
                font_path=font_path,
                font_name=font_name,
                size=24,
                thickness=2,
                bold=False,
                border_thickness=2,
                text_color=(255, 255, 255),
                border_color=(0, 0, 0)
            )
            
            debug_log(f"Test mit Font '{font_name}' (Pfad: {font_path})")
        
        # Test-Bild erstellen
        test_image = create_test_image(font_settings=font_settings)
        
        # Font-Vergleich erstellen
        comparison_image = create_comparison_image(
            [
                font_settings,
                font_settings.clone(),  # Klon mit Standardwerten
                # Weitere Varianten
                OpenCVFontSettings(font_name='HERSHEY_SIMPLEX', size=24, 
                                 text_color=(255, 255, 0)),
            ]
        )
        
        print("✅ Rendering-Test abgeschlossen!")
        if export:
            print(f"   Debug-Bilder wurden im Verzeichnis '{DEBUG_IMAGE_DIR}' gespeichert.")
        
        return True
    except Exception as e:
        print(f"❌ Rendering-Test fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False

# ===============================================
# 📤 EXPORTS
# ===============================================

__all__ = [
    'render_truetype_text',
    'render_text_with_pillow',
    'render_text_with_opencv',
    'create_test_image',
    'create_comparison_image',
    'run_rendering_test',
    'enable_debug_mode',
    'PILLOW_AVAILABLE',
    'FREETYPE_AVAILABLE'
]

if __name__ == "__main__":
    # Test ausführen wenn direkt gestartet
    print("🧪 Starte Font-Rendering-Test...")
    run_rendering_test(export=True)
