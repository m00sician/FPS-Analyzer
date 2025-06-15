#!/usr/bin/env python3

"""

FPS Analyzer - Professional FPS Analysis Tool

Updated main application with Video Comparison Feature + settings persistence and Layout Editor integration

🎯 NEW: SEGMENT SELECTION FEATURE - Analyze only selected video segments

COMPLETE VERSION with all features integrated

"""
import sys
import os
import time
import cv2
import numpy as np
import torch
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog, QDialog
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage, QFont
# Import modules

from menu_manager import MenuManager
from ui_manager import UIManager, ThemeManager
from color_manager import ColorSelectionDialog
from analysis_worker import AnalysisWorker, resize_with_aspect_ratio
from settings_manager import SettingsManager
# ✨ NEW IMPORTS für Layout Editor

from layout_editor import LayoutEditorDialog
from layout_manager import LayoutManager
# 🔧 FIXED: Safe import of OpenCVFontSettings

try:
    from font_manager import OpenCVFontSettings
    FONT_MANAGER_AVAILABLE = True
    print("✅ OpenCVFontSettings imported successfully")
except ImportError as e:
    print(f"⚠️ Could not import OpenCVFontSettings: {e}")
    print("🔄 Creating fallback OpenCVFontSettings class")
    FONT_MANAGER_AVAILABLE = False
    # Create a fallback OpenCVFontSettings class

    class OpenCVFontSettings:
        """Fallback OpenCVFontSettings class"""

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
            """Get thickness with bold modifier"""

            base_thickness = self.thickness

            if self.bold:

                return base_thickness + 2

            return base_thickness
        def to_qfont(self):

            """Convert to QFont for compatibility"""
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
            qt_size = int(self.size * 12)
            qfont = QFont(qt_family, qt_size)
            qfont.setBold(self.bold)
            return qfont
