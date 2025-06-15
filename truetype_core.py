"""
TrueType Core Module - Provides TrueType font support for FPS Analyzer
"""

import os
import sys
import platform
import glob
from typing import Dict, List, Tuple, Optional, Union, Any
import numpy as np

# Check for Pillow
try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("WARNING: Pillow not installed. TrueType fonts will not be available.")
    print("Install with: pip install Pillow")

# Check for FreeType support in OpenCV
def check_freetype_support():
    try:
        import cv2
        cv2.freetype.createFreeType2()
        return True
    except:
        return False

FREETYPE_AVAILABLE = check_freetype_support()

# Debug mode
_DEBUG_MODE = False

def enable_debug_mode(export_images=False):
    global _DEBUG_MODE
    _DEBUG_MODE = True

def debug_log(message):
    if _DEBUG_MODE:
        print(f"[FONT DEBUG] {message}")

class SystemFontDiscovery:
    """Discovers system fonts"""
    
    def __init__(self):
        self.system_fonts = []
        self._font_cache = {}
        self.popular_font_names = [
            'arial', 'helvetica', 'times', 'calibri', 'verdana', 'georgia',
            'bebas neue', 'bebasneue', 'roboto', 'open sans', 'montserrat', 'lato',
            'raleway', 'poppins', 'ubuntu', 'segoe ui', 'tahoma', 'comic sans',
            'impact', 'consolas', 'courier'
        ]
        
    def discover_fonts(self) -> List[Dict]:
        """Discover ALL system fonts"""
        if self.system_fonts:
            return self.system_fonts
            
        font_paths = []
        system = platform.system().lower()
        
        # Define font directories by OS
        if system == "windows":
            font_dirs = [
                "C:/Windows/Fonts/",
                os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/")
            ]
        elif system == "darwin":
            font_dirs = [
                "/System/Library/Fonts/",
                "/Library/Fonts/",
                os.path.expanduser("~/Library/Fonts/")
            ]
        else:  # Linux
            font_dirs = [
                "/usr/share/fonts/",
                "/usr/local/share/fonts/",
                os.path.expanduser("~/.fonts/"),
                os.path.expanduser("~/.local/share/fonts/")
            ]
        
        # Scan directories - ALLE FONTS
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                for ext in ['*.ttf', '*.otf', '*.TTF', '*.OTF']:
                    pattern = os.path.join(font_dir, '**', ext)
                    for font_path in glob.glob(pattern, recursive=True):
                        try:
                            font_name = os.path.splitext(os.path.basename(font_path))[0]
                            font_info = {
                                'name': font_name,
                                'path': font_path,
                                'type': 'ttf' if font_path.lower().endswith('.ttf') else 'otf',
                                'size': os.path.getsize(font_path)
                            }
                            self.system_fonts.append(font_info)
                            self._font_cache[font_name.lower()] = font_info
                        except:
                            pass
        
        # Sort by name
        self.system_fonts.sort(key=lambda x: x['name'].lower())
        debug_log(f"Discovered {len(self.system_fonts)} fonts")
        return self.system_fonts
    
    def get_font_by_name(self, name: str) -> Optional[Dict]:
        """Get font by name"""
        if not self.system_fonts:
            self.discover_fonts()
        
        # Direct lookup
        name_lower = name.lower()
        if name_lower in self._font_cache:
            return self._font_cache[name_lower]
        
        # Partial match
        for font in self.system_fonts:
            if name_lower in font['name'].lower():
                return font
        
        return None
    
    def get_popular_fonts(self) -> List[Dict]:
        """Get only popular fonts from the discovered fonts"""
        if not self.system_fonts:
            self.discover_fonts()
        
        popular = []
        
        # Filter for popular fonts
        for font in self.system_fonts:
            font_name_lower = font['name'].lower()
            # Check if font name contains any popular font name
            if any(popular_name in font_name_lower for popular_name in self.popular_font_names):
                popular.append(font)
        
        # Bebas Neue an den Anfang setzen wenn vorhanden
        bebas_index = next((i for i, font in enumerate(popular) 
                           if 'bebas' in font['name'].lower()), None)
        if bebas_index is not None:
            bebas_font = popular.pop(bebas_index)
            popular.insert(0, bebas_font)
        
        debug_log(f"Found {len(popular)} popular fonts (including Bebas Neue)")
        return popular

