"""
Font Management Module für FPS Analyzer - WITH LIVE PREVIEW
Handles OpenCV font selection, styling, and border options with live preview
"""
import cv2
import numpy as np
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, 
                             QPushButton, QMessageBox, QCheckBox, QSlider, QSpinBox, QGroupBox)
from PyQt6.QtGui import QFont, QFontDatabase, QPixmap, QImage
from PyQt6.QtCore import Qt

# Import our custom widgets
try:
    from ui_manager import CustomSpinBox
except ImportError:
    # Fallback if custom widgets not available
    CustomSpinBox = QSpinBox

class OpenCVFontManager:
    """Manages OpenCV fonts and styling options"""
    
    def __init__(self):
        # OpenCV verfügbare Fonts
        self.opencv_fonts = {
            'HERSHEY_SIMPLEX': cv2.FONT_HERSHEY_SIMPLEX,
            'HERSHEY_PLAIN': cv2.FONT_HERSHEY_PLAIN,
            'HERSHEY_DUPLEX': cv2.FONT_HERSHEY_DUPLEX,
            'HERSHEY_COMPLEX': cv2.FONT_HERSHEY_COMPLEX,
            'HERSHEY_TRIPLEX': cv2.FONT_HERSHEY_TRIPLEX,
            'HERSHEY_COMPLEX_SMALL': cv2.FONT_HERSHEY_COMPLEX_SMALL,
            'HERSHEY_SCRIPT_SIMPLEX': cv2.FONT_HERSHEY_SCRIPT_SIMPLEX,
            'HERSHEY_SCRIPT_COMPLEX': cv2.FONT_HERSHEY_SCRIPT_COMPLEX
        }
        
        # Font-Beschreibungen für bessere UX
        self.font_descriptions = {
            'HERSHEY_SIMPLEX': 'Simplex - Clean, readable (recommended)',
            'HERSHEY_PLAIN': 'Plain - Minimal, thin',
            'HERSHEY_DUPLEX': 'Duplex - Medium weight, good for labels',
            'HERSHEY_COMPLEX': 'Complex - Bold, thick strokes',
            'HERSHEY_TRIPLEX': 'Triplex - Very bold, gaming style',
            'HERSHEY_COMPLEX_SMALL': 'Complex Small - Compact bold',
            'HERSHEY_SCRIPT_SIMPLEX': 'Script Simplex - Italic style',
            'HERSHEY_SCRIPT_COMPLEX': 'Script Complex - Bold italic'
        }
    
    def get_available_fonts(self):
        """Get list of available OpenCV fonts"""
        return list(self.opencv_fonts.keys())
    
    def get_opencv_font(self, font_name):
        """Get OpenCV font constant"""
        return self.opencv_fonts.get(font_name, cv2.FONT_HERSHEY_SIMPLEX)
    
    def get_font_description(self, font_name):
        """Get user-friendly font description"""
        return self.font_descriptions.get(font_name, font_name)

class OpenCVFontSettings:
    """Container for OpenCV font settings"""
    
    def __init__(self, font_name='HERSHEY_SIMPLEX', size=1.0, thickness=2, 
                 bold=False, border_thickness=2, border_color=(0, 0, 0)):
        self.font_name = font_name
        self.size = size
        self.thickness = thickness
        self.bold = bold
        self.border_thickness = border_thickness
        self.border_color = border_color
    
    def get_opencv_font(self):
        """Get OpenCV font constant"""
        font_manager = OpenCVFontManager()
        return font_manager.get_opencv_font(self.font_name)
    
    def get_effective_thickness(self):
        """Get thickness with bold modifier"""
        base_thickness = self.thickness
        if self.bold:
            return base_thickness + 2
        return base_thickness
    
    def to_qfont(self):
        """Convert to QFont for compatibility (approximation)"""
        # Mapping für QFont compatibility
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
        qt_size = int(self.size * 12)  # Approximate conversion
        
        qfont = QFont(qt_family, qt_size)
        qfont.setBold(self.bold)
        return qfont

