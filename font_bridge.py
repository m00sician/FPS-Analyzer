"""
Font Bridge - Seamless TrueType integration for FPS Analyzer
Integrates DirectTTFRenderer with the existing font system, ensuring
only TrueType fonts are used with no fallbacks to OpenCV.
"""

import os
import sys
import numpy as np
from typing import Dict, List, Tuple, Optional, Union, Any

# Force TrueType renderer import
try:
    from direct_ttf_renderer import DirectTTFRenderer, get_renderer, FontError, FontNotFoundError, RenderingError
    TTF_RENDERER_AVAILABLE = True
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import DirectTTFRenderer: {e}")
    print("Please ensure direct_ttf_renderer.py is in the Python path")
    TTF_RENDERER_AVAILABLE = False
    raise ImportError("DirectTTFRenderer is required for font rendering")

# Constants
DEFAULT_FONT = "arial"
DEFAULT_SIZE = 24
DEFAULT_COLOR = (255, 255, 255)  # White (BGR)
DEFAULT_BORDER_COLOR = (0, 0, 0)  # Black (BGR)

class TTFontSettings:
    """
    TrueType font settings with guaranteed TrueType rendering
    Compatible with existing font system but never falls back to OpenCV
    """
    
    def __init__(self, font_name: str = DEFAULT_FONT, 
                font_path: str = None,
                size: float = DEFAULT_SIZE, 
                thickness: int = 2, 
                bold: bool = False,
                italic: bool = False, 
                border_thickness: int = 2,
                border_color: Tuple[int, int, int] = DEFAULT_BORDER_COLOR,
                text_color: Tuple[int, int, int] = DEFAULT_COLOR):
        """
        Initialize TrueType font settings
        
        Args:
            font_name: Name of the font
            font_path: Path to font file (optional)
            size: Font size
            thickness: Text thickness
            bold: Bold style
            italic: Italic style
            border_thickness: Border thickness
            border_color: Border color (BGR)
            text_color: Text color (BGR)
        """
        self.font_name = font_name
        self.font_path = font_path
        self.size = size
        self.thickness = thickness
        self.bold = bold
        self.italic = italic
        self.border_thickness = border_thickness
        self.border_color = border_color
        self.text_color = text_color
        
        # Get renderer instance
        self._renderer = get_renderer()
        self._pil_font = None
        
        # Initialize font - must succeed or raise error
        self._initialize_font()
    
    def _initialize_font(self):
        """
        Initialize TrueType font - must succeed or raise error
        """
        try:
            # Try font path first if provided
            if self.font_path and os.path.exists(self.font_path):
                self._pil_font = self._renderer.load_font(
                    self.font_path, 
                    size=int(self.size),
                    bold=self.bold,
                    italic=self.italic
                )
                return
            
            # Otherwise try by name
            self._pil_font = self._renderer.load_font(
                self.font_name, 
                size=int(self.size),
                bold=self.bold,
                italic=self.italic
            )
        except (FontError, FontNotFoundError) as e:
            # Try fallback fonts before giving up
            try:
                # Try common fallbacks
                for fallback in ["arial", "helvetica", "dejavu", "roboto", "noto"]:
                    try:
                        self._pil_font = self._renderer.load_font(
                            fallback, 
                            size=int(self.size),
                            bold=self.bold,
                            italic=self.italic
                        )
                        self.font_name = fallback  # Update name to match what was loaded
                        print(f"⚠️ Using fallback font '{fallback}' instead of '{self.font_name}'")
                        return
                    except:
                        continue
            except:
                pass
            
            # If we get here, all fallbacks failed
            raise FontError(f"Could not load any TrueType font. Original error: {str(e)}")
    
    def render_text(self, img: np.ndarray, text: str, position: Tuple[int, int], 
                   scale_factor: float = 1.0) -> np.ndarray:
        """
        Render text onto an image with TrueType font
        
        Args:
            img: NumPy array image (BGR format)
            text: Text to render
            position: (x, y) position
            scale_factor: Scale factor for size adjustment
            
        Returns:
            Image with rendered text
        """
        # Calculate scaled size
        if scale_factor != 1.0:
            scaled_size = int(self.size * scale_factor)
            
            # Load new font with scaled size
            try:
                if self.font_path and os.path.exists(self.font_path):
                    font = self._renderer.load_font(
                        self.font_path, 
                        size=scaled_size,
                        bold=self.bold,
                        italic=self.italic
                    )
                else:
                    font = self._renderer.load_font(
                        self.font_name, 
                        size=scaled_size,
                        bold=self.bold,
                        italic=self.italic
                    )
            except:
                # Use original font if scaling fails
                font = self._pil_font
        else:
            font = self._pil_font
        
        # Scale border thickness
        border_thickness = max(1, int(self.border_thickness * scale_factor))
        
        # Render text
        return self._renderer.render_text(
            img=img,
            text=text,
            position=position,
            font=font,
            text_color=self.text_color,
            border_color=self.border_color,
            border_thickness=border_thickness
        )
    
    def get_text_size(self, text: str, scale_factor: float = 1.0) -> Tuple[int, int]:
        """
        Get size of text when rendered
        
        Args:
            text: Text to measure
            scale_factor: Scale factor for size adjustment
            
        Returns:
            (width, height) of the text in pixels
        """
        # Calculate scaled size
        if scale_factor != 1.0:
            scaled_size = int(self.size * scale_factor)
            
            # Load new font with scaled size
            try:
                if self.font_path and os.path.exists(self.font_path):
                    font = self._renderer.load_font(
                        self.font_path, 
                        size=scaled_size,
                        bold=self.bold,
                        italic=self.italic
                    )
                else:
                    font = self._renderer.load_font(
                        self.font_name, 
                        size=scaled_size,
                        bold=self.bold,
                        italic=self.italic
                    )
                return self._renderer.get_text_size(text, font)
            except:
                # Use original font if scaling fails
                pass
        
        return self._renderer.get_text_size(text, self._pil_font)
    
    def clone(self):
        """Create a copy of this font settings object"""
        return TTFontSettings(
            font_name=self.font_name,
            font_path=self.font_path,
            size=self.size,
            thickness=self.thickness,
            bold=self.bold,
            italic=self.italic,
            border_thickness=self.border_thickness,
            border_color=self.border_color,
            text_color=self.text_color
        )
    
    def is_freetype_available(self):
        """Always returns True for compatibility with existing code"""
        return True
    
    def get_opencv_font(self):
        """Dummy method for compatibility - throws error if called"""
        raise RuntimeError("OpenCV fonts are not supported - TrueType only")
    
    def get_effective_thickness(self):
        """Dummy method for compatibility"""
        return self.thickness + (1 if self.bold else 0)

