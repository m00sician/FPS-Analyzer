"""
Video Comparison Creator for FPS Analyzer - PNG TEMPLATE VERSION
Creates side-by-side comparison videos with PNG template support
Passes through the same FPS graph template as the main video
"""
import os
import time
import cv2
import numpy as np
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QLineEdit, QGroupBox, QGridLayout, QComboBox, QProgressBar,
                             QFileDialog, QMessageBox, QTextEdit, QCheckBox, QFrame, QWidget)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from analysis_worker import AnalysisWorker


class ViewportPreviewWidget(QFrame):
    """Compact preview strip showing which part of the video will be cropped."""
    def __init__(self, label, parent=None):
        super().__init__(parent)
        self._label  = label
        self._offset = 0.5
        self._thumb  = None
        self._vid_w  = 1920
        self._vid_h  = 1080
        self.setStyleSheet("background: #1a2530; border: 1px solid #334;")

    def load_video(self, path):
        self._thumb = None
        if not path or not os.path.exists(path):
            self.update(); return
        try:
            cap = cv2.VideoCapture(path)
            if cap.isOpened():
                self._vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self._vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.set(cv2.CAP_PROP_POS_FRAMES, min(30, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) - 1))
                ret, frame = cap.read()
                if ret:
                    h = self.height() or 40
                    scale = h / frame.shape[0]
                    w = max(1, int(frame.shape[1] * scale))
                    thumb = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
                    rgb = cv2.cvtColor(thumb, cv2.COLOR_BGR2RGB)
                    from PyQt6.QtGui import QImage
                    self._thumb = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
            cap.release()
        except Exception:
            pass
        self.update()

    def set_offset(self, value):
        self._offset = value / 100.0
        self.update()

    def paintEvent(self, _):
        from PyQt6.QtGui import QPainter, QPen, QColor, QFont
        p = QPainter(self)
        ww, wh = self.width(), self.height()
        if self._thumb:
            tw, th = self._thumb.width(), self._thumb.height()
            dw = int(tw * wh / max(th, 1))
            x0 = (ww - dw) // 2
            p.drawImage(x0, 0, self._thumb.scaled(
                dw, wh, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            crop_frac = min(1.0, self._vid_h / max(self._vid_w, 1))
            max_off   = max(0.0, 1.0 - crop_frac)
            left_f    = self._offset * max_off
            cx1 = x0 + int(left_f * dw)
            cx2 = x0 + int((left_f + crop_frac) * dw)
            p.fillRect(x0, 0, max(0, cx1 - x0), wh, QColor(0, 0, 0, 150))
            p.fillRect(cx2, 0, max(0, x0 + dw - cx2), wh, QColor(0, 0, 0, 150))
            p.setPen(QPen(QColor(60, 200, 80), 1))
            p.drawRect(cx1, 1, max(0, cx2 - cx1 - 1), wh - 2)
        else:
            p.fillRect(0, 0, ww, wh, QColor(26, 37, 48))
            p.setPen(QColor(80, 100, 120))
            f = QFont(); f.setPixelSize(10); p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"Video {self._label}")

class ComparisonWorker(QThread):
    """Worker thread for processing comparison videos with PNG template support"""
    progress_update = pyqtSignal(str, int, str)
    video_completed = pyqtSignal(str, bool, str)
    comparison_complete = pyqtSignal(bool, str)
    frame_preview = pyqtSignal(str, np.ndarray)
    
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
        self.current_workers = []  # Track active workers
    
    def cancel(self):
        """Cancel both video processing"""
        self.is_cancelled = True
        # Cancel all active workers
        for worker in self.current_workers:
            if worker and hasattr(worker, 'is_cancelled'):
                worker.is_cancelled = True
        if self.worker_a:
            self.worker_a.is_cancelled = True
        if self.worker_b:
            self.worker_b.is_cancelled = True
    
    def run(self):
        """Process both videos for comparison"""
        try:
            # Get resolution from settings
            comparison_resolution = self.settings.get('comparison_resolution', (960, 1080))
            resolution_name = self.settings.get('resolution_name', '1080p')
            
            # Prepare output paths
            output_a = os.path.join(self.output_dir, f"{self.video_a_name}_comparison_left_{resolution_name}.mp4")
            output_b = os.path.join(self.output_dir, f"{self.video_b_name}_comparison_right_{resolution_name}.mp4")
            
            # Update settings for comparison mode - each video keeps its own colour
            def _bgr_to_hex(bgr):
                try:
                    b, g, r = int(bgr[0]), int(bgr[1]), int(bgr[2])
                    return f"#{r:02X}{g:02X}{b:02X}"
                except Exception:
                    return '#00FF00'
            col_a = _bgr_to_hex(self.settings.get('color_a', [220, 120, 50]))
            col_b = _bgr_to_hex(self.settings.get('color_b', [50, 140, 255]))

            comparison_settings_a = self.settings.copy()
            comparison_settings_a.update({
                'resolution': comparison_resolution,
                'comparison_mode': True,
                'crop_mode': 'center',
                'simplified_ui': True,
                'video_name': self.video_a_name,
                'color_settings': {'framerate_color': col_a, 'frametime_color': col_a},
            })
            
            comparison_settings_b = self.settings.copy()
            comparison_settings_b.update({
                'resolution': comparison_resolution,
                'comparison_mode': True,
                'crop_mode': 'center', 
                'simplified_ui': True,
                'video_name': self.video_b_name,
                'color_settings': {'framerate_color': col_b, 'frametime_color': col_b},
            })
            
            # Process Video A
            self.progress_update.emit("Video A", 0, f"🎯 Starting analysis of {self.video_a_name} ({resolution_name})...")
            
            # Create worker A
            self.worker_a = AnalysisWorker(self.video_a_path, output_a, comparison_settings_a)
            self.current_workers.append(self.worker_a)
            
            # Connect signals
            self.worker_a.progress_update.connect(
                lambda progress, message: self.check_and_emit_progress("Video A", progress, message)
            )
            self.worker_a.frame_preview.connect(
                lambda frame: self.frame_preview.emit("Video A", frame)
            )
            
            # Run Video A analysis directly (not as thread)
            self.worker_a.analyze_video()
            
            # Check if cancelled after Video A
            if self.is_cancelled:
                self.comparison_complete.emit(False, "❌ Comparison cancelled by user")
                return
            
            self.video_completed.emit("Video A", True, f"✅ Video A completed")
            
            # Process Video B
            self.progress_update.emit("Video B", 0, f"🎯 Starting analysis of {self.video_b_name} ({resolution_name})...")
            
            # Create worker B
            self.worker_b = AnalysisWorker(self.video_b_path, output_b, comparison_settings_b)
            self.current_workers.append(self.worker_b)
            
            # Connect signals
            self.worker_b.progress_update.connect(
                lambda progress, message: self.check_and_emit_progress("Video B", progress, message)
            )
            self.worker_b.frame_preview.connect(
                lambda frame: self.frame_preview.emit("Video B", frame)
            )
            
            # Run Video B analysis
            self.worker_b.analyze_video()
            
            # Check if cancelled
            if self.is_cancelled:
                self.comparison_complete.emit(False, "❌ Comparison cancelled by user")
                return
            
            self.video_completed.emit("Video B", True, f"✅ Video B completed")
            
            # Success
            final_message = (f"✅ Both comparison videos created successfully!\n\n"
                           f"📊 Resolution: {resolution_name} ({comparison_resolution[0]}x{comparison_resolution[1]})\n"
                           f"📁 Output directory: {self.output_dir}\n\n"
                           f"💡 Tip: Use video editing software to place these side-by-side!")
            self.comparison_complete.emit(True, final_message)
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.comparison_complete.emit(False, f"❌ Comparison error: {str(e)}")
    
    def check_and_emit_progress(self, video_name, progress, message):
        """Check for cancellation before emitting progress"""
        if self.is_cancelled:
            # Set the worker's cancel flag
            if video_name == "Video A" and self.worker_a:
                self.worker_a.is_cancelled = True
            elif video_name == "Video B" and self.worker_b:
                self.worker_b.is_cancelled = True
            return
        
        self.progress_update.emit(video_name, progress, message)

class ComparisonCreatorDialog(QDialog):
    """Dialog for creating video comparisons with PNG template support"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_analyzer = parent
        self.setWindowTitle("📊 Video Comparison Creator")
        self.setModal(True)
        self.resize(1000, 950)
        
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
        """Create video selection section with viewport sliders"""
        from PyQt6.QtWidgets import QSlider
        group = QGroupBox("🎬 Video Selection")
        layout = QGridLayout(group)
        layout.setVerticalSpacing(6)
        layout.setColumnStretch(1, 1)

        def _make_viewport_row(label, attr_slider, attr_preview, attr_label, default_color):
            from PyQt6.QtWidgets import QColorDialog
            from PyQt6.QtGui import QColor
            row_widget = QWidget()
            lr = QHBoxLayout(row_widget)
            lr.setContentsMargins(0, 0, 0, 0)
            lr.setSpacing(6)
            preview = ViewportPreviewWidget(label)
            preview.setFixedSize(160, 40)
            lr.addWidget(preview)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(50)
            slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            slider.setTickInterval(25)
            slider.setToolTip(f"Horizontaler Crop-Offset Video {label}\n0% = links  ·  50% = Mitte  ·  100% = rechts")
            lr.addWidget(slider, 1)
            lbl = QLabel("50%")
            lbl.setFixedWidth(36)
            lr.addWidget(lbl)
            slider.valueChanged.connect(lambda v, l=lbl, p=preview: (l.setText(f"{v}%"), p.set_offset(v)))

            # Color picker button (line + FPS number color for this video)
            color_btn = QPushButton()
            color_btn.setFixedSize(28, 28)
            color_btn.setToolTip(f"Line / FPS colour for video {label}")
            qc = QColor(default_color[2], default_color[1], default_color[0])  # BGR → RGB
            color_btn.setStyleSheet(f"background-color: {qc.name()}; border: 1px solid #555;")
            setattr(self, f"_color_{label.lower()}", list(default_color))  # store BGR

            def _pick_color(checked=False, btn=color_btn, lab=label):
                cur = getattr(self, f"_color_{lab.lower()}")
                initial = QColor(cur[2], cur[1], cur[0])
                chosen = QColorDialog.getColor(initial, self, f"Farbe Video {lab}")
                if chosen.isValid():
                    bgr = [chosen.blue(), chosen.green(), chosen.red()]
                    setattr(self, f"_color_{lab.lower()}", bgr)
                    btn.setStyleSheet(f"background-color: {chosen.name()}; border: 1px solid #555;")

            color_btn.clicked.connect(_pick_color)
            lr.addWidget(color_btn)

            setattr(self, attr_slider,  slider)
            setattr(self, attr_preview, preview)
            setattr(self, attr_label,   lbl)
            return row_widget

        # ── Video A ──────────────────────────────────────────────────────────
        layout.addWidget(QLabel("Video A:"), 0, 0)
        self.video_a_edit = QLineEdit()
        self.video_a_edit.setPlaceholderText("Select first video file...")
        layout.addWidget(self.video_a_edit, 0, 1)
        browse_a_btn = QPushButton("📁 Browse A")
        browse_a_btn.clicked.connect(lambda: self.browse_video("A"))
        layout.addWidget(browse_a_btn, 0, 2)

        layout.addWidget(QLabel("Name A:"), 1, 0)
        self.video_a_name_edit = QLineEdit("Video A")
        layout.addWidget(self.video_a_name_edit, 1, 1, 1, 2)

        layout.addWidget(QLabel("Viewport A:"), 2, 0)
        vp_a = _make_viewport_row("A", "viewport_a_slider", "viewport_a_preview", "viewport_a_label", (220, 120, 50))
        self.video_a_edit.textChanged.connect(lambda p: self.viewport_a_preview.load_video(p))
        layout.addWidget(vp_a, 2, 1, 1, 2)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #334;")
        layout.addWidget(sep, 3, 0, 1, 3)

        # ── Video B ──────────────────────────────────────────────────────────
        layout.addWidget(QLabel("Video B:"), 4, 0)
        self.video_b_edit = QLineEdit()
        self.video_b_edit.setPlaceholderText("Select second video file...")
        layout.addWidget(self.video_b_edit, 4, 1)
        browse_b_btn = QPushButton("📁 Browse B")
        browse_b_btn.clicked.connect(lambda: self.browse_video("B"))
        layout.addWidget(browse_b_btn, 4, 2)

        layout.addWidget(QLabel("Name B:"), 5, 0)
        self.video_b_name_edit = QLineEdit("Video B")
        layout.addWidget(self.video_b_name_edit, 5, 1, 1, 2)

        layout.addWidget(QLabel("Viewport B:"), 6, 0)
        vp_b = _make_viewport_row("B", "viewport_b_slider", "viewport_b_preview", "viewport_b_label", (50, 140, 255))
        self.video_b_edit.textChanged.connect(lambda p: self.viewport_b_preview.load_video(p))
        layout.addWidget(vp_b, 6, 1, 1, 2)

        return group
    
    def create_settings_section(self):
        """Create settings section with ALL options from main UI"""
        group = QGroupBox("⚙️ Comparison Settings")
        layout = QGridLayout(group)
        
        # Output Resolution Dropdown
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
        
        
        # ✅ BITRATE SELECTION (like main UI)
        layout.addWidget(QLabel("📊 Bitrate:"), 1, 0)
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.setMinimumWidth(140)
        bitrate_options = [
            ('OpenCV (Auto)', 'opencv'),
            ('ProRes 422 HQ', 'prores'),
            ('40 Mbps', '40'),
            ('60 Mbps', '60'),
            ('80 Mbps', '80'),
            ('100 Mbps', '100'),
            ('120 Mbps', '120')
        ]
        for name, value in bitrate_options:
            self.bitrate_combo.addItem(name, value)
        self.bitrate_combo.setCurrentIndex(3)  # Default to 60 Mbps
        layout.addWidget(self.bitrate_combo, 1, 1)
        
        
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

        # Combined side-by-side output
        self.combined_checkbox = QCheckBox("📊 Combined Side-by-Side Output  (one video · shared FPS graph)")
        self.combined_checkbox.setChecked(True)
        self.combined_checkbox.setToolTip(
            "Creates ONE video: both clips side by side,\n"
            "with a shared frame-rate graph carrying two lines below them."
        )
        layout.addWidget(self.combined_checkbox, 4, 0, 1, 3)

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
        """Copy settings from parent analyzer including templates"""
        if hasattr(self.parent_analyzer, 'bitrate_combo'):
            # Find matching bitrate option
            parent_bitrate = self.parent_analyzer.bitrate_combo.currentData()
            for i in range(self.bitrate_combo.count()):
                if self.bitrate_combo.itemData(i) == parent_bitrate:
                    self.bitrate_combo.setCurrentIndex(i)
                    break
        
        if hasattr(self.parent_analyzer, 'sensitivity_combo'):
            parent_sensitivity = self.parent_analyzer.sensitivity_combo.currentText()
            self.sensitivity_combo.setCurrentText(parent_sensitivity)
        
        # Update template label
        
        self.log("📋 Settings copied from main window")
    
    def start_comparison(self):
        """Start comparison creation with PNG template support"""
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
        
        # Get bitrate setting
        bitrate_value = self.bitrate_combo.currentData()
        
        # Get template settings from parent
        fps_template_data = None
        if hasattr(self.parent_analyzer, 'fps_graph_combo'):
            fps_template_data = self.parent_analyzer.fps_graph_combo.currentData()
        
        # Create settings with proper template configuration
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
            'export_png': self.export_png_checkbox.isChecked(),
            # Pass through the FPS template from parent - PROPERLY FORMATTED
            'fps_graph_template': fps_template_data,
            'frametime_template': None,  # No frametime in comparison mode
            # Add template_config for the renderer
            'template_config': {
                'fps_graph_template': fps_template_data,
                'frametime_template': None
            },
            'viewport_a': getattr(self, 'viewport_a_slider', None) and self.viewport_a_slider.value() / 100.0 or 0.5,
            'viewport_b': getattr(self, 'viewport_b_slider', None) and self.viewport_b_slider.value() / 100.0 or 0.5,
            'color_a': getattr(self, '_color_a', [220, 120, 50]),
            'color_b': getattr(self, '_color_b', [50, 140, 255]),
            # Frosted-glass effect + the full overlay style from the Layout Editor
            'frosted_glass': getattr(self.parent_analyzer, 'overlay_style', {}).get('frosted_glass', False),
            'frost_blur': getattr(self.parent_analyzer, 'overlay_style', {}).get('frost_blur', 25),
            'frost_darken': getattr(self.parent_analyzer, 'overlay_style', {}).get('frost_darken', 0.35),
            'overlay_style': dict(getattr(self.parent_analyzer, 'overlay_style', {}) or {}),
        }
        
        # Get video names
        video_a_name = self.video_a_name_edit.text().strip() or "Video_A"
        video_b_name = self.video_b_name_edit.text().strip() or "Video_B"
        
        # Debug output goes HERE
        print(f"🔍 DEBUG: settings has template_config: {'template_config' in settings}")
        print(f"🔍 DEBUG: template_config inhalt: {settings.get('template_config')}")
        print(f"🔍 DEBUG: diff_threshold = {settings.get('diff_threshold')} (from sensitivity_combo)")

        # Combined or separate mode?
        if getattr(self, 'combined_checkbox', None) and self.combined_checkbox.isChecked():
            from dual_comparison_worker import DualComparisonWorker
            self.comparison_worker = DualComparisonWorker(
                self.video_a_path, self.video_b_path,
                video_a_name, video_b_name,
                output_dir, settings
            )
            self.comparison_worker.progress.connect(
                lambda phase, pct, msg: self._on_dual_progress(phase, pct, msg)
            )
            self.comparison_worker.finished.connect(
                lambda ok, msg: self.on_comparison_complete(ok, msg)
            )
            self.comparison_worker.preview.connect(self.on_frame_preview)
            self.log(f'🎬 Combined Mode: {video_a_name} vs {video_b_name}')
        else:
            self.comparison_worker = ComparisonWorker(
                self.video_a_path, self.video_b_path,
                video_a_name, video_b_name,
                output_dir, settings
            )
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
        
        # Log template info
        if fps_template_data and isinstance(fps_template_data, dict):
            template_name = fps_template_data.get('template', 'Default')
            self.log(f"🚀 Starting comparison with template: {template_name} ({resolution_name})")
        else:
            self.log(f"🚀 Starting comparison: {video_a_name} vs {video_b_name} ({resolution_name})")
    
    def cancel_comparison(self):
        """Cancel comparison creation"""
        if self.comparison_worker and self.comparison_worker.isRunning():
            self.comparison_worker.cancel()
            self.log("⏹️ Cancelling comparison creation...")
            
            # UI sofort updaten
            self.start_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.progress_a.setVisible(False)
            self.progress_b.setVisible(False)
            self.preview_display.setText("⏹️ Cancelled")
            
            # Wait briefly for a clean shutdown
            QTimer.singleShot(2000, self.check_cancel_complete)

    def check_cancel_complete(self):
        """Check if cancel completed"""
        if self.comparison_worker and self.comparison_worker.isRunning():
            self.comparison_worker.terminate()
            self.log("⚠️ Force terminated comparison worker")
        
        self.comparison_worker = None
        self.is_processing = False
    
    def _on_dual_progress(self, phase, percent, message):
        """Handle progress from DualComparisonWorker."""
        if percent <= 40:
            self.progress_a.setValue(min(100, percent * 2))  # 0-40% → Video A 0-80%
            self.progress_b.setValue(0)
        elif percent <= 80:
            self.progress_a.setValue(100)
            self.progress_b.setValue(min(100, (percent - 40) * 2))  # 40-80% → Video B 0-80%
        else:
            self.progress_a.setValue(100)
            self.progress_b.setValue(100)
        if percent != getattr(self, '_last_logged_pct', -1):
            self._last_logged_pct = percent
            self.log(message)

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
        # Wait for thread to fully finish before releasing the object
        if self.comparison_worker and self.comparison_worker.isRunning():
            self.comparison_worker.wait(5000)
        self.comparison_worker = None
        self.is_processing = False
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        
        # Verstecke Progress Bars
        self.progress_a.setVisible(False)
        self.progress_b.setVisible(False)
        
        if success:
            self.log("🎉 Comparison creation completed!")
            self.preview_display.setText("✅ Comparison\nCompleted")
            QMessageBox.information(self, 'Comparison Complete', message)
        else:
            # Tell cancel and error apart
            if "cancel" in message.lower():
                self.log("⏹️ Comparison cancelled by user")
                self.preview_display.setText("⏹️ Cancelled")
            else:
                self.log(f"❌ Comparison failed: {message}")
                self.preview_display.setText("❌ Error")
                QMessageBox.critical(self, 'Comparison Failed', message)
    
    def on_frame_preview(self, video_name, frame):
        """Handle frame preview updates"""
        try:
            from PyQt6.QtGui import QImage, QPixmap
            import numpy as np
            if frame is None or not hasattr(frame, 'shape'):
                return
            self.preview_label.setText(f"📹 {video_name} Preview:")
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb_frame = np.ascontiguousarray(rgb_frame)
            h, w, ch = rgb_frame.shape
            q_image = QImage(rgb_frame.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(q_image)
            scaled_pixmap = pixmap.scaled(
                192, 216,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
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