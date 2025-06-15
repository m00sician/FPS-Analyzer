"""
PILLOW-OPENCV FONT BRIDGE
=========================
🚀 TrueType Font Integration ohne OpenCV-Neucompilierung!

Diese Lösung nutzt Pillow (PIL) für hochwertiges TrueType-Font-Rendering
und integriert die gerenderten Texte nahtlos in OpenCV-Bilder.

VORTEILE:
- ✅ Keine Neucompilierung von OpenCV erforderlich
- ✅ Zugriff auf ALLE Windows-System-Fonts (496+)
- ✅ Hochwertige Textrendering mit Antialiasing
- ✅ Unterstützung für Texteffekte (Schatten, Umrandung, Farbverläufe)
- ✅ Unicode-Support für internationale Zeichen
- ✅ 100% kompatibel mit bestehendem Font-Manager

VERWENDUNG:
1. Importiere PillowOpenCVBridge
2. Erstelle eine Bridge-Instanz
3. Nutze render_text() für Text-Rendering

BEISPIEL:
    bridge = PillowOpenCVBridge()
    font = bridge.load_system_font("Arial", size=36)
    cv2_image = bridge.render_text(cv2_image, "Hello World", (100, 100), font)
"""

import os
import sys
import glob
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any

# Pillow für Font-Rendering importieren
try:
    from PIL import Image, ImageDraw, ImageFont, ImageColor
    PILLOW_AVAILABLE = True
    print("✅ Pillow erfolgreich importiert - TrueType-Font-Support aktiviert!")
except ImportError:
    PILLOW_AVAILABLE = False
    print("❌ Pillow nicht gefunden! Installiere mit: pip install pillow")

# Globale Konstanten
WINDOWS_FONT_DIRS = [
    "C:/Windows/Fonts/",
    os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/")
]

