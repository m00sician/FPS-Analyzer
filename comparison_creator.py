"""
Video Comparison Creator für FPS Analyzer
Creates side-by-side comparison videos with adaptive resolution and center-crop
UPDATED VERSION - With Output Resolution Dropdown
"""
import os
import time
import cv2
import numpy as np
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QLineEdit, QGroupBox, QGridLayout, QComboBox, QProgressBar,
                             QFileDialog, QMessageBox, QTextEdit, QCheckBox, QFrame, QWidget)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QPixmap
from analysis_worker import AnalysisWorker

class ComparisonWorker(QThread):
    """Worker thread for processing comparison videos"""
    progress_update = pyqtSignal(str, int, str)  # video_name, progress, message
    video_completed = pyqtSignal(str, bool, str)  # video_name, success, message
    comparison_complete = pyqtSignal(bool, str)  # success, message
    frame_preview = pyqtSignal(str, np.ndarray)  # video_name, frame
    
    def __init__(self, video_a_path, video_b_path, video_a_name, video_b_name, output_dir, settings):
        super().__init__()
        self.video_a_path = video_a_path
        self.video_b_path = video_b_path
        self.video_a_name = video_a_name
        self.video_b_name = video_b_name
        self.output_dir = output_dir
        self.settings = settings
        self.is_cancelled = False
        
        # Workers for each video
        self.worker_a = None
        self.worker_b = None
        
    def cancel(self):
        """Cancel both video processing"""
        self.is_cancelled = True
        if self.worker_a:
            self.worker_a.cancel()
        if self.worker_b:
            self.worker_b.cancel()
    
    def run(self):
        """Process both videos for comparison"""
        try:
            # Get resolution from settings
            comparison_resolution = self.settings.get('comparison_resolution', (960, 1080))
            resolution_name = self.settings.get('resolution_name', '1080p')
            
            # Prepare output paths
            output_a = os.path.join(self.output_dir, f"{self.video_a_name}_comparison_left_{resolution_name}.mp4")
            output_b = os.path.join(self.output_dir, f"{self.video_b_name}_comparison_right_{resolution_name}.mp4")
            
            # Update settings for comparison mode
            comparison_settings_a = self.settings.copy()
            comparison_settings_a.update({
                'resolution': comparison_resolution,
                'comparison_mode': True,
                'crop_mode': 'center',
                'simplified_ui': True,
                'video_name': self.video_a_name
            })
            
            comparison_settings_b = self.settings.copy()
            comparison_settings_b.update({
                'resolution': comparison_resolution,
                'comparison_mode': True,
                'crop_mode': 'center', 
                'simplified_ui': True,
                'video_name': self.video_b_name
            })
            
            # Process Video A
            self.progress_update.emit("Video A", 0, f"🎯 Starting analysis of {self.video_a_name} ({resolution_name})...")
            success_a = self.process_video(self.video_a_path, output_a, comparison_settings_a, "Video A")
            
            if not success_a or self.is_cancelled:
                return
            
            # Process Video B
            self.progress_update.emit("Video B", 0, f"🎯 Starting analysis of {self.video_b_name} ({resolution_name})...")
            success_b = self.process_video(self.video_b_path, output_b, comparison_settings_b, "Video B")
            
            if success_a and success_b and not self.is_cancelled:
                final_message = (f"✅ Both comparison videos created successfully!\n\n"
                               f"📊 Resolution: {resolution_name} ({comparison_resolution[0]}x{comparison_resolution[1]})\n"
                               f"📁 Output directory: {self.output_dir}\n\n"
                               f"💡 Tip: Use video editing software to place these side-by-side!")
                self.comparison_complete.emit(True, final_message)
            else:
                self.comparison_complete.emit(False, "❌ Comparison creation failed")
                
        except Exception as e:
            self.comparison_complete.emit(False, f"❌ Comparison error: {str(e)}")
    
    def process_video(self, input_path, output_path, settings, video_name):
        """Process a single video for comparison"""
        try:
            # Create worker with comparison settings - USE EXISTING AnalysisWorker
            worker = AnalysisWorker(input_path, output_path, settings)
            
            # Connect signals properly
            worker.progress_update.connect(
                lambda progress, message: self.progress_update.emit(video_name, progress, message)
            )
            
            # Connect frame preview signal
            worker.frame_preview.connect(
                lambda frame: self.frame_preview.emit(video_name, frame)
            )
            
            # Store worker reference
            if video_name == "Video A":
                self.worker_a = worker
            else:
                self.worker_b = worker
            
            # Run analysis
            worker.analyze_video()
            
            # Check if cancelled
            if self.is_cancelled:
                return False
            
            self.video_completed.emit(video_name, True, f"✅ {video_name} completed")
            return True
            
        except Exception as e:
            self.video_completed.emit(video_name, False, f"❌ {video_name} failed: {str(e)}")
            return False

