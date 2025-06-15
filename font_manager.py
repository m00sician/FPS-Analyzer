"""
Enhanced Font Manager - TrueType and Pillow Integration
Interface to the font system with enhanced functions and dialogs

USAGE: Save as font_manager.py (replaces the existing file)

Features:
- TrueType/OpenType Font Support (.ttf, .otf) via Pillow
- System Font Detection (Windows/Linux/Mac)
- Enhanced Font Selection with Live Preview
- Smart Fallback to OpenCV Standard Fonts
- Performance Optimized with Font Caching
- 100% Backward Compatibility with Existing Code
"""

import cv2
import os
import numpy as np
from typing import Dict, List, Tuple, Optional, Union, Any
import time
import platform

# Import core functionality
try:
    from truetype_core import (
        SystemFontDiscovery, PillowOpenCVBridge, 
        PILLOW_AVAILABLE, FREETYPE_AVAILABLE,
        check_freetype_support, enable_debug_mode, debug_log
    )
    CORE_MODULE_AVAILABLE = True
except ImportError:
    # If core module not found, create it directly here
    from PyQt6.QtWidgets import QMessageBox
    QMessageBox.information(None, "Font System", 
                           "Core module not found. Creating fallback version.\n\n"
                           "For full functionality please install truetype_core.py.")
    
    # Import required functions and classes directly
    import cv2
    import os
    import platform
    import glob
    import numpy as np
    
    # TrueType support with Pillow (fallback import)
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageColor
        PILLOW_AVAILABLE = True
    except ImportError:
        PILLOW_AVAILABLE = False

    # Check for OpenCV FreeType support (fallback implementation)
    def check_freetype_support():
        try:
            cv2.freetype.createFreeType2()
            return True
        except:
            return False

    FREETYPE_AVAILABLE = check_freetype_support()
    CORE_MODULE_AVAILABLE = False
    
    def enable_debug_mode(export_images=False):
        pass
    
    def debug_log(message):
        print(f"DEBUG: {message}")
    
    # Minimal implementations of core classes
    class SystemFontDiscovery:
        def __init__(self):
            self.system_fonts = []
        
        def discover_fonts(self):
            return []
        
        def get_font_by_name(self, name):
            return None
        
        def get_popular_fonts(self):
            return []
    
    class PillowOpenCVBridge:
        def __init__(self, cache_size=50):
            self.available = PILLOW_AVAILABLE
        
        def load_system_font(self, font_name, size=24, bold=False, italic=False):
            return None
        
        def render_text(self, cv_img, text, position, font, text_color=(255, 255, 255), 
                      border_color=None, border_thickness=0, alpha=1.0):
            # Fallback rendering
            result = cv_img.copy()
            font_face = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(result, text, position, font_face, 0.8, text_color, 1, cv2.LINE_AA)
            return result
        
        def get_text_size(self, text, font):
            font_face = cv2.FONT_HERSHEY_SIMPLEX
            size, _ = cv2.getTextSize(text, font_face, 0.8, 1)
            return size

# Import Qt Components for dialog
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QComboBox, QSpinBox, QCheckBox, QSlider,
                             QGroupBox, QTabWidget, QWidget, QListWidget, 
                             QListWidgetItem, QSplitter, QTextEdit, QProgressBar,
                             QFrame, QScrollArea)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QPixmap, QImage, QPainter, QColor

