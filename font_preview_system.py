"""
Font Preview System für FPS Analyzer - FIXED UPDATE MECHANISM & SMOOTHING
Live preview of font settings with selectable backgrounds and working updates
"""
import cv2
import numpy as np
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox, QComboBox
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, QTimer
from overlay_renderer import draw_fps_overlay
from background_manager import BackgroundManager

class FontPreviewDialog(QDialog):
    """Dialog for previewing font settings with selectable backgrounds - IMPROVED"""
    
    def __init__(self, parent, current_frame=None):
        super().__init__(parent)
        self.parent_analyzer = parent
        self.current_frame = current_frame
        self.setWindowTitle("🎨 Font Preview - Live Demo")
        self.setModal(False)  # Non-modal
        self.resize(1000, 700)
        
        # Background manager
        self.background_manager = BackgroundManager()
        self.current_background = "Dark Gradient"  # Default
        
        # Mock data for preview
        self.mock_fps_history = [60.0, 59.8, 60.1, 58.9, 60.0, 59.7, 60.2, 59.5, 60.0] * 20
        self.mock_frame_times = [16.7, 16.8, 16.6, 17.0, 16.7, 16.9, 16.5, 17.2, 16.7] * 20
        
        # 🔧 IMPROVED: Stable FPS for preview (no flickering)
        self.mock_current_fps = 59.8  # Fixed value for better preview
        
        # Timer for live updates - REDUCED frequency to avoid flicker
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_preview)
        self.update_timer.start(2000)  # Update every 2 seconds instead of 1
        
        # Resize timer
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.handle_resize_finished)
        
        # Cache for performance - IMPROVED
        self.last_font_hash = None
        self.last_color_hash = None
        self.last_background = None
        self.last_window_size = None
        self.cached_preview = None  # Cache the rendered preview
        
        self.setup_ui()
        self.update_preview()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Info header
        info_label = QLabel("🎨 Live Font Preview - Adjust settings and see changes instantly!")
        info_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 5px; font-size: 14px;")
        layout.addWidget(info_label)
        
        # Preview area
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(900, 500)
        self.preview_label.setStyleSheet("border: 2px solid #555; background-color: #1a1a1a;")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setScaledContents(False)
        layout.addWidget(self.preview_label, 1)
        
        # Controls
        controls_layout = QVBoxLayout()
        
        # Background and frame selection row
        selection_layout = QHBoxLayout()
        
        # Background selector
        bg_layout = QHBoxLayout()
        bg_layout.addWidget(QLabel("🖼️ Background:"))
        
        self.background_combo = QComboBox()
        self.background_combo.addItems(self.background_manager.get_available_backgrounds())
        self.background_combo.setCurrentText(self.current_background)
        self.background_combo.currentTextChanged.connect(self.change_background)
        bg_layout.addWidget(self.background_combo)
        
        selection_layout.addLayout(bg_layout)
        selection_layout.addStretch()
        
        # Use current frame checkbox
        self.use_current_frame = QCheckBox("Use Current Video Frame")
        self.use_current_frame.setChecked(self.current_frame is not None)
        self.use_current_frame.setEnabled(self.current_frame is not None)
        self.use_current_frame.toggled.connect(self.force_update_preview)
        selection_layout.addWidget(self.use_current_frame)
        
        controls_layout.addLayout(selection_layout)
        
        # Button row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # Font settings button
        font_settings_btn = QPushButton("🔤 Adjust Font Settings")
        font_settings_btn.clicked.connect(self.open_font_settings)
        button_layout.addWidget(font_settings_btn)
        
        # Color settings button
        color_settings_btn = QPushButton("🎨 Adjust Colors")
        color_settings_btn.clicked.connect(self.open_color_settings)
        button_layout.addWidget(color_settings_btn)
        
        # 🔧 NEW: Manual refresh button
        refresh_btn = QPushButton("🔄 Refresh Preview")
        refresh_btn.clicked.connect(self.force_update_preview)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        button_layout.addWidget(refresh_btn)
        
        button_layout.addStretch()
        
        # Close button
        close_btn = QPushButton("✓ Close Preview")
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        button_layout.addWidget(close_btn)
        
        controls_layout.addLayout(button_layout)
        layout.addLayout(controls_layout)
        
        # Apply parent theme
        if hasattr(self.parent_analyzer, 'current_theme'):
            self.setStyleSheet(self.parent_analyzer.styleSheet())
    
    def change_background(self, background_name):
        """Change the preview background"""
        self.current_background = background_name
        print(f"🖼️ Background changed to: {background_name}")
        self.force_update_preview()
    
    def get_preview_frame(self):
        """Get frame for preview (video frame or selected background)"""
        if self.use_current_frame.isChecked() and self.current_frame is not None:
            # Use actual video frame
            return self.current_frame.copy()
        else:
            # Create selected background
            background = self.background_manager.create_background(
                self.current_background, 1920, 1080
            )
            # Add simple UI elements for context
            background = self.background_manager.add_simple_ui_elements(background)
            return background
    
    def draw_text_with_smooth_border(self, img, text, position, font, font_scale, color, thickness, border_color=(0, 0, 0), border_thickness=2):
        """🎨 IMPROVED: Draw text with better anti-aliasing"""
        x, y = position
        
        # Use LINE_AA for smooth anti-aliased rendering
        line_type = cv2.LINE_AA
        
        # Draw border with multiple passes for smoother effect
        for offset in range(border_thickness, 0, -1):
            for dx in [-offset, 0, offset]:
                for dy in [-offset, 0, offset]:
                    if dx != 0 or dy != 0:
                        cv2.putText(img, text, (x + dx, y + dy), font, font_scale, 
                                   border_color, thickness + offset, lineType=line_type)
        
        # Draw main text with anti-aliasing
        cv2.putText(img, text, position, font, font_scale, color, thickness, lineType=line_type)
    
    def update_preview(self):
        """Update the font preview with IMPROVED performance and stability"""
        try:
            # Get current settings from parent
            font_settings = {
                'fps_font': self.parent_analyzer.fps_font_settings,
                'framerate_font': self.parent_analyzer.framerate_font_settings,
                'frametime_font': self.parent_analyzer.frametime_font_settings
            }
            
            color_settings = {
                'framerate_color': self.parent_analyzer.framerate_color,
                'frametime_color': self.parent_analyzer.frametime_color
            }
            
            # Get current window size
            current_size = self.size()
            
            # Create hash of current settings
            current_font_hash = hash(str(font_settings))
            current_color_hash = hash(str(color_settings))
            
            # 🔧 IMPROVED: More selective update checking
            settings_changed = (
                self.last_font_hash != current_font_hash or 
                self.last_color_hash != current_color_hash or
                self.last_background != self.current_background
            )
            
            size_changed = self.last_window_size != current_size
            
            # Only update if something actually changed
            if not settings_changed and not size_changed and self.cached_preview is not None:
                return  # No changes, skip expensive update
            
            # Store current hashes and settings
            self.last_font_hash = current_font_hash
            self.last_color_hash = current_color_hash
            self.last_background = self.current_background
            self.last_window_size = current_size
            
            print(f"🔄 Font Preview: Updating with background: {self.current_background}")
            
            # Get base frame (now with selectable background)
            frame = self.get_preview_frame()
            
            # Convert to RGB for overlay processing
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Get frametime scale setting
            if hasattr(self.parent_analyzer, 'frametime_scale_combo'):
                frametime_scale = self.parent_analyzer.frametime_scale_combo.currentData()
            else:
                frametime_scale = {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']}
            
            # 🔧 IMPROVED: Create smooth animated FPS for better preview
            # Vary FPS slightly for more realistic preview
            import time
            time_factor = time.time() % 10  # 10-second cycle
            fps_variation = 1.5 * np.sin(time_factor * 0.6)  # Smooth sine wave
            animated_fps = 59.8 + fps_variation  # 58.3 to 61.3 range
            
            # Apply overlay with current settings and STABLE animated FPS
            frame_with_overlay = draw_fps_overlay(
                frame_rgb,
                self.mock_fps_history,
                animated_fps,  # Smooth animated FPS
                self.mock_frame_times,
                True,  # show_frame_time_graph
                180,   # max_len
                self.mock_fps_history,  # global_fps_values
                self.mock_frame_times,  # global_frame_times
                frametime_scale,
                font_settings,
                color_settings,
                getattr(self.parent_analyzer, 'ftg_position', 'bottom_right')
            )
            
            # Cache the preview
            self.cached_preview = frame_with_overlay.copy()
            
            # Convert to Qt format and display
            h, w, ch = frame_with_overlay.shape
            bytes_per_line = ch * w
            qt_image = QImage(frame_with_overlay.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            
            # Scale to fit preview area with smooth transformation
            preview_size = self.preview_label.size()
            pixmap = QPixmap.fromImage(qt_image)
            scaled_pixmap = pixmap.scaled(
                preview_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation  # Smooth scaling
            )
            
            self.preview_label.setPixmap(scaled_pixmap)
            print(f"✅ Font Preview: Update completed! Background: {self.current_background}")
            
        except Exception as e:
            print(f"❌ Preview update error: {e}")
            import traceback
            traceback.print_exc()
            # Show error in preview
            error_pixmap = QPixmap(640, 360)
            error_pixmap.fill(Qt.GlobalColor.darkRed)
            self.preview_label.setPixmap(error_pixmap)
            self.preview_label.setText(f"Preview Error: {str(e)}")
    
    def open_font_settings(self):
        """Open font settings dialog and force refresh"""
        self.parent_analyzer.select_opencv_fonts()
        # Force immediate update after font settings change
        self.force_update_preview()
    
    def open_color_settings(self):
        """Open color settings dialog and force refresh"""
        self.parent_analyzer.select_colors()
        # Force immediate update after color settings change
        self.force_update_preview()
    
    def closeEvent(self, event):
        """Stop timers when closing"""
        self.update_timer.stop()
        self.resize_timer.stop()
        event.accept()
    
    def resizeEvent(self, event):
        """Handle window resize events"""
        super().resizeEvent(event)
        self.resize_timer.stop()
        self.resize_timer.start(500)
    
    def handle_resize_finished(self):
        """Called when user has finished resizing the window"""
        current_size = self.size()
        if self.last_window_size != current_size:
            print(f"🔄 Font Preview: Window resized to {current_size.width()}x{current_size.height()}")
            self.force_update_preview()
    
    def force_update_preview(self):
        """🔧 IMPROVED: Force an immediate preview update"""
        # Clear all cache to force complete refresh
        self.last_font_hash = None
        self.last_color_hash = None
        self.last_background = None
        self.last_window_size = None
        self.cached_preview = None
        
        print("🔄 Font Preview: Forced update triggered")
        self.update_preview()