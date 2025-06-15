"""
Direct TrueType Font Renderer - No OpenCV Fallbacks
Provides high-quality text rendering with TrueType fonts using Pillow
with zero fallbacks to OpenCV fonts. Includes detailed error reporting.
"""

import numpy as np
import os
import sys
import platform
import glob
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Any

# Force Pillow import - fail explicitly if not available
try:
    from PIL import Image, ImageDraw, ImageFont, ImageColor
    PILLOW_AVAILABLE = True
except ImportError:
    raise ImportError(
        "CRITICAL ERROR: Pillow library is required for TrueType font rendering.\n"
        "Please install it with: pip install Pillow"
    )

# Force specific errors rather than silent fallbacks
class FontError(Exception):
    """Error raised when font operations fail"""
    pass

class FontNotFoundError(FontError):
    """Error raised when a font cannot be found"""
    pass

class RenderingError(FontError):
    """Error raised when text rendering fails"""
    pass

class DirectTTFRenderer:
    """
    Direct TrueType Font Renderer with zero OpenCV fallbacks
    and robust error handling
    """
    
    def __init__(self, cache_size=50, debug_mode=False):
        """Initialize the renderer with optional debugging"""
        self.font_cache = {}  # Cache for loaded fonts
        self.cache_size = cache_size
        self.debug_mode = debug_mode
        self.system_fonts = {}
        self.available_fonts = []
        
        # Initialize system font discovery
        self._discover_system_fonts()
        
    def _discover_system_fonts(self):
        """Discover available system fonts and populate cache"""
        if self.debug_mode:
            print("🔍 Scanning for system fonts...")
            
        font_paths = []
        system = platform.system().lower()
        
        # Windows font directories
        if system == "windows":
            font_dirs = [
                "C:/Windows/Fonts/",
                os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/")
            ]
        # macOS font directories
        elif system == "darwin":
            font_dirs = [
                "/System/Library/Fonts/",
                "/Library/Fonts/",
                os.path.expanduser("~/Library/Fonts/")
            ]
        # Linux font directories
        else:
            font_dirs = [
                "/usr/share/fonts/",
                "/usr/local/share/fonts/",
                os.path.expanduser("~/.fonts/"),
                os.path.expanduser("~/.local/share/fonts/"),
                "/usr/share/fonts/truetype/",
                "/usr/share/fonts/opentype/"
            ]
            
        # Scan all directories for fonts
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                for ext in ['*.ttf', '*.otf', '*.TTF', '*.OTF']:
                    try:
                        pattern = os.path.join(font_dir, '**', ext)
                        for font_path in glob.glob(pattern, recursive=True):
                            try:
                                # Extract font name from filename
                                font_name = os.path.splitext(os.path.basename(font_path))[0]
                                font_name_lower = font_name.lower()
                                
                                # Store with multiple keys for easier lookup
                                self.system_fonts[font_name_lower] = font_path
                                
                                # Store simplified name without style suffixes
                                simple_name = font_name.split('-')[0] if '-' in font_name else font_name
                                self.system_fonts[simple_name.lower()] = font_path
                                
                                # Add to available fonts list
                                self.available_fonts.append({
                                    'name': font_name,
                                    'path': font_path,
                                    'type': 'ttf' if font_path.lower().endswith('.ttf') else 'otf'
                                })
                            except Exception as e:
                                if self.debug_mode:
                                    print(f"⚠️ Error processing font {font_path}: {e}")
                    except Exception as e:
                        if self.debug_mode:
                            print(f"⚠️ Error scanning {font_dir} with pattern {ext}: {e}")
        
        # Sort fonts by name
        self.available_fonts.sort(key=lambda x: x['name'].lower())
        
        if self.debug_mode:
            print(f"✅ Found {len(self.available_fonts)} TrueType/OpenType fonts")
    
    def get_font_path(self, font_name: str) -> str:
        """
        Get path to a font by name with robust error handling
        
        Args:
            font_name: Font name or path
            
        Returns:
            Path to the font file
            
        Raises:
            FontNotFoundError: If the font cannot be found
        """
        # Direct path
        if os.path.exists(font_name):
            return font_name
            
        # Exact match in system fonts
        font_key = font_name.lower()
        if font_key in self.system_fonts:
            return self.system_fonts[font_key]
            
        # Partial matching
        for name, path in self.system_fonts.items():
            if font_key in name or name in font_key:
                return path
                
        # Try common fallbacks but still within TrueType
        fallbacks = ['arial', 'helvetica', 'dejavu', 'liberation', 'roboto', 'noto']
        for fallback in fallbacks:
            for name, path in self.system_fonts.items():
                if fallback in name:
                    if self.debug_mode:
                        print(f"⚠️ Font '{font_name}' not found, using fallback: {name}")
                    return path
        
        # If we get here, no suitable font was found
        raise FontNotFoundError(
            f"Could not find font '{font_name}' or any suitable fallback. "
            f"Available fonts: {', '.join(sorted(self.system_fonts.keys())[:10])}..."
        )
    
    def load_font(self, font_name: str, size: int = 24, bold: bool = False, 
                 italic: bool = False) -> ImageFont.FreeTypeFont:
        """
        Load a TrueType font with detailed error handling
        
        Args:
            font_name: Font name or path
            size: Font size in pixels
            bold: Whether to use bold style
            italic: Whether to use italic style
            
        Returns:
            PIL ImageFont object
            
        Raises:
            FontNotFoundError: If the font cannot be found
            FontError: If the font cannot be loaded
        """
        # Create cache key
        cache_key = f"{font_name}_{size}_{bold}_{italic}"
        
        # Return from cache if available
        if cache_key in self.font_cache:
            return self.font_cache[cache_key]
        
        try:
            # Get font path with robust error handling
            font_path = self.get_font_path(font_name)
            
            # Load font with Pillow
            font = ImageFont.truetype(font_path, size=size)
            
            # Cache management - remove oldest entry if cache is full
            if len(self.font_cache) >= self.cache_size:
                oldest_key = next(iter(self.font_cache))
                del self.font_cache[oldest_key]
            
            # Store in cache
            self.font_cache[cache_key] = font
            return font
            
        except FontNotFoundError:
            raise  # Re-raise font not found errors
        except Exception as e:
            raise FontError(f"Failed to load font '{font_name}': {str(e)}")
    
    def render_text(self, img: np.ndarray, text: str, position: Tuple[int, int],
                   font: ImageFont.FreeTypeFont, text_color: Tuple[int, int, int] = (255, 255, 255),
                   border_color: Optional[Tuple[int, int, int]] = None,
                   border_thickness: int = 0, alpha: float = 1.0) -> np.ndarray:
        """
        Render text onto an image with robust alpha compositing
        
        Args:
            img: NumPy array of shape (H, W, 3) - BGR format (OpenCV)
            text: Text to render
            position: (x, y) position for the text
            font: PIL ImageFont object
            text_color: Text color in BGR format (OpenCV)
            border_color: Border color in BGR format (OpenCV)
            border_thickness: Border thickness in pixels
            alpha: Alpha transparency (0-1)
            
        Returns:
            Image with rendered text
            
        Raises:
            RenderingError: If text rendering fails
        """
        try:
            # Ensure input image is valid
            if img is None or not isinstance(img, np.ndarray) or len(img.shape) != 3:
                raise RenderingError(
                    f"Invalid input image: expected NumPy array of shape (H, W, 3), "
                    f"got {type(img).__name__} with shape {getattr(img, 'shape', 'unknown')}"
                )
                
            # Get image dimensions
            h, w, c = img.shape
            if c != 3:
                raise RenderingError(f"Expected 3-channel BGR image, got {c} channels")
            
            # Create a transparent PIL image for the text
            pil_img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(pil_img)
            
            # Extract position
            x, y = position
            
            # Prepare colors (BGR to RGB conversion)
            if text_color is None:
                text_color = (255, 255, 255)
            text_rgb = (text_color[2], text_color[1], text_color[0], int(255 * alpha))
            
            # Draw border if requested
            if border_color is not None and border_thickness > 0:
                border_rgb = (border_color[2], border_color[1], border_color[0], int(255 * alpha))
                
                # Draw text at multiple offsets for border effect
                for dx in range(-border_thickness, border_thickness + 1, 1):
                    for dy in range(-border_thickness, border_thickness + 1, 1):
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), text, fill=border_rgb, font=font)
            
            # Draw main text
            draw.text((x, y), text, fill=text_rgb, font=font)
            
            # Convert PIL image to NumPy array
            text_array = np.array(pil_img)
            
            # Create a copy of the input image
            result = img.copy()
            
            # Get alpha channel and create mask where alpha > 0
            alpha_channel = text_array[:, :, 3].astype(np.float32) / 255.0
            
            # For each color channel, blend original with text where alpha > 0
            for c in range(3):  # BGR channels
                channel = result[:, :, c].astype(np.float32)
                text_channel = text_array[:, :, 2-c].astype(np.float32)  # RGB to BGR
                
                # Alpha compositing: result = (1-alpha)*original + alpha*text
                channel = (1.0 - alpha_channel) * channel + alpha_channel * text_channel
                
                # Update the result
                result[:, :, c] = channel.astype(np.uint8)
            
            return result
            
        except Exception as e:
            raise RenderingError(f"Text rendering failed: {str(e)}")
    
    def get_text_size(self, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
        """
        Get size of text when rendered with the given font
        
        Args:
            text: Text to measure
            font: PIL ImageFont object
            
        Returns:
            (width, height) of the text in pixels
            
        Raises:
            FontError: If text size calculation fails
        """
        try:
            # Use getbbox for newer Pillow versions
            if hasattr(font, 'getbbox'):
                bbox = font.getbbox(text)
                width = bbox[2] - bbox[0]
                height = bbox[3] - bbox[1]
                return (width, height)
            # Fall back to getsize for older Pillow versions
            elif hasattr(font, 'getsize'):
                return font.getsize(text)
            else:
                # Last resort fallback
                return (len(text) * font.size // 2, font.size)
        except Exception as e:
            raise FontError(f"Failed to calculate text size: {str(e)}")
    
    def get_available_fonts(self) -> List[Dict]:
        """
        Get list of all available TrueType/OpenType fonts
        
        Returns:
            List of font information dictionaries
        """
        return self.available_fonts
    
    def get_common_fonts(self) -> List[Dict]:
        """
        Get list of common/recommended fonts that are available
        
        Returns:
            List of font information dictionaries
        """
        common_names = [
            'arial', 'helvetica', 'times', 'courier', 'verdana', 
            'tahoma', 'calibri', 'georgia', 'segoe', 'trebuchet',
            'roboto', 'opensans', 'lato', 'montserrat', 'sourcesans',
            'ubuntu', 'droid', 'dejavu'
        ]
        
        common_fonts = []
        for name in common_names:
            for font in self.available_fonts:
                if name.lower() in font['name'].lower():
                    common_fonts.append(font)
                    break
        
        return common_fonts

# Global instance for convenience
_default_renderer = None

def get_renderer(debug_mode=False):
    """Get the global renderer instance"""
    global _default_renderer
    if _default_renderer is None:
        _default_renderer = DirectTTFRenderer(debug_mode=debug_mode)
    return _default_renderer