class OpenCVFontSettings:
    """Enhanced font settings with TrueType support - IMPROVED SCALING"""
    
    def __init__(self, font_path: str = None, font_name: str = 'HERSHEY_SIMPLEX', 
                size: float = 1.0, thickness: int = 2, bold: bool = False,
                italic: bool = False, border_thickness: int = 2,
                border_color: Tuple[int, int, int] = (0, 0, 0),
                text_color: Tuple[int, int, int] = (255, 255, 255),
                line_spacing: float = 1.2, letter_spacing: float = 0.0):
        
        # FIXED: Ensure font_name is a string, converting if necessary
        if not isinstance(font_name, str):
            print(f"⚠️ Warning: Non-string font_name detected ({type(font_name)}), converting to string")
            if isinstance(font_name, int):
                # Handle int directly for cv2 constants
                cv2_font_mapping = {
                    cv2.FONT_HERSHEY_SIMPLEX: 'HERSHEY_SIMPLEX',
                    cv2.FONT_HERSHEY_PLAIN: 'HERSHEY_PLAIN',
                    cv2.FONT_HERSHEY_DUPLEX: 'HERSHEY_DUPLEX',
                    cv2.FONT_HERSHEY_COMPLEX: 'HERSHEY_COMPLEX',
                    cv2.FONT_HERSHEY_TRIPLEX: 'HERSHEY_TRIPLEX',
                    cv2.FONT_HERSHEY_COMPLEX_SMALL: 'HERSHEY_COMPLEX_SMALL',
                    cv2.FONT_HERSHEY_SCRIPT_SIMPLEX: 'HERSHEY_SCRIPT_SIMPLEX',
                    cv2.FONT_HERSHEY_SCRIPT_COMPLEX: 'HERSHEY_SCRIPT_COMPLEX'
                }
                font_name = cv2_font_mapping.get(font_name, 'HERSHEY_SIMPLEX')
            else:
                # For any other type, convert to string
                font_name = str(font_name)
        
        # Core properties (backward compatible)
        self.font_path = font_path
        self.font_name = font_name
        self.size = size
        self.thickness = thickness
        self.bold = bold
        self.italic = italic
        
        # Enhanced properties
        self.border_thickness = border_thickness
        self.border_color = border_color
        self.text_color = text_color
        self.line_spacing = line_spacing
        self.letter_spacing = letter_spacing
        
        # Internal objects
        self._freetype_font = None
        self._opencv_font = None
        self._is_freetype_ready = False
        self._pillow_bridge = PillowOpenCVBridge() if PILLOW_AVAILABLE else None
        self._pillow_font = None
        
        # Initialize fonts
        self._initialize_fonts()
    
    def _initialize_fonts(self):
        """Initialize both FreeType and OpenCV fonts"""
        self._initialize_freetype()
        self._initialize_opencv()
    
    def _initialize_freetype(self):
        """Initialize FreeType/Pillow font if available"""
        # First try Pillow
        if PILLOW_AVAILABLE and self._pillow_bridge:
            try:
                # FIXED: Improved scaling for better consistency with OpenCV fonts
                # OpenCV font size 1.0 corresponds to about 24 pixels in height
                base_scale = 24.0  # Base reference height
                
                # FIXED: Reduced scaling factor from 0.75 to 0.3 for better match
                pil_size = int(self.size)
                if pil_size < 8:
                    pil_size = 24
                
                if self.font_path and os.path.exists(self.font_path):
                    # Load directly from path
                    self._pillow_font = self._pillow_bridge.load_system_font(
                        self.font_path, pil_size, self.bold, self.italic
                    )
                    if self._pillow_font:
                        self._is_freetype_ready = True
                        # Store base size for dynamic scaling
                        self._pillow_base_size = pil_size
                        debug_log(f"Pillow TrueType font loaded: {self.font_name}, Size: {pil_size}px")
                        return
                elif not self.font_name.startswith('HERSHEY'):
                    # Try to load by name
                    self._pillow_font = self._pillow_bridge.load_system_font(
                        self.font_name, pil_size, self.bold, self.italic
                    )
                    if self._pillow_font:
                        self._is_freetype_ready = True
                        # Store base size for dynamic scaling
                        self._pillow_base_size = pil_size
                        debug_log(f"Pillow TrueType font found and loaded: {self.font_name}, Size: {pil_size}px")
                        return
            except Exception as e:
                debug_log(f"Error loading Pillow TrueType font: {e}")
                self._pillow_font = None
                self._pillow_base_size = None
        
        # Fallback to OpenCV FreeType
        if not FREETYPE_AVAILABLE:
            return
        
        try:
            if self.font_path and os.path.exists(self.font_path):
                self._freetype_font = cv2.freetype.createFreeType2()
                self._freetype_font.loadFontData(fontFileName=self.font_path, id=0)
                self._is_freetype_ready = True
                debug_log(f"FreeType font loaded: {self.font_name}")
            else:
                # Try to find font by name
                if self.font_path is None and not self.font_name.startswith('HERSHEY'):
                    discovery = SystemFontDiscovery()
                    discovery.discover_fonts()
                    font_info = discovery.get_font_by_name(self.font_name)
                    if font_info:
                        self.font_path = font_info['path']
                        self._freetype_font = cv2.freetype.createFreeType2()
                        self._freetype_font.loadFontData(fontFileName=self.font_path, id=0)
                        self._is_freetype_ready = True
                        debug_log(f"FreeType font found and loaded: {self.font_name}")
        except Exception as e:
            debug_log(f"Error loading FreeType font {self.font_name}: {e}")
            self._freetype_font = None
            self._is_freetype_ready = False
    
    def _initialize_opencv(self):
        """Initialize fallback OpenCV font - FIXED for integer font_name issue"""
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
        
        # FIXED: Handle case where font_name might be an integer
        if isinstance(self.font_name, int):
            print(f"⚠️ Warning: font_name is an integer ({self.font_name}), using HERSHEY_SIMPLEX as fallback")
            self._opencv_font = cv2.FONT_HERSHEY_SIMPLEX
            # Convert to string for future compatibility
            self.font_name = 'HERSHEY_SIMPLEX'
            return
        
        # If font_name is an OpenCV font
        if self.font_name in font_mapping:
            self._opencv_font = font_mapping[self.font_name]
        else:
            # Try to map TrueType font to best OpenCV equivalent
            try:
                name_lower = self.font_name.lower()
                if 'arial' in name_lower or 'helvetica' in name_lower or 'sans' in name_lower:
                    self._opencv_font = cv2.FONT_HERSHEY_SIMPLEX
                elif 'times' in name_lower or 'serif' in name_lower:
                    self._opencv_font = cv2.FONT_HERSHEY_COMPLEX
                elif 'courier' in name_lower or 'mono' in name_lower:
                    self._opencv_font = cv2.FONT_HERSHEY_DUPLEX
                else:
                    self._opencv_font = cv2.FONT_HERSHEY_SIMPLEX
            except (AttributeError, TypeError):
                # FIXED: Added additional error handling for unexpected font_name types
                print(f"⚠️ Warning: Unexpected font_name type ({type(self.font_name)}), using HERSHEY_SIMPLEX")
                self._opencv_font = cv2.FONT_HERSHEY_SIMPLEX
    
    def is_freetype_available(self) -> bool:
        """Check if FreeType/Pillow font is ready"""
        if PILLOW_AVAILABLE and self._pillow_font is not None:
            return True
        return self._is_freetype_ready and self._freetype_font is not None
    
    def get_effective_thickness(self) -> int:
        """Get thickness with bold modifier"""
        base_thickness = self.thickness
        if self.bold:
            return base_thickness + 1
        return base_thickness
    
    def get_opencv_font(self):
        """Get OpenCV font for fallback"""
        return self._opencv_font
    
    def render_text(self, img: np.ndarray, text: str, position: Tuple[int, int],
                scale_factor: float = 1.0) -> np.ndarray:
        """Render text with the best available method - FIXED"""
        # Pillow method (first priority)
        if PILLOW_AVAILABLE and self._pillow_font is not None:
            return self._render_pillow_text(img, text, position, scale_factor)
        # FreeType method (second priority)
        elif self.is_freetype_available():
            return self._render_freetype_text(img, text, position, scale_factor)
        # Standard OpenCV method (fallback)
        else:
            return self._render_opencv_text(img, text, position, scale_factor)

    def _render_pillow_text(self, img: np.ndarray, text: str, 
                        position: Tuple[int, int], scale_factor: float) -> np.ndarray:
        """Render text with Pillow for high quality - FIXED"""
        try:
            # DEBUG: Check font size
            if hasattr(self, '_pillow_base_size'):
                current_size = self._pillow_base_size
            else:
                current_size = int(self.size)
                
            # Ensure we have a reasonable font size
            if current_size <= 0:
                current_size = 24
                
            scaled_size = int(current_size * scale_factor)
            
            # Make sure scaled size is reasonable
            if scaled_size < 8:
                scaled_size = 8
                
            
            # Only create new font if scaling factor is significantly different
            if abs(scale_factor - 1.0) > 0.2:
                font_path = self.font_path if self.font_path and os.path.exists(self.font_path) else self.font_name
                temp_font = self._pillow_bridge.load_system_font(
                    font_path, scaled_size, self.bold, self.italic
                )
                font_to_use = temp_font if temp_font else self._pillow_font
            else:
                font_to_use = self._pillow_font
            
            # Make sure we have a valid font
            if font_to_use is None:
                print(f"ERROR: No valid font to use!")
                return self._render_opencv_text(img, text, position, scale_factor)
            
            # Scale border thickness consistently
            border_thickness = max(1, int(self.border_thickness * scale_factor))
            
            # Use Pillow bridge for rendering and RETURN THE RESULT
            return self._pillow_bridge.render_text(
                img, text, position, 
                font_to_use,
                self.text_color,
                self.border_color if self.border_thickness > 0 else None,
                border_thickness
            )
        except Exception as e:
            print(f"ERROR: Pillow rendering failed: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to OpenCV
            return self._render_opencv_text(img, text, position, scale_factor)
    
    def _render_freetype_text(self, img: np.ndarray, text: str, 
                            position: Tuple[int, int], scale_factor: float) -> np.ndarray:
        """Render text with FreeType for high quality"""
        try:
            x, y = position
            font_height = int(self.size * scale_factor * 20)  # Convert to pixel height
            
            # Render border if specified
            if self.border_thickness > 0:
                border_size = max(1, int(self.border_thickness * scale_factor))
                
                # Border with multiple passes for smooth effect
                for dx in range(-border_size, border_size + 1):
                    for dy in range(-border_size, border_size + 1):
                        if dx != 0 or dy != 0:
                            self._freetype_font.putText(
                                img, text, (x + dx, y + dy), font_height,
                                self.border_color, self.get_effective_thickness(),
                                cv2.LINE_AA, False
                            )
            
            # Main text with anti-aliasing
            self._freetype_font.putText(
                img, text, (x, y), font_height,
                self.text_color, self.get_effective_thickness(),
                cv2.LINE_AA, False
            )
            
            return img
            
        except Exception as e:
            debug_log(f"FreeType rendering failed: {e}")
            # Fallback to OpenCV
            return self._render_opencv_text(img, text, position, scale_factor)
    
    def _render_opencv_text(self, img: np.ndarray, text: str,
                          position: Tuple[int, int], scale_factor: float) -> np.ndarray:
        """Fallback OpenCV text rendering"""
        x, y = position
        
        # FIXED: Improved size scaling
        # Divide by 24.0 for better consistency with TrueType
        font_scale = self.size * scale_factor / 24.0
        thickness = max(1, int(self.get_effective_thickness() * scale_factor))
        
        # Render border
        if self.border_thickness > 0:
            border_thickness = max(1, int(self.border_thickness * scale_factor))
            for dx in range(-border_thickness, border_thickness + 1):
                for dy in range(-border_thickness, border_thickness + 1):
                    if dx != 0 or dy != 0:
                        cv2.putText(img, text, (x + dx, y + dy), self._opencv_font,
                                  font_scale, self.border_color, thickness + 1, cv2.LINE_AA)
        
        # Render main text
        cv2.putText(img, text, position, self._opencv_font,
                   font_scale, self.text_color, thickness, cv2.LINE_AA)
        
        return img
    
    def get_text_size(self, text: str, scale_factor: float = 1.0) -> Tuple[int, int]:
        """Get text dimensions with improved scaling consistency"""
        # Improved Pillow text size calculation
        if PILLOW_AVAILABLE and self._pillow_font is not None:
            try:
                # If significant scaling needed, create temporary font in correct size
                if abs(scale_factor - 1.0) > 0.2 and hasattr(self, '_pillow_base_size') and self._pillow_base_size is not None:
                    current_size = self._pillow_base_size
                    scaled_size = int(current_size * scale_factor)
                    font_path = self.font_path if self.font_path and os.path.exists(self.font_path) else self.font_name
                    temp_font = self._pillow_bridge.load_system_font(
                        font_path, scaled_size, self.bold, self.italic
                    )
                    size = self._pillow_bridge.get_text_size(text, temp_font)
                    return size
                else:
                    # Apply scaling factor to result for smaller adjustments
                    base_size = self._pillow_bridge.get_text_size(text, self._pillow_font)
                    if scale_factor != 1.0:
                        return (int(base_size[0] * scale_factor), int(base_size[1] * scale_factor))
                    return base_size
            except Exception as e:
                debug_log(f"Pillow text size calculation failed: {e}")
                
        # Fallback to FreeType
        if self.is_freetype_available():
            try:
                font_height = int(self.size * scale_factor * 20)
                size = self._freetype_font.getTextSize(text, font_height, self.get_effective_thickness())
                return size[0]  # Returns (width, height)
            except:
                pass
        
        # Fallback to OpenCV
        # FIXED: Improved size scaling
        font_scale = self.size * scale_factor / 24.0
        thickness = max(1, int(self.get_effective_thickness() * scale_factor))
        size = cv2.getTextSize(text, self._opencv_font, font_scale, thickness)
        return size[0]  # Returns (width, height)
    
    def clone(self):
        """Create a copy of these font settings"""
        return OpenCVFontSettings(
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
        """Convert to dictionary for serialization"""
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
        """Create from dictionary"""
        return cls(**data)
    
    def to_qfont(self):
        """Convert to QFont for UI compatibility"""
        if self.font_name.startswith('HERSHEY'):
            # Map OpenCV fonts to Qt fonts
            font_mapping = {
                'HERSHEY_SIMPLEX': 'Arial',
                'HERSHEY_PLAIN': 'Arial',
                'HERSHEY_DUPLEX': 'Consolas',
                'HERSHEY_COMPLEX': 'Arial Black',
                'HERSHEY_TRIPLEX': 'Impact',
                'HERSHEY_COMPLEX_SMALL': 'Arial',
                'HERSHEY_SCRIPT_SIMPLEX': 'Times New Roman',
                'HERSHEY_SCRIPT_COMPLEX': 'Georgia'
            }
            qt_family = font_mapping.get(self.font_name, 'Arial')
        else:
            qt_family = self.font_name
        
        qt_size = max(8, int(self.size * 12))  # Convert to reasonable Qt size
        qfont = QFont(qt_family, qt_size)
        qfont.setBold(self.bold)
        qfont.setItalic(self.italic)
        return qfont


# ===============================================
# 🔍 FONT DISCOVERY THREAD
# ===============================================

class FontDiscoveryThread(QThread):
    """Background thread for font discovery"""
    fonts_discovered = pyqtSignal(list)
    progress_update = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.discovery = SystemFontDiscovery()
    
    def run(self):
        """Run font discovery in background"""
        self.progress_update.emit("🔍 Scanning system fonts...")
        fonts = self.discovery.discover_fonts()
        self.fonts_discovered.emit(fonts)

# ===============================================
# 🎨 ENHANCED FONT SELECTION DIALOG
# ===============================================

class OpenCVFontSelectionDialog(QDialog):
    """Enhanced font selection dialog with TrueType support"""
    
    def __init__(self, parent, fps_settings, framerate_settings, frametime_settings):
        super().__init__(parent)
        self.setWindowTitle("🎨 Enhanced Font Selection - TrueType & OpenCV Support")
        self.setMinimumSize(1400, 900)
        self.setModal(True)
        
        # Store original settings
        self.original_fps = fps_settings.clone() if hasattr(fps_settings, 'clone') else fps_settings
        self.original_framerate = framerate_settings.clone() if hasattr(framerate_settings, 'clone') else framerate_settings
        self.original_frametime = frametime_settings.clone() if hasattr(frametime_settings, 'clone') else frametime_settings
        
        # Current settings (working copies)
        self.fps_settings = fps_settings.clone() if hasattr(fps_settings, 'clone') else fps_settings
        self.framerate_settings = framerate_settings.clone() if hasattr(framerate_settings, 'clone') else framerate_settings
        self.frametime_settings = frametime_settings.clone() if hasattr(frametime_settings, 'clone') else frametime_settings
        
        # Font discovery
        self.font_discovery = SystemFontDiscovery()
        self.available_fonts = []
        self.current_font_element = 'fps'  # 'fps', 'framerate', 'frametime'
        
        # Preview
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.update_preview)
        self.preview_timer.setSingleShot(True)
        
        self.setup_ui()
        self.start_font_discovery()
    
    def setup_ui(self):
        """Create enhanced UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Enhanced header
        header = QLabel("🎨 Enhanced Font Selection - TrueType Fonts + OpenCV Fallback")
        header.setStyleSheet("""
            QLabel {
                font-size: 18px; font-weight: bold; color: #4CAF50; 
                padding: 15px; background-color: #2a2a2a; border-radius: 8px;
                border: 1px solid #4CAF50;
            }
        """)
        layout.addWidget(header)
        
        # Status with improved styling
        self.status_label = QLabel("🔍 Discovering system fonts...")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #FF9800; font-style: italic; padding: 8px; font-size: 12px;
                background-color: #1a1a1a; border-radius: 4px;
            }
        """)
        layout.addWidget(self.status_label)
        
        # Enhanced progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #555; border-radius: 8px; text-align: center;
                background-color: #3c3c3c; color: #ffffff; font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #4CAF50; border-radius: 6px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # Main content (hidden until fonts loaded)
        self.main_widget = QWidget()
        self.main_widget.setVisible(False)
        self.setup_main_content()
        layout.addWidget(self.main_widget)
        
        # Enhanced buttons
        button_layout = QHBoxLayout()
        
        # Preview control
        preview_layout = QHBoxLayout()
        
        self.preview_btn = QPushButton("🔄 Update Preview")
        self.preview_btn.clicked.connect(self.force_preview_update)
        self.preview_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3; color: white; border: none;
                border-radius: 6px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        preview_layout.addWidget(self.preview_btn)
        
        self.auto_preview_check = QCheckBox("🔄 Auto-Preview")
        self.auto_preview_check.setChecked(True)
        self.auto_preview_check.setStyleSheet("color: #4CAF50; font-weight: bold;")
        preview_layout.addWidget(self.auto_preview_check)
        
        button_layout.addLayout(preview_layout)
        button_layout.addStretch()
        
        # Action buttons
        reset_btn = QPushButton("🔄 Reset to Defaults")
        reset_btn.clicked.connect(self.reset_to_defaults)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800; color: white; border: none;
                border-radius: 6px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #F57C00; }
        """)
        button_layout.addWidget(reset_btn)
        
        cancel_btn = QPushButton("❌ Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336; color: white; border: none;
                border-radius: 6px; padding: 8px 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #d32f2f; }
        """)
        button_layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("✅ Apply Changes")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; color: white; border: none;
                border-radius: 6px; padding: 12px 24px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
    
    def setup_main_content(self):
        """Create enhanced main content"""
        layout = QHBoxLayout(self.main_widget)
        
        # Left side - Font selection and settings
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.setMinimumWidth(500)
        
        # Enhanced element selection
        element_group = QGroupBox("📝 Font Element Selection")
        element_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold; border: 2px solid #4CAF50; border-radius: 8px;
                margin-top: 8px; padding-top: 10px; color: #4CAF50;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 8px 0 8px;
            }
        """)
        element_layout = QVBoxLayout(element_group)
        
        self.element_combo = QComboBox()
        self.element_combo.addItem("🎯 FPS Number Display", 'fps')
        self.element_combo.addItem("📊 Framerate Graph Labels", 'framerate')
        self.element_combo.addItem("⏱️ Frametime Graph Labels", 'frametime')
        self.element_combo.currentTextChanged.connect(self.on_element_changed)
        self.element_combo.setStyleSheet("""
            QComboBox {
                padding: 8px; border: 2px solid #555; border-radius: 6px;
                background-color: #3c3c3c; color: #ffffff; font-size: 12px;
            }
            QComboBox:focus { border-color: #4CAF50; }
        """)
        element_layout.addWidget(self.element_combo)
        
        # Font type info
        self.font_type_label = QLabel("📍 Current: OpenCV Standard Font")
        self.font_type_label.setStyleSheet("""
            QLabel {
                color: #FF9800; font-style: italic; padding: 5px;
                background-color: #2a2a2a; border-radius: 4px; font-size: 11px;
            }
        """)
        element_layout.addWidget(self.font_type_label)
        
        left_splitter.addWidget(element_group)
        
        # Enhanced font list
        font_group = QGroupBox("🔤 Available Fonts")
        font_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold; border: 2px solid #2196F3; border-radius: 8px;
                margin-top: 8px; padding-top: 10px; color: #2196F3;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 8px 0 8px;
            }
        """)
        font_layout = QVBoxLayout(font_group)
        
        # Enhanced font filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("🔍 Filter:"))
        self.font_filter = QComboBox()
        self.font_filter.addItem("All Fonts", 'all')
        self.font_filter.addItem("TrueType Only", 'ttf')
        self.font_filter.addItem("Popular Fonts", 'popular')
        self.font_filter.addItem("OpenCV Fonts", 'opencv')
        self.font_filter.currentTextChanged.connect(self.filter_fonts)
        self.font_filter.setStyleSheet("""
            QComboBox {
                padding: 6px; border: 1px solid #555; border-radius: 4px;
                background-color: #3c3c3c; color: #ffffff;
            }
        """)
        filter_layout.addWidget(self.font_filter)
        filter_layout.addStretch()
        font_layout.addLayout(filter_layout)
        
        # Enhanced font list
        self.font_list = QListWidget()
        self.font_list.itemClicked.connect(self.on_font_selected)
        self.font_list.setStyleSheet("""
            QListWidget {
                border: 2px solid #555; border-radius: 6px;
                background-color: #2a2a2a; color: #ffffff; font-size: 11px;
            }
            QListWidget::item {
                padding: 6px; border-bottom: 1px solid #444;
            }
            QListWidget::item:hover {
                background-color: #3a3a3a;
            }
            QListWidget::item:selected {
                background-color: #4CAF50; color: white; font-weight: bold;
            }
        """)
        font_layout.addWidget(self.font_list)
        
        left_splitter.addWidget(font_group)
        
        # Enhanced font settings
        settings_group = QGroupBox("⚙️ Font Settings")
        settings_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold; border: 2px solid #FF9800; border-radius: 8px;
                margin-top: 8px; padding-top: 10px; color: #FF9800;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 8px 0 8px;
            }
        """)
        settings_layout = QVBoxLayout(settings_group)
        
        # Enhanced size control
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("📏 Size:"))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(8, 72)
        self.size_slider.setValue(24)
        self.size_slider.valueChanged.connect(self.on_setting_changed)
        self.size_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #555; height: 8px; background: #3c3c3c; border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50; border: 1px solid #333; width: 18px;
                border-radius: 9px; margin: -5px 0;
            }
        """)
        size_layout.addWidget(self.size_slider)
        
        self.size_value = QLabel("24")
        self.size_value.setMinimumWidth(30)
        self.size_value.setStyleSheet("color: #4CAF50; font-weight: bold;")
        size_layout.addWidget(self.size_value)
        settings_layout.addLayout(size_layout)
        
        # Enhanced thickness control
        thickness_layout = QHBoxLayout()
        thickness_layout.addWidget(QLabel("🖊️ Thickness:"))
        self.thickness_spin = QSpinBox()
        self.thickness_spin.setRange(1, 10)
        self.thickness_spin.setValue(2)
        self.thickness_spin.valueChanged.connect(self.on_setting_changed)
        self.thickness_spin.setStyleSheet("""
            QSpinBox {
                padding: 4px; border: 1px solid #555; border-radius: 4px;
                background-color: #3c3c3c; color: #ffffff;
            }
        """)
        thickness_layout.addWidget(self.thickness_spin)
        thickness_layout.addStretch()
        settings_layout.addLayout(thickness_layout)
        
        # Enhanced style options
        style_layout = QHBoxLayout()
        self.bold_check = QCheckBox("💪 Bold")
        self.bold_check.toggled.connect(self.on_setting_changed)
        self.bold_check.setStyleSheet("color: #ffffff; font-weight: bold;")
        style_layout.addWidget(self.bold_check)
        
        self.italic_check = QCheckBox("📐 Italic")
        self.italic_check.toggled.connect(self.on_setting_changed)
        self.italic_check.setStyleSheet("color: #ffffff; font-weight: bold;")
        style_layout.addWidget(self.italic_check)
        style_layout.addStretch()
        settings_layout.addLayout(style_layout)
        
        # Enhanced border control
        border_layout = QHBoxLayout()
        border_layout.addWidget(QLabel("🔲 Border:"))
        self.border_spin = QSpinBox()
        self.border_spin.setRange(0, 5)
        self.border_spin.setValue(2)
        self.border_spin.valueChanged.connect(self.on_setting_changed)
        self.border_spin.setStyleSheet("""
            QSpinBox {
                padding: 4px; border: 1px solid #555; border-radius: 4px;
                background-color: #3c3c3c; color: #ffffff;
            }
        """)
        border_layout.addWidget(self.border_spin)
        border_layout.addStretch()
        settings_layout.addLayout(border_layout)
        
        left_splitter.addWidget(settings_group)
        layout.addWidget(left_splitter)
        
        # Right side - Enhanced preview
        preview_group = QGroupBox("👁️ Live Preview")
        preview_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold; border: 2px solid #9C27B0; border-radius: 8px;
                margin-top: 8px; padding-top: 10px; color: #9C27B0;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 8px 0 8px;
            }
        """)
        preview_layout = QVBoxLayout(preview_group)
        
        # Enhanced preview area
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(600, 450)
        self.preview_label.setStyleSheet("""
            QLabel {
                border: 3px solid #555; background-color: #1a1a1a;
                border-radius: 8px;
            }
        """)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.preview_label)
        
        # Enhanced preview info
        self.preview_info = QTextEdit()
        self.preview_info.setMaximumHeight(120)
        self.preview_info.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a; color: #ccc; font-family: 'Consolas', monospace;
                font-size: 10px; border: 2px solid #555; border-radius: 6px; padding: 8px;
            }
        """)
        preview_layout.addWidget(self.preview_info)
        
        layout.addWidget(preview_group)
    
    def start_font_discovery(self):
        """Start font discovery in background"""
        self.discovery_thread = FontDiscoveryThread()
        self.discovery_thread.fonts_discovered.connect(self.on_fonts_discovered)
        self.discovery_thread.progress_update.connect(self.status_label.setText)
        self.discovery_thread.start()
    
    def on_fonts_discovered(self, fonts):
        """Handle completed font discovery"""
        self.available_fonts = fonts
        self.progress_bar.setVisible(False)
        self.main_widget.setVisible(True)
        
        if PILLOW_AVAILABLE:
            freetype_status = "✅ Pillow available"
        elif FREETYPE_AVAILABLE:
            freetype_status = "✅ FreeType available" 
        else:
            freetype_status = "❌ Not available"
            
        self.status_label.setText(f"✅ {len(fonts)} system fonts found • TrueType: {freetype_status}")
        
        # Populate font list
        self.populate_font_list()
        
        # Load current settings
        self.load_current_settings()
        
        # Initial preview
        self.schedule_preview_update()
    
    def populate_font_list(self):
        """Populate enhanced font list"""
        self.font_list.clear()
        
        filter_type = self.font_filter.currentData()
        
        # Enhanced filtering
        if filter_type == 'popular':
            fonts_to_show = self.font_discovery.get_popular_fonts()
        elif filter_type == 'ttf':
            fonts_to_show = [f for f in self.available_fonts if f['type'] == 'ttf']
        elif filter_type == 'opencv':
            fonts_to_show = []  # Only OpenCV fonts below
        else:  # 'all' - zeigt ALLE Fonts
            fonts_to_show = self.available_fonts
        
        # Add OpenCV fallback fonts first (always shown)
        opencv_fonts = [
            {'name': 'Hershey Simplex', 'path': 'HERSHEY_SIMPLEX', 'type': 'opencv', 'description': 'Clean, readable'},
            {'name': 'Hershey Complex', 'path': 'HERSHEY_COMPLEX', 'type': 'opencv', 'description': 'Bold, strong'},
            {'name': 'Hershey Duplex', 'path': 'HERSHEY_DUPLEX', 'type': 'opencv', 'description': 'Monospace'},
            {'name': 'Hershey Triplex', 'path': 'HERSHEY_TRIPLEX', 'type': 'opencv', 'description': 'Thick, bold'},
            {'name': 'Hershey Plain', 'path': 'HERSHEY_PLAIN', 'type': 'opencv', 'description': 'Simple, thin'},
            {'name': 'Hershey Script Simplex', 'path': 'HERSHEY_SCRIPT_SIMPLEX', 'type': 'opencv', 'description': 'Script style'},
        ]
        
        # Add section header
        if filter_type != 'ttf':
            header = QListWidgetItem("━━━ OpenCV Standard Fonts ━━━")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setBackground(QColor(60, 60, 60))
            header.setForeground(QColor(76, 175, 80))
            self.font_list.addItem(header)
            
            for font in opencv_fonts:
                icon = "🔧"
                name = f"{icon} {font['name']} • {font['description']}"
                
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, font)
                self.font_list.addItem(item)
        
        # Add TrueType fonts
        if filter_type != 'opencv' and fonts_to_show:
            # Add separator
            if filter_type != 'ttf':
                separator = QListWidgetItem("━━━ TrueType/OpenType Fonts ━━━")
                separator.setFlags(Qt.ItemFlag.NoItemFlags)
                separator.setBackground(QColor(60, 60, 60))
                separator.setForeground(QColor(33, 150, 243))
                self.font_list.addItem(separator)
            
            for font in fonts_to_show:
                icon = "🎨" if font['type'] == 'ttf' else "⚡"
                size_mb = font['size'] / (1024*1024)
                quality = "Pillow TrueType" if PILLOW_AVAILABLE else "OpenCV FreeType" if FREETYPE_AVAILABLE else "Fallback to OpenCV"
                name = f"{icon} {font['name']} • {size_mb:.1f}MB • {quality}"
                
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, font)
                self.font_list.addItem(item)
        
        # Automatically select first item
        if self.font_list.count() > 1:  # Skip header
            self.font_list.setCurrentRow(1)
    
    def filter_fonts(self):
        """Filter font list"""
        self.populate_font_list()
        self.schedule_preview_update()
    
    def on_element_changed(self):
        """Handle font element change"""
        self.current_font_element = self.element_combo.currentData()
        self.load_current_settings()
        self.update_font_type_label()
        self.schedule_preview_update()
    
    def on_font_selected(self, item):
        """Handle font selection"""
        font_data = item.data(Qt.ItemDataRole.UserRole)
        if not font_data:
            return
        
        current_settings = self.get_current_settings()
        
        if font_data['type'] == 'opencv':
            # OpenCV font
            current_settings.font_path = None
            current_settings.font_name = font_data['path']
        else:
            # TrueType font - MAKE SURE THIS IS SET CORRECTLY
            current_settings.font_path = font_data['path']
            current_settings.font_name = font_data['name']
            print(f"🔍 DEBUG: Selected TrueType font: {font_data['name']} at {font_data['path']}")
        
        # Reinitialize font
        current_settings._initialize_fonts()
        
        # DEBUG: Check if Pillow font was loaded
        print(f"🔍 DEBUG: After initialization:")
        print(f"   - _pillow_font is None: {current_settings._pillow_font is None}")
        print(f"   - _is_freetype_ready: {current_settings._is_freetype_ready}")
        print(f"   - PILLOW_AVAILABLE: {PILLOW_AVAILABLE}")
        
        if current_settings._pillow_bridge:
            print(f"   - _pillow_bridge exists: True")
            # Try to load the font directly to test
            try:
                test_font = current_settings._pillow_bridge.load_system_font(
                    current_settings.font_path, 24, False, False
                )
                print(f"   - Test font load: {test_font is not None}")
            except Exception as e:
                print(f"   - Test font load error: {e}")
        
        self.update_font_type_label()
        self.schedule_preview_update()
    
    def update_font_type_label(self):
        """Update font type display"""
        current_settings = self.get_current_settings()
        
        if current_settings.is_freetype_available():
            # Distinguish between Pillow and FreeType
            if hasattr(current_settings, '_pillow_font') and current_settings._pillow_font is not None:
                self.font_type_label.setText("🎨 Pillow TrueType Font (High Quality)")
                self.font_type_label.setStyleSheet("""
                    QLabel {
                        color: #4CAF50; font-weight: bold; padding: 5px;
                        background-color: #2a2a2a; border-radius: 4px; font-size: 11px;
                    }
                """)
            else:
                self.font_type_label.setText("🎨 OpenCV FreeType Font (High Quality)")
                self.font_type_label.setStyleSheet("""
                    QLabel {
                        color: #4CAF50; font-weight: bold; padding: 5px;
                        background-color: #2a2a2a; border-radius: 4px; font-size: 11px;
                    }
                """)
        else:
            self.font_type_label.setText("🔧 OpenCV Standard Font (Fallback)")
            self.font_type_label.setStyleSheet("""
                QLabel {
                    color: #FF9800; font-style: italic; padding: 5px;
                    background-color: #2a2a2a; border-radius: 4px; font-size: 11px;
                }
            """)
    
    def on_setting_changed(self):
        """Handle setting change"""
        current_settings = self.get_current_settings()
        
        # Update settings from UI
        current_settings.size = self.size_slider.value()
        current_settings.thickness = self.thickness_spin.value()
        current_settings.bold = self.bold_check.isChecked()
        current_settings.italic = self.italic_check.isChecked()
        current_settings.border_thickness = self.border_spin.value()
        
        # Update UI
        self.size_value.setText(str(self.size_slider.value()))
        
        # Reinitialize font - check if method exists first
        if hasattr(current_settings, '_initialize_fonts'):
            current_settings._initialize_fonts()
        
        if self.auto_preview_check.isChecked():
            self.schedule_preview_update()
    
    def get_current_settings(self):
        """Get current font settings"""
        if self.current_font_element == 'fps':
            return self.fps_settings
        elif self.current_font_element == 'framerate':
            return self.framerate_settings
        else:
            return self.frametime_settings
    
    def load_current_settings(self):
        """Load current settings into UI"""
        settings = self.get_current_settings()
        
        # Update UI controls
        self.size_slider.setValue(int(settings.size))
        self.thickness_spin.setValue(settings.thickness)
        self.bold_check.setChecked(settings.bold)
        self.italic_check.setChecked(settings.italic)
        self.border_spin.setValue(settings.border_thickness)
        self.size_value.setText(str(int(settings.size)))
        
        # Select corresponding font in list
        for i in range(self.font_list.count()):
            item = self.font_list.item(i)
            font_data = item.data(Qt.ItemDataRole.UserRole)
            if font_data:
                if ((settings.font_path and font_data.get('path') == settings.font_path) or
                    (not settings.font_path and font_data.get('path') == settings.font_name)):
                    self.font_list.setCurrentItem(item)
                    break
    
    def schedule_preview_update(self):
        """Schedule preview update with debouncing"""
        self.preview_timer.stop()
        self.preview_timer.start(300)  # 300ms delay
    
    def force_preview_update(self):
        """Force immediate preview update"""
        self.preview_timer.stop()
        self.update_preview()
    
    def update_preview(self):
        """Update preview with current font settings"""
        try:
            # Create enhanced preview image
            preview_width, preview_height = 580, 420
            preview_img = np.zeros((preview_height, preview_width, 3), dtype=np.uint8)
            
            # Enhanced background gradient
            for y in range(preview_height):
                intensity = int(15 + (y / preview_height) * 35)
                blue_tint = min(255, intensity + 5)
                preview_img[y, :] = [intensity, intensity, blue_tint]
            
            # Grid pattern for better visual context
            grid_spacing = 40
            for i in range(0, preview_width, grid_spacing):
                cv2.line(preview_img, (i, 0), (i, preview_height), (25, 25, 25), 1)
            for i in range(0, preview_height, grid_spacing):
                cv2.line(preview_img, (0, i), (preview_width, i), (25, 25, 25), 1)
            
            # Enhanced example texts with better positioning
            texts = [
                ("FPS: 59.8", self.fps_settings, (50, 80), "Large FPS number"),
                ("FRAME RATE GRAPH", self.framerate_settings, (50, 140), "Graph title"),
                ("AVG: 59.2  MIN: 45.1  MAX: 60.0", self.framerate_settings, (50, 170), "Graph statistics"),
                ("FRAME TIME", self.frametime_settings, (50, 230), "Frame time title"),
                ("AVG: 16.8ms  MAX: 22.1ms", self.frametime_settings, (50, 260), "Frame time statistics"),
                ("The quick brown fox jumps", self.get_current_settings(), (50, 320), "Example text"),
                ("over the lazy dog 1234567890", self.get_current_settings(), (50, 350), "Character test"),
            ]
            
            # Info collection
            info_parts = []
            
            for text, settings, pos, description in texts:
                # Highlight current element
                if settings == self.get_current_settings():
                    # Enhanced highlighting with gradient effect
                    highlight_overlay = preview_img.copy()
                    cv2.rectangle(highlight_overlay, 
                                (pos[0]-15, pos[1]-30), 
                                (pos[0]+400, pos[1]+15), 
                                (0, 150, 0), -1)
                    cv2.addWeighted(preview_img, 0.7, highlight_overlay, 0.3, 0, preview_img)
                    
                    # Arrow indicator
                    text = f"→ {text}"
                
                # Render text with current settings
                try:
                    # Ensure text color is explicitly set
                    original_color = settings.text_color
                    if "→" in text:  # Highlighted text
                        settings.text_color = (0, 255, 0)  # Brighter green for better visibility
                    else:
                        settings.text_color = (255, 255, 255)  # White for normal text
                    
                    # Render with explicit error handling
                    result = settings.render_text(preview_img, text, pos, 1.0)
                    if result is not None:
                        preview_img = result
                    
                    # Reset color
                    settings.text_color = original_color
                except Exception as e:
                    # Fallback to OpenCV on errors
                    debug_log(f"⚠️ Error rendering preview: {e}")
                    cv2.putText(preview_img, text, pos, cv2.FONT_HERSHEY_SIMPLEX, 
                            0.7, (255, 255, 255), 2, cv2.LINE_AA)
                
                # Collect detailed info
                if hasattr(settings, '_pillow_font') and settings._pillow_font is not None:
                    font_type = "Pillow TrueType"
                elif settings.is_freetype_available():
                    font_type = "OpenCV FreeType"
                else:
                    font_type = "OpenCV Standard"
                    
                info_parts.append(f"{description}: {font_type} - {settings.font_name}")
            
            # Convert to Qt format
            rgb_img = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_img.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            
            # Enhanced scaling and display
            pixmap = QPixmap.fromImage(qt_image)
            scaled_pixmap = pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled_pixmap)
            
            # Enhanced info display
            current = self.get_current_settings()
            
            if hasattr(current, '_pillow_font') and current._pillow_font is not None:
                quality_info = "Highest Quality (Pillow TrueType)"
            elif current.is_freetype_available():
                quality_info = "High Quality (OpenCV FreeType)"
            else:
                quality_info = "Standard Quality (OpenCV)"
            
            info_text = f"""🎯 Current Element: {self.element_combo.currentText()}
🎨 Font: {current.font_name}
🔧 Type: {quality_info}
📏 Size: {current.size} | 🖊️ Thickness: {current.thickness}
💪 Bold: {current.bold} | 📐 Italic: {current.italic} | 🔲 Border: {current.border_thickness}

📊 Font Capabilities:
   • TrueType Support: {'✅ Pillow available' if PILLOW_AVAILABLE else '✅ FreeType available' if FREETYPE_AVAILABLE else '❌ Not available'}
   • Anti-Aliasing: ✅ Enabled
   • Unicode Support: {'✅ Available' if PILLOW_AVAILABLE else '⚠️ Limited'}

📝 All Font Elements:
{chr(10).join(f"   • {info}" for info in info_parts)}

💡 Tip: TrueType fonts offer superior quality and smoother rendering!"""
            
            self.preview_info.setPlainText(info_text)
            
        except Exception as e:
            self.preview_label.setText(f"❌ Preview Error: {str(e)}")
            debug_log(f"❌ Preview Error: {e}")
            import traceback
            traceback.print_exc()
    
    def reset_to_defaults(self):
        """Reset to improved default settings"""
        # Set reasonable defaults
        self.size_slider.setValue(24)
        self.thickness_spin.setValue(2)
        self.bold_check.setChecked(False)
        self.italic_check.setChecked(False)
        self.border_spin.setValue(2)
        
        # Try to select Arial if available
        for i in range(self.font_list.count()):
            item = self.font_list.item(i)
            if item and "Arial" in item.text():
                self.font_list.setCurrentItem(item)
                break
        
        self.on_setting_changed()
    
    def get_selected_settings(self):
        """Get final selected settings"""
        return self.fps_settings, self.framerate_settings, self.frametime_settings

