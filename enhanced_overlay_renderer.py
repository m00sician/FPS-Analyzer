"""
Enhanced Overlay Renderer - FREETYPE/PILLOW INTEGRATION UPDATE
🚀 MASSIVE UPGRADE: Updates existing enhanced_overlay_renderer.py with TrueType support

INSTRUCTIONS: Replace the existing enhanced_overlay_renderer.py with this code

🎨 NEW Features:
- ✨ TrueType Font Rendering with Anti-Aliasing via Pillow & FreeType
- 🔄 Smart Fallback to OpenCV Fonts  
- 🎯 Enhanced Text Quality & Smoothness
- 📱 Unicode Support
- ⚡ Performance Optimized
- 🔄 100% Backward Compatibility
- 🎨 Integration with existing Layout Manager
"""

import cv2
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Optional, Union, Any

# Import color converter if available
try:
    from color_manager import hex_to_bgr
except ImportError:
    # Fallback color conversion
    def hex_to_bgr(hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to BGR"""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (b, g, r)

# ===============================================
# 🔧 FREETYPE/PILLOW INTEGRATION
# ===============================================

# Import the enhanced font system
try:
    from font_manager import (
        OpenCVFontSettings as EnhancedFontSettings, 
        FREETYPE_AVAILABLE, PILLOW_AVAILABLE,
        check_freetype_support, get_font_manager
    )
    ENHANCED_FONTS_AVAILABLE = True
    print("✅ Enhanced Font System integrated - TrueType support available!")
except ImportError as e:
    print(f"⚠️ Enhanced Font System not available: {e}")
    ENHANCED_FONTS_AVAILABLE = False
    FREETYPE_AVAILABLE = False
    PILLOW_AVAILABLE = False
    
    # Ultimate fallback - FIXED: Added proper render_text method
    class EnhancedFontSettings:
        def __init__(self, font_name='HERSHEY_SIMPLEX', size=24, thickness=2, bold=False, **kwargs):
            self.font_name = font_name
            self.size = size
            self.thickness = thickness
            self.bold = bold
            self.border_thickness = kwargs.get('border_thickness', 2)
            self.text_color = kwargs.get('text_color', (255, 255, 255))
            self.border_color = kwargs.get('border_color', (0, 0, 0))
        
        def get_opencv_font(self):
            import cv2
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
            return font_mapping.get(self.font_name, cv2.FONT_HERSHEY_SIMPLEX)
        
        def get_effective_thickness(self):
            return self.thickness + (1 if self.bold else 0)
            
        # FIXED: Added proper render_text method
        def render_text(self, img, text, position, scale_factor=1.0):
            """Fallback text rendering with OpenCV"""
            import cv2
            result = img.copy()
            x, y = position
            
            # Calculate proper scale
            font_scale = (self.size / 24.0) * scale_factor
            thickness = max(1, int(self.get_effective_thickness() * scale_factor))
            
            # Render border if needed
            if self.border_thickness > 0:
                border_thickness = max(1, int(self.border_thickness * scale_factor))
                for dx in range(-border_thickness, border_thickness + 1):
                    for dy in range(-border_thickness, border_thickness + 1):
                        if dx != 0 or dy != 0:
                            cv2.putText(result, text, (x + dx, y + dy), 
                                      self.get_opencv_font(), font_scale, 
                                      self.border_color, thickness + 1, cv2.LINE_AA)
            
            # Render main text
            cv2.putText(result, text, (x, y), self.get_opencv_font(),
                       font_scale, self.text_color, thickness, cv2.LINE_AA)
            return result
        
        def get_text_size(self, text, scale_factor=1.0):
            """Get text dimensions with OpenCV"""
            import cv2
            font_scale = (self.size / 24.0) * scale_factor
            thickness = max(1, int(self.get_effective_thickness() * scale_factor))
            size = cv2.getTextSize(text, self.get_opencv_font(), font_scale, thickness)
            return size[0]
        
        def is_freetype_available(self):
            return False

# ===============================================
# 🎨 ENHANCED OVERLAY ELEMENTS
# ===============================================

class OverlayElement(ABC):
    """Enhanced base class for all overlay elements with TrueType support"""
    
    def __init__(self, element_id, default_config=None):
        self.element_id = element_id
        self.config = default_config or {}
        self.visible = True
        self.position = (0, 0)
        self.size = (100, 50)
        self.scale_factor = 1.0
        self.resolution_scale = 1.0
        
        # Enhanced properties
        self.text_quality = 'high'  # 'high', 'medium', 'low'
        self.anti_aliasing = True
        self.use_truetype = ENHANCED_FONTS_AVAILABLE and (FREETYPE_AVAILABLE or PILLOW_AVAILABLE)
    
    def update_config(self, layout_config, scale_factor=1.0, resolution_scale=1.0):
        """Enhanced update element configuration with TrueType support"""
        if self.element_id in layout_config:
            element_config = layout_config[self.element_id]
            
            # Apply combined scaling
            combined_scale = scale_factor * resolution_scale
            
            self.position = (
                int(element_config.get('x', 0) * combined_scale),
                int(element_config.get('y', 0) * combined_scale)
            )
            self.size = (
                int(element_config.get('width', 100) * combined_scale),
                int(element_config.get('height', 50) * combined_scale)
            )
            self.visible = element_config.get('visible', True)
            self.scale_factor = scale_factor
            self.resolution_scale = resolution_scale
            
            # Enhanced properties
            self.text_quality = element_config.get('text_quality', 'high')
            self.anti_aliasing = element_config.get('anti_aliasing', True)
            
            #print(f"🎯 {self.element_id}: pos{self.position} size{self.size} scale{combined_scale:.2f} "
                  #f"quality:{self.text_quality} truetype:{self.use_truetype}")
    
    @abstractmethod
    def render(self, overlay, data, font_settings, color_settings):
        """Render this element onto the overlay"""
        pass
    
    def draw_text_with_border(self, img, text, position, font, font_scale, color, thickness, 
                             border_color=(0, 0, 0), border_thickness=2):
        """Enhanced text rendering with TrueType support - FIXED"""
        try:
            # Check if we have enhanced font settings
            if hasattr(font, 'render_text'):
                # Use enhanced font rendering
                effective_scale = self.scale_factor * self.resolution_scale * font_scale
                
                # Set text color for enhanced rendering
                font.text_color = color
                if border_thickness > 0:
                    font.border_color = border_color
                    font.border_thickness = border_thickness
                
                # IMPORTANT: render_text returns the modified image
                result = font.render_text(img, text, position, effective_scale)
                return result
            else:
                # Fallback to legacy rendering
                return self._legacy_text_rendering(img, text, position, font, font_scale, 
                                                 color, thickness, border_color, border_thickness)
        except Exception as e:
            print(f"❌ Enhanced text rendering failed: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to legacy rendering
            return self._legacy_text_rendering(img, text, position, font, font_scale, 
                                             color, thickness, border_color, border_thickness)
    
    def _legacy_text_rendering(self, img, text, position, font, font_scale, color, thickness, 
                              border_color, border_thickness):
        """Legacy text rendering fallback"""
        x, y = position
        line_type = cv2.LINE_AA if self.anti_aliasing else cv2.LINE_8
        
        # Render border
        if border_thickness > 0:
            for offset in range(border_thickness, 0, -1):
                for dx in range(-offset, offset + 1):
                    for dy in range(-offset, offset + 1):
                        if dx != 0 or dy != 0:
                            cv2.putText(img, text, (x + dx, y + dy), font, font_scale,
                                       border_color, thickness + offset, lineType=line_type)
        
        # Render main text
        cv2.putText(img, text, position, font, font_scale, color, thickness, lineType=line_type)
        return img

class FPSNumberElement(OverlayElement):
    """Enhanced FPS number display with TrueType support"""
    
    def __init__(self):
        super().__init__('fps_display', {
            'font_scale_multiplier': 1.0,
            'show_label': True,
            'color_coding': True,
            'glow_effect': False
        })
    
    def render(self, overlay, data, font_settings, color_settings):
        if not self.visible:
            return overlay
        
        current_fps = data.get('current_fps', 0.0)
        fps_font_settings = font_settings.get('fps_font')
        
        # Enhanced scaling
        effective_scale = self.scale_factor * self.resolution_scale
        scale_multiplier = self.config.get('font_scale_multiplier', 1.0)
        final_scale = effective_scale * scale_multiplier
        
        # Enhanced color coding
        if self.config.get('color_coding', True):
            if current_fps >= 55:
                fps_color = (0, 255, 0)  # Vibrant green
            elif current_fps >= 30:
                # Smooth gradient from orange to yellow
                factor = (current_fps - 30) / 25
                fps_color = (0, int(200 + 55 * factor), int(255 * factor))
            else:
                # Red with intensity based on how low FPS is
                intensity = max(100, int(255 * (current_fps / 30)))
                fps_color = (0, 50, intensity)
        else:
            fps_color = (255, 255, 255)
        
        # Enhanced FPS number rendering
        fps_text = f"{int(current_fps)}"
        fps_y = self.position[1] + int(self.size[1] * 0.6)
        
        # Use enhanced rendering if available
        if hasattr(fps_font_settings, 'render_text'):
            try:
                # Set text color for enhanced rendering
                fps_font_settings.text_color = fps_color
                # FIXED: Assign result back to overlay
                overlay = fps_font_settings.render_text(overlay, fps_text, (self.position[0], fps_y), final_scale)
            except:
                # Fallback to legacy method
                overlay = self._render_legacy_fps(overlay, fps_text, fps_y, fps_font_settings, fps_color, final_scale)
        else:
            overlay = self._render_legacy_fps(overlay, fps_text, fps_y, fps_font_settings, fps_color, final_scale)
        
        # Enhanced FPS label
        if self.config.get('show_label', True):
            label_scale = final_scale * 0.6
            label_y = fps_y + int(30 * effective_scale)
            
            if hasattr(fps_font_settings, 'render_text'):
                try:
                    fps_font_settings.text_color = (255, 255, 255)
                    # FIXED: Assign result back to overlay
                    overlay = fps_font_settings.render_text(overlay, "FPS", (self.position[0], label_y), label_scale)
                except:
                    overlay = self._render_legacy_label(overlay, fps_font_settings, label_y, label_scale)
            else:
                overlay = self._render_legacy_label(overlay, fps_font_settings, label_y, label_scale)
        
        return overlay
    
    def _render_legacy_fps(self, overlay, fps_text, fps_y, font_settings, color, scale):
        """Legacy FPS rendering"""
        if hasattr(font_settings, 'get_opencv_font'):
            font = font_settings.get_opencv_font()
            font_scale = font_settings.size * scale * 0.04
            thickness = max(1, int(font_settings.get_effective_thickness() * scale))
            border_thickness = max(1, int(getattr(font_settings, 'border_thickness', 2) * scale))
        else:
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 1.5 * scale
            thickness = max(1, int(3 * scale))
            border_thickness = max(1, int(2 * scale))
        
        overlay = self.draw_text_with_border(
            overlay, fps_text, (self.position[0], fps_y),
            font, font_scale, color, thickness,
            border_thickness=border_thickness
        )
        return overlay
    
    def _render_legacy_label(self, overlay, font_settings, label_y, scale):
        """Legacy label rendering"""
        if hasattr(font_settings, 'get_opencv_font'):
            font = font_settings.get_opencv_font()
            font_scale = font_settings.size * scale * 0.02
            thickness = max(1, int(font_settings.get_effective_thickness() * scale))
            border_thickness = max(1, int(getattr(font_settings, 'border_thickness', 2) * scale))
        else:
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.8 * scale
            thickness = max(1, int(2 * scale))
            border_thickness = max(1, int(1 * scale))
        
        overlay = self.draw_text_with_border(
            overlay, "FPS", (self.position[0], label_y),
            font, font_scale, (255, 255, 255), thickness,
            border_thickness=border_thickness
        )
        return overlay

class FrameRateGraphElement(OverlayElement):
    """Enhanced framerate graph with TrueType labels"""
    
    def __init__(self):
        super().__init__('frame_rate_graph', {
            'max_fps': 60,
            'grid_values': [60, 45, 30, 15, 0],
            'label_values': [60, 30, 0],
            'title': 'FRAME RATE',
            'show_title': True,
            'show_grid': True,
            'show_labels': True,
            'show_background': True
        })
    
    def render(self, overlay, data, font_settings, color_settings):
        if not self.visible:
            return overlay
        
        fps_history = data.get('fps_history', [])
        max_len = data.get('max_len', 180)
        
        if len(fps_history) < 2:
            return overlay
        
        # Enhanced font and color settings
        framerate_font_settings = font_settings.get('framerate_font')
        framerate_color = hex_to_bgr(color_settings.get('framerate_color', '#00FF00'))
        
        effective_scale = self.scale_factor * self.resolution_scale
        
        # Enhanced background
        self._draw_enhanced_background(overlay)
        
        # Enhanced title with TrueType
        if self.config.get('show_title', True):
            title = self.config.get('title', 'FRAME RATE')
            title_y = self.position[1] - max(20, int(30 * effective_scale))
            title_scale = effective_scale * 1.3
            
            # Enhanced title rendering
            if hasattr(framerate_font_settings, 'render_text'):
                try:
                    # Title shadow for depth
                    if hasattr(framerate_font_settings, 'clone'):
                        shadow_font = framerate_font_settings.clone()
                    else:
                        shadow_font = framerate_font_settings
                    shadow_font.text_color = (0, 0, 0)
                    overlay = shadow_font.render_text(overlay, title, 
                                          (self.position[0] + 2, title_y + 2), title_scale)
                    
                    # Main title
                    framerate_font_settings.text_color = (255, 255, 255)
                    overlay = framerate_font_settings.render_text(overlay, title, 
                                                      (self.position[0], title_y), title_scale)
                except:
                    overlay = self._render_legacy_title(overlay, title, title_y, framerate_font_settings, title_scale)
            else:
                overlay = self._render_legacy_title(overlay, title, title_y, framerate_font_settings, title_scale)
        
        # Enhanced grid
        max_fps = self.config.get('max_fps', 60)
        grid_values = self.config.get('grid_values', [60, 45, 30, 15, 0])
        self._draw_enhanced_grid(overlay, grid_values, max_fps)
        
        # Enhanced labels
        if self.config.get('show_labels', True):
            overlay = self._draw_enhanced_labels(overlay, grid_values, max_fps, framerate_font_settings, effective_scale)
        
        # Enhanced FPS line
        self._draw_enhanced_fps_line(overlay, fps_history, max_len, max_fps, framerate_color, effective_scale)
        
        return overlay
    
    def _draw_enhanced_background(self, overlay):
        """Enhanced background with gradient"""
        if not self.config.get('show_background', True):
            return
        
        # Create gradient background
        bg_overlay = overlay.copy()
        
        for y in range(self.size[1]):
            alpha = 0.3 - (y / self.size[1]) * 0.1
            intensity = int(20 + y / self.size[1] * 15)
            color = (intensity, intensity, intensity)
            
            cv2.rectangle(bg_overlay,
                         (self.position[0], self.position[1] + y),
                         (self.position[0] + self.size[0], self.position[1] + y + 1),
                         color, -1)
        
        # Blend with original
        cv2.addWeighted(overlay, 0.8, bg_overlay, 0.2, 0, overlay)
        
        # Enhanced border
        border_color = (100, 100, 100)
        border_width = max(2, int(3 * self.resolution_scale))
        cv2.rectangle(overlay,
                     (self.position[0] - 5, self.position[1] - 5),
                     (self.position[0] + self.size[0] + 5, self.position[1] + self.size[1] + 5),
                     border_color, border_width)
    
    def _draw_enhanced_grid(self, overlay, grid_values, max_value):
        """Enhanced grid with better styling"""
        if not self.config.get('show_grid', True):
            return
        
        effective_scale = self.scale_factor * self.resolution_scale
        
        for i, value in enumerate(grid_values):
            y_pos = self.position[1] + self.size[1] - int((value / max_value) * self.size[1])
            
            # Enhanced line styling
            if value == max_value or value == 0:
                color = (80, 80, 80)
                thickness = max(2, int(2 * effective_scale))
            elif value == max_value // 2:
                color = (70, 70, 70)
                thickness = max(1, int(1.5 * effective_scale))
            else:
                color = (50, 50, 50)
                thickness = max(1, int(1 * effective_scale))
            
            cv2.line(overlay,
                    (self.position[0], y_pos),
                    (self.position[0] + self.size[0], y_pos),
                    color, thickness, cv2.LINE_AA)
    
    def _draw_enhanced_labels(self, overlay, grid_values, max_fps, font_settings, effective_scale):
        """Enhanced labels with TrueType"""
        if not self.config.get('show_labels', True):
            print("❌ show_labels is False!")
            return overlay
        
        label_values = self.config.get('label_values', [60, 30, 0])
        label_scale = effective_scale * 0.8
        
        print(f"🔍 FRAME RATE LABELS DEBUG:")
        print(f"   - label_values: {label_values}")
        print(f"   - grid_values: {grid_values}")
        print(f"   - Graph position: {self.position}")
        print(f"   - Graph size: {self.size}")
        print(f"   - Overlay shape: {overlay.shape}")
        
        for fps_val in label_values:
            if fps_val in grid_values:
                y_pos = self.position[1] + self.size[1] - int((fps_val / max_fps) * self.size[1])
                label_x = self.position[0] + self.size[0] + 15  # War + max(5, int(5 * effective_scale))
                y_pos = y_pos - 8  # 8 Pixel nach oben
                
                label_text = f"{int(fps_val)}"
                
                print(f"   📍 Label '{label_text}' at x:{label_x}, y:{y_pos}")
                
                # Prüfe ob Position innerhalb des Bildes ist
                if label_x >= overlay.shape[1] - 50:
                    print(f"   ⚠️ Label x-position {label_x} is near or outside image width {overlay.shape[1]}")
                
                # Enhanced label rendering
                if hasattr(font_settings, 'render_text'):
                    try:
                        font_settings.text_color = (255, 255, 255)
                        font_settings.border_color = (0, 0, 0)
                        font_settings.border_thickness = 2
                        
                        overlay = font_settings.render_text(overlay, label_text, (label_x, y_pos), label_scale)
                        print(f"   ✅ render_text called successfully for '{label_text}'")
                    except Exception as e:
                        print(f"   ❌ render_text failed: {e}")
                        import traceback
                        traceback.print_exc()
                        overlay = self._render_legacy_label(overlay, label_text, label_x, y_pos, font_settings, label_scale)
                else:
                    print(f"   ⚠️ Using legacy label rendering")
                    overlay = self._render_legacy_label(overlay, label_text, label_x, y_pos, font_settings, label_scale)
            else:
                print(f"   ⚠️ fps_val {fps_val} not in grid_values")
        
        return overlay
    
    def _draw_enhanced_fps_line(self, overlay, fps_history, max_len, max_fps, color, effective_scale):
        """Enhanced FPS line with adaptive quality"""
        hist = fps_history[-max_len:] if len(fps_history) > max_len else fps_history
        if len(hist) < 2:
            return
        
        # Generate points
        fps_points = []
        for i, fps_val in enumerate(hist):
            progress = i / (max_len - 1) if max_len > 1 else 0
            x = self.position[0] + int(self.size[0] * progress)
            y = self.position[1] + self.size[1] - int((min(fps_val, max_fps) / max_fps) * self.size[1])
            fps_points.append((x, y))
        
        # Enhanced line rendering
        line_thickness = max(2, int(4 * effective_scale))
        
        for i in range(len(fps_points) - 1):
            cv2.line(overlay, fps_points[i], fps_points[i + 1], color, 
                    line_thickness, cv2.LINE_AA)
    
    def _render_legacy_title(self, overlay, title, title_y, font_settings, scale):
        """Legacy title rendering"""
        if hasattr(font_settings, 'get_opencv_font'):
            font = font_settings.get_opencv_font()
            font_scale = font_settings.size * scale * 0.03
            thickness = max(1, int(font_settings.get_effective_thickness() * scale))
        else:
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 1.2 * scale
            thickness = max(1, int(2 * scale))
        
        overlay = self.draw_text_with_border(overlay, title, (self.position[0], title_y),
                                  font, font_scale, (255, 255, 255), thickness)
        return overlay
    
    def _render_legacy_label(self, overlay, label_text, label_x, y_pos, font_settings, scale):
        """Legacy label rendering"""
        if hasattr(font_settings, 'get_opencv_font'):
            font = font_settings.get_opencv_font()
            font_scale = font_settings.size * scale * 0.02
            thickness = max(1, int(font_settings.get_effective_thickness() * scale))
        else:
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6 * scale
            thickness = max(1, int(1 * scale))
        
        # Zeichne weißen Text mit schwarzem Rand
        overlay = self.draw_text_with_border(overlay, label_text, (label_x, y_pos),
                                font, font_scale, (255, 255, 255), thickness,
                                border_color=(0, 0, 0), border_thickness=2)
        return overlay

class FrameTimeGraphElement(OverlayElement):
    """Enhanced frametime graph with TrueType support"""
    
    def __init__(self):
        super().__init__('frame_time_graph', {
            'title': 'FRAME TIME',
            'show_title': True,
            'show_grid': True,
            'show_labels': True,
            'show_background': True
        })
    
    def render(self, overlay, data, font_settings, color_settings):
        if not self.visible:
            return overlay
        
        frame_times = data.get('frame_times', [])
        frametime_scale = data.get('frametime_scale', {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']})
        max_len = data.get('max_len', 180)
        
        if len(frame_times) < 2:
            return overlay
        
        # Enhanced font and color settings
        frametime_font_settings = font_settings.get('frametime_font')
        frametime_color = hex_to_bgr(color_settings.get('frametime_color', '#00FF00'))
        
        effective_scale = self.scale_factor * self.resolution_scale
        
        # Enhanced background
        self._draw_enhanced_background(overlay)
        
        # Enhanced title
        if self.config.get('show_title', True):
            title = self.config.get('title', 'FRAME TIME')
            title_y = self.position[1] - max(20, int(30 * effective_scale))
            title_scale = effective_scale * 1.2
            
            if hasattr(frametime_font_settings, 'render_text'):
                try:
                    frametime_font_settings.text_color = (255, 255, 255)
                    overlay = frametime_font_settings.render_text(overlay, title, (self.position[0], title_y), title_scale)
                except:
                    overlay = self._render_legacy_title(overlay, title, title_y, frametime_font_settings, title_scale)
            else:
                overlay = self._render_legacy_title(overlay, title, title_y, frametime_font_settings, title_scale)
        
        # Scale settings
        ft_min = frametime_scale['min']
        ft_mid = frametime_scale['mid']
        ft_max = frametime_scale['max']
        ft_labels = frametime_scale['labels']
        
        # Enhanced grid and labels
        self._draw_enhanced_frametime_grid(overlay, ft_min, ft_mid, ft_max, effective_scale)
        
        if self.config.get('show_labels', True):
            overlay = self._draw_enhanced_frametime_labels(overlay, ft_labels, ft_min, ft_max, 
                                               frametime_font_settings, effective_scale)
        
        # Enhanced frametime line
        self._draw_enhanced_frametime_line(overlay, frame_times, max_len, ft_min, ft_max, 
                                         frametime_color, effective_scale)
        
        return overlay
    
    def _draw_enhanced_background(self, overlay):
        """Enhanced background for frametime graph"""
        if not self.config.get('show_background', True):
            return
        
        # Similar to framerate graph but with different accent
        bg_overlay = overlay.copy()
        
        for y in range(self.size[1]):
            intensity = int(15 + y / self.size[1] * 10)
            color = (intensity + 5, intensity, intensity)  # Slight blue tint
            
            cv2.rectangle(bg_overlay,
                         (self.position[0], self.position[1] + y),
                         (self.position[0] + self.size[0], self.position[1] + y + 1),
                         color, -1)
        
        cv2.addWeighted(overlay, 0.85, bg_overlay, 0.15, 0, overlay)
        
        # Border
        border_color = (80, 80, 120)
        border_width = max(1, int(2 * self.resolution_scale))
        cv2.rectangle(overlay,
                     (self.position[0] - 3, self.position[1] - 3),
                     (self.position[0] + self.size[0] + 3, self.position[1] + self.size[1] + 3),
                     border_color, border_width)
    
    def _draw_enhanced_frametime_grid(self, overlay, ft_min, ft_mid, ft_max, effective_scale):
        """Enhanced frametime grid"""
        if not self.config.get('show_grid', True):
            return
        
        grid_values = [ft_min, ft_mid, ft_max]
        
        for ft_val in grid_values:
            y_pos = self.position[1] + self.size[1] - int(((ft_val - ft_min) / (ft_max - ft_min)) * self.size[1])
            
            # Special styling for target frametime (16.67ms = 60fps)
            if abs(ft_val - 16.67) < 1.0:
                color = (0, 150, 255)  # Blue for 60fps target
                thickness = max(2, int(2 * effective_scale))
            elif ft_val == ft_mid:
                color = (100, 100, 100)
                thickness = max(1, int(1.5 * effective_scale))
            else:
                color = (60, 60, 60)
                thickness = max(1, int(1 * effective_scale))
            
            cv2.line(overlay,
                    (self.position[0], y_pos),
                    (self.position[0] + self.size[0], y_pos),
                    color, thickness, cv2.LINE_AA)
    
    def _draw_enhanced_frametime_labels(self, overlay, labels, ft_min, ft_max, font_settings, effective_scale):
        """Enhanced frametime labels with precision"""
        if not self.config.get('show_labels', True):
            return overlay
        
        label_scale = effective_scale * 0.7
        
        for label in labels:
            try:
                ft_val = float(label)
                y_pos = self.position[1] + self.size[1] - int(((ft_val - ft_min) / (ft_max - ft_min)) * self.size[1])
                label_x = self.position[0] + self.size[0] + 10  # War + max(5, int(8 * effective_scale))
                y_pos = y_pos - 10  # 20 Pixel nach oben
                
                label_text = f"{label}ms"
                
                if hasattr(font_settings, 'render_text'):
                    try:
                        font_settings.text_color = (255, 255, 255)
                        overlay = font_settings.render_text(overlay, label_text, (label_x, y_pos + 5), label_scale)
                    except:
                        overlay = self._render_legacy_label(overlay, label_text, label_x, y_pos, font_settings, label_scale)
                else:
                    overlay = self._render_legacy_label(overlay, label_text, label_x, y_pos, font_settings, label_scale)
            except ValueError:
                continue
        
        return overlay
    
    def _draw_enhanced_frametime_line(self, overlay, frame_times, max_len, ft_min, ft_max, color, effective_scale):
        """Enhanced frametime line with quality indicators"""
        ft_hist = frame_times[-max_len:] if len(frame_times) > max_len else frame_times
        if len(ft_hist) < 2:
            return
        
        # Generate points
        ft_points = []
        for i, ft_val in enumerate(ft_hist):
            progress = i / (len(ft_hist) - 1) if len(ft_hist) > 1 else 0
            x = self.position[0] + int(self.size[0] * progress)
            clamped_ft = min(max(ft_val, ft_min), ft_max)
            y = self.position[1] + self.size[1] - int(((clamped_ft - ft_min) / (ft_max - ft_min)) * self.size[1])
            ft_points.append((x, y))
        
        # Enhanced line rendering
        line_thickness = max(2, int(3 * effective_scale))
        
        for i in range(len(ft_points) - 1):
            cv2.line(overlay, ft_points[i], ft_points[i + 1], color,
                    line_thickness, cv2.LINE_AA)
    
    def _render_legacy_title(self, overlay, title, title_y, font_settings, scale):
        """Legacy title rendering"""
        if hasattr(font_settings, 'get_opencv_font'):
            font = font_settings.get_opencv_font()
            font_scale = font_settings.size * scale * 0.025
            thickness = max(1, int(font_settings.get_effective_thickness() * scale))
        else:
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 1.0 * scale
            thickness = max(1, int(2 * scale))
        
        overlay = self.draw_text_with_border(overlay, title, (self.position[0], title_y),
                                  font, font_scale, (255, 255, 255), thickness)
        return overlay
    
    def _render_legacy_label(self, overlay, label_text, label_x, y_pos, font_settings, scale):
        """Legacy label rendering"""
        if hasattr(font_settings, 'get_opencv_font'):
            font = font_settings.get_opencv_font()
            font_scale = font_settings.size * scale * 0.015
            thickness = max(1, int(font_settings.get_effective_thickness() * scale))
        else:
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5 * scale
            thickness = max(1, int(1 * scale))
        
        overlay = self.draw_text_with_border(overlay, label_text, (label_x, y_pos + 5),
                                  font, font_scale, (255, 255, 255), thickness)
        return overlay

class FPSStatisticsElement(OverlayElement):
    """Enhanced FPS statistics with TrueType rendering"""
    
    def __init__(self):
        super().__init__('fps_statistics', {
            'show_avg': True,
            'show_min': True,
            'show_max': True,
            'stats_spacing': 80,
            'layout': 'horizontal',
            'precision': 1
        })
    
    def render(self, overlay, data, font_settings, color_settings):
        if not self.visible:
            return overlay
        
        fps_history = data.get('fps_history', [])
        global_fps_values = data.get('global_fps_values', [])
        
        if len(fps_history) == 0:
            return overlay
        
        # Enhanced font settings
        framerate_font_settings = font_settings.get('framerate_font')
        effective_scale = self.scale_factor * self.resolution_scale
        
        # Calculate statistics
        if global_fps_values and len(global_fps_values) > 0:
            avg_fps = sum(global_fps_values) / len(global_fps_values)
            min_fps = min(global_fps_values)
            max_fps = max(global_fps_values)
        else:
            recent_fps = fps_history[-60:] if len(fps_history) >= 60 else fps_history
            avg_fps = sum(recent_fps) / len(recent_fps)
            min_fps = min(recent_fps)
            max_fps = max(recent_fps)
        
        # Enhanced rendering
        overlay = self._render_enhanced_stats(overlay, avg_fps, min_fps, max_fps, framerate_font_settings, effective_scale)
        return overlay
    
    def _render_enhanced_stats(self, overlay, avg_fps, min_fps, max_fps, font_settings, effective_scale):
        """Render enhanced FPS statistics"""
        spacing = int(self.config.get('stats_spacing', 80) * effective_scale)
        precision = self.config.get('precision', 1)
        text_scale = effective_scale * 0.8
        
        x_offset = 0
        
        if self.config.get('show_avg', True):
            avg_text = f"AVG: {avg_fps:.{precision}f}"
            overlay = self._render_stat_text(overlay, avg_text, x_offset, font_settings, (255, 255, 255), text_scale)
            x_offset += spacing
        
        if self.config.get('show_min', True):
            min_text = f"MIN: {min_fps:.{precision}f}"
            # Color coding for min FPS
            min_color = (0, 255, 0) if min_fps >= 55 else (0, 200, 255) if min_fps >= 30 else (0, 100, 255)
            overlay = self._render_stat_text(overlay, min_text, x_offset, font_settings, min_color, text_scale)
            x_offset += spacing
        
        if self.config.get('show_max', True):
            max_text = f"MAX: {max_fps:.{precision}f}"
            overlay = self._render_stat_text(overlay, max_text, x_offset, font_settings, (255, 255, 255), text_scale)
        
        return overlay
    
    def _render_stat_text(self, overlay, text, x_offset, font_settings, color, scale):
        """Render individual statistic text"""
        if hasattr(font_settings, 'render_text'):
            try:
                font_settings.text_color = color
                overlay = font_settings.render_text(overlay, text, (self.position[0] + x_offset, self.position[1]), scale)
            except:
                overlay = self._render_legacy_stat(overlay, text, x_offset, font_settings, color, scale)
        else:
            overlay = self._render_legacy_stat(overlay, text, x_offset, font_settings, color, scale)
        return overlay
    
    def _render_legacy_stat(self, overlay, text, x_offset, font_settings, color, scale):
        """Legacy statistic rendering"""
        if hasattr(font_settings, 'get_opencv_font'):
            font = font_settings.get_opencv_font()
            font_scale = font_settings.size * scale * 0.02
            thickness = max(1, int(font_settings.get_effective_thickness() * scale))
        else:
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6 * scale
            thickness = max(1, int(1 * scale))
        
        overlay = self.draw_text_with_border(overlay, text, (self.position[0] + x_offset, self.position[1]),
                                  font, font_scale, color, thickness)
        return overlay

class FrameTimeStatisticsElement(OverlayElement):
    """Enhanced frametime statistics with TrueType rendering"""
    
    def __init__(self):
        super().__init__('frametime_statistics', {
            'show_avg': True,
            'show_max': True,
            'show_fps_equivalent': False,
            'stats_spacing': 50,
            'layout': 'horizontal',
            'precision': 1
        })
    
    def render(self, overlay, data, font_settings, color_settings):
        if not self.visible:
            return overlay
        
        frame_times = data.get('frame_times', [])
        global_frame_times = data.get('global_frame_times', [])
        
        if len(frame_times) == 0:
            return overlay
        
        # Enhanced font settings
        frametime_font_settings = font_settings.get('frametime_font')
        effective_scale = self.scale_factor * self.resolution_scale
        
        # Calculate statistics
        if global_frame_times and len(global_frame_times) > 0:
            ft_avg = sum(global_frame_times) / len(global_frame_times)
            ft_max = max(global_frame_times)
        else:
            recent_ft = frame_times[-60:] if len(frame_times) >= 60 else frame_times
            ft_avg = sum(recent_ft) / len(recent_ft)
            ft_max = max(recent_ft)
        
        # Enhanced rendering
        overlay = self._render_enhanced_frametime_stats(overlay, ft_avg, ft_max, frametime_font_settings, effective_scale)
        return overlay
    
    def _render_enhanced_frametime_stats(self, overlay, ft_avg, ft_max, font_settings, effective_scale):
        """Render enhanced frametime statistics"""
        spacing = int(100 * effective_scale)  # War 100, jetzt 120 für mehr Platz
        precision = self.config.get('precision', 1)
        text_scale = effective_scale * 0.8
        
        x_offset = 0
        
        if self.config.get('show_avg', True):
            avg_text = f"AVG: {ft_avg:.{precision}f}ms"
            if self.config.get('show_fps_equivalent', True):
                avg_fps = 1000 / ft_avg if ft_avg > 0 else 0
                avg_text += f" ({avg_fps:.0f}fps)"
            
            overlay = self._render_stat_text(overlay, avg_text, x_offset, font_settings, (255, 255, 255), text_scale)
            x_offset += spacing + 20  # Zusätzliche 20 Pixel Abstand
        
        if self.config.get('show_max', True):
            max_text = f"MAX: {ft_max:.{precision}f}ms"
            if self.config.get('show_fps_equivalent', True):
                max_fps = 1000 / ft_max if ft_max > 0 else 0
                max_text += f" ({max_fps:.0f}fps)"
            
            # Color coding for max frametime
            max_color = (0, 255, 0) if ft_max <= 20 else (0, 200, 255) if ft_max <= 35 else (0, 100, 255)
            
            overlay = self._render_stat_text(overlay, max_text, x_offset, font_settings, max_color, text_scale)
        
        return overlay
    
    def _render_stat_text(self, overlay, text, x_offset, font_settings, color, scale):
        """Render individual statistic text"""
        if hasattr(font_settings, 'render_text'):
            try:
                font_settings.text_color = color
                overlay = font_settings.render_text(overlay, text, (self.position[0] + x_offset, self.position[1]), scale)
            except:
                overlay = self._render_legacy_stat(overlay, text, x_offset, font_settings, color, scale)
        else:
            overlay = self._render_legacy_stat(overlay, text, x_offset, font_settings, color, scale)
        return overlay
    
    def _render_legacy_stat(self, overlay, text, x_offset, font_settings, color, scale):
        """Legacy statistic rendering"""
        if hasattr(font_settings, 'get_opencv_font'):
            font = font_settings.get_opencv_font()
            font_scale = font_settings.size * scale * 0.015
            thickness = max(1, int(font_settings.get_effective_thickness() * scale))
        else:
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5 * scale
            thickness = max(1, int(1 * scale))
        
        overlay = self.draw_text_with_border(overlay, text, (self.position[0] + x_offset, self.position[1]),
                                  font, font_scale, color, thickness)
        return overlay

# ===============================================
# 🚀 ENHANCED OVERLAY RENDERER WITH TRUETYPE
# ===============================================

class EnhancedOverlayRenderer:
    """Enhanced overlay renderer with TrueType support and improved quality"""
    
    def __init__(self):
        self.elements = {
            'fps_display': FPSNumberElement(),
            'frame_rate_graph': FrameRateGraphElement(),
            'frame_time_graph': FrameTimeGraphElement(),
            'fps_statistics': FPSStatisticsElement(),
            'frametime_statistics': FrameTimeStatisticsElement()
        }
        
        # Enhanced quality settings
        self.rendering_quality = 'high'  # 'high', 'medium', 'low'
        self.use_anti_aliasing = True
        self.use_truetype = ENHANCED_FONTS_AVAILABLE and (FREETYPE_AVAILABLE or PILLOW_AVAILABLE)
        
        print(f"🚀 Enhanced Overlay Renderer initialized!")
        if PILLOW_AVAILABLE:
            print(f"   • TrueType Support: ✅ Pillow available")
        elif FREETYPE_AVAILABLE:
            print(f"   • TrueType Support: ✅ OpenCV FreeType available")
        else:
            print(f"   • TrueType Support: ❌ Not available (Standard OpenCV)")
        print(f"   • Enhanced Fonts: {'✅ Available' if ENHANCED_FONTS_AVAILABLE else '❌ Fallback Mode'}")
    
    def get_resolution_scale_factor(self, width, height):
        """Calculate resolution scale factor with enhanced precision - UPDATED"""
        base_width, base_height = 1920, 1080
        scale_x = width / base_width
        scale_y = height / base_height
        scale_factor = min(scale_x, scale_y)
        
        # Enhanced scaling with quality preservation
        if self.rendering_quality == 'high':
            scale_factor = min(2.0, max(0.3, scale_factor))
        else:
            scale_factor = min(1.5, max(0.5, scale_factor))
        
        print(f"🎯 ENHANCED RESOLUTION SCALING: {width}x{height} -> scale: {scale_factor:.3f}")
        return scale_factor
    
    def render_overlay(self, frame, fps_history, current_fps, frame_times=None,
                      show_frame_time_graph=True, max_len=180, global_fps_values=None,
                      global_frame_times=None, frametime_scale=None, font_settings=None,
                      color_settings=None, layout_config=None):
        """
        Enhanced render function with TrueType support - UPDATED for integration
        """
        h, w, _ = frame.shape
        overlay = frame.copy()
        
        # Enhanced scaling calculations
        layout_scale_factor = min(w / 1920, h / 1080)
        resolution_scale_factor = self.get_resolution_scale_factor(w, h)
        
        # Quality-based adjustments
        if self.rendering_quality == 'high':
            layout_scale_factor = max(0.4, min(layout_scale_factor, 2.5))
        else:
            layout_scale_factor = max(0.5, min(layout_scale_factor, 2.0))
        
        print(f"🎯 ENHANCED OVERLAY SCALING: Layout={layout_scale_factor:.3f}, Resolution={resolution_scale_factor:.3f}")
        
        # Update elements with enhanced configuration
        if layout_config:
            for element in self.elements.values():
                element.update_config(layout_config, layout_scale_factor, resolution_scale_factor)
                element.text_quality = self.rendering_quality
                element.anti_aliasing = self.use_anti_aliasing
                element.use_truetype = self.use_truetype
        else:
            self._apply_enhanced_default_layout(w, h, layout_scale_factor, resolution_scale_factor)
        
        # Enhanced font settings conversion
        enhanced_font_settings = self._convert_to_enhanced_fonts(font_settings)
        
        # Prepare enhanced data
        data = {
            'current_fps': current_fps,
            'fps_history': fps_history,
            'frame_times': frame_times if show_frame_time_graph else None,
            'max_len': max_len,
            'global_fps_values': global_fps_values,
            'global_frame_times': global_frame_times,
            'frametime_scale': frametime_scale or {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']}
        }
        
        # Default color settings
        if color_settings is None:
            color_settings = {'framerate_color': '#00FF00', 'frametime_color': '#00FF00'}
        
        # Render all elements with enhanced quality
        for element_id, element in self.elements.items():
            try:
                overlay = element.render(overlay, data, enhanced_font_settings, color_settings)
            except Exception as e:
                print(f"❌ Error rendering {element_id}: {e}")
                # Continue with other elements
        
        return overlay
    
    def _convert_to_enhanced_fonts(self, font_settings):
        """Convert legacy font settings to enhanced font settings"""
        if not font_settings:
            return self._get_default_enhanced_fonts()
        
        enhanced_settings = {}
        
        # Corrected conversion logic
        for font_type, settings in font_settings.items():
            if isinstance(settings, EnhancedFontSettings):
                # Already enhanced
                enhanced_settings[font_type] = settings
            else:
                # Convert legacy settings
                try:
                    enhanced_settings[font_type] = EnhancedFontSettings(
                        font_name=getattr(settings, 'font_name', 'HERSHEY_SIMPLEX'),
                        size=getattr(settings, 'size', 24),
                        thickness=getattr(settings, 'thickness', 2),
                        bold=getattr(settings, 'bold', False),
                        border_thickness=getattr(settings, 'border_thickness', 2),
                        text_color=getattr(settings, 'text_color', (255, 255, 255)),
                        border_color=getattr(settings, 'border_color', (0, 0, 0))
                    )
                    print(f"   ✅ {font_type} successfully converted to EnhancedFontSettings")
                except Exception as e:
                    print(f"⚠️ Font conversion failed for {font_type}: {e}")
                    enhanced_settings[font_type] = self._get_fallback_font()
        
        return enhanced_settings
    
    def _get_default_enhanced_fonts(self):
        """Get default enhanced font settings"""
        return {
            'fps_font': EnhancedFontSettings('HERSHEY_SIMPLEX', 32, 3, True, border_thickness=3),
            'framerate_font': EnhancedFontSettings('HERSHEY_SIMPLEX', 16, 2, False, border_thickness=2),
            'frametime_font': EnhancedFontSettings('HERSHEY_SIMPLEX', 14, 1, False, border_thickness=1)
        }
    
    def _get_fallback_font(self):
        """Get fallback font settings"""
        return EnhancedFontSettings('HERSHEY_SIMPLEX', 16, 2, False)
    
    def _apply_enhanced_default_layout(self, width, height, layout_scale_factor, resolution_scale_factor):
        """Apply enhanced default layout with better proportions - UPDATED"""
        combined_scale = layout_scale_factor * resolution_scale_factor
        
        # Enhanced positioning with better proportions
        margin = max(30, int(50 * combined_scale))
        
        # FPS Display - top left with better sizing
        self.elements['fps_display'].position = (margin, margin)
        self.elements['fps_display'].size = (int(120 * combined_scale), int(80 * combined_scale))
        
        # Frame Rate Graph - larger and better positioned
        graph_width = int(1200 * combined_scale)
        graph_height = int(250 * combined_scale)
        self.elements['frame_rate_graph'].position = (margin, height - graph_height - margin)
        self.elements['frame_rate_graph'].size = (graph_width, graph_height)
        
        # Frame Time Graph - enhanced proportions
        ft_width = int(450 * combined_scale)
        ft_height = int(180 * combined_scale)
        self.elements['frame_time_graph'].position = (width - ft_width - margin, height - ft_height - margin)
        self.elements['frame_time_graph'].size = (ft_width, ft_height)
        
        # Enhanced statistics positioning
        stats_y_offset = int(40 * combined_scale)
        
        # FPS Statistics - below frame rate graph
        fps_stats_y = height - margin + stats_y_offset
        self.elements['fps_statistics'].position = (margin, fps_stats_y)
        self.elements['fps_statistics'].size = (int(350 * combined_scale), int(25 * combined_scale))
        
        # Frame Time Statistics - below frame time graph
        ft_stats_y = height - margin + stats_y_offset
        self.elements['frametime_statistics'].position = (width - int(280 * combined_scale) - margin, ft_stats_y)
        self.elements['frametime_statistics'].size = (int(280 * combined_scale), int(25 * combined_scale))
        
        # Update element properties
        for element in self.elements.values():
            element.scale_factor = layout_scale_factor
            element.resolution_scale = resolution_scale_factor
            element.text_quality = self.rendering_quality
            element.anti_aliasing = self.use_anti_aliasing
            element.use_truetype = self.use_truetype
        
        print(f"✅ ENHANCED DEFAULT LAYOUT: Applied with combined scale {combined_scale:.3f}")

# ===============================================
# 🔄 BACKWARD COMPATIBILITY WRAPPERS
# ===============================================

def draw_fps_overlay_with_layout(frame, fps_history, current_fps, frame_times=None,
                                show_frame_time_graph=True, max_len=180, global_fps_values=None,
                                global_frame_times=None, frametime_scale=None, font_settings=None,
                                color_settings=None, layout_config=None):
    """Enhanced compatibility wrapper with TrueType support - UPDATED"""
    renderer = EnhancedOverlayRenderer()
    return renderer.render_overlay(
        frame, fps_history, current_fps, frame_times, show_frame_time_graph,
        max_len, global_fps_values, global_frame_times, frametime_scale,
        font_settings, color_settings, layout_config
    )

def draw_fps_overlay_with_legacy_position(frame, fps_history, current_fps, frame_times=None,
                                         show_frame_time_graph=True, max_len=180, global_fps_values=None,
                                         global_frame_times=None, frametime_scale=None, font_settings=None,
                                         color_settings=None, ftg_position="bottom_right"):
    """Enhanced legacy compatibility with TrueType support - UPDATED"""
    h, w = frame.shape[:2]
    
    # Enhanced layout conversion
    renderer = EnhancedOverlayRenderer()
    resolution_scale = renderer.get_resolution_scale_factor(w, h)
    layout_scale = min(w / 1920, h / 1080)
    combined_scale = layout_scale * resolution_scale
    
    # Create enhanced layout config with better scaling
    layout_config = {
        'fps_display': {
            'x': int(50 * combined_scale), 'y': int(50 * combined_scale),
            'width': int(120 * combined_scale), 'height': int(80 * combined_scale),
            'visible': True, 'text_quality': 'high'
        },
        'frame_rate_graph': {
            'x': int(50 * combined_scale), 'y': int((h/combined_scale - 300) * combined_scale),
            'width': int(1200 * combined_scale), 'height': int(250 * combined_scale),
            'visible': True, 'text_quality': 'high'
        },
        'fps_statistics': {
            'x': int(50 * combined_scale), 'y': int((h/combined_scale - 30) * combined_scale),
            'width': int(350 * combined_scale), 'height': int(25 * combined_scale),
            'visible': True, 'text_quality': 'high'
        }
    }
    
    # Position frame time elements based on ftg_position
    if ftg_position == "bottom_left":
        layout_config['frame_time_graph'] = {
            'x': int(50 * combined_scale), 'y': int((h/combined_scale - 550) * combined_scale),
            'width': int(450 * combined_scale), 'height': int(180 * combined_scale),
            'visible': show_frame_time_graph, 'text_quality': 'high'
        }
        layout_config['frametime_statistics'] = {
            'x': int(50 * combined_scale), 'y': int((h/combined_scale - 350) * combined_scale),
            'width': int(280 * combined_scale), 'height': int(25 * combined_scale),
            'visible': show_frame_time_graph, 'text_quality': 'high'
        }
    elif ftg_position == "top_right":
        layout_config['frame_time_graph'] = {
            'x': int((w/combined_scale - 500) * combined_scale), 'y': int(50 * combined_scale),
            'width': int(450 * combined_scale), 'height': int(180 * combined_scale),
            'visible': show_frame_time_graph, 'text_quality': 'high'
        }
        layout_config['frametime_statistics'] = {
            'x': int((w/combined_scale - 330) * combined_scale), 'y': int(250 * combined_scale),
            'width': int(280 * combined_scale), 'height': int(25 * combined_scale),
            'visible': show_frame_time_graph, 'text_quality': 'high'
        }
    else:  # bottom_right (default)
        layout_config['frame_time_graph'] = {
            'x': int((w/combined_scale - 500) * combined_scale), 'y': int((h/combined_scale - 230) * combined_scale),
            'width': int(450 * combined_scale), 'height': int(180 * combined_scale),
            'visible': show_frame_time_graph, 'text_quality': 'high'
        }
        layout_config['frametime_statistics'] = {
            'x': int((w/combined_scale - 330) * combined_scale), 'y': int((h/combined_scale - 30) * combined_scale),
            'width': int(280 * combined_scale), 'height': int(25 * combined_scale),
            'visible': show_frame_time_graph, 'text_quality': 'high'
        }
    
    return draw_fps_overlay_with_layout(
        frame, fps_history, current_fps, frame_times, show_frame_time_graph,
        max_len, global_fps_values, global_frame_times, frametime_scale,
        font_settings, color_settings, layout_config
    )

# Added legacy compatibility function
def draw_fps_overlay(frame, fps_history, current_fps, frame_times=None,
                    show_frame_time_graph=True, max_len=180, global_fps_values=None,
                    global_frame_times=None, frametime_scale=None, font_settings=None,
                    color_settings=None, ftg_position="bottom_right"):
    """Legacy compatibility function for older modules"""
    print("🔄 Legacy draw_fps_overlay called - forwarding to draw_fps_overlay_with_legacy_position")
    return draw_fps_overlay_with_legacy_position(
        frame, fps_history, current_fps, frame_times, show_frame_time_graph,
        max_len, global_fps_values, global_frame_times, frametime_scale,
        font_settings, color_settings, ftg_position
    )

# ===============================================
# 📤 EXPORTS
# ===============================================

__all__ = [
    'EnhancedOverlayRenderer',
    'OverlayElement', 
    'FPSNumberElement',
    'FrameRateGraphElement',
    'FrameTimeGraphElement', 
    'FPSStatisticsElement',
    'FrameTimeStatisticsElement',
    'draw_fps_overlay_with_layout',
    'draw_fps_overlay_with_legacy_position',
    'draw_fps_overlay',  # Added for compatibility
    'ENHANCED_FONTS_AVAILABLE',
    'FREETYPE_AVAILABLE',
    'PILLOW_AVAILABLE'
]

print(f"🚀 Enhanced Overlay Renderer with TrueType integration ready!")
if PILLOW_AVAILABLE:
    print(f"   • TrueType Rendering: ✅ Active (Pillow)")
elif FREETYPE_AVAILABLE:
    print(f"   • TrueType Rendering: ✅ Active (OpenCV FreeType)")
else:
    print(f"   • TrueType Rendering: ❌ Fallback Mode")
print(f"   • Enhanced Quality: ✅ Enabled")
print(f"   • Backward Compatibility: ✅ 100%")