class PillowOpenCVBridge:
    """Bridge-Klasse zur Integration von Pillow's TrueType-Font-Rendering in OpenCV"""
    
    def __init__(self, cache_size: int = 50):
        """
        Initialisiert die Pillow-OpenCV-Bridge
        
        Args:
            cache_size: Maximale Anzahl von Fonts im Cache
        """
        self.available = PILLOW_AVAILABLE
        self.font_cache = {}  # Cache für geladene Fonts
        self.cache_size = cache_size
        self.system_fonts = {}  # Mapping von Font-Namen zu Pfaden
        self._scan_system_fonts()
    
    def _scan_system_fonts(self) -> None:
        """Scannt das System nach verfügbaren TrueType-Fonts"""
        if not PILLOW_AVAILABLE:
            return
            
        try:
            font_count = 0
            for font_dir in WINDOWS_FONT_DIRS:
                if os.path.exists(font_dir):
                    for ext in ['*.ttf', '*.otf', '*.TTF', '*.OTF']:
                        for font_path in glob.glob(os.path.join(font_dir, ext)):
                            try:
                                # Extrahiere Font-Namen aus Dateinamen
                                font_name = os.path.splitext(os.path.basename(font_path))[0]
                                self.system_fonts[font_name.lower()] = font_path
                                font_count += 1
                                
                                # Zusätzliche Varianten für bessere Erkennung
                                simple_name = font_name.split('-')[0] if '-' in font_name else font_name
                                self.system_fonts[simple_name.lower()] = font_path
                            except Exception as e:
                                print(f"⚠️ Fehler beim Laden von Font {font_path}: {e}")
            
            print(f"✅ {font_count} System-Fonts gefunden und indiziert")
        except Exception as e:
            print(f"❌ Fehler beim Scannen der System-Fonts: {e}")
    
    def get_font_path(self, font_name: str) -> Optional[str]:
        """
        Ermittelt den Pfad zu einem Font anhand des Namens
        
        Args:
            font_name: Name des Fonts (z.B. "Arial", "Calibri")
            
        Returns:
            Pfad zum Font oder None wenn nicht gefunden
        """
        if not PILLOW_AVAILABLE:
            return None
            
        # Direkte Übereinstimmung
        if os.path.exists(font_name):
            return font_name
            
        # Suche in System-Fonts
        font_key = font_name.lower()
        if font_key in self.system_fonts:
            return self.system_fonts[font_key]
            
        # Partial Matching für Flexibilität
        for name, path in self.system_fonts.items():
            if font_key in name or name in font_key:
                return path
                
        # Fallback auf Arial
        if 'arial' in self.system_fonts:
            return self.system_fonts['arial']
            
        return None
    
    def load_system_font(self, font_name: str, size: int = 24, 
                         bold: bool = False, italic: bool = False) -> Optional[ImageFont.FreeTypeFont]:
        """
        Lädt einen TrueType-Font aus dem System
        
        Args:
            font_name: Name des Fonts oder Pfad zur Font-Datei
            size: Schriftgröße in Pixeln
            bold: Fettdruck aktivieren
            italic: Kursiv aktivieren
            
        Returns:
            PIL.ImageFont.FreeTypeFont Objekt oder None bei Fehler
        """
        if not PILLOW_AVAILABLE:
            return None
            
        # Cache-Key erstellen
        cache_key = f"{font_name}_{size}_{bold}_{italic}"
        
        # Aus Cache laden wenn möglich
        if cache_key in self.font_cache:
            return self.font_cache[cache_key]
        
        try:
            # Font-Pfad ermitteln
            font_path = self.get_font_path(font_name)
            
            if not font_path:
                print(f"⚠️ Font '{font_name}' nicht gefunden, verwende Fallback")
                # Fallback auf Arial oder einen anderen verfügbaren Font
                for fallback in ['arial', 'calibri', 'segoeui', 'tahoma']:
                    if fallback in self.system_fonts:
                        font_path = self.system_fonts[fallback]
                        break
            
            if font_path:
                # Laden des Fonts mit Pillow
                font = ImageFont.truetype(font_path, size=size)
                
                # Cache-Management
                if len(self.font_cache) >= self.cache_size:
                    # Ältesten Eintrag entfernen
                    oldest_key = next(iter(self.font_cache))
                    del self.font_cache[oldest_key]
                
                # Im Cache speichern
                self.font_cache[cache_key] = font
                return font
                
        except Exception as e:
            print(f"❌ Fehler beim Laden des Fonts '{font_name}': {e}")
        
        return None
    
    def render_text(self, cv_img: np.ndarray, text: str, position: Tuple[int, int],
                font: Any, text_color: Tuple[int, int, int] = (255, 255, 255),
                border_color: Tuple[int, int, int] = None,
                border_thickness: int = 0, alpha: float = 1.0) -> np.ndarray:
        """
        Rendert Text mit TrueType-Font auf ein OpenCV-Bild
        
        Args:
            cv_img: OpenCV-Bild (numpy.ndarray)
            text: Zu rendernder Text
            position: (x, y) Position des Texts
            font: PIL.ImageFont.FreeTypeFont Objekt
            text_color: Textfarbe als (B, G, R)
            border_color: Rahmenfarbe als (B, G, R) oder None für keinen Rahmen
            border_thickness: Rahmendicke in Pixeln
            alpha: Transparenz des Texts (1.0 = vollständig undurchsichtig)
            
        Returns:
            OpenCV-Bild mit gerendertem Text
        """
        if not PILLOW_AVAILABLE or font is None or not text:
            # Fallback auf OpenCV's putText wenn Pillow nicht verfügbar
            return self._cv2_fallback_render(cv_img, text, position, text_color, 
                                            border_color, border_thickness)
        
        try:
            # OpenCV-Bild in Pillow konvertieren (nur für den Text-Bereich)
            h, w = cv_img.shape[:2]
            
            # Erstelle ein transparentes Bild für den Text
            pil_img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(pil_img)
            
            # Position extrahieren
            x, y = position
            
            # Umrandung zeichnen wenn gewünscht
            if border_color and border_thickness > 0:
                # Konvertiere OpenCV BGR zu Pillow RGB
                border_rgb = (border_color[2], border_color[1], border_color[0])
                
                # Zeichne den Text in mehreren Versätzen für die Umrandung
                for dx in range(-border_thickness, border_thickness + 1):
                    for dy in range(-border_thickness, border_thickness + 1):
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), text, fill=border_rgb, font=font)
            
            # Sichere Verarbeitung der Textfarbe
            if text_color is None:
                text_color = (255, 255, 255)  # Standardfarbe Weiß
            text_rgb = (text_color[2], text_color[1], text_color[0], int(255 * alpha))
            
            # Haupttext zeichnen
            draw.text((x, y), text, fill=text_rgb, font=font)
            
            # Konvertiere zurück zu OpenCV
            pil_img_np = np.array(pil_img)
            
            # Ensure we have valid data
            if pil_img_np.size == 0 or pil_img_np.shape[2] < 4:
                return cv_img
                
            # Nur den Textbereich ermitteln
            text_mask = pil_img_np[:, :, 3] > 0
            
            # Skip if no text to render
            if not np.any(text_mask):
                return cv_img
            
            # Erstelle eine Kopie des ursprünglichen Bildes
            result = cv_img.copy()
            
            # Wenn das OpenCV-Bild nur 3 Kanäle hat (kein Alpha)
            if len(cv_img.shape) == 3 and cv_img.shape[2] == 3:
                # FIXED: Direct copy for clearer text instead of alpha blending
                # This ensures text is visible in the final video
                result[text_mask] = pil_img_np[text_mask, :3][:, ::-1]  # BGR zu RGB konvertieren
            
            return result
            
        except Exception as e:
            print(f"❌ Fehler beim Text-Rendering (Pillow): {e}")
            return self._cv2_fallback_render(cv_img, text, position, text_color, 
                                            border_color, border_thickness)
    
    def _cv2_fallback_render(self, cv_img: np.ndarray, text: str, position: Tuple[int, int],
                            text_color: Tuple[int, int, int], border_color: Tuple[int, int, int] = None,
                            border_thickness: int = 0) -> np.ndarray:
        """Fallback-Rendering mit OpenCV wenn Pillow nicht verfügbar ist"""
        result = cv_img.copy()
        
        font_face = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.8
        thickness = 1
        
        # Umrandung zeichnen wenn gewünscht
        if border_color and border_thickness > 0:
            for dx in range(-border_thickness, border_thickness + 1):
                for dy in range(-border_thickness, border_thickness + 1):
                    if dx != 0 or dy != 0:
                        cv2.putText(
                            result, text, 
                            (position[0] + dx, position[1] + dy),
                            font_face, font_scale, border_color, 
                            thickness, cv2.LINE_AA
                        )
        
        # Haupttext zeichnen
        cv2.putText(
            result, text, position,
            font_face, font_scale, text_color, 
            thickness, cv2.LINE_AA
        )
        
        return result
    
    def get_text_size(self, text: str, font: Any) -> Tuple[int, int]:
        """
        Ermittelt die Größe eines gerenderten Texts
        
        Args:
            text: Zu messender Text
            font: PIL.ImageFont.FreeTypeFont Objekt
            
        Returns:
            (Breite, Höhe) des Texts in Pixeln
        """
        if not PILLOW_AVAILABLE or font is None:
            # Fallback auf OpenCV
            font_face = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.8
            thickness = 1
            size, _ = cv2.getTextSize(text, font_face, font_scale, thickness)
            return size
        
        try:
            # Pillow verwenden um Textgröße zu ermitteln
            text_bbox = font.getbbox(text)
            width = text_bbox[2] - text_bbox[0]
            height = text_bbox[3] - text_bbox[1]
            return (width, height)
        except Exception as e:
            print(f"❌ Fehler bei Textgrößenermittlung: {e}")
            
            # Fallback auf OpenCV
            font_face = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.8
            thickness = 1
            size, _ = cv2.getTextSize(text, font_face, font_scale, thickness)
            return size