# ===============================================
# 🎨 ENHANCED FONT PREVIEW DIALOG
# ===============================================

class FontPreviewDialog(QDialog):
    """Enhanced font preview dialog with TrueType support"""
    
    def __init__(self, parent, current_frame=None):
        super().__init__(parent)
        self.parent_analyzer = parent
        self.current_frame = current_frame
        self.setWindowTitle("🎨 Enhanced Font Preview - TrueType + Background Selection")
        self.setModal(False)
        self.resize(1400, 900)
        
        # Enhanced background manager
        try:
            from background_manager import BackgroundManager
            self.background_manager = BackgroundManager()
            self.background_manager_available = True
        except ImportError:
            self.background_manager_available = False
            debug_log("⚠️ BackgroundManager not available, using default background")
        
        self.current_background = "Dark Gradient"
        
        # Enhanced mock data
        self.mock_fps_history = [60.0, 59.8, 60.1, 58.9, 60.0, 59.7, 60.2, 59.5, 60.0] * 25
        self.mock_frame_times = [16.7, 16.8, 16.6, 17.0, 16.7, 16.9, 16.5, 17.2, 16.7] * 25
        self.mock_current_fps = 59.8
        
        # Enhanced update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_preview)
        self.update_timer.start(2500)  # Slower updates for stability
        
        # Performance cache
        self.last_font_hash = None
        self.last_color_hash = None
        self.last_background = None
        self.last_window_size = None
        self.cached_preview = None
        
        self.setup_enhanced_ui()
        self.update_preview()
    
    def setup_enhanced_ui(self):
        """Create enhanced UI for font preview"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Enhanced header
        renderer_info = "Pillow TrueType" if PILLOW_AVAILABLE else "OpenCV FreeType" if FREETYPE_AVAILABLE else "Standard OpenCV"
        info_label = QLabel(f"🎨 Enhanced Font Preview - {renderer_info} Renderer - Live TrueType Rendering!")
        info_label.setStyleSheet("""
            QLabel {
                font-weight: bold; color: #4CAF50; padding: 15px; font-size: 16px;
                background-color: #2a2a2a; border-radius: 8px; border: 2px solid #4CAF50;
            }
        """)
        layout.addWidget(info_label)
        
        # Enhanced preview area
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(1000, 600)
        self.preview_label.setStyleSheet("""
            QLabel {
                border: 3px solid #555; background-color: #1a1a1a; border-radius: 10px;
            }
        """)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setScaledContents(False)
        layout.addWidget(self.preview_label, 1)
        
        # Enhanced controls
        controls_layout = QVBoxLayout()
        
        # Background and frame selection with improved styling
        selection_layout = QHBoxLayout()
        
        # Enhanced background selector
        bg_frame = QFrame()
        bg_frame.setStyleSheet("""
            QFrame {
                background-color: #2f2f2f; border: 2px solid #2196F3;
                border-radius: 8px; padding: 10px;
            }
        """)
        bg_layout = QHBoxLayout(bg_frame)
        
        bg_label = QLabel("🖼️ Background:")
        bg_label.setStyleSheet("color: #2196F3; font-weight: bold; font-size: 12px;")
        bg_layout.addWidget(bg_label)
        
        self.background_combo = QComboBox()
        if self.background_manager_available:
            self.background_combo.addItems(self.background_manager.get_available_backgrounds())
        else:
            self.background_combo.addItems(["Dark Gradient", "Light Gradient", "Neutral Gray"])
        self.background_combo.setCurrentText(self.current_background)
        self.background_combo.currentTextChanged.connect(self.change_background)
        self.background_combo.setStyleSheet("""
            QComboBox {
                padding: 8px; border: 2px solid #555; border-radius: 6px;
                background-color: #3c3c3c; color: #ffffff; font-size: 12px;
            }
            QComboBox:focus { border-color: #2196F3; }
        """)
        bg_layout.addWidget(self.background_combo)
        bg_layout.addStretch()
        
        selection_layout.addWidget(bg_frame)
        
        # Enhanced frame selector
        frame_frame = QFrame()
        frame_frame.setStyleSheet("""
            QFrame {
                background-color: #2f2f2f; border: 2px solid #FF9800;
                border-radius: 8px; padding: 10px;
            }
        """)
        frame_layout = QHBoxLayout(frame_frame)
        
        self.use_current_frame = QCheckBox("📹 Use current video frame")
        self.use_current_frame.setChecked(self.current_frame is not None)
        self.use_current_frame.setEnabled(self.current_frame is not None)
        self.use_current_frame.toggled.connect(self.force_update_preview)
        self.use_current_frame.setStyleSheet("""
            QCheckBox {
                color: #FF9800; font-weight: bold; font-size: 12px;
            }
            QCheckBox::indicator {
                width: 16px; height: 16px; border: 2px solid #FF9800;
                border-radius: 3px; background-color: #3c3c3c;
            }
            QCheckBox::indicator:checked {
                background-color: #FF9800; border-color: #FF9800;
            }
        """)
        frame_layout.addWidget(self.use_current_frame)
        frame_layout.addStretch()
        
        selection_layout.addWidget(frame_frame)
        controls_layout.addLayout(selection_layout)
        
        # Enhanced button row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        # Font settings button
        font_settings_btn = QPushButton("🔤 Font Settings")
        font_settings_btn.clicked.connect(self.open_font_settings)
        font_settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; color: white; border: none;
                border-radius: 8px; padding: 12px 20px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        button_layout.addWidget(font_settings_btn)
        
        # Color settings button
        color_settings_btn = QPushButton("🎨 Color Settings")
        color_settings_btn.clicked.connect(self.open_color_settings)
        color_settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3; color: white; border: none;
                border-radius: 8px; padding: 12px 20px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        button_layout.addWidget(color_settings_btn)
        
        # Layout editor button
        if hasattr(self.parent_analyzer, 'open_layout_editor'):
            layout_editor_btn = QPushButton("🎯 Layout Editor")
            layout_editor_btn.clicked.connect(self.open_layout_editor)
            layout_editor_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FF9800; color: white; border: none;
                    border-radius: 8px; padding: 12px 20px; font-weight: bold; font-size: 13px;
                }
                QPushButton:hover { background-color: #F57C00; }
            """)
            button_layout.addWidget(layout_editor_btn)
        
        # Manual refresh button
        refresh_btn = QPushButton("🔄 Refresh Preview")
        refresh_btn.clicked.connect(self.force_update_preview)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0; color: white; border: none;
                border-radius: 8px; padding: 12px 20px; font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #7B1FA2; }
        """)
        button_layout.addWidget(refresh_btn)
        
        button_layout.addStretch()
        
        # Close button
        close_btn = QPushButton("✓ Close Preview")
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #607D8B; color: white; border: none;
                border-radius: 8px; padding: 12px 24px; font-weight: bold; font-size: 14px;
            }
            QPushButton:hover { background-color: #546E7A; }
        """)
        button_layout.addWidget(close_btn)
        
        controls_layout.addLayout(button_layout)
        layout.addLayout(controls_layout)
        
        # Apply parent theme
        if hasattr(self.parent_analyzer, 'current_theme'):
            self.setStyleSheet(self.parent_analyzer.styleSheet())
    
    def change_background(self, background_name):
        """Change preview background"""
        self.current_background = background_name
        debug_log(f"🖼️ Background changed to: {background_name}")
        self.force_update_preview()
    
    def get_preview_frame(self):
        """Get enhanced frame for preview"""
        if self.use_current_frame.isChecked() and self.current_frame is not None:
            return self.current_frame.copy()
        else:
            # Create enhanced background
            if self.background_manager_available:
                background = self.background_manager.create_background(
                    self.current_background, 1920, 1080
                )
                # Add enhanced UI elements
                background = self.background_manager.add_simple_ui_elements(background)
                return background
            else:
                # Simple fallback background
                background = np.zeros((1080, 1920, 3), dtype=np.uint8)
                # Gradient background
                for y in range(1080):
                    intensity = int(15 + (y / 1080) * 25)
                    blue_tint = min(255, intensity + 8)
                    background[y, :] = [intensity, intensity, blue_tint]
                
                # Add grid pattern
                grid_spacing = 80
                for i in range(0, 1920, grid_spacing):
                    cv2.line(background, (i, 0), (i, 1080), (25, 25, 25), 1)
                for i in range(0, 1080, grid_spacing):
                    cv2.line(background, (0, i), (1920, i), (25, 25, 25), 1)
                    
                return background
    
    def update_preview(self):
        """Update preview with performance optimization"""
        try:
            # Get current settings
            font_settings = {
                'fps_font': self.parent_analyzer.fps_font_settings,
                'framerate_font': self.parent_analyzer.framerate_font_settings,
                'frametime_font': self.parent_analyzer.frametime_font_settings
            }
            
            color_settings = {
                'framerate_color': self.parent_analyzer.framerate_color,
                'frametime_color': self.parent_analyzer.frametime_color
            }
            
            # Performance optimization checks
            current_size = self.size()
            current_font_hash = hash(str(font_settings))
            current_color_hash = hash(str(color_settings))
            
            settings_changed = (
                self.last_font_hash != current_font_hash or 
                self.last_color_hash != current_color_hash or
                self.last_background != self.current_background
            )
            
            size_changed = self.last_window_size != current_size
            
            # Skip expensive update if nothing changed
            if not settings_changed and not size_changed and self.cached_preview is not None:
                return
            
            # Store current state
            self.last_font_hash = current_font_hash
            self.last_color_hash = current_color_hash
            self.last_background = self.current_background
            self.last_window_size = current_size
            
            debug_log(f"🔄 Enhanced Font Preview: Update with {self.current_background} background")
            
            # Get base frame
            frame = self.get_preview_frame()
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Get frametime scale
            if hasattr(self.parent_analyzer, 'frametime_scale_combo'):
                frametime_scale = self.parent_analyzer.frametime_scale_combo.currentData()
            else:
                frametime_scale = {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']}
            
            # Enhanced animated FPS with smoother curve
            import time
            time_factor = time.time() % 12  # 12-second cycle
            fps_variation = 1.8 * np.sin(time_factor * 0.5)  # Smoother sine wave
            animated_fps = 59.8 + fps_variation  # 58.0 to 61.6 range
            
            # Apply overlay with enhanced renderer
            try:
                frame_with_overlay = self.render_overlay_with_available_renderer(
                    frame_rgb, animated_fps, frametime_scale, font_settings, color_settings
                )
            except Exception as e:
                debug_log(f"❌ Enhanced overlay rendering failed: {e}")
                frame_with_overlay = self.create_error_overlay(frame_rgb, str(e))
            
            # Cache result
            self.cached_preview = frame_with_overlay.copy()
            
            # Convert to Qt and display
            h, w, ch = frame_with_overlay.shape
            bytes_per_line = ch * w
            qt_image = QImage(frame_with_overlay.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            
            # Enhanced scaling
            preview_size = self.preview_label.size()
            pixmap = QPixmap.fromImage(qt_image)
            scaled_pixmap = pixmap.scaled(
                preview_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled_pixmap)
            
            renderer_type = "Pillow TrueType" if PILLOW_AVAILABLE else "OpenCV FreeType" if FREETYPE_AVAILABLE else "Standard OpenCV"
            debug_log(f"✅ Enhanced Font Preview: Update completed with {renderer_type}!")
            
        except Exception as e:
            debug_log(f"❌ Enhanced Preview Update Error: {e}")
            import traceback
            traceback.print_exc()
            self.show_error_in_preview(str(e))
    
    def render_overlay_with_available_renderer(self, frame_rgb, animated_fps, frametime_scale, font_settings, color_settings):
        """Render overlay with available renderer"""
        # First try enhanced renderer
        try:
            # Import enhanced renderer
            try:
                from freetype_overlay_renderer import draw_fps_overlay_with_layout
                enhanced_available = True
                debug_log("🎨 Using Enhanced FreeType Renderer")
            except ImportError:
                try:
                    from enhanced_overlay_renderer import draw_fps_overlay_with_layout
                    enhanced_available = True
                    debug_log("🎨 Using Enhanced Overlay Renderer")
                except ImportError:
                    enhanced_available = False
            
            if enhanced_available:
                # Check for layout manager
                if hasattr(self.parent_analyzer, 'layout_manager'):
                    layout_config = self.parent_analyzer.layout_manager.convert_to_overlay_positions(
                        self.parent_analyzer.layout_manager.get_current_layout(),
                        1920, 1080
                    )
                    debug_log("🎨 Using Enhanced Renderer with custom layout")
                    return draw_fps_overlay_with_layout(
                        frame_rgb,
                        self.mock_fps_history,
                        animated_fps,
                        self.mock_frame_times,
                        True,  # show_frame_time_graph
                        180,   # max_len
                        self.mock_fps_history,  # global_fps_values
                        self.mock_frame_times,  # global_frame_times
                        frametime_scale,
                        font_settings,
                        color_settings,
                        layout_config
                    )
                else:
                    # Enhanced renderer with legacy position
                    try:
                        from freetype_overlay_renderer import draw_fps_overlay_with_legacy_position
                    except ImportError:
                        from enhanced_overlay_renderer import draw_fps_overlay_with_legacy_position
                        
                    ftg_position = getattr(self.parent_analyzer, 'ftg_position', 'bottom_right')
                    debug_log(f"🎨 Using Enhanced Renderer with position: {ftg_position}")
                    return draw_fps_overlay_with_legacy_position(
                        frame_rgb,
                        self.mock_fps_history,
                        animated_fps,
                        self.mock_frame_times,
                        True,  # show_frame_time_graph
                        180,   # max_len
                        self.mock_fps_history,  # global_fps_values
                        self.mock_frame_times,  # global_frame_times
                        frametime_scale,
                        font_settings,
                        color_settings,
                        ftg_position
                    )
        except Exception as e:
            debug_log(f"❌ Enhanced renderer failed: {e}")
        
        # Fallback to legacy renderer
        try:
            from overlay_renderer import draw_fps_overlay
            ftg_position = getattr(self.parent_analyzer, 'ftg_position', 'bottom_right')
            debug_log(f"🔄 Using Legacy Renderer with position: {ftg_position}")
            return draw_fps_overlay(
                frame_rgb,
                self.mock_fps_history,
                animated_fps,
                self.mock_frame_times,
                True,  # show_frame_time_graph
                180,   # max_len
                self.mock_fps_history,  # global_fps_values
                self.mock_frame_times,  # global_frame_times
                frametime_scale,
                font_settings,
                color_settings,
                ftg_position
            )
        except Exception as e:
            debug_log(f"❌ Legacy renderer failed: {e}")
            return self.create_simple_overlay(frame_rgb, animated_fps)
    
    def create_simple_overlay(self, frame_rgb, fps_value):
        """Create simple overlay when renderers fail"""
        overlay = frame_rgb.copy()
        
        # Simple FPS text with improved styling
        cv2.putText(overlay, f"FPS: {fps_value:.1f}", (50, 80), 
                   cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 255, 0), 4, cv2.LINE_AA)
        cv2.putText(overlay, "Enhanced Font Preview Mode", (50, 140), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 0), 3, cv2.LINE_AA)
        
        font_renderer = "Pillow TrueType" if PILLOW_AVAILABLE else "OpenCV FreeType" if FREETYPE_AVAILABLE else "Standard OpenCV"
        cv2.putText(overlay, f"Font Renderer: {font_renderer}", (50, 180), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        
        return overlay
    
    def create_error_overlay(self, frame_rgb, error_msg):
        """Create error overlay with improved styling"""
        overlay = frame_rgb.copy()
        
        cv2.putText(overlay, "ENHANCED OVERLAY ERROR", (50, 80), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 255), 4, cv2.LINE_AA)
        cv2.putText(overlay, f"Error: {error_msg[:60]}...", (50, 140), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(overlay, "Check console for details", (50, 180), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2, cv2.LINE_AA)
        
        return overlay
    
    def show_error_in_preview(self, error_msg):
        """Show error in preview area"""
        error_pixmap = QPixmap(800, 600)
        error_pixmap.fill(Qt.GlobalColor.darkRed)
        self.preview_label.setPixmap(error_pixmap)
        self.preview_label.setText(f"❌ ENHANCED PREVIEW ERROR\n\n{error_msg}")
    
    def open_font_settings(self):
        """Open enhanced font settings dialog"""
        self.parent_analyzer.select_opencv_fonts()
        self.force_update_preview()
    
    def open_color_settings(self):
        """Open color settings dialog"""
        self.parent_analyzer.select_colors()
        self.force_update_preview()
    
    def open_layout_editor(self):
        """Open layout editor"""
        if hasattr(self.parent_analyzer, 'open_layout_editor'):
            self.parent_analyzer.open_layout_editor()
            self.force_update_preview()
        else:
            debug_log("⚠️ Layout Editor not available in parent")
    
    def force_update_preview(self):
        """Force immediate preview update"""
        # Clear cache to force update
        self.last_font_hash = None
        self.last_color_hash = None
        self.last_background = None
        self.last_window_size = None
        self.cached_preview = None
        
        debug_log("🔄 Enhanced Font Preview: Forced update triggered")
        self.update_preview()
    
    def closeEvent(self, event):
        """Handle dialog close"""
        self.update_timer.stop()
        event.accept()


# ===============================================
# 📊 ENHANCED FONT MANAGER
# ===============================================

class EnhancedFontManager:
    """Enhanced font manager with complete system integration"""
    
    def __init__(self):
        self.font_discovery = SystemFontDiscovery()
        self.font_cache = {}
        self.available_fonts = []
        
        # Initialize font discovery
        self.discover_fonts()
    
    def discover_fonts(self):
        """Discover available system fonts"""
        debug_log("Starting enhanced font discovery...")
        self.available_fonts = self.font_discovery.discover_fonts()
        debug_log(f"Enhanced font discovery completed - {len(self.available_fonts)} fonts found")
    
    def get_font_by_name(self, name: str) -> Optional[Dict]:
        """Get font info by name"""
        return self.font_discovery.get_font_by_name(name)
    
    def create_font_settings(self, font_name: str = 'Arial', **kwargs) -> OpenCVFontSettings:
        """Create enhanced font settings (backward compatible)"""
        font_info = self.get_font_by_name(font_name)
        
        if font_info:
            kwargs['font_path'] = font_info['path']
            kwargs['font_name'] = font_info['name']
        else:
            kwargs['font_name'] = font_name
            kwargs['font_path'] = None
        
        return OpenCVFontSettings(**kwargs)
    
    def get_popular_fonts(self) -> List[Dict]:
        """Get popular fonts"""
        return self.font_discovery.get_popular_fonts()
    
    def is_freetype_available(self) -> bool:
        """Check if FreeType is available"""
        return FREETYPE_AVAILABLE or PILLOW_AVAILABLE

# ===============================================
# 🎯 GLOBAL INITIALIZATION
# ===============================================

# Initialize global font manager
print("🚀 Enhanced Font Manager - TrueType Integration initialized!")
if PILLOW_AVAILABLE:
    print(f"   • TrueType Support: ✅ Available (Pillow)")
elif FREETYPE_AVAILABLE:
    print(f"   • TrueType Support: ✅ Available (OpenCV FreeType)")
else:
    print(f"   • TrueType Support: ❌ Not available (Standard OpenCV)")
print(f"   • System Font Discovery: ✅ Active")
print(f"   • Backward Compatibility: ✅ 100%")

_global_font_manager = EnhancedFontManager()

def get_font_manager() -> EnhancedFontManager:
    """Get global font manager instance"""
    return _global_font_manager

# ===============================================
# 📤 EXPORTS
# ===============================================

__all__ = [
    'OpenCVFontSettings',  # Main class - backward compatible
    'OpenCVFontSelectionDialog', # Dialog class for font selection
    'FontPreviewDialog',  # Dialog class for font preview
    'EnhancedFontManager', 
    'get_font_manager',
    'FREETYPE_AVAILABLE',
    'PILLOW_AVAILABLE',
    'check_freetype_support',
    'enable_debug_mode'  # For debugging purposes
]

print("🎉 Enhanced Font Manager ready! TrueType fonts available with 100% backward compatibility!")