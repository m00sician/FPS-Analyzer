#!/usr/bin/env python3
"""
FPS Analyzer - Professional FPS Analysis Tool
Updated main application with settings persistence and cleaned branding
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
from font_manager import OpenCVFontSettings
from color_manager import ColorSelectionDialog
from analysis_worker import AnalysisWorker, resize_with_aspect_ratio
from settings_manager import SettingsManager

class FPSAnalyzer(QMainWindow):
    """Main FPS Analyzer Application with settings persistence"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle('🎯 FPS Analyzer - Professional Video Analysis v2.3')
        self.resize(1600, 1000)
        
        # Core properties
        self.video_cap = None
        self.playback_timer = QTimer(self)
        self.playback_timer.timeout.connect(self.next_frame)
        self.analysis_worker = None
        self.cuda_available = torch.cuda.is_available()
        
        # Preview settings
        self.internal_resolution = (1920, 1080)
        self.preview_quality = cv2.INTER_LANCZOS4
        
        # Settings Manager for persistence
        self.settings_manager = SettingsManager()
        
        # Load saved settings
        saved_settings = self.settings_manager.load_settings()
        
        # Font settings (OpenCV) - Load from saved settings
        self.fps_font_settings = OpenCVFontSettings(
            saved_settings.get('fps_font_name', 'HERSHEY_SIMPLEX'),
            saved_settings.get('fps_font_size', 1.2),
            saved_settings.get('fps_font_thickness', 2),
            saved_settings.get('fps_font_bold', True),
            saved_settings.get('fps_font_border', 2)
        )
        self.framerate_font_settings = OpenCVFontSettings(
            saved_settings.get('framerate_font_name', 'HERSHEY_SIMPLEX'),
            saved_settings.get('framerate_font_size', 0.6),
            saved_settings.get('framerate_font_thickness', 1),
            saved_settings.get('framerate_font_bold', False),
            saved_settings.get('framerate_font_border', 1)
        )
        self.frametime_font_settings = OpenCVFontSettings(
            saved_settings.get('frametime_font_name', 'HERSHEY_SIMPLEX'),
            saved_settings.get('frametime_font_size', 0.5),
            saved_settings.get('frametime_font_thickness', 1),
            saved_settings.get('frametime_font_bold', False),
            saved_settings.get('frametime_font_border', 1)
        )
        
        # Legacy QFont compatibility
        self.fps_font = QFont("Arial", 12)
        self.framerate_font = QFont("Arial", 10)
        self.frametime_font = QFont("Arial", 9)
        
        # Color settings - Load from saved settings
        self.framerate_color = saved_settings.get('framerate_color', '#00FF00')
        self.frametime_color = saved_settings.get('frametime_color', '#00FF00')
        
        # Frame Time Graph position - Load from saved settings
        self.ftg_position = saved_settings.get('ftg_position', 'bottom_right')
        
        # Theme - Load from saved settings
        self.current_theme = saved_settings.get('theme', 'dark')
        
        # Initialize components
        self.setup_application()

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
        
        self.log("✓ FPS Analyzer initialized successfully with saved settings!")

    def load_ui_settings(self):
        """Load saved UI settings into widgets"""
        saved_settings = self.settings_manager.load_settings()
        
        try:
            # Load resolution setting
            saved_resolution = saved_settings.get('output_resolution', (1920, 1080))
            for i in range(self.resolution_combo.count()):
                if self.resolution_combo.itemData(i) == saved_resolution:
                    self.resolution_combo.setCurrentIndex(i)
                    break
            
            # Load bitrate setting
            saved_bitrate = saved_settings.get('bitrate', 60)
            self.bitrate_combo.setCurrentText(str(saved_bitrate))
            
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
            
            self.log(f"✓ Loaded saved settings: {saved_resolution}, {saved_bitrate}Mbps")
            
        except Exception as e:
            self.log(f"⚠️ Could not load some UI settings: {e}")

    def save_current_settings(self):
        """Save current settings to file"""
        try:
            # Collect all current settings
            settings = {
                # Font settings
                'fps_font_name': self.fps_font_settings.font_name,
                'fps_font_size': self.fps_font_settings.size,
                'fps_font_thickness': self.fps_font_settings.thickness,
                'fps_font_bold': self.fps_font_settings.bold,
                'fps_font_border': self.fps_font_settings.border_thickness,
                
                'framerate_font_name': self.framerate_font_settings.font_name,
                'framerate_font_size': self.framerate_font_settings.size,
                'framerate_font_thickness': self.framerate_font_settings.thickness,
                'framerate_font_bold': self.framerate_font_settings.bold,
                'framerate_font_border': self.framerate_font_settings.border_thickness,
                
                'frametime_font_name': self.frametime_font_settings.font_name,
                'frametime_font_size': self.frametime_font_settings.size,
                'frametime_font_thickness': self.frametime_font_settings.thickness,
                'frametime_font_bold': self.frametime_font_settings.bold,
                'frametime_font_border': self.frametime_font_settings.border_thickness,
                
                # Color settings
                'framerate_color': self.framerate_color,
                'frametime_color': self.frametime_color,
                
                # UI settings
                'output_resolution': self.resolution_combo.currentData() if hasattr(self, 'resolution_combo') else (1920, 1080),
                'bitrate': int(self.bitrate_combo.currentText()) if hasattr(self, 'bitrate_combo') else 60,
                'frametime_scale_index': self.frametime_scale_combo.currentIndex() if hasattr(self, 'frametime_scale_combo') else 1,
                'sensitivity_index': self.sensitivity_combo.currentIndex() if hasattr(self, 'sensitivity_combo') else 2,
                
                # Other settings
                'theme': self.current_theme,
                'ftg_position': self.ftg_position,
                'internal_resolution': self.internal_resolution
            }
            
            self.settings_manager.save_settings(settings)
            self.log("✓ Settings saved successfully")
            
        except Exception as e:
            self.log(f"❌ Could not save settings: {e}")

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
        from font_preview_system import FontPreviewDialog
        
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
        
        from png_sequence_exporter import PNGSequenceExporter
        self.png_exporter = PNGSequenceExporter(input_file, sequence_dir, settings)
        self.png_exporter.progress_update.connect(self.on_png_export_progress)
        self.png_exporter.export_complete.connect(self.on_png_export_complete)
        
        # Update UI
        self.export_png_sequence_btn.setEnabled(False)
        self.export_png_sequence_btn.setText('🎬 Exporting...')
        
        self.png_exporter.start()
    
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

    def select_colors(self):
        """Open Color Selection Dialog and save settings"""
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

    # ===== SETTINGS EXTRACTION =====
    def get_current_settings(self):
        """Extract current settings from UI widgets"""
        try:
            # Bitrate
            bitrate_widget = self.bitrate_combo
            if hasattr(bitrate_widget, 'currentText'):
                bitrate_text = bitrate_widget.currentText()
            else:
                bitrate_text = "60"
            
            try:
                bitrate_value = int(bitrate_text)
            except ValueError:
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
                frametime_scale = {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']}
                
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
                }
            }
            
            # Save current settings for next session
            self.save_current_settings()
            
            return settings
            
        except Exception as e:
            self.log(f"❌ Error extracting settings: {e}")
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
                }
            }

    # ===== VIDEO HANDLING =====
    def browse_input(self):
        """Browse for input video file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Select Input Video', '', 
            'Video Files (*.mp4 *.mov *.avi *.mkv *.m4v *.webm);;All Files (*)')
        if file_path:
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
        """Load video for preview"""
        try:
            self.log(f"📹 Loading video: {os.path.basename(file_path)}")
            
            if self.video_cap:
                self.video_cap.release()
            
            if not os.path.exists(file_path):
                raise ValueError(f"File not found: {file_path}")
            
            file_size = os.path.getsize(file_path) / (1024*1024)
            self.log(f"📊 File size: {file_size:.1f} MB")
            
            video_info = self.get_video_info(file_path)
            if video_info:
                aspect_ratio = video_info['width'] / video_info['height']
                self.log(f"📺 Video: {video_info['width']}x{video_info['height']} (AR: {aspect_ratio:.2f}), "
                        f"{video_info['fps']:.2f} fps, {video_info['frame_count']} frames")
            
            self.video_cap = cv2.VideoCapture(file_path)
            if not self.video_cap.isOpened():
                raise ValueError("Could not open video file")
            
            frame_count = int(self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.timeline_slider.setMaximum(frame_count - 1)
            self.timeline_slider.setEnabled(True)
            self.play_button.setEnabled(True)
            
            ret, frame = self.video_cap.read()
            if ret:
                self.display_frame(frame)
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            
            self.status_label.setText(f"✓ Video loaded: {os.path.basename(file_path)}")
            
        except Exception as e:
            error_msg = f'Could not load video: {str(e)}'
            QMessageBox.warning(self, 'Video Load Error', error_msg)
            self.log(f"✗ ERROR: {error_msg}")
            self.status_label.setText("✗ Error loading video")

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
        """Start or stop FPS analysis"""
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
        
        # Get settings (this also saves them)
        settings = self.get_current_settings()
        
        # Start analysis
        self.log(f"🎯 Starting FPS Analysis with Aspect Ratio Preservation...")
        self.log(f"📊 Settings: {settings['resolution']}, {settings['bitrate']}Mbps, Sensitivity={settings['diff_threshold']}")
        
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
        self.status_label.setText("🚀 Starting analysis with settings verification...")
        
        self.analysis_worker.start()

    def on_progress_update(self, progress, message):
        """Handle progress updates"""
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)
        if progress % 10 == 0 or "FPS:" in message or "AR Preserved" in message:
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
            self.log("✅ FPS Analysis completed successfully with aspect ratio preservation!")
            self.status_label.setText("✅ Analysis completed successfully")
            
            output_file = self.output_edit.text()
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file) / (1024*1024)
                completion_msg = (f'🎉 FPS Analysis completed successfully!\n\n'
                                f'📁 Output file: {os.path.basename(output_file)}\n'
                                f'📊 File size: {file_size:.1f} MB\n'
                                f'✅ Aspect ratio preserved\n\n'
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
    """Main application entry point"""
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
    
    # Create and show main window
    window = FPSAnalyzer()
    window.show()
    
    # Success messages
    print("\n" + "="*60)
    print("🎯 FPS Analyzer - Professional Video Analysis v2.3")
    print("="*60)
    print("✅ Application started successfully!")
    print("📝 Features loaded:")
    print("   • Modular architecture with Custom Widgets")
    print("   • OpenCV Font System with Live Preview")
    print("   • Aspect Ratio Preservation")
    print("   • Frame Time Graph Positioning")
    print("   • Background Selector for Font Preview")
    print("   • Batch Processing Support")
    print("   • Settings Persistence (Auto-save/load)")
    print("🚀 Ready for professional video analysis!")
    print("="*60)
    
    # Run application
    sys.exit(app.exec())

if __name__ == '__main__':
    main()