# Factory function to create font settings for different elements
def create_font_settings_for_element(element_type: str) -> TTFontSettings:
    """
    Create font settings for different UI elements
    
    Args:
        element_type: Type of UI element ('fps', 'framerate', or 'frametime')
        
    Returns:
        TTFontSettings object for the element
    """
    renderer = get_renderer()
    
    # Get available fonts
    available_fonts = renderer.get_common_fonts()
    if not available_fonts:
        available_fonts = renderer.get_available_fonts()
    
    # Get best available font
    font_path = None
    font_name = DEFAULT_FONT
    
    if available_fonts:
        # Use first available font
        font_info = available_fonts[0]
        font_path = font_info['path']
        font_name = font_info['name']
    
    # Configure based on element type
    if element_type == 'fps':
        # FPS number - large, bold
        return TTFontSettings(
            font_name=font_name,
            font_path=font_path,
            size=32,
            thickness=3,
            bold=True,
            border_thickness=3,
            text_color=(0, 255, 0)  # Green
        )
    elif element_type == 'framerate':
        # Framerate graph labels - medium
        return TTFontSettings(
            font_name=font_name,
            font_path=font_path,
            size=16,
            thickness=2,
            bold=False,
            border_thickness=2,
            text_color=(255, 255, 255)  # White
        )
    else:  # frametime
        # Frametime graph labels - small
        return TTFontSettings(
            font_name=font_name,
            font_path=font_path,
            size=14,
            thickness=1,
            bold=False,
            border_thickness=1,
            text_color=(255, 255, 255)  # White
        )

def create_default_font_settings():
    """
    Create default font settings for FPS Analyzer
    
    Returns:
        Dictionary of font settings for different elements
    """
    return {
        'fps_font': create_font_settings_for_element('fps'),
        'framerate_font': create_font_settings_for_element('framerate'),
        'frametime_font': create_font_settings_for_element('frametime')
    }