class PillowOpenCVBridge:
    """Bridge between Pillow and OpenCV for font rendering"""
    
    def __init__(self, cache_size=50):
        self.available = PILLOW_AVAILABLE
        self._font_cache = {}
        self._cache_size = cache_size
    
    def load_system_font(self, font_name_or_path: str, size: int = 24, 
                        bold: bool = False, italic: bool = False) -> Optional[Any]:
        """Load a system font"""
        if not PILLOW_AVAILABLE:
            return None
        
        # Cache key
        cache_key = f"{font_name_or_path}_{size}_{bold}_{italic}"
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
        
        try:
            # Try direct path first
            if os.path.exists(font_name_or_path):
                font = ImageFont.truetype(font_name_or_path, size=size)
            else:
                # Try to find font by name
                discovery = SystemFontDiscovery()
                font_info = discovery.get_font_by_name(font_name_or_path)
                if font_info:
                    font = ImageFont.truetype(font_info['path'], size=size)
                else:
                    # Fallback to default
                    font = ImageFont.load_default()
            
            # Cache management
            if len(self._font_cache) >= self._cache_size:
                # Remove oldest
                oldest = next(iter(self._font_cache))
                del self._font_cache[oldest]
            
            self._font_cache[cache_key] = font
            return font
            
        except Exception as e:
            debug_log(f"Failed to load font {font_name_or_path}: {e}")
            return None
    
    def render_text(self, cv_img: np.ndarray, text: str, position: Tuple[int, int],
                font: Any, text_color: Tuple[int, int, int] = (255, 255, 255),
                border_color: Optional[Tuple[int, int, int]] = None,
                border_thickness: int = 0, alpha: float = 1.0) -> np.ndarray:
        
        if not PILLOW_AVAILABLE or font is None:
            return cv_img
        
        try:
            # Convert OpenCV BGR to RGB
            img_rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            
            # Create drawing context - USE RGB NOT RGBA!
            draw = ImageDraw.Draw(pil_img)
            
            # Convert BGR colors to RGB (no alpha channel)
            text_rgb = (text_color[2], text_color[1], text_color[0])
            
            # WICHTIG: Y-Position Anpassung für TrueType Fonts
            # TrueType verwendet top-left, OpenCV verwendet baseline
            # Offset abhängig von der Fontgröße
            if hasattr(font, 'size'):
                y_offset = -int(font.size * 0.25)  # 25% der Fontgröße nach oben
            else:
                y_offset = -8  # Default offset
            
            adjusted_position = (position[0], position[1] + y_offset)
            
            
            # Draw border if needed
            if border_color is not None and border_thickness > 0:
                border_rgb = (border_color[2], border_color[1], border_color[0])
                for dx in range(-border_thickness, border_thickness + 1):
                    for dy in range(-border_thickness, border_thickness + 1):
                        if dx != 0 or dy != 0:
                            draw.text((adjusted_position[0] + dx, adjusted_position[1] + dy), text, 
                                    font=font, fill=border_rgb)
            
            # Draw main text
            draw.text(adjusted_position, text, font=font, fill=text_rgb)
            
            # Convert back to OpenCV BGR
            img_array = np.array(pil_img)
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            return img_bgr
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return cv_img
    
    def get_text_size(self, text: str, font: Any) -> Tuple[int, int]:
        """Get text size"""
        if not PILLOW_AVAILABLE or font is None:
            return (len(text) * 10, 20)  # Rough estimate
        
        try:
            # For newer Pillow versions
            if hasattr(font, 'getbbox'):
                bbox = font.getbbox(text)
                return (bbox[2] - bbox[0], bbox[3] - bbox[1])
            # For older versions
            elif hasattr(font, 'getsize'):
                return font.getsize(text)
            else:
                return (len(text) * 10, 20)
        except:
            return (len(text) * 10, 20)

# Import cv2 for the BGR/RGB conversion
try:
    import cv2
except ImportError:
    print("WARNING: OpenCV not installed. Some features may not work.")