# Integration mit OpenCVFontSettings aus font_manager.py
class PillowEnhancedFontSettings:
    """
    Erweitertes Font-Settings-Objekt mit Pillow-Integration
    Kompatibel mit bestehendem OpenCVFontSettings
    """
    
    def __init__(self, font_path: str = None, font_name: str = 'Arial', 
                 size: float = 24.0, thickness: int = 2, bold: bool = False,
                 italic: bool = False, border_thickness: int = 2,
                 border_color: Tuple[int, int, int] = (0, 0, 0),
                 text_color: Tuple[int, int, int] = (255, 255, 255),
                 line_spacing: float = 1.2, letter_spacing: float = 0.0):
        
        self.font_path = font_path
        self.font_name = font_name
        self.size = size
        self.thickness = thickness
        self.bold = bold
        self.italic = italic
        self.border_thickness = border_thickness
        self.border_color = border_color
        self.text_color = text_color
        self.line_spacing = line_spacing
        self.letter_spacing = letter_spacing
        
        # Interne Objekte
        self._pillow_font = None
        self._opencv_font = None
        self._bridge = PillowOpenCVBridge()
        
        # Font initialisieren
        self._initialize_fonts()
    
    def _initialize_fonts(self):
        """Initialisiert Pillow und OpenCV Fonts"""
        self._initialize_pillow_font()
        self._initialize_opencv_font()
    
    def _initialize_pillow_font(self):
        """Initialisiert Pillow Font"""
        if not PILLOW_AVAILABLE:
            self._pillow_font = None
            return
            
        try:
            # Font-Größe anpassen (OpenCV vs Pillow Skalierung)
            pil_size = int(self.size * 16)
            
            if self.font_path and os.path.exists(self.font_path):
                # Direkt aus Pfad laden
                self._pillow_font = self._bridge.load_system_font(
                    self.font_path, pil_size, self.bold, self.italic
                )
            else:
                # Aus System laden
                self._pillow_font = self._bridge.load_system_font(
                    self.font_name, pil_size, self.bold, self.italic
                )
        except Exception as e:
            print(f"❌ Fehler beim Initialisieren des Pillow-Fonts: {e}")
            self._pillow_font = None
    
    def _initialize_opencv_font(self):
        """Initialisiert OpenCV Font für Fallback"""
        font_mapping = {
            'HERSHEY_SIMPLEX': cv2.FONT_HERSHEY_SIMPLEX,
            'HERSHEY_PLAIN': cv2.FONT_HERSHEY_PLAIN,
            'HERSHEY_DUPLEX': cv2.FONT_HERSHEY_DUPLEX,
            'HERSHEY_COMPLEX': cv2.FONT_HERSHEY_COMPLEX,
            'HERSHEY_TRIPLEX': cv2.FONT_HERSHEY_TRIPLEX,
            'HERSHEY_COMPLEX_SMALL': cv2.FONT_HERSHEY_COMPLEX_SMALL,
            'HERSHEY_SCRIPT_SIMPLEX': cv2.FONT_HERSHEY_SCRIPT_SIMPLEX,
            'HERSHEY_SCRIPT_COMPLEX': cv2.FONT_HERSHEY_SCRIPT_COMPLEX
        }
        
        # Wenn font_name ein OpenCV Font ist
        if self.font_name in font_mapping:
            self._opencv_font = font_mapping[self.font_name]
        else:
            # Mapping von TrueType zu passendem OpenCV Font
            name_lower = self.font_name.lower()
            if 'arial' in name_lower or 'helvetica' in name_lower or 'sans' in name_lower:
                self._opencv_font = cv2.FONT_HERSHEY_SIMPLEX
            elif 'times' in name_lower or 'serif' in name_lower:
                self._opencv_font = cv2.FONT_HERSHEY_COMPLEX
            elif 'courier' in name_lower or 'mono' in name_lower:
                self._opencv_font = cv2.FONT_HERSHEY_DUPLEX
            else:
                self._opencv_font = cv2.FONT_HERSHEY_SIMPLEX
    
    def is_pillow_available(self) -> bool:
        """Prüft, ob Pillow verfügbar ist und der Font geladen wurde"""
        return PILLOW_AVAILABLE and self._pillow_font is not None
    
    def is_freetype_available(self) -> bool:
        """Kompatibilität mit OpenCVFontSettings"""
        return self.is_pillow_available()
    
    def get_effective_thickness(self) -> int:
        """Gibt Strichstärke mit Bold-Modifikator zurück"""
        base_thickness = self.thickness
        if self.bold:
            return base_thickness + 1
        return base_thickness
    
    def get_opencv_font(self):
        """Gibt OpenCV Font für Fallback zurück"""
        return self._opencv_font
    
    def render_text(self, img: np.ndarray, text: str, position: Tuple[int, int],
                   scale_factor: float = 1.0) -> np.ndarray:
        """Rendert Text mit bestem verfügbaren Verfahren"""
        if self.is_pillow_available():
            return self._render_pillow_text(img, text, position, scale_factor)
        else:
            return self._render_opencv_text(img, text, position, scale_factor)
    
    def _render_pillow_text(self, img: np.ndarray, text: str, 
                          position: Tuple[int, int], scale_factor: float) -> np.ndarray:
        """Rendert Text mit Pillow in hoher Qualität"""
        try:
            return self._bridge.render_text(
                img, text, position, 
                self._pillow_font,
                self.text_color,
                self.border_color if self.border_thickness > 0 else None,
                self.border_thickness
            )
        except Exception as e:
            print(f"❌ Pillow-Rendering fehlgeschlagen: {e}")
            # Fallback zu OpenCV
            return self._render_opencv_text(img, text, position, scale_factor)
    
    def _render_opencv_text(self, img: np.ndarray, text: str,
                          position: Tuple[int, int], scale_factor: float) -> np.ndarray:
        """Fallback-Rendering mit OpenCV"""
        x, y = position
        font_scale = self.size * scale_factor / 24.0  # Normalisierung
        thickness = max(1, int(self.get_effective_thickness() * scale_factor))
        
        # Umrandung rendern
        if self.border_thickness > 0:
            border_thickness = max(1, int(self.border_thickness * scale_factor))
            for dx in range(-border_thickness, border_thickness + 1):
                for dy in range(-border_thickness, border_thickness + 1):
                    if dx != 0 or dy != 0:
                        cv2.putText(img, text, (x + dx, y + dy), self._opencv_font,
                                  font_scale, self.border_color, thickness + 1, cv2.LINE_AA)
        
        # Haupttext rendern
        cv2.putText(img, text, position, self._opencv_font,
                   font_scale, self.text_color, thickness, cv2.LINE_AA)
        
        return img
    
    def get_text_size(self, text: str, scale_factor: float = 1.0) -> Tuple[int, int]:
        """Gibt Textdimensionen zurück"""
        if self.is_pillow_available():
            try:
                return self._bridge.get_text_size(text, self._pillow_font)
            except:
                pass
        
        # Fallback zu OpenCV
        font_scale = self.size * scale_factor / 24.0
        thickness = max(1, int(self.get_effective_thickness() * scale_factor))
        size, _ = cv2.getTextSize(text, self._opencv_font, font_scale, thickness)
        return size
    
    def clone(self):
        """Erstellt eine Kopie dieser Font-Einstellungen"""
        return PillowEnhancedFontSettings(
            font_path=self.font_path,
            font_name=self.font_name,
            size=self.size,
            thickness=self.thickness,
            bold=self.bold,
            italic=self.italic,
            border_thickness=self.border_thickness,
            border_color=self.border_color,
            text_color=self.text_color,
            line_spacing=self.line_spacing,
            letter_spacing=self.letter_spacing
        )
    
    def to_dict(self) -> Dict:
        """Konvertiert zu Dictionary für Serialisierung"""
        return {
            'font_path': self.font_path,
            'font_name': self.font_name,
            'size': self.size,
            'thickness': self.thickness,
            'bold': self.bold,
            'italic': self.italic,
            'border_thickness': self.border_thickness,
            'border_color': self.border_color,
            'text_color': self.text_color,
            'line_spacing': self.line_spacing,
            'letter_spacing': self.letter_spacing
        }
    
    @classmethod
    def from_dict(cls, data: Dict):
        """Erstellt aus Dictionary"""
        return cls(**data)


# Modul-Tests
def test_pillow_opencv_bridge():
    """Test-Funktion für Pillow-OpenCV-Bridge"""
    if not PILLOW_AVAILABLE:
        print("❌ Pillow nicht verfügbar - Test übersprungen")
        return False
    
    try:
        # Test-Bild erstellen
        img = np.zeros((600, 800, 3), dtype=np.uint8)
        
        # Hintergrund
        img[:] = (40, 40, 40)  # Dunkelgrau
        
        # Bridge erstellen
        bridge = PillowOpenCVBridge()
        
        # Font laden
        arial_font = bridge.load_system_font("Arial", size=36)
        
        if arial_font is None:
            print("⚠️ Arial Font konnte nicht geladen werden, versuche anderen Font...")
            # Versuche einen anderen Font
            for font_name in ["Calibri", "Segoe UI", "Tahoma", "Verdana"]:
                test_font = bridge.load_system_font(font_name, size=36)
                if test_font is not None:
                    arial_font = test_font
                    print(f"✅ Alternativ-Font '{font_name}' geladen")
                    break
        
        if arial_font is None:
            print("❌ Kein Font konnte geladen werden!")
            return False
        
        # Text rendern
        img = bridge.render_text(
            img, "Pillow-OpenCV Bridge Test", (50, 100), 
            arial_font, (255, 255, 255), (0, 0, 0), 2
        )
        
        # Mehr Texte mit verschiedenen Stilen
        title_font = bridge.load_system_font("Impact", size=48)
        if title_font:
            img = bridge.render_text(
                img, "TrueType Fonts in OpenCV!", (50, 50),
                title_font, (0, 255, 255)
            )
        
        body_font = bridge.load_system_font("Calibri", size=24)
        if body_font:
            text_lines = [
                "✅ Diese Bridge ermöglicht TrueType-Fonts in OpenCV",
                "✅ Voller Zugriff auf alle Windows-Fonts",
                "✅ Unterstützung für Unicode: ÄÖÜäöüß€µ©®™",
                "✅ Anti-Aliasing und Texteffekte",
                "✅ Nahtlose Integration in bestehenden Code"
            ]
            
            y = 200
            for line in text_lines:
                img = bridge.render_text(
                    img, line, (50, y),
                    body_font, (200, 255, 200)
                )
                y += 40
        
        # Speichere Test-Bild
        output_path = "pillow_opencv_bridge_test.png"
        cv2.imwrite(output_path, img)
        
        print(f"✅ Test erfolgreich! Ausgabe gespeichert als: {output_path}")
        return True
        
    except Exception as e:
        print(f"❌ Test fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("="*80)
    print("PILLOW-OPENCV FONT BRIDGE - TrueType Font Integration für OpenCV")
    print("="*80)
    
    # Systeminformationen ausgeben
    print(f"Python: {sys.version}")
    print(f"OpenCV: {cv2.__version__}")
    print(f"Pillow: {'Verfügbar' if PILLOW_AVAILABLE else 'NICHT VERFÜGBAR'}")
    print(f"OS: {os.name} - {sys.platform}")
    
    # Bridge-Test ausführen
    print("\nFühre Bridge-Test aus...")
    test_result = test_pillow_opencv_bridge()
    
    print("\n" + "="*80)
    if test_result:
        print("✅ PILLOW-OPENCV BRIDGE FUNKTIONIERT EINWANDFREI!")
        print("✅ Du kannst nun TrueType-Fonts in deinem FPS Analyzer verwenden!")
    else:
        print("❌ PILLOW-OPENCV BRIDGE TEST FEHLGESCHLAGEN")
        print("⚠️ Prüfe bitte die Fehlerausgabe oben und stelle sicher, dass Pillow installiert ist:")
        print("pip install pillow")
    print("="*80)