def patch_overlay_renderer():
    """
    Patch the overlay renderer to use TrueType fonts
    """
    try:
        import enhanced_overlay_renderer
        
        # Patch the draw_text_with_border method
        original_method = enhanced_overlay_renderer.OverlayElement.draw_text_with_border
        
        def patched_draw_text_with_border(self, img, text, position, font, font_scale, color, thickness, 
                                        border_color=(0, 0, 0), border_thickness=2):
            """Patched text rendering method that only uses TrueType fonts"""
            try:
                # Check if we have TTFontSettings
                if hasattr(font, 'render_text'):
                    effective_scale = self.scale_factor * self.resolution_scale
                    
                    # Set text color for rendering
                    font.text_color = color
                    if border_thickness > 0:
                        font.border_color = border_color
                        font.border_thickness = border_thickness
                    
                    # Render text with TrueType font
                    return font.render_text(img, text, position, effective_scale)
                else:
                    # Convert to TTFontSettings on the fly
                    tt_font = TTFontSettings(
                        font_name="arial",
                        size=24 * font_scale,
                        thickness=thickness,
                        bold=False,
                        border_thickness=border_thickness,
                        border_color=border_color,
                        text_color=color
                    )
                    
                    # Render with TrueType font
                    effective_scale = self.scale_factor * self.resolution_scale
                    return tt_font.render_text(img, text, position, effective_scale)
            except Exception as e:
                print(f"❌ TrueType text rendering failed: {e}")
                print(f"Text: '{text}', Position: {position}")
                import traceback
                traceback.print_exc()
                
                # Create emergency TrueType rendering - NEVER fall back to OpenCV
                try:
                    emergency_font = TTFontSettings()
                    emergency_font.text_color = color
                    emergency_font.border_color = border_color
                    emergency_font.border_thickness = border_thickness
                    return emergency_font.render_text(img, text, position, 1.0)
                except Exception as e2:
                    print(f"❌ Emergency TrueType rendering also failed: {e2}")
                    # Return original image as absolute last resort
                    return img
        
        # Apply patch
        enhanced_overlay_renderer.OverlayElement.draw_text_with_border = patched_draw_text_with_border
        print("✅ Enhanced Overlay Renderer patched to use TrueType fonts exclusively")
        
    except ImportError:
        print("⚠️ Could not patch enhanced_overlay_renderer - module not found")
    except Exception as e:
        print(f"❌ Failed to patch overlay renderer: {e}")

def patch_analysis_worker():
    """
    Patch the analysis worker to use TrueType fonts
    """
    try:
        import analysis_worker
        
        # Store original method for backup
        original_method = analysis_worker.AnalysisWorker.create_overlay
        
        def patched_create_overlay(self, frame_rgb, fps_history, displayed_fps, frame_times, show_frametime, 
                                global_fps_values, global_frame_times, frametime_scale, font_settings, color_settings):
            """Patched create_overlay method that ensures TrueType fonts are used"""
            # Ensure we have proper TrueType font settings
            if not font_settings or not all(hasattr(font, 'render_text') for font in font_settings.values()):
                print("🔍 Converting to TrueType font settings")
                try:
                    # Create new TrueType font settings
                    tt_font_settings = create_default_font_settings()
                    
                    # Copy any color settings
                    if color_settings:
                        if 'framerate_color' in color_settings:
                            tt_font_settings['framerate_font'].text_color = color_settings['framerate_color']
                        if 'frametime_color' in color_settings:
                            tt_font_settings['frametime_font'].text_color = color_settings['frametime_color']
                    
                    font_settings = tt_font_settings
                except Exception as e:
                    print(f"❌ Failed to create TrueType font settings: {e}")
                    # Create minimal emergency settings
                    font_settings = create_default_font_settings()
            
            # Call original method with updated font settings
            return original_method(self, frame_rgb, fps_history, displayed_fps, frame_times, show_frametime,
                                 global_fps_values, global_frame_times, frametime_scale, font_settings, color_settings)
        
        # Apply patch
        analysis_worker.AnalysisWorker.create_overlay = patched_create_overlay
        print("✅ Analysis Worker patched to use TrueType fonts exclusively")
        
    except ImportError:
        print("⚠️ Could not patch analysis_worker - module not found")
    except Exception as e:
        print(f"❌ Failed to patch analysis worker: {e}")

# Apply patches when module is imported
patch_overlay_renderer()
patch_analysis_worker()