class FPSAnalyzer(QMainWindow):
    """Main FPS Analyzer Application with Video Comparison Feature + settings persistence and Layout Editor + Segment Selection"""
    def __init__(self):

        super().__init__()

        self.setWindowTitle('🎯 FPS Analyzer - Professional Video Analysis v2.5 (with Segment Selection)')

        self.resize(1600, 1000)
        # Core properties

        self.video_cap = None

        self.playback_timer = QTimer(self)

        self.playback_timer.timeout.connect(self.next_frame)

        self.analysis_worker = None

        self.cuda_available = torch.cuda.is_available()
        # 🎯 NEW: Segment Selection variables

        self.start_frame = None

        self.end_frame = None

        self.total_frames = 0

        self.video_fps = 30.0  # Default FPS

        self.segment_state = 0  # 0=set_start, 1=set_end, 2=complete
        # Preview settings

        self.internal_resolution = (1920, 1080)

        self.preview_quality = cv2.INTER_LANCZOS4
        # Settings Manager for persistence

        self.settings_manager = SettingsManager()
        # ✨ NEW: Layout Manager for custom element positioning

        self.layout_manager = LayoutManager(self.settings_manager)
        # Load saved settings

        saved_settings = self.settings_manager.load_settings()
        # ✨ NEW: Load saved layout

        saved_layout = saved_settings.get('custom_layout', None)

        if saved_layout:

            self.layout_manager.set_current_layout(saved_layout)

            print("✅ Custom layout loaded from settings")
        # 🎯 NEW: Load saved segment settings - REMOVED (video-specific)

        # self.start_frame = saved_settings.get('last_start_frame', None)

        # self.end_frame = saved_settings.get('last_end_frame', None)

        self.start_frame = None

        self.end_frame = None
        # Set initial segment state 

        self.segment_state = 0  # Always start fresh
        # 🔧 FIXED: Font settings initialization with fallback

        self.initialize_font_settings(saved_settings)
        # Legacy QFont compatibility

        self.fps_font = QFont("Arial", 12)

        self.framerate_font = QFont("Arial", 10)

        self.frametime_font = QFont("Arial", 9)
        # Color settings - Load from saved settings

        self.framerate_color = saved_settings.get('framerate_color', '#00FF00')

        self.frametime_color = saved_settings.get('frametime_color', '#00FF00')
        # Theme - Load from saved settings

        self.current_theme = saved_settings.get('theme', 'dark')
        # Initialize components

        self.setup_application()
        
    def initialize_font_settings(self, saved_settings):
        """🔧 ENHANCED: Initialize font settings with TrueType support"""
        try:
            print("🎨 Initializing Enhanced Font System with TrueType support...")
            
            # Import enhanced font manager
            from font_manager import OpenCVFontSettings, get_font_manager, PILLOW_AVAILABLE, FREETYPE_AVAILABLE
            
            # Get font manager instance
            font_manager = get_font_manager()
            
            print(f"✅ Font Manager Status:")
            print(f"   • Pillow/TrueType Support: {'✅ Available' if PILLOW_AVAILABLE else '❌ Not Available'}")
            print(f"   • OpenCV FreeType Support: {'✅ Available' if FREETYPE_AVAILABLE else '❌ Not Available'}")
            print(f"   • System Fonts: {len(font_manager.available_fonts)} discovered")
            
            # FPS Font Settings - DEFAULT TO BEBAS NEUE
            fps_font_name = saved_settings.get('fps_font_name', 'BebasNeue-Regular')
            if not isinstance(fps_font_name, str):
                fps_font_name = 'BebasNeue-Regular'
                
            self.fps_font_settings = OpenCVFontSettings(
                font_path=saved_settings.get('fps_font_path', None),
                font_name=fps_font_name,
                size=saved_settings.get('fps_font_size', 32),
                thickness=saved_settings.get('fps_font_thickness', 3),
                bold=saved_settings.get('fps_font_bold', True),
                border_thickness=saved_settings.get('fps_font_border', 3),
                text_color=(255, 255, 255),
                border_color=(0, 0, 0)
            )
            
            # Framerate Font Settings - DEFAULT TO BEBAS NEUE
            framerate_font_name = saved_settings.get('framerate_font_name', 'BebasNeue-Regular')
            if not isinstance(framerate_font_name, str):
                framerate_font_name = 'BebasNeue-Regular'
                
            self.framerate_font_settings = OpenCVFontSettings(
                font_path=saved_settings.get('framerate_font_path', None),
                font_name=framerate_font_name,
                size=saved_settings.get('framerate_font_size', 16),
                thickness=saved_settings.get('framerate_font_thickness', 2),
                bold=saved_settings.get('framerate_font_bold', False),
                border_thickness=saved_settings.get('framerate_font_border', 2),
                text_color=(255, 255, 255),
                border_color=(0, 0, 0)
            )
            
            # Frametime Font Settings - DEFAULT TO BEBAS NEUE
            frametime_font_name = saved_settings.get('frametime_font_name', 'BebasNeue-Regular')
            if not isinstance(frametime_font_name, str):
                frametime_font_name = 'BebasNeue-Regular'
                
            self.frametime_font_settings = OpenCVFontSettings(
                font_path=saved_settings.get('frametime_font_path', None),
                font_name=frametime_font_name,
                size=saved_settings.get('frametime_font_size', 14),
                thickness=saved_settings.get('frametime_font_thickness', 1),
                bold=saved_settings.get('frametime_font_bold', False),
                border_thickness=saved_settings.get('frametime_font_border', 1),
                text_color=(255, 255, 255),
                border_color=(0, 0, 0)
            )
            
            # Status summary
            print(f"✅ Enhanced Font Settings initialized successfully:")
            print(f"   • FPS Font: {self.fps_font_settings.font_name}")
            print(f"   • Framerate Font: {self.framerate_font_settings.font_name}")
            print(f"   • Frametime Font: {self.frametime_font_settings.font_name}")
            
        except Exception as e:
            print(f"⚠️ Error initializing enhanced font settings: {e}")
            # ... rest of the error handling
    
    def setup_application(self):

        """Initialize all application components"""

        # Create managers

        self.ui_manager = UIManager(self)
        self.menu_manager = MenuManager(self)
        self.theme_manager = ThemeManager(self)
        # Setup UI and menus

        self.ui_manager.create_main_ui()
        self.menu_manager.create_all_menus()
        # Apply saved theme

        self.apply_theme(self.current_theme)
        # Load saved UI settings

        self.load_ui_settings()
        self.log("✓ FPS Analyzer initialized successfully with saved settings and segment selection!")
    def load_ui_settings(self):
        """Load saved UI settings into widgets - UPDATED for opencv handling"""

        saved_settings = self.settings_manager.load_settings()
        try:

            # Load resolution setting

            saved_resolution = saved_settings.get('output_resolution', (1920, 1080))

            for i in range(self.resolution_combo.count()):

                if self.resolution_combo.itemData(i) == saved_resolution:

                    self.resolution_combo.setCurrentIndex(i)

                    break
            # Load bitrate setting with proper opencv handling

            saved_bitrate = saved_settings.get('bitrate', 60)
            if saved_bitrate == 'opencv':

                # Find and select the 'opencv' option

                for i in range(self.bitrate_combo.count()):

                    if self.bitrate_combo.itemData(i) == 'opencv':

                        self.bitrate_combo.setCurrentIndex(i)

                        break

            elif isinstance(saved_bitrate, int):

                # Find and select the numeric bitrate

                for i in range(self.bitrate_combo.count()):

                    item_data = self.bitrate_combo.itemData(i)

                    if isinstance(item_data, str) and item_data.isdigit() and int(item_data) == saved_bitrate:

                        self.bitrate_combo.setCurrentIndex(i)

                        break
            # Update the method label immediately

            if hasattr(self.ui_manager, 'update_bitrate_method_label'):

                self.ui_manager.update_bitrate_method_label()
            # Load frametime scale setting

            saved_frametime_scale = saved_settings.get('frametime_scale_index', 1)

            if 0 <= saved_frametime_scale < self.frametime_scale_combo.count():

                self.frametime_scale_combo.setCurrentIndex(saved_frametime_scale)
            # Load sensitivity setting

            saved_sensitivity_index = saved_settings.get('sensitivity_index', 2)

            if 0 <= saved_sensitivity_index < self.sensitivity_combo.count():

                self.sensitivity_combo.setCurrentIndex(saved_sensitivity_index)
            # Load preview settings

            saved_internal_res = saved_settings.get('internal_resolution', (1920, 1080))

            self.internal_resolution = saved_internal_res
            # 🎯 NEW: Update segment display if segments are loaded

            if self.start_frame is not None or self.end_frame is not None:

                self.update_segment_display()
            self.log(f"✓ Loaded saved settings: {saved_resolution}, bitrate: {saved_bitrate}")
        except Exception as e:

            self.log(f"⚠️ Could not load some UI settings: {e}")
    def save_current_settings(self):
        """🔧 ENHANCED: Save current settings including TrueType font paths"""
        try:
            # Get current bitrate value properly
            current_bitrate = 60  # fallback
            if hasattr(self, 'bitrate_combo'):
                bitrate_data = self.bitrate_combo.currentData()
                if bitrate_data == 'opencv':
                    current_bitrate = 'opencv'
                elif isinstance(bitrate_data, str) and bitrate_data.isdigit():
                    current_bitrate = int(bitrate_data)
                else:
                    current_bitrate = 60

            # 🎨 ENHANCED: Collect font settings with TrueType paths
            settings = {
                # Enhanced font settings with TrueType support
                'fps_font_name': self.fps_font_settings.font_name,
                'fps_font_path': getattr(self.fps_font_settings, 'font_path', None),
                'fps_font_size': self.fps_font_settings.size,
                'fps_font_thickness': self.fps_font_settings.thickness,
                'fps_font_bold': self.fps_font_settings.bold,
                'fps_font_border': getattr(self.fps_font_settings, 'border_thickness', 2),

                'framerate_font_name': self.framerate_font_settings.font_name,
                'framerate_font_path': getattr(self.framerate_font_settings, 'font_path', None),
                'framerate_font_size': self.framerate_font_settings.size,
                'framerate_font_thickness': self.framerate_font_settings.thickness,
                'framerate_font_bold': self.framerate_font_settings.bold,
                'framerate_font_border': getattr(self.framerate_font_settings, 'border_thickness', 2),

                'frametime_font_name': self.frametime_font_settings.font_name,
                'frametime_font_path': getattr(self.frametime_font_settings, 'font_path', None),
                'frametime_font_size': self.frametime_font_settings.size,
                'frametime_font_thickness': self.frametime_font_settings.thickness,
                'frametime_font_bold': self.frametime_font_settings.bold,
                'frametime_font_border': getattr(self.frametime_font_settings, 'border_thickness', 2),

                # Color settings
                'framerate_color': self.framerate_color,
                'frametime_color': self.frametime_color,

                # UI settings
                'output_resolution': self.resolution_combo.currentData() if hasattr(self, 'resolution_combo') else (1920, 1080),
                'bitrate': current_bitrate,
                'frametime_scale_index': self.frametime_scale_combo.currentIndex() if hasattr(self, 'frametime_scale_combo') else 1,
                'sensitivity_index': self.sensitivity_combo.currentIndex() if hasattr(self, 'sensitivity_combo') else 2,

                # Other settings
                'theme': self.current_theme,
                'ftg_position': getattr(self, 'ftg_position', 'bottom_right'),
                'internal_resolution': self.internal_resolution,

                # Layout settings
                'custom_layout': self.layout_manager.get_current_layout() if hasattr(self, 'layout_manager') else None,
                
                # Enhanced font system info
                'font_system_version': '2.0_freetype',
                'freetype_available': getattr(self.fps_font_settings, 'is_freetype_available', lambda: False)()
            }

            self.settings_manager.save_settings(settings)
            
            # Enhanced status message
            font_status = "TrueType" if settings.get('freetype_available', False) else "Standard"
            self.log(f"✅ Enhanced settings saved successfully (Font System: {font_status})")

        except Exception as e:
            self.log(f"❌ Could not save enhanced settings: {e}")
    def show_font_preview(self):
        """🔧 ENHANCED: Show enhanced font preview dialog with TrueType support"""

        try:

            # Import enhanced font preview

            from font_manager import FontPreviewDialog, FREETYPE_AVAILABLE
            # Get current frame if video is loaded

            current_frame = None

            if self.video_cap and self.video_cap.isOpened():

                current_pos = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)

                ret, frame = self.video_cap.read()

                if ret:

                    current_frame = frame

                    self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, current_pos - 1))
            # Open enhanced preview dialog

            preview_dialog = FontPreviewDialog(self, current_frame)

            preview_dialog.show()
            font_status = "TrueType" if FREETYPE_AVAILABLE else "Standard OpenCV"

            self.log(f"🎨 Enhanced Font Preview opened - {font_status} rendering active!")
        except ImportError as e:

            self.log(f"❌ Could not open enhanced font preview: {e}")

            # Fallback to basic message

            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.information(self, 'Enhanced Font Preview', 

                                f'Enhanced Font Preview not available:\n{str(e)}\n\n'

                                'Please ensure font_manager.py is up to date.')

        except Exception as e:

            self.log(f"❌ Enhanced font preview error: {e}")

            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, 'Enhanced Font Preview Error', 

                            f'Enhanced font preview error:\n{str(e)}')
    def select_opencv_fonts(self):

        """🔧 ENHANCED: Open enhanced font selection dialog with TrueType support"""
        try:

            # Import enhanced font selection dialog

            from font_manager import OpenCVFontSelectionDialog, FREETYPE_AVAILABLE
            from PyQt6.QtWidgets import QDialog
            # Open enhanced dialog

            dialog = OpenCVFontSelectionDialog(self, self.fps_font_settings, 
                                            self.framerate_font_settings, self.frametime_font_settings)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                fps_settings, framerate_settings, frametime_settings = dialog.get_selected_settings()
                # Update font settings

                self.fps_font_settings = fps_settings
                self.framerate_font_settings = framerate_settings
                self.frametime_font_settings = frametime_settings
                # Update QFont for compatibility (if needed)

                if hasattr(fps_settings, 'to_qfont'):
                    self.fps_font = fps_settings.to_qfont()
                    self.framerate_font = framerate_settings.to_qfont()
                    self.frametime_font = frametime_settings.to_qfont()
                # Enhanced logging

                fps_type = "TrueType" if fps_settings.is_freetype_available() else "OpenCV"
                framerate_type = "TrueType" if framerate_settings.is_freetype_available() else "OpenCV"
                frametime_type = "TrueType" if frametime_settings.is_freetype_available() else "OpenCV"
                self.log(f"✅ Enhanced Fonts updated:")
                self.log(f"  • FPS: {fps_settings.font_name} ({fps_type}) Size:{fps_settings.size}")
                self.log(f"  • Framerate: {framerate_settings.font_name} ({framerate_type}) Size:{framerate_settings.size}")
                self.log(f"  • Frametime: {frametime_settings.font_name} ({frametime_type}) Size:{frametime_settings.size}")
                # Save enhanced settings

                self.save_current_settings()
        except ImportError as e:
            self.log(f"❌ Enhanced font selection not available: {e}")

            # Fallback to basic message

            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, 'Enhanced Font Selection', 
                                f'Enhanced Font Selection not available:\n{str(e)}\n\n'
                                'Using standard OpenCV fonts.')
        except Exception as e:
            self.log(f"❌ Enhanced font selection error: {e}")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, 'Enhanced Font Selection Error', 
                            f'Enhanced font selection error:\n{str(e)}')
    # ==========================================

    # 🎯 NEW: SEGMENT SELECTION METHODS

    # ==========================================
    def handle_segment_button(self):
        """🎯 NEW: Handle the main segment button - toggles between start/end"""

        if not self.video_cap or not self.video_cap.isOpened():

            self.log("⚠️ No video loaded")

            return
        current_frame = int(self.video_cap.get(cv2.CAP_PROP_POS_FRAMES))
        # Validate frame number

        if current_frame < 0:

            current_frame = 0

        elif current_frame >= self.total_frames:

            current_frame = self.total_frames - 1
        if self.segment_state == 0:

            # Set start point

            self.start_frame = current_frame

            self.segment_state = 1

            time_str = self.frame_to_time_string(current_frame)

            self.log(f"📍 Start point set at frame {current_frame} ({time_str})")
        elif self.segment_state == 1:

            # Set end point

            if current_frame <= self.start_frame:

                QMessageBox.warning(self, 'Invalid Selection', 

                                   f'End point must be after start point!\n\n'

                                   f'Start: {self.frame_to_time_string(self.start_frame)}\n'

                                   f'Current: {self.frame_to_time_string(current_frame)}\n\n'

                                   f'Please seek to a frame after the start point.')

                return
            self.end_frame = current_frame

            self.segment_state = 2

            time_str = self.frame_to_time_string(current_frame)

            duration_frames = self.end_frame - self.start_frame

            duration_time = self.frame_to_time_string(duration_frames)

            self.log(f"📍 End point set at frame {current_frame} ({time_str})")

            self.log(f"📊 Segment duration: {duration_frames} frames ({duration_time})")
        # Update UI

        self.update_segment_display()

        self.update_segment_buttons()
        # Don't save settings on every segment change - too frequent
    def clear_selection(self):

        """Clear segment selection"""
        self.start_frame = None
        self.end_frame = None
        self.segment_state = 0
        self.update_segment_display()
        self.update_segment_buttons()
        self.log("🗑️ Segment selection cleared")
        # Don't save settings - segments are video-specific
    def frame_to_time_string(self, frame_number):
        """Convert frame number to time string (MM:SS or HH:MM:SS)"""

        if frame_number < 0:

            return "00:00"
        seconds = frame_number / self.video_fps

        hours = int(seconds // 3600)

        minutes = int((seconds % 3600) // 60)

        seconds = int(seconds % 60)
        if hours > 0:

            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        else:

            return f"{minutes:02d}:{seconds:02d}"
    def update_segment_display(self):

        """Update segment info display"""
        if not hasattr(self, 'segment_info_label'):
            return  # UI not ready yet
        if self.start_frame is None and self.end_frame is None:
            self.segment_info_label.setText("No segment")
            self.segment_info_label.setStyleSheet("""
                QLabel {
                    color: #aaaaaa; font-size: 11px; padding: 6px 8px;
                    background-color: #1a1a1a; border-radius: 3px;
                    border: 1px solid #444;
                }
            """)

            return
        if self.start_frame is not None and self.end_frame is not None:

            # Full selection

            start_time = self.frame_to_time_string(self.start_frame)

            end_time = self.frame_to_time_string(self.end_frame)

            duration_frames = self.end_frame - self.start_frame

            duration_time = self.frame_to_time_string(duration_frames)
            # Calculate percentage of total video

            percentage = (duration_frames / self.total_frames * 100) if self.total_frames > 0 else 0
            text = f"{start_time} → {end_time} ({percentage:.0f}%)"

            self.segment_info_label.setText(text)

            self.segment_info_label.setStyleSheet("""

                QLabel {

                    color: #4CAF50; font-size: 11px; padding: 6px 8px; font-weight: bold;

                    background-color: #1a1a1a; border-radius: 3px;

                    border: 1px solid #4CAF50;

                }

            """)
        elif self.start_frame is not None:

            # Only start set

            start_time = self.frame_to_time_string(self.start_frame)
            text = f"Start: {start_time}"
            self.segment_info_label.setText(text)
            self.segment_info_label.setStyleSheet("""
                QLabel {
                    color: #FF9800; font-size: 11px; padding: 6px 8px; font-weight: bold;
                    background-color: #1a1a1a; border-radius: 3px;
                    border: 1px solid #FF9800;
                }
            """)
    def update_segment_buttons(self):

        """🎯 NEW: Update segment button state and labels"""
        if not hasattr(self, 'segment_btn'):
            return  # UI not ready yet
        if self.segment_state == 0:

            # Ready to set start

            self.segment_btn.setText("📍 Set Start Point")
            self.segment_btn.setStyleSheet("""
                QPushButton {
                    font-size: 12px; padding: 6px 12px; 
                    background-color: #2E7D32; color: white; 
                    border: none; border-radius: 4px; font-weight: bold;
                }
                QPushButton:hover { background-color: #4CAF50; }
                QPushButton:disabled { background-color: #404040; color: #666; }
            """)

            self.segment_btn.setEnabled(True)
        elif self.segment_state == 1:

            # Ready to set end

            start_time = self.frame_to_time_string(self.start_frame) if self.start_frame is not None else "00:00"

            self.segment_btn.setText(f"📍 Set End Point")

            self.segment_btn.setStyleSheet("""

                QPushButton {

                    font-size: 12px; padding: 6px 12px; 

                    background-color: #C62828; color: white; 

                    border: none; border-radius: 4px; font-weight: bold;

                }

                QPushButton:hover { background-color: #f44336; }

                QPushButton:disabled { background-color: #404040; color: #666; }

            """)
            self.segment_btn.setEnabled(True)
        elif self.segment_state == 2:

            # Selection complete

            duration_frames = self.end_frame - self.start_frame if (self.start_frame is not None and self.end_frame is not None) else 0
            duration_time = self.frame_to_time_string(duration_frames)
            self.segment_btn.setText(f"✅ Complete ({duration_time})")
            self.segment_btn.setStyleSheet("""
                QPushButton {
                    font-size: 12px; padding: 6px 12px; 
                    background-color: #4CAF50; color: white; 
                    border: 1px solid #66BB6A; border-radius: 4px; font-weight: bold;
                }
                QPushButton:hover { background-color: #66BB6A; }
                QPushButton:disabled { background-color: #404040; color: #666; }
            """)

            self.segment_btn.setEnabled(False)  # Disabled when complete
        # Enable/disable clear button

        has_selection = self.start_frame is not None or self.end_frame is not None

        self.clear_selection_btn.setEnabled(has_selection)
    def enable_segment_controls(self, enable=True):

        """Enable or disable segment controls when video is loaded/unloaded"""
        if not hasattr(self, 'segment_btn'):
            return  # UI not ready yet
        if enable:

            # Only enable main button if not in complete state

            self.segment_btn.setEnabled(self.segment_state != 2)
        else:
            self.segment_btn.setEnabled(False)
        # Clear button depends on selection

        has_selection = self.start_frame is not None or self.end_frame is not None
        self.clear_selection_btn.setEnabled(enable and has_selection)
    # ==========================================

    # END OF SEGMENT SELECTION METHODS

    # ==========================================
    # ✨ NEW: Layout Editor Methods

    def open_layout_editor(self):
        """Open the layout editor dialog"""

        current_layout = self.layout_manager.get_current_layout()
        # Create layout editor dialog

        layout_dialog = LayoutEditorDialog(self, current_layout)

        layout_dialog.layout_changed.connect(self.on_layout_changed)
        # Show dialog

        layout_dialog.show()

        self.log("🎨 Layout Editor opened - design your custom FPS overlay!")
    def on_layout_changed(self, new_layout):

        """Handle layout changes from editor"""
        success = self.layout_manager.set_current_layout(new_layout)
        if success:
            self.log("✅ Custom layout applied successfully!")

            # Update current frame preview if video is loaded

            self.refresh_current_frame()

            # Save settings

            self.save_current_settings()
        else:
            self.log("❌ Failed to apply layout - invalid configuration")
    # ===== BATCH PROCESSOR =====

    def open_batch_processor(self):
        """Open batch processor dialog"""

        try:

            from batch_processor import BatchProcessorDialog
            dialog = BatchProcessorDialog(self)

            dialog.exec()
            self.log("📦 Batch Processor opened")
        except ImportError as e:

            self.log(f"❌ Could not open Batch Processor: {e}")

            QMessageBox.warning(self, 'Batch Processor Error', 

                               f'Could not open Batch Processor:\n{str(e)}\n\nPlease check that batch_processor.py is available.')

        except Exception as e:

            self.log(f"❌ Batch Processor error: {e}")

            QMessageBox.warning(self, 'Batch Processor Error', f'Batch Processor error:\n{str(e)}')
    # ===== VIDEO COMPARISON =====

    def open_comparison_creator(self):

        """Open video comparison creator dialog"""
        try:
            from comparison_creator import ComparisonCreatorDialog
            dialog = ComparisonCreatorDialog(self)
            dialog.exec()
            self.log("📊 Video Comparison Creator opened")
        except ImportError as e:
            self.log(f"❌ Could not open Comparison Creator: {e}")
            QMessageBox.warning(self, 'Comparison Creator Error', 
                               f'Could not open Video Comparison Creator:\n{str(e)}\n\nPlease check that comparison_creator.py is available.')
        except Exception as e:
            self.log(f"❌ Comparison Creator error: {e}")
            QMessageBox.warning(self, 'Comparison Creator Error', f'Comparison Creator error:\n{str(e)}')
    # ===== THEME MANAGEMENT =====

    def apply_theme(self, theme):
        """Apply application theme and save preference"""

        self.current_theme = theme

        if theme == "dark":

            self.setStyleSheet(self.theme_manager.get_dark_theme())

        elif theme == "light":

            self.setStyleSheet(self.theme_manager.get_light_theme())
        # Save theme preference

        self.save_current_settings()
    # ===== PREVIEW SETTINGS =====

    def set_internal_resolution(self, width, height):

        """Set internal preview resolution and save"""
        self.internal_resolution = (width, height)
        self.log(f"✓ Preview internal resolution set to {width}x{height}")
        # Update menu checkmarks

        if hasattr(self, 'resolution_actions'):
            for action in self.resolution_actions:
                action.setChecked(f"{width}x{height}" in action.text())
        self.refresh_current_frame()
        self.save_current_settings()
    def set_preview_quality(self, interpolation):
        """Set preview quality and save"""

        self.preview_quality = interpolation

        quality_names = {

            cv2.INTER_NEAREST: "Fastest",

            cv2.INTER_LINEAR: "Fast", 

            cv2.INTER_CUBIC: "Good",

            cv2.INTER_LANCZOS4: "Best"

        }

        self.log(f"✓ Preview quality set to {quality_names.get(interpolation, 'Unknown')}")
        # Update menu checkmarks

        if hasattr(self, 'quality_actions'):

            for action in self.quality_actions:

                action.setChecked(interpolation in [cv2.INTER_NEAREST, cv2.INTER_LINEAR, cv2.INTER_CUBIC, cv2.INTER_LANCZOS4] and 

                                str(interpolation) in action.text())
        self.refresh_current_frame()

        self.save_current_settings()
    def refresh_current_frame(self):

        """Refresh currently displayed frame"""
        if hasattr(self, 'video_cap') and self.video_cap and self.video_cap.isOpened():
            current_pos = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)
            ret, frame = self.video_cap.read()
            if ret:
                self.display_frame(frame)
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, current_pos - 1))
    def resizeEvent(self, event):
        """Handle window resize"""

        super().resizeEvent(event)

        self.refresh_current_frame()
    # ===== MENU ACTIONS =====

    def toggle_log_visibility(self):

        """Toggle log visibility"""
        is_visible = self.log_action.isChecked()
        self.log_text.setVisible(is_visible)
    def toggle_cuda(self):
        """Toggle CUDA setting"""

        is_enabled = self.cuda_action.isChecked()

        self.use_cuda_checkbox.setChecked(is_enabled)
    def toggle_frametime_graph(self):

        """Toggle frametime graph"""
        is_enabled = self.frametime_action.isChecked()
        self.show_frametime_checkbox.setChecked(is_enabled)
    # ===== FONT PREVIEW SYSTEM =====

    def show_font_preview(self):
        """Show live font preview dialog"""

        try:

            from font_manager import FontPreviewDialog
            # Get current frame if video is loaded

            current_frame = None

            if self.video_cap and self.video_cap.isOpened():

                current_pos = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)

                ret, frame = self.video_cap.read()

                if ret:

                    current_frame = frame

                    self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, current_pos - 1))
            # Open preview dialog

            preview_dialog = FontPreviewDialog(self, current_frame)

            preview_dialog.show()
            self.log("🎨 Font preview opened - adjust settings to see live changes!")
        except ImportError as e:

            self.log(f"❌ Could not open font preview: {e}")

            QMessageBox.warning(self, 'Font Preview Error', 

                               f'Could not open font preview:\n{str(e)}\n\nPlease check that font_manager.py is available.')

        except Exception as e:

            self.log(f"❌ Font preview error: {e}")

            QMessageBox.warning(self, 'Font Preview Error', f'Font preview error:\n{str(e)}')
    # ===== PNG ALPHA SEQUENCE EXPORT =====

    def export_png_alpha_sequence(self):

        """🎬 Export PNG Alpha Sequence for Premiere Pro"""

        # Validate input

        input_file = self.input_edit.text().strip()
        if not input_file or not os.path.exists(input_file):
            QMessageBox.warning(self, 'Error', 'Please select a valid input video file first')
            return
        # Select output directory

        output_dir = QFileDialog.getExistingDirectory(
            self, 'Select Output Directory for PNG Sequence', 
            os.path.dirname(input_file)
        )
        if not output_dir:
            return
        # Create subfolder for sequence

        sequence_name = f"{os.path.splitext(os.path.basename(input_file))[0]}_graphs"
        sequence_dir = os.path.join(output_dir, sequence_name)
        os.makedirs(sequence_dir, exist_ok=True)
        # Get current settings

        settings = self.get_current_settings()
        # Start export

        self.log(f"🎬 Starting PNG Alpha Sequence Export...")
        self.log(f"📁 Output Directory: {sequence_dir}")
        try:
            from png_sequence_exporter import PNGSequenceExporter
            self.png_exporter = PNGSequenceExporter(input_file, sequence_dir, settings)
            self.png_exporter.progress_update.connect(self.on_png_export_progress)
            self.png_exporter.export_complete.connect(self.on_png_export_complete)
            # Update UI

            self.export_png_sequence_btn.setEnabled(False)
            self.export_png_sequence_btn.setText('🎬 Exporting...')
            self.png_exporter.start()
        except ImportError as e:
            self.log(f"❌ PNG Export not available: {e}")
            QMessageBox.warning(self, 'Export Error', f'PNG Sequence Export not available:\n{str(e)}')
    def on_png_export_progress(self, progress, message):
        """Handle PNG export progress"""

        self.status_label.setText(message)

        if progress % 100 == 0:  # Log every 100 frames

            self.log(message)
    def on_png_export_complete(self, success, message, total_frames):

        """Handle PNG export completion"""
        self.png_exporter = None
        self.export_png_sequence_btn.setEnabled(True)
        self.export_png_sequence_btn.setText('🎬 Export PNG Alpha Sequence')
        if success:
            self.log(f"✅ PNG Alpha Sequence exported successfully!")
            self.log(f"📊 Total frames: {total_frames}")
            self.status_label.setText("✅ PNG sequence exported successfully")
            completion_msg = (f'🎬 PNG Alpha Sequence exported successfully!\n\n'
                            f'📁 Location: {message}\n'
                            f'📊 Total frames: {total_frames}\n'
                            f'🎞️ Ready for Adobe Premiere Pro!\n\n'
                            f'In Premiere: File → Import → Select first PNG → Check "Image Sequence"')
            QMessageBox.information(self, 'Export Complete', completion_msg)
        else:
            self.log(f"❌ PNG export failed: {message}")
            self.status_label.setText("❌ PNG export failed")
            QMessageBox.critical(self, 'Export Failed', f'❌ PNG Export failed:\n\n{message}')
    # ===== FONT SELECTION =====

    def select_opencv_fonts(self):
        """Open OpenCV Font Selection Dialog and save settings"""

        try:

            if FONT_MANAGER_AVAILABLE:

                from font_manager import OpenCVFontSelectionDialog
                dialog = OpenCVFontSelectionDialog(self, self.fps_font_settings, 

                                                 self.framerate_font_settings, self.frametime_font_settings)

                if dialog.exec() == QDialog.DialogCode.Accepted:

                    fps_settings, framerate_settings, frametime_settings = dialog.get_selected_settings()
                    self.fps_font_settings = fps_settings

                    self.framerate_font_settings = framerate_settings

                    self.frametime_font_settings = frametime_settings
                    # Update QFont for compatibility

                    self.fps_font = fps_settings.to_qfont()

                    self.framerate_font = framerate_settings.to_qfont()

                    self.frametime_font = frametime_settings.to_qfont()
                    self.log(f"✓ OpenCV Fonts updated:")

                    self.log(f"  FPS: {fps_settings.font_name} Size:{fps_settings.size:.1f} Bold:{fps_settings.bold}")
                    # Save settings

                    self.save_current_settings()

            else:

                QMessageBox.information(self, 'Font Settings', 

                                       'Font selection dialog is not available.\n\n'

                                       'Default fonts will be used for overlay rendering.')

                self.log("⚠️ Font selection not available - using defaults")
        except Exception as e:

            self.log(f"❌ Font selection error: {e}")

            QMessageBox.warning(self, 'Font Selection Error', f'Error opening font selection:\n{str(e)}')
    def select_colors(self):

        """Open Color Selection Dialog and save settings"""
        try:
            dialog = ColorSelectionDialog(self, self.framerate_color, self.frametime_color)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                framerate_color, frametime_color = dialog.get_selected_colors()
                from PyQt6.QtGui import QColor
                if QColor(framerate_color).isValid() and QColor(frametime_color).isValid():
                    self.framerate_color = framerate_color
                    self.frametime_color = frametime_color
                    self.log(f"✓ Colors updated:")
                    self.log(f"  Frame Rate: {framerate_color} | Frame Time: {frametime_color}")
                    # Save settings

                    self.save_current_settings()
                else:
                    self.log("✗ Invalid color format detected")
        except Exception as e:
            self.log(f"❌ Color selection error: {e}")
            QMessageBox.warning(self, 'Color Selection Error', f'Error opening color selection:\n{str(e)}')
    # ===== SETTINGS EXTRACTION =====

    def get_current_settings(self):
        """Extract current settings from UI widgets - FIXED with proper opencv handling"""

        try:

            # ✅ FIXED: Bitrate - handle OpenCV vs FFmpeg correctly

            bitrate_widget = self.bitrate_combo

            if hasattr(bitrate_widget, 'currentData'):

                bitrate_data = bitrate_widget.currentData()

                if bitrate_data == 'opencv':

                    bitrate_value = 'opencv'  # Keep as string

                elif isinstance(bitrate_data, str) and bitrate_data.isdigit():

                    bitrate_value = int(bitrate_data)  # Convert to int

                else:

                    bitrate_value = 60  # Fallback

            else:

                bitrate_value = 60
            # Resolution

            resolution_widget = self.resolution_combo

            if hasattr(resolution_widget, 'currentData'):

                resolution = resolution_widget.currentData()

            else:

                resolution = (1920, 1080)
            # Frame time scale

            frametime_widget = self.frametime_scale_combo

            if hasattr(frametime_widget, 'currentData'):

                frametime_scale = frametime_widget.currentData()

            else:

                frametime_scale = {'min': 16.7, 'mid': 33.3, 'max': 50.0, 'labels': ['16.7', '33.3', '50.0']}
            # Detection sensitivity

            sensitivity_widget = self.sensitivity_combo

            if hasattr(sensitivity_widget, 'currentData'):

                diff_threshold = sensitivity_widget.currentData()

            else:

                diff_threshold = 0.002
            settings = {
                'resolution': resolution,
                'bitrate': bitrate_value,
                'use_cuda': self.use_cuda_checkbox.isChecked() and self.cuda_available,
                'show_frametime': self.show_frametime_checkbox.isChecked(),
                'frametime_scale': frametime_scale,
                'diff_threshold': diff_threshold,
                'ftg_position': getattr(self, 'ftg_position', 'bottom_right'),
                'font_settings': {
                    'fps_font': self.fps_font_settings,
                    'framerate_font': self.framerate_font_settings,
                    'frametime_font': self.frametime_font_settings
                },
                'color_settings': {
                    'framerate_color': self.framerate_color,
                    'frametime_color': self.frametime_color
                },
                'layout_config': self.layout_manager.convert_to_overlay_positions(
                    self.layout_manager.get_current_layout(),
                    resolution[0],
                    resolution[1]
                ),
                'start_frame': self.start_frame,
                'end_frame': self.end_frame
            }

            # Debug print
            print("🔍 DEBUG get_current_settings:")
            for font_type, font in settings['font_settings'].items():
                print(f"   • {font_type}: {type(font).__name__}")
            # Save current settings for next session

            self.save_current_settings()
            return settings
        except Exception as e:

            self.log(f"❌ Error extracting settings: {e}")

            return self.get_fallback_settings()
    def get_fallback_settings(self):

        """Fallback settings when extraction fails"""
        return {
            'resolution': (1920, 1080),
            'bitrate': 60,
            'use_cuda': False,
            'show_frametime': True,
            'frametime_scale': {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']},
            'diff_threshold': 0.002,
            'ftg_position': 'bottom_right',
            'font_settings': {
                'fps_font': self.fps_font_settings,
                'framerate_font': self.framerate_font_settings,
                'frametime_font': self.frametime_font_settings
            },
            'color_settings': {
                'framerate_color': self.framerate_color,
                'frametime_color': self.frametime_color
            },
            'layout_config': self.layout_manager.convert_to_overlay_positions(
                self.layout_manager.get_default_layout(),
                1920, 1080
            ),
            'start_frame': None,
            'end_frame': None
        }
    # ===== VIDEO HANDLING =====

    def browse_input(self):
        """Browse for input video file"""

        file_path, _ = QFileDialog.getOpenFileNames(

            self, 'Select Input Video', '', 

            'Video Files (*.mp4 *.mov *.avi *.mkv *.m4v *.webm);;All Files (*)')
        if file_path:

            file_path = file_path[0]  # Take first file

            self.input_edit.setText(file_path)

            self.load_video_for_preview(file_path)
            base_name = os.path.splitext(file_path)[0]

            self.output_edit.setText(f"{base_name}_fps_analysis.mp4")
    def browse_output(self):

        """Browse for output video file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, 'Select Output Video', '', 
            'MP4 Files (*.mp4);;All Files (*)')
        if file_path:
            self.output_edit.setText(file_path)
    def load_video_for_preview(self, file_path):
        """Load video for preview - ERWEITERT mit Segment Support"""

        try:

            self.log(f"📹 Loading video: {os.path.basename(file_path)}")
            if self.video_cap:

                self.video_cap.release()
            if not os.path.exists(file_path):

                raise ValueError(f"File not found: {file_path}")
            file_size = os.path.getsize(file_path) / (1024*1024)

            self.log(f"📊 File size: {file_size:.1f} MB")
            # ⚡ Performance info for large files

            if file_size > 10000:  # > 10 GB

                self.log("⚠️ Large file detected - playback may be slow due to high resolution/bitrate")

                self.log("💡 Tip: Use segment selection to focus on specific parts for better performance")
            video_info = self.get_video_info(file_path)

            if video_info:

                aspect_ratio = video_info['width'] / video_info['height']

                self.log(f"📺 Video: {video_info['width']}x{video_info['height']} (AR: {aspect_ratio:.2f}), "

                        f"{video_info['fps']:.2f} fps, {video_info['frame_count']} frames")
                # ⚡ Performance warnings for high resolution videos

                if video_info['width'] >= 3840:  # 4K or higher

                    self.log("⚠️ 4K+ resolution detected - playback may be slow")

                    self.log("💡 Preview uses 1080p internal scaling for better performance")

                elif video_info['width'] >= 2560:  # 1440p

                    self.log("💡 High resolution video - preview optimized for smooth playback")
                # 🎯 NEW: Store video properties for segment calculations

                self.total_frames = video_info['frame_count']

                self.video_fps = video_info['fps']
            self.video_cap = cv2.VideoCapture(file_path)

            if not self.video_cap.isOpened():

                raise ValueError("Could not open video file")
            frame_count = int(self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT))

            self.timeline_slider.setMaximum(frame_count - 1)

            self.timeline_slider.setEnabled(True)

            self.play_button.setEnabled(True)
            # 🎯 NEW: Enable segment controls when video is loaded + CLEAR PREVIOUS SEGMENTS

            self.clear_selection()  # Clear any previous segments from other videos

            self.enable_segment_controls(True)
            ret, frame = self.video_cap.read()

            if ret:

                self.display_frame(frame)

                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            # 🎯 NEW: Update segment display for new video

            self.update_segment_display()

            self.update_segment_buttons()
            self.status_label.setText(f"✓ Video loaded: {os.path.basename(file_path)} - Segment controls enabled")
        except Exception as e:

            error_msg = f'Could not load video: {str(e)}'

            QMessageBox.warning(self, 'Video Load Error', error_msg)

            self.log(f"✗ ERROR: {error_msg}")

            self.status_label.setText("✗ Error loading video")
            # 🎯 NEW: Disable segment controls on error

            self.enable_segment_controls(False)
    def get_video_info(self, file_path):

        """Get video information"""
        try:
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                return None
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            cap.release()
            return {
                'frame_count': frame_count,
                'fps': fps,
                'width': width,
                'height': height,
                'duration': duration
            }
        except Exception as e:
            self.log(f"Error getting video info: {e}")
            return None
    def display_frame(self, frame):
        """Display frame with dynamic scaling and aspect ratio preservation"""

        try:

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            h, w, ch = rgb_frame.shape
            target_width, target_height = self.internal_resolution

            rgb_frame = resize_with_aspect_ratio(rgb_frame, target_width, target_height)
            h, w = target_height, target_width
            q_image = QImage(rgb_frame.data, w, h, ch * w, QImage.Format.Format_RGB888)

            pixmap = QPixmap.fromImage(q_image)
            widget_size = self.preview_label.size()

            scaled_pixmap = pixmap.scaled(

                widget_size,

                Qt.AspectRatioMode.KeepAspectRatio,

                Qt.TransformationMode.SmoothTransformation

            )
            self.preview_label.setPixmap(scaled_pixmap)
        except Exception as e:

            self.log(f"✗ Could not display frame: {e}")
    # ===== PLAYBACK CONTROLS =====

    def toggle_playback(self):

        """Toggle video playback"""
        if not self.video_cap:
            return
        if self.playback_timer.isActive():
            self.playback_timer.stop()
            self.play_button.setText('▶️ Play')
        else:
            fps = self.video_cap.get(cv2.CAP_PROP_FPS) or 30
            interval = int(1000 / fps)
            self.playback_timer.start(interval)
            self.play_button.setText('⏸️ Pause')
    def next_frame(self):
        """Go to next frame"""

        if not self.video_cap:

            return
        ret, frame = self.video_cap.read()

        if ret:

            current_frame = int(self.video_cap.get(cv2.CAP_PROP_POS_FRAMES))

            self.timeline_slider.blockSignals(True)

            self.timeline_slider.setValue(current_frame)

            self.timeline_slider.blockSignals(False)
            self.display_frame(frame)

        else:

            self.toggle_playback()
    def scrub_video(self, frame_number):

        """Scrub to specific frame"""
        if self.video_cap:
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = self.video_cap.read()
            if ret:
                self.display_frame(frame)
    # ===== FPS ANALYSIS =====

    def toggle_analysis(self):
        """Start or stop FPS analysis - ERWEITERT mit Segment Support"""

        if self.analysis_worker and self.analysis_worker.isRunning():

            self.log("⏹️ Cancelling FPS analysis...")

            self.analysis_worker.cancel()

            self.analysis_worker.wait(3000)

            self.analysis_worker = None
            self.analyze_button.setText('🎯 Start FPS Analysis')

            self.analyze_button.setStyleSheet(

                "font-weight: bold; font-size: 16px; padding: 12px 24px; "

                "background-color: #4CAF50; color: white; border: none; border-radius: 8px;"

            )

            self.progress_bar.setVisible(False)

            self.status_label.setText("❌ Analysis cancelled")

            return
        # Validate inputs

        input_file = self.input_edit.text().strip()

        output_file = self.output_edit.text().strip()
        if not input_file or not os.path.exists(input_file):

            QMessageBox.warning(self, 'Error', 'Please select a valid input file')

            return
        if not output_file:

            QMessageBox.warning(self, 'Error', 'Please specify an output file')

            return
        # 🎯 NEW: Segment validation and confirmation

        segment_mode = False

        if self.start_frame is not None or self.end_frame is not None:

            # Validate complete segment selection

            if self.start_frame is None:

                QMessageBox.warning(self, 'Incomplete Selection', 

                                   'Please set a start point or clear the selection to analyze the full video.')

                return
            if self.end_frame is None:

                QMessageBox.warning(self, 'Incomplete Selection', 

                                   'Please set an end point or clear the selection to analyze the full video.')

                return
            # Calculate segment info

            duration_frames = self.end_frame - self.start_frame

            duration_time = self.frame_to_time_string(duration_frames)

            percentage = (duration_frames / self.total_frames * 100) if self.total_frames > 0 else 0
            # Ask for confirmation

            reply = QMessageBox.question(self, 'Segment Analysis', 

                                       f'🎯 Analyze selected segment only?\n\n'

                                       f'📍 Start: {self.frame_to_time_string(self.start_frame)}\n'

                                       f'📍 End: {self.frame_to_time_string(self.end_frame)}\n'

                                       f'⏱️ Duration: {duration_time} ({duration_frames} frames)\n'

                                       f'📊 Percentage: {percentage:.1f}% of total video\n\n'

                                       f'The output video will contain only this segment.',

                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:

                return
            segment_mode = True
        # Get settings (this also saves them and includes layout config and segment info)

        settings = self.get_current_settings()
        # Start analysis

        if segment_mode:

            self.log(f"🎯 Starting SEGMENT FPS Analysis...")

            self.log(f"📍 Segment: frames {self.start_frame}-{self.end_frame} ({self.frame_to_time_string(self.end_frame - self.start_frame)})")

        else:

            self.log(f"🎯 Starting FULL FPS Analysis...")
        self.log(f"📊 Settings: {settings['resolution']}, {settings['bitrate']}")
        # 🎯 NEW: Pass segment info to AnalysisWorker

        # Fallback: add segment info to settings

        settings['segment_start_frame'] = self.start_frame

        settings['segment_end_frame'] = self.end_frame

        self.analysis_worker = AnalysisWorker(input_file, output_file, settings)

        # Set segment parameters separately to maintain compatibility

        if hasattr(self.analysis_worker, 'set_segment_range'):

            self.analysis_worker.set_segment_range(self.start_frame, self.end_frame)

        else:

            # Fallback: add segment info to settings

            settings['segment_start_frame'] = self.start_frame

            settings['segment_end_frame'] = self.end_frame

            self.analysis_worker = AnalysisWorker(input_file, output_file, settings)

        self.analysis_worker.progress_update.connect(self.on_progress_update)

        self.analysis_worker.frame_preview.connect(self.on_frame_preview)

        self.analysis_worker.analysis_complete.connect(self.on_analysis_complete)
        # Update UI

        self.analyze_button.setText('⏹️ Cancel Analysis')

        self.analyze_button.setStyleSheet(

            "font-weight: bold; font-size: 16px; padding: 12px 24px; "

            "background-color: #f44336; color: white; border: none; border-radius: 8px;"

        )

        self.progress_bar.setVisible(True)

        self.progress_bar.setValue(0)
        if segment_mode:

            self.status_label.setText("🚀 Starting segment analysis...")

        else:

            self.status_label.setText("🚀 Starting full analysis...")
        self.analysis_worker.start()
    def on_progress_update(self, progress, message):

        """Handle progress updates"""
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)
        if progress % 10 == 0 or "FPS:" in message or "Layout Applied" in message or "Segment" in message:
            self.log(message)
    def on_frame_preview(self, frame):
        """Handle frame preview updates"""

        self.display_frame(frame)
    def on_analysis_complete(self, success, message):

        """Handle analysis completion"""
        self.analysis_worker = None
        self.analyze_button.setText('🎯 Start FPS Analysis')
        self.analyze_button.setStyleSheet(
            "font-weight: bold; font-size: 16px; padding: 12px 24px; "
            "background-color: #4CAF50; color: white; border: none; border-radius: 8px;"
        )
        self.progress_bar.setVisible(False)
        if success:
            mode_str = "segment" if (self.start_frame is not None and self.end_frame is not None) else "full"
            self.log(f"✅ FPS Analysis ({mode_str}) completed successfully!")
            self.status_label.setText(f"✅ Analysis ({mode_str}) completed successfully")
            output_file = self.output_edit.text()
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file) / (1024*1024)
                if mode_str == "segment":
                    duration_time = self.frame_to_time_string(self.end_frame - self.start_frame)
                    completion_msg = (f'🎉 Segment FPS Analysis completed successfully!\n\n'
                                    f'📁 Output file: {os.path.basename(output_file)}\n'
                                    f'📊 File size: {file_size:.1f} MB\n'
                                    f'🎯 Analyzed segment: {duration_time}\n'
                                    f'🎨 Custom layout applied\n\n'
                                    f'The analyzed video contains only the selected segment!')
                else:
                    completion_msg = (f'🎉 FPS Analysis completed successfully!\n\n'
                                    f'📁 Output file: {os.path.basename(output_file)}\n'
                                    f'📊 File size: {file_size:.1f} MB\n'
                                    f'🎨 Custom layout applied\n\n'
                                    f'The analyzed video is ready to use!')
                QMessageBox.information(self, 'Analysis Complete', completion_msg)
        else:
            self.log(f"❌ Analysis failed: {message}")
            self.status_label.setText("❌ Analysis failed")
            QMessageBox.critical(self, 'Analysis Failed', f'❌ FPS Analysis failed:\n\n{message}')
    # ===== LOGGING =====

    def log(self, message):
        """Add message to log"""

        timestamp = time.strftime("%H:%M:%S")

        self.log_text.append(f"[{timestamp}] {message}")

        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

        print(f"[{timestamp}] {message}")
    # ===== CLEANUP =====

    def closeEvent(self, event):

        """Handle application close"""

        # Save settings before closing

        self.save_current_settings()
        if self.analysis_worker and self.analysis_worker.isRunning():
            self.analysis_worker.cancel()
            self.analysis_worker.wait(3000)
        if self.video_cap:
            self.video_cap.release()
        event.accept()
# ===== APPLICATION SETUP =====
def check_dependencies():
    """Check required dependencies"""

    missing_deps = []
    try:

        import cv2

        print(f"✅ OpenCV version: {cv2.__version__}")

    except ImportError:

        missing_deps.append("opencv-python")
    try:

        import torch

        print(f"✅ PyTorch version: {torch.__version__}")

        if torch.cuda.is_available():

            print(f"🚀 CUDA available - GPU: {torch.cuda.get_device_name(0)}")

        else:

            print("⚠️ CUDA not available - will use CPU")

    except ImportError:

        missing_deps.append("torch")
    try:

        import numpy

        print(f"✅ NumPy version: {numpy.__version__}")

    except ImportError:

        missing_deps.append("numpy")
    return len(missing_deps) == 0, missing_deps
def main():

    """🚀 ENHANCED: Main application entry point with TrueType status"""
    app = QApplication(sys.argv)
    app.setApplicationName("FPS Analyzer - Professional Video Analysis")
    app.setOrganizationName("FPS Analysis Tools")
    # Check dependencies

    deps_ok, missing = check_dependencies()
    if not deps_ok:
        QMessageBox.critical(None, 'Missing Dependencies', 
                        f'❌ Required libraries not found:\n\n{", ".join(missing)}\n\n'
                        'Please install them using:\n'
                        f'pip install {" ".join(missing)}')
        sys.exit(1)
    # Check FreeType support

    try:
        from font_manager import FREETYPE_AVAILABLE, get_font_manager
        font_manager = get_font_manager()
        freetype_status = "✅ Available" if FREETYPE_AVAILABLE else "❌ Not Available"
        system_fonts = len(font_manager.available_fonts)
    except:
        freetype_status = "❌ Not Available"
        system_fonts = 0
    # Create and show main window

    window = FPSAnalyzer()
    window.show()
    # Enhanced success messages

    print("\n" + "="*70)
    print("🎯 FPS Analyzer - Professional Video Analysis v1.0")
    print("="*70)
    print("✅ Application started successfully!")
    print(f"🎨 Font System Status:")
    print(f"   • TrueType Support: {freetype_status}")
    print(f"   • System Fonts Discovered: {system_fonts}")
    print(f"   • Enhanced Rendering: ✅ Active")
    print("="*70)
    # Run application

    sys.exit(app.exec())
if __name__ == '__main__':
    main()