class OpenCVFontSelectionDialog(QDialog):
    """Dialog for selecting OpenCV fonts and styling options with LIVE PREVIEW"""
    
    def __init__(self, parent, fps_font_settings, framerate_font_settings, frametime_font_settings):
        super().__init__(parent)
        self.setWindowTitle("OpenCV Font & Style Selection")
        self.setModal(True)
        self.resize(700, 600)  # Slightly taller for preview
        
        # Store original settings
        self.fps_settings = fps_font_settings or OpenCVFontSettings()
        self.framerate_settings = framerate_font_settings or OpenCVFontSettings()
        self.frametime_settings = frametime_font_settings or OpenCVFontSettings()
        
        self.font_manager = OpenCVFontManager()
        
        # Setup UI
        self.setup_ui()
        
        # Apply parent theme
        if hasattr(parent, 'current_theme'):
            self.setStyleSheet(parent.styleSheet())
        
        # Initial preview update
        self.update_live_preview()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Info Label
        info_label = QLabel("🎯 OpenCV Font & Style Configuration")
        info_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 5px; font-size: 14px;")
        layout.addWidget(info_label)
        
        # 🎨 NEW: Live Font Preview Area
        self.preview_label = QLabel()
        self.preview_label.setFixedHeight(120)
        self.preview_label.setStyleSheet("""
            QLabel {
                background-color: #1a1a1a; 
                color: white; 
                padding: 10px; 
                border: 2px solid #555; 
                border-radius: 8px;
                font-size: 12px;
            }
        """)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setScaledContents(True)
        layout.addWidget(self.preview_label)
        
        # Font preview area
        old_preview_label = QLabel("Preview: The quick brown fox jumps over the lazy dog 123")
        old_preview_label.setStyleSheet("background-color: #1a1a1a; color: white; padding: 20px; border: 2px solid #555; font-size: 16px;")
        old_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(old_preview_label)
        # Keep reference for compatibility
        self.old_preview_label = old_preview_label
        
        # Create tabs for different font types
        font_groups_layout = QHBoxLayout()
        
        # FPS Font Group
        fps_group = self.create_font_group("🎯 FPS Number", self.fps_settings)
        font_groups_layout.addWidget(fps_group)
        
        # Framerate Font Group
        framerate_group = self.create_font_group("📊 Frame Rate", self.framerate_settings)
        font_groups_layout.addWidget(framerate_group)
        
        # Frametime Font Group
        frametime_group = self.create_font_group("⏱️ Frame Time", self.frametime_settings)
        font_groups_layout.addWidget(frametime_group)
        
        layout.addLayout(font_groups_layout)
        
        # Global Border Settings
        border_group = QGroupBox("🖼️ Global Border Settings")
        border_layout = QGridLayout(border_group)
        
        border_layout.addWidget(QLabel("Border Thickness:"), 0, 0)
        self.global_border_thickness = QSlider(Qt.Orientation.Horizontal)
        self.global_border_thickness.setRange(0, 5)
        self.global_border_thickness.setValue(2)
        self.global_border_thickness.valueChanged.connect(self.update_live_preview)
        border_layout.addWidget(self.global_border_thickness, 0, 1)
        self.global_border_thickness_label = QLabel("2")
        border_layout.addWidget(self.global_border_thickness_label, 0, 2)
        
        border_layout.addWidget(QLabel("Apply to All:"), 1, 0)
        apply_border_btn = QPushButton("Apply Border to All")
        apply_border_btn.clicked.connect(self.apply_global_border)
        border_layout.addWidget(apply_border_btn, 1, 1)
        
        layout.addWidget(border_group)
        
        # Quick Style Presets
        presets_group = QGroupBox("🎨 Quick Style Presets")
        presets_layout = QHBoxLayout(presets_group)
        
        presets = [
            ("📺 Gaming", {
                "fps": OpenCVFontSettings('HERSHEY_TRIPLEX', 1.5, 3, True, 3),
                "framerate": OpenCVFontSettings('HERSHEY_SIMPLEX', 0.6, 2, False, 2),
                "frametime": OpenCVFontSettings('HERSHEY_SIMPLEX', 0.5, 1, False, 1)
            }),
            ("🎯 Professional", {
                "fps": OpenCVFontSettings('HERSHEY_SIMPLEX', 1.2, 2, True, 2),
                "framerate": OpenCVFontSettings('HERSHEY_PLAIN', 0.5, 1, False, 1),
                "frametime": OpenCVFontSettings('HERSHEY_PLAIN', 0.5, 1, False, 1)
            }),
            ("💻 Minimal", {
                "fps": OpenCVFontSettings('HERSHEY_PLAIN', 1.0, 1, False, 1),
                "framerate": OpenCVFontSettings('HERSHEY_PLAIN', 0.4, 1, False, 0),
                "frametime": OpenCVFontSettings('HERSHEY_PLAIN', 0.4, 1, False, 0)
            }),
            ("🔥 Bold", {
                "fps": OpenCVFontSettings('HERSHEY_COMPLEX', 1.8, 4, True, 4),
                "framerate": OpenCVFontSettings('HERSHEY_DUPLEX', 0.7, 2, True, 2),
                "frametime": OpenCVFontSettings('HERSHEY_DUPLEX', 0.6, 2, True, 2)
            })
        ]
        
        for name, preset_data in presets:
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, data=preset_data: self.apply_preset(data))
            presets_layout.addWidget(btn)
        
        layout.addWidget(presets_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # 🔧 FIXED: Update Preview Button - now working
        preview_btn = QPushButton("🔍 Update Preview")
        preview_btn.clicked.connect(self.update_live_preview)
        button_layout.addWidget(preview_btn)
        
        reset_btn = QPushButton("↺ Reset to Defaults")
        reset_btn.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(reset_btn)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        ok_button.setDefault(True)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
    
    def create_font_group(self, title, settings):
        """Create a font configuration group with CustomSpinBox support"""
        group = QGroupBox(title)
        layout = QGridLayout(group)
        
        # Font Family
        layout.addWidget(QLabel("Font:"), 0, 0)
        font_combo = QComboBox()
        for font_name in self.font_manager.get_available_fonts():
            font_combo.addItem(f"{font_name}", font_name)
        font_combo.setCurrentText(settings.font_name)
        font_combo.currentTextChanged.connect(self.update_live_preview)
        layout.addWidget(font_combo, 0, 1)
        
        # Font Size - Using CustomSpinBox if available
        layout.addWidget(QLabel("Size:"), 1, 0)
        if CustomSpinBox != QSpinBox:
            # Use our custom spinbox
            size_spin = CustomSpinBox()
            size_spin.setRange(1, 50)
            size_spin.setValue(int(settings.size * 10))
            size_spin.setSuffix(" (×0.1)")
            size_spin.valueChanged.connect(self.update_live_preview)
        else:
            # Fallback to regular QSpinBox
            size_spin = QSpinBox()
            size_spin.setRange(1, 50)
            size_spin.setValue(int(settings.size * 10))
            size_spin.setSuffix(" (×0.1)")
            size_spin.valueChanged.connect(self.update_live_preview)
        layout.addWidget(size_spin, 1, 1)
        
        # Thickness - Using CustomSpinBox if available
        layout.addWidget(QLabel("Thickness:"), 2, 0)
        if CustomSpinBox != QSpinBox:
            # Use our custom spinbox
            thickness_spin = CustomSpinBox()
            thickness_spin.setRange(1, 10)
            thickness_spin.setValue(settings.thickness)
            thickness_spin.valueChanged.connect(self.update_live_preview)
        else:
            # Fallback to regular QSpinBox
            thickness_spin = QSpinBox()
            thickness_spin.setRange(1, 10)
            thickness_spin.setValue(settings.thickness)
            thickness_spin.valueChanged.connect(self.update_live_preview)
        layout.addWidget(thickness_spin, 2, 1)
        
        # Bold
        bold_check = QCheckBox("Bold (+2 thickness)")
        bold_check.setChecked(settings.bold)
        bold_check.toggled.connect(self.update_live_preview)
        layout.addWidget(bold_check, 3, 0, 1, 2)
        
        # Border Thickness - Using CustomSpinBox if available
        layout.addWidget(QLabel("Border:"), 4, 0)
        if CustomSpinBox != QSpinBox:
            # Use our custom spinbox
            border_spin = CustomSpinBox()
            border_spin.setRange(0, 5)
            border_spin.setValue(settings.border_thickness)
            border_spin.valueChanged.connect(self.update_live_preview)
        else:
            # Fallback to regular QSpinBox
            border_spin = QSpinBox()
            border_spin.setRange(0, 5)
            border_spin.setValue(settings.border_thickness)
            border_spin.valueChanged.connect(self.update_live_preview)
        layout.addWidget(border_spin, 4, 1)
        
        # Store controls for later access
        if "FPS" in title:
            self.fps_controls = {
                'font': font_combo, 'size': size_spin, 'thickness': thickness_spin,
                'bold': bold_check, 'border': border_spin
            }
        elif "Frame Rate" in title:
            self.framerate_controls = {
                'font': font_combo, 'size': size_spin, 'thickness': thickness_spin,
                'bold': bold_check, 'border': border_spin
            }
        else:  # Frame Time
            self.frametime_controls = {
                'font': font_combo, 'size': size_spin, 'thickness': thickness_spin,
                'bold': bold_check, 'border': border_spin
            }
        
        return group
    
    def draw_text_with_border_preview(self, img, text, position, font, font_scale, color, thickness, border_color=(0, 0, 0), border_thickness=2):
        """Draw text with border for preview - optimized for small preview"""
        x, y = position
        
        # Draw border
        for dx in [-border_thickness, 0, border_thickness]:
            for dy in [-border_thickness, 0, border_thickness]:
                if dx != 0 or dy != 0:  # Skip center
                    cv2.putText(img, text, (x + dx, y + dy), font, font_scale, border_color, 
                               thickness + 1, lineType=cv2.LINE_AA)
        
        # Draw main text
        cv2.putText(img, text, position, font, font_scale, color, thickness, lineType=cv2.LINE_AA)
    
    def update_live_preview(self):
        """🎨 FIXED: Update the live font preview with corrected aspect ratio"""
        try:
            # 🔧 FIXED: Better aspect ratio for preview (16:9-ish)
            canvas_width, canvas_height = 600, 120  # Less stretched, better proportions
            canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
            canvas[:] = (26, 26, 26)  # Dark gray background
            
            # Get current settings for each font type
            fps_font = self.fps_controls['font'].currentData()
            fps_size = self.get_widget_value(self.fps_controls['size'], 12) / 10.0
            fps_thickness = self.get_widget_value(self.fps_controls['thickness'], 2)
            fps_bold = self.fps_controls['bold'].isChecked()
            fps_border = self.get_widget_value(self.fps_controls['border'], 2)
            
            framerate_font = self.framerate_controls['font'].currentData()
            framerate_size = self.get_widget_value(self.framerate_controls['size'], 6) / 10.0
            framerate_thickness = self.get_widget_value(self.framerate_controls['thickness'], 1)
            framerate_bold = self.framerate_controls['bold'].isChecked()
            framerate_border = self.get_widget_value(self.framerate_controls['border'], 1)
            
            frametime_font = self.frametime_controls['font'].currentData()
            frametime_size = self.get_widget_value(self.frametime_controls['size'], 5) / 10.0
            frametime_thickness = self.get_widget_value(self.frametime_controls['thickness'], 1)
            frametime_bold = self.frametime_controls['bold'].isChecked()
            frametime_border = self.get_widget_value(self.frametime_controls['border'], 1)
            
            # Get OpenCV font constants
            fps_opencv_font = self.font_manager.get_opencv_font(fps_font)
            framerate_opencv_font = self.font_manager.get_opencv_font(framerate_font)
            frametime_opencv_font = self.font_manager.get_opencv_font(frametime_font)
            
            # Apply bold effect
            fps_final_thickness = fps_thickness + (2 if fps_bold else 0)
            framerate_final_thickness = framerate_thickness + (2 if framerate_bold else 0)
            frametime_final_thickness = frametime_thickness + (2 if frametime_bold else 0)
            
            # 🎨 Draw preview samples as requested
            y_offset = 30
            
            # 1. FPS Number preview: "FPS: 60"
            self.draw_text_with_border_preview(
                canvas, "FPS: 60", 
                (20, y_offset), 
                fps_opencv_font, fps_size * 0.8,  # Scale down for preview
                (0, 255, 0), fps_final_thickness, 
                border_thickness=fps_border
            )
            
            # 2. Frame Rate preview: Font description
            fps_desc = self.font_manager.get_font_description(fps_font).split(' - ')[1] if ' - ' in self.font_manager.get_font_description(fps_font) else fps_font
            framerate_text = f"Font: {fps_desc} | Size: {fps_size:.1f}"
            self.draw_text_with_border_preview(
                canvas, framerate_text, 
                (20, y_offset + 35), 
                framerate_opencv_font, framerate_size * 1.2,  # Scale up for visibility
                (255, 255, 255), framerate_final_thickness, 
                border_thickness=framerate_border
            )
            
            # 3. Frame Time preview: "Thickness X"
            frametime_text = f"Thickness: {fps_final_thickness}"
            self.draw_text_with_border_preview(
                canvas, frametime_text, 
                (20, y_offset + 65), 
                frametime_opencv_font, frametime_size * 1.5,  # Scale up for visibility
                (100, 200, 255), frametime_final_thickness, 
                border_thickness=frametime_border
            )
            
            # Convert to Qt format and display
            canvas_rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            h, w, ch = canvas_rgb.shape
            bytes_per_line = ch * w
            qt_image = QImage(canvas_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            
            # Create pixmap and scale to fit
            pixmap = QPixmap.fromImage(qt_image)
            scaled_pixmap = pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.preview_label.setPixmap(scaled_pixmap)
            
            # Also update the old preview for compatibility
            self.update_old_preview()
            
        except Exception as e:
            print(f"❌ Live preview error: {e}")
            # Fallback to text-only preview
            self.preview_label.setText(f"Preview Error: {str(e)}")
    
    def update_old_preview(self):
        """Update the old preview label (compatibility)"""
        # Get current FPS settings for preview
        fps_font = self.fps_controls['font'].currentData()
        fps_size = self.get_widget_value(self.fps_controls['size'], 12) / 10.0
        fps_thickness = self.get_widget_value(self.fps_controls['thickness'], 2)
        fps_bold = self.fps_controls['bold'].isChecked()
        
        effective_thickness = fps_thickness + (2 if fps_bold else 0)
        
        description = self.font_manager.get_font_description(fps_font)
        preview_text = f"FPS: 60.0 | Font: {description} | Size: {fps_size:.1f} | Thickness: {effective_thickness}"
        
        self.old_preview_label.setText(preview_text)
        
        # Update border thickness label
        border_val = self.global_border_thickness.value()
        self.global_border_thickness_label.setText(str(border_val))
    
    def get_widget_value(self, widget, default=0):
        """Safely get value from widget"""
        if hasattr(widget, 'value'):
            return widget.value()
        return default
    
    def apply_preset(self, preset_data):
        """Apply a font preset to all controls"""
        # Apply FPS settings
        fps_data = preset_data["fps"]
        self.fps_controls['font'].setCurrentText(fps_data.font_name)
        
        fps_size_widget = self.fps_controls['size']
        if hasattr(fps_size_widget, 'setValue'):
            fps_size_widget.setValue(int(fps_data.size * 10))
            
        fps_thickness_widget = self.fps_controls['thickness']
        if hasattr(fps_thickness_widget, 'setValue'):
            fps_thickness_widget.setValue(fps_data.thickness)
            
        self.fps_controls['bold'].setChecked(fps_data.bold)
        
        fps_border_widget = self.fps_controls['border']
        if hasattr(fps_border_widget, 'setValue'):
            fps_border_widget.setValue(fps_data.border_thickness)
        
        # Apply Framerate settings
        framerate_data = preset_data["framerate"]
        self.framerate_controls['font'].setCurrentText(framerate_data.font_name)
        
        framerate_size_widget = self.framerate_controls['size']
        if hasattr(framerate_size_widget, 'setValue'):
            framerate_size_widget.setValue(int(framerate_data.size * 10))
            
        framerate_thickness_widget = self.framerate_controls['thickness']
        if hasattr(framerate_thickness_widget, 'setValue'):
            framerate_thickness_widget.setValue(framerate_data.thickness)
            
        self.framerate_controls['bold'].setChecked(framerate_data.bold)
        
        framerate_border_widget = self.framerate_controls['border']
        if hasattr(framerate_border_widget, 'setValue'):
            framerate_border_widget.setValue(framerate_data.border_thickness)
        
        # Apply Frametime settings
        frametime_data = preset_data["frametime"]
        self.frametime_controls['font'].setCurrentText(frametime_data.font_name)
        
        frametime_size_widget = self.frametime_controls['size']
        if hasattr(frametime_size_widget, 'setValue'):
            frametime_size_widget.setValue(int(frametime_data.size * 10))
            
        frametime_thickness_widget = self.frametime_controls['thickness']
        if hasattr(frametime_thickness_widget, 'setValue'):
            frametime_thickness_widget.setValue(frametime_data.thickness)
            
        self.frametime_controls['bold'].setChecked(frametime_data.bold)
        
        frametime_border_widget = self.frametime_controls['border']
        if hasattr(frametime_border_widget, 'setValue'):
            frametime_border_widget.setValue(frametime_data.border_thickness)
        
        self.update_live_preview()
    
    def apply_global_border(self):
        """Apply global border thickness to all fonts"""
        border_val = self.global_border_thickness.value()
        
        for controls in [self.fps_controls, self.framerate_controls, self.frametime_controls]:
            border_widget = controls['border']
            if hasattr(border_widget, 'setValue'):
                border_widget.setValue(border_val)
        
        self.update_live_preview()
    
    def reset_to_defaults(self):
        """Reset all settings to defaults"""
        defaults = {
            "fps": OpenCVFontSettings('HERSHEY_SIMPLEX', 1.2, 2, True, 2),
            "framerate": OpenCVFontSettings('HERSHEY_SIMPLEX', 0.6, 1, False, 1),
            "frametime": OpenCVFontSettings('HERSHEY_SIMPLEX', 0.5, 1, False, 1)
        }
        self.apply_preset(defaults)
    
    def get_selected_settings(self):
        """Return the selected font settings"""
        fps_settings = OpenCVFontSettings(
            self.fps_controls['font'].currentData(),
            self.get_widget_value(self.fps_controls['size'], 12) / 10.0,
            self.get_widget_value(self.fps_controls['thickness'], 2),
            self.fps_controls['bold'].isChecked(),
            self.get_widget_value(self.fps_controls['border'], 2)
        )
        
        framerate_settings = OpenCVFontSettings(
            self.framerate_controls['font'].currentData(),
            self.get_widget_value(self.framerate_controls['size'], 6) / 10.0,
            self.get_widget_value(self.framerate_controls['thickness'], 1),
            self.framerate_controls['bold'].isChecked(),
            self.get_widget_value(self.framerate_controls['border'], 1)
        )
        
        frametime_settings = OpenCVFontSettings(
            self.frametime_controls['font'].currentData(),
            self.get_widget_value(self.frametime_controls['size'], 5) / 10.0,
            self.get_widget_value(self.frametime_controls['thickness'], 1),
            self.frametime_controls['bold'].isChecked(),
            self.get_widget_value(self.frametime_controls['border'], 1)
        )
        
        return fps_settings, framerate_settings, frametime_settings