class ComparisonCreatorDialog(QDialog):
    """Dialog for creating video comparisons with resolution options"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_analyzer = parent
        self.setWindowTitle("📊 Video Comparison Creator")
        self.setModal(True)
        self.resize(1000, 850)  # Slightly larger for new controls
        
        # Comparison data
        self.video_a_path = ""
        self.video_b_path = ""
        self.comparison_worker = None
        self.is_processing = False
        
        self.setup_ui()
        self.apply_theme()
    
    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("📊 Video Comparison Creator")
        title_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 5px; font-size: 18px;")
        layout.addWidget(title_label)
        
        description = QLabel(
            "Create side-by-side comparison videos with adaptive resolution and center-crop\n"
            "Choose your output resolution for optimal comparison quality!"
        )
        description.setStyleSheet("color: #cccccc; padding: 5px; font-size: 12px;")
        layout.addWidget(description)
        
        # Video Selection Section
        video_section = self.create_video_selection_section()
        layout.addWidget(video_section)
        
        # Settings Section (ENHANCED with Resolution Dropdown)
        settings_section = self.create_settings_section()
        layout.addWidget(settings_section)
        
        # Output Section
        output_section = self.create_output_section()
        layout.addWidget(output_section)
        
        # Progress Section
        progress_section = self.create_progress_section()
        layout.addWidget(progress_section)
        
        # Control Buttons
        controls = self.create_control_buttons()
        layout.addLayout(controls)
    
    def create_video_selection_section(self):
        """Create video selection section"""
        group = QGroupBox("🎬 Video Selection")
        layout = QGridLayout(group)
        
        # Video A
        layout.addWidget(QLabel("Video A:"), 0, 0)
        self.video_a_edit = QLineEdit()
        self.video_a_edit.setPlaceholderText("Select first video file...")
        layout.addWidget(self.video_a_edit, 0, 1)
        
        browse_a_btn = QPushButton("📁 Browse A")
        browse_a_btn.clicked.connect(lambda: self.browse_video("A"))
        layout.addWidget(browse_a_btn, 0, 2)
        
        # Video A Name
        layout.addWidget(QLabel("Name A:"), 1, 0)
        self.video_a_name_edit = QLineEdit("Video A")
        layout.addWidget(self.video_a_name_edit, 1, 1, 1, 2)
        
        # Video B
        layout.addWidget(QLabel("Video B:"), 2, 0)
        self.video_b_edit = QLineEdit()
        self.video_b_edit.setPlaceholderText("Select second video file...")
        layout.addWidget(self.video_b_edit, 2, 1)
        
        browse_b_btn = QPushButton("📁 Browse B")
        browse_b_btn.clicked.connect(lambda: self.browse_video("B"))
        layout.addWidget(browse_b_btn, 2, 2)
        
        # Video B Name
        layout.addWidget(QLabel("Name B:"), 3, 0)
        self.video_b_name_edit = QLineEdit("Video B")
        layout.addWidget(self.video_b_name_edit, 3, 1, 1, 2)
        
        return group
    
    def create_settings_section(self):
        """Create settings section with Output Resolution Dropdown"""
        group = QGroupBox("⚙️ Comparison Settings")
        layout = QGridLayout(group)
        
        # ✨ NEW: Output Resolution Dropdown
        layout.addWidget(QLabel("📺 Output Resolution:"), 0, 0)
        self.resolution_combo = QComboBox()
        
        # Resolution options for comparison videos
        resolution_options = [
            ('720p Comparison (640x720)', (640, 720), '720p'),
            ('1080p Comparison (960x1080)', (960, 1080), '1080p'),  # Standard
            ('1440p Comparison (1280x1440)', (1280, 1440), '1440p'),
            ('4K Comparison (1920x2160)', (1920, 2160), '4K')
        ]
        
        for display_name, resolution, short_name in resolution_options:
            self.resolution_combo.addItem(display_name, {'resolution': resolution, 'name': short_name})
        
        # Set default to 1080p
        self.resolution_combo.setCurrentIndex(1)
        self.resolution_combo.currentIndexChanged.connect(self.on_resolution_changed)
        layout.addWidget(self.resolution_combo, 0, 1)
        
        # Resolution info label
        self.resolution_info_label = QLabel("📏 Each video will be center-cropped to 960 pixels wide")
        self.resolution_info_label.setStyleSheet("color: #999; font-size: 10px; font-style: italic;")
        layout.addWidget(self.resolution_info_label, 0, 2)
        
        # Bitrate
        layout.addWidget(QLabel("📊 Bitrate:"), 1, 0)
        self.bitrate_edit = QLineEdit("60")
        self.bitrate_edit.setMaximumWidth(80)
        bitrate_layout = QHBoxLayout()
        bitrate_layout.addWidget(self.bitrate_edit)
        bitrate_layout.addWidget(QLabel("Mbit/s"))
        bitrate_layout.addStretch()
        layout.addLayout(bitrate_layout, 1, 1)
        
        # Detection Sensitivity
        layout.addWidget(QLabel("🎯 Detection Sensitivity:"), 2, 0)
        self.sensitivity_combo = QComboBox()
        sensitivity_options = [
            ('Very High (0.0005)', 0.0005),
            ('High (0.001)', 0.001),
            ('Medium (0.002)', 0.002),
            ('Low (0.005)', 0.005),
            ('Very Low (0.01)', 0.01)
        ]
        for name, val in sensitivity_options:
            self.sensitivity_combo.addItem(name, val)
        self.sensitivity_combo.setCurrentIndex(2)  # Medium
        layout.addWidget(self.sensitivity_combo, 2, 1)
        
        # PNG Export Option
        self.export_png_checkbox = QCheckBox("🎬 Also export PNG Alpha Sequences")
        self.export_png_checkbox.setToolTip("Export UI overlays as transparent PNG sequences for Premiere Pro")
        layout.addWidget(self.export_png_checkbox, 3, 0, 1, 3)
        
        return group
    
    def on_resolution_changed(self):
        """Handle resolution selection change"""
        current_data = self.resolution_combo.currentData()
        if current_data:
            resolution = current_data['resolution']
            width, height = resolution
            
            # Update info label
            crop_width = width  # For comparison, we crop to the target width
            self.resolution_info_label.setText(f"📏 Each video will be center-cropped to {crop_width} pixels wide")
            
            self.log(f"📺 Output resolution changed to {current_data['name']} ({width}x{height})")
    
    def create_output_section(self):
        """Create output section"""
        group = QGroupBox("📁 Output")
        layout = QHBoxLayout(group)
        
        layout.addWidget(QLabel("Output Directory:"))
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("Select output directory...")
        layout.addWidget(self.output_dir_edit)
        
        browse_output_btn = QPushButton("📁 Browse")
        browse_output_btn.clicked.connect(self.browse_output_directory)
        layout.addWidget(browse_output_btn)
        
        return group
    
    def create_progress_section(self):
        """Create progress section with single preview window in nice frame"""
        group = QGroupBox("📊 Progress")
        layout = QVBoxLayout(group)
        
        # Create horizontal layout for progress + preview
        progress_layout = QHBoxLayout()
        
        # Left side: Progress bars in nice frame
        progress_group = QGroupBox("📈 Processing Status")
        progress_widget_layout = QVBoxLayout(progress_group)
        
        # Video A Progress
        progress_widget_layout.addWidget(QLabel("Video A Progress:"))
        self.progress_a = QProgressBar()
        self.progress_a.setVisible(False)
        progress_widget_layout.addWidget(self.progress_a)
        
        # Video B Progress  
        progress_widget_layout.addWidget(QLabel("Video B Progress:"))
        self.progress_b = QProgressBar()
        self.progress_b.setVisible(False)
        progress_widget_layout.addWidget(self.progress_b)
        
        progress_layout.addWidget(progress_group)
        
        # Right side: Preview window in nice frame
        preview_group = QGroupBox("📹 Live Preview")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        
        # Current video label
        self.preview_label = QLabel("Current Video Preview:")
        self.preview_label.setStyleSheet("color: #cccccc; font-weight: bold; font-size: 11px;")
        preview_layout.addWidget(self.preview_label)
        
        # Preview display
        self.preview_display = QLabel()
        self.preview_display.setFixedSize(192, 216)  # 960x1080 scaled to 20%
        self.preview_display.setStyleSheet("""
            QLabel {
                border: 2px solid #555;
                border-radius: 8px;
                background-color: #1a1a1a;
                color: #888;
                text-align: center;
                font-size: 11px;
                margin: 5px;
            }
        """)
        self.preview_display.setText("No preview\navailable")
        self.preview_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_display.setScaledContents(True)
        preview_layout.addWidget(self.preview_display)
        
        # Add some spacing
        preview_layout.addStretch()
        
        # Set fixed width for preview group
        preview_group.setFixedWidth(230)
        progress_layout.addWidget(preview_group)
        
        layout.addLayout(progress_layout)
        
        # Log section
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(120)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                border: 2px solid #555;
                color: #ffffff;
                border-radius: 5px;
                padding: 5px;
            }
        """)
        self.log_text.setPlaceholderText("🔍 Comparison processing log will appear here...")
        layout.addWidget(self.log_text)
        
        return group
    
    def create_control_buttons(self):
        """Create control buttons"""
        layout = QHBoxLayout()
        
        # Use Parent Settings
        use_parent_btn = QPushButton("📋 Use Current Settings")
        use_parent_btn.clicked.connect(self.use_parent_settings)
        layout.addWidget(use_parent_btn)
        
        layout.addStretch()
        
        # Start Comparison
        self.start_btn = QPushButton("🚀 Create Comparison")
        self.start_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                font-size: 14px;
                padding: 10px 20px;
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #66BB6A;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666;
            }
        """)
        self.start_btn.clicked.connect(self.start_comparison)
        layout.addWidget(self.start_btn)
        
        # Cancel
        self.cancel_btn = QPushButton("⏹️ Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                font-size: 14px;
                padding: 10px 20px;
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #ef5350;
            }
        """)
        self.cancel_btn.clicked.connect(self.cancel_comparison)
        self.cancel_btn.setEnabled(False)
        layout.addWidget(self.cancel_btn)
        
        # Close
        close_btn = QPushButton("✓ Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        return layout
    
    def browse_video(self, video_type):
        """Browse for video file"""
        file_path, _ = QFileDialog.getOpenFileNames(
            self, f'Select Video {video_type}', '', 
            'Video Files (*.mp4 *.mov *.avi *.mkv *.m4v *.webm *.prores);;All Files (*)'
        )
        
        if file_path:
            file_path = file_path[0]  # Take first file
            if video_type == "A":
                self.video_a_path = file_path
                self.video_a_edit.setText(file_path)
                # Auto-generate name from filename
                filename = os.path.splitext(os.path.basename(file_path))[0]
                self.video_a_name_edit.setText(filename)
            else:
                self.video_b_path = file_path
                self.video_b_edit.setText(file_path)
                # Auto-generate name from filename
                filename = os.path.splitext(os.path.basename(file_path))[0]
                self.video_b_name_edit.setText(filename)
            
            # Auto-set output directory to first video's directory
            if not self.output_dir_edit.text():
                self.output_dir_edit.setText(os.path.dirname(file_path))
            
            self.log(f"✅ Video {video_type} selected: {os.path.basename(file_path)}")
    
    def browse_output_directory(self):
        """Browse for output directory"""
        directory = QFileDialog.getExistingDirectory(self, 'Select Output Directory')
        if directory:
            self.output_dir_edit.setText(directory)
            self.log(f"📁 Output directory: {directory}")
    
    def use_parent_settings(self):
        """Copy settings from parent analyzer"""
        if hasattr(self.parent_analyzer, 'bitrate_combo'):
            self.bitrate_edit.setText(self.parent_analyzer.bitrate_combo.currentText())
        
        if hasattr(self.parent_analyzer, 'sensitivity_combo'):
            parent_sensitivity = self.parent_analyzer.sensitivity_combo.currentText()
            self.sensitivity_combo.setCurrentText(parent_sensitivity)
        
        self.log("📋 Settings copied from main window")
    
    def start_comparison(self):
        """Start comparison creation"""
        # Validate inputs
        if not self.video_a_path or not os.path.exists(self.video_a_path):
            QMessageBox.warning(self, 'Error', 'Please select a valid Video A file')
            return
        
        if not self.video_b_path or not os.path.exists(self.video_b_path):
            QMessageBox.warning(self, 'Error', 'Please select a valid Video B file')
            return
        
        output_dir = self.output_dir_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, 'Error', 'Please select an output directory')
            return
        
        # Create output directory if needed
        os.makedirs(output_dir, exist_ok=True)
        
        # Get resolution settings
        resolution_data = self.resolution_combo.currentData()
        comparison_resolution = resolution_data['resolution']
        resolution_name = resolution_data['name']
        
        # Get other settings
        try:
            bitrate_value = int(self.bitrate_edit.text())
        except ValueError:
            bitrate_value = 60
        
        settings = {
            'comparison_resolution': comparison_resolution,
            'resolution_name': resolution_name,
            'bitrate': bitrate_value,
            'use_cuda': getattr(self.parent_analyzer, 'cuda_available', False),
            'diff_threshold': self.sensitivity_combo.currentData(),
            'font_settings': {
                'fps_font': getattr(self.parent_analyzer, 'fps_font_settings', None),
                'framerate_font': getattr(self.parent_analyzer, 'framerate_font_settings', None),
            },
            'color_settings': {
                'framerate_color': getattr(self.parent_analyzer, 'framerate_color', '#00FF00'),
            },
            'export_png': self.export_png_checkbox.isChecked()
        }
        
        # Get video names
        video_a_name = self.video_a_name_edit.text().strip() or "Video_A"
        video_b_name = self.video_b_name_edit.text().strip() or "Video_B"
        
        # Start comparison worker
        self.comparison_worker = ComparisonWorker(
            self.video_a_path, self.video_b_path,
            video_a_name, video_b_name,
            output_dir, settings
        )
        
        # Connect signals
        self.comparison_worker.progress_update.connect(self.on_progress_update)
        self.comparison_worker.video_completed.connect(self.on_video_completed)
        self.comparison_worker.comparison_complete.connect(self.on_comparison_complete)
        self.comparison_worker.frame_preview.connect(self.on_frame_preview)
        
        # Update UI
        self.is_processing = True
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_a.setVisible(True)
        self.progress_b.setVisible(True)
        self.progress_a.setValue(0)
        self.progress_b.setValue(0)
        
        # Reset preview window
        self.preview_display.setText("Processing...")
        
        # Start processing
        self.comparison_worker.start()
        self.log(f"🚀 Starting comparison: {video_a_name} vs {video_b_name} ({resolution_name})")
    
    def cancel_comparison(self):
        """Cancel comparison creation"""
        if self.comparison_worker:
            self.comparison_worker.cancel()
            self.log("⏹️ Cancelling comparison creation...")
    
    def on_progress_update(self, video_name, progress, message):
        """Handle progress updates"""
        if video_name == "Video A":
            self.progress_a.setValue(progress)
        else:
            self.progress_b.setValue(progress)
        
        if progress % 20 == 0 or "completed" in message.lower():
            self.log(message)
    
    def on_video_completed(self, video_name, success, message):
        """Handle individual video completion"""
        self.log(message)
        if success:
            if video_name == "Video A":
                self.progress_a.setValue(100)
            else:
                self.progress_b.setValue(100)
    
    def on_comparison_complete(self, success, message):
        """Handle comparison completion"""
        self.comparison_worker = None
        self.is_processing = False
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        
        if success:
            self.log("🎉 Comparison creation completed!")
            
            # Reset preview to completed state
            self.preview_display.setText("✅ Comparison\nCompleted")
            
            QMessageBox.information(self, 'Comparison Complete', message)
        else:
            self.log(f"❌ Comparison failed: {message}")
            
            # Reset preview to error state
            self.preview_display.setText("❌ Error")
            
            QMessageBox.critical(self, 'Comparison Failed', message)
    
    def on_frame_preview(self, video_name, frame):
        """Handle frame preview updates"""
        try:
            from PyQt6.QtGui import QImage, QPixmap
            
            # Update preview label to show current video
            self.preview_label.setText(f"📹 {video_name} Preview:")
            
            # Convert BGR frame to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            
            # Create QImage
            q_image = QImage(rgb_frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(q_image)
            
            # Scale to preview size
            scaled_pixmap = pixmap.scaled(
                192, 216,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            # Display in single preview window
            self.preview_display.setPixmap(scaled_pixmap)
            
        except Exception as e:
            print(f"⚠️ Preview error for {video_name}: {e}")
    
    def log(self, message):
        """Add message to log"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        print(f"[COMPARISON] {message}")
    
    def apply_theme(self):
        """Apply parent theme"""
        if hasattr(self.parent_analyzer, 'current_theme'):
            self.setStyleSheet(self.parent_analyzer.styleSheet())
    
    def closeEvent(self, event):
        """Handle dialog close"""
        if self.is_processing:
            reply = QMessageBox.question(
                self, 'Processing Active', 
                'Comparison creation is still running. Cancel and close?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                if self.comparison_worker:
                    self.comparison_worker.cancel()
                    self.comparison_worker.wait(3000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()