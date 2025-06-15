"""
UI Management Module für FPS Analyzer - ERWEITERT MIT SEGMENT SELECTION + NEUE FRAME TIME STANDARDS
Handles all UI component creation and layout with proper Qt object management
🎯 NEW: Segment Selection Feature für Video-Teilanalyse
✅ UPDATED: Neue Frame Time Standards (16.7ms, 33.3ms, 50ms) mit FPS-Angaben
"""

import torch
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QLineEdit, QComboBox, QProgressBar, QSizePolicy, QSlider, 
                             QTextEdit, QCheckBox, QSpinBox, QFrame, QApplication, QGroupBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPen, QBrush, QPolygon, QIntValidator
from PyQt6.QtCore import QPoint

class CustomComboBox(QComboBox):
    """Custom ComboBox with proper Qt object cleanup"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QComboBox {
                padding: 6px 25px 6px 6px;
                border: 1px solid #555;
                border-radius: 4px;
                background-color: #3c3c3c;
                color: #ffffff;
            }
            QComboBox:hover { border-color: #777; }
            QComboBox:focus { border-color: #4CAF50; }
            QComboBox::drop-down { border: none; width: 20px; background: transparent; }
            QComboBox::down-arrow { image: none; border: none; width: 0px; height: 0px; }
        """)

    def paintEvent(self, event):
        """Proper QPainter cleanup to prevent memory leaks"""
        super().paintEvent(event)
        painter = QPainter(self)
        if not painter.isActive():
            return
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = self.rect()
            arrow_x = rect.width() - 15
            arrow_y = rect.height() // 2
            triangle = QPolygon([
                QPoint(arrow_x - 4, arrow_y - 2),
                QPoint(arrow_x + 4, arrow_y - 2),
                QPoint(arrow_x, arrow_y + 3)
            ])
            if self.underMouse():
                painter.setBrush(QBrush(Qt.GlobalColor.green))
            else:
                painter.setBrush(QBrush(Qt.GlobalColor.white))
            painter.setPen(QPen(Qt.GlobalColor.transparent))
            painter.drawPolygon(triangle)
        except Exception as e:
            print(f"❌ Error in CustomComboBox painting: {e}")
        finally:
            if painter.isActive():
                painter.end()

class CustomSpinBox(QFrame):
    """Custom SpinBox with proper cleanup and value handling"""
    valueChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.minimum_value = 1
        self.maximum_value = 50
        self.current_value = 12
        self.suffix_text = " (×0.1)"
        self.value_input = None
        self.up_button = None
        self.down_button = None
        self.setup_ui()

    def setup_ui(self):
        """Setup UI with proper parent-child relationships"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Value input field
        self.value_input = QLineEdit(self)
        self.value_input.setText(str(self.current_value))
        self.value_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #555; border-radius: 4px 0px 0px 4px;
                background-color: #3c3c3c; color: #ffffff; padding: 6px; font-size: 11px;
            }
            QLineEdit:focus { border-color: #4CAF50; }
        """)
        self.value_input.textChanged.connect(self.on_text_changed)
        layout.addWidget(self.value_input)

        # Button container
        button_frame = QFrame(self)
        button_frame.setFixedWidth(20)
        button_layout = QVBoxLayout(button_frame)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(0)

        # Up/Down buttons
        self.up_button = QPushButton("▲", button_frame)
        self.up_button.setFixedSize(20, 16)
        self.up_button.clicked.connect(self.increment_value)
        button_layout.addWidget(self.up_button)

        self.down_button = QPushButton("▼", button_frame)
        self.down_button.setFixedSize(20, 16)
        self.down_button.clicked.connect(self.decrement_value)
        button_layout.addWidget(self.down_button)

        layout.addWidget(button_frame)

    def setValue(self, value):
        value = max(self.minimum_value, min(value, self.maximum_value))
        self.current_value = value
        if self.value_input:
            self.value_input.setText(str(value))

    def value(self):
        return self.current_value

    def increment_value(self):
        new_value = min(self.current_value + 1, self.maximum_value)
        if new_value != self.current_value:
            self.setValue(new_value)
            self.valueChanged.emit(new_value)

    def decrement_value(self):
        new_value = max(self.current_value - 1, self.minimum_value)
        if new_value != self.current_value:
            self.setValue(new_value)
            self.valueChanged.emit(new_value)

    def on_text_changed(self, text):
        try:
            value = int(text)
            value = max(self.minimum_value, min(value, self.maximum_value))
            if value != self.current_value:
                self.current_value = value
                self.valueChanged.emit(value)
        except ValueError:
            if self.value_input:
                self.value_input.setText(str(self.current_value))

class UIManager:
    """UI Manager with proper Qt object lifecycle management"""

    def __init__(self, parent):
        self.parent = parent
        self.widgets = {}
        self.layouts = {}

    def create_main_ui(self):
        """Create the main user interface with proper cleanup tracking"""
        central_widget = QWidget()
        self.parent.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        self.layouts['main'] = layout

        # Add components in order
        self.widgets['status_header'] = self.create_status_header()
        layout.addWidget(self.widgets['status_header'])

        self.widgets['preview_area'] = self.create_preview_area()
        layout.addWidget(self.widgets['preview_area'])

        self.widgets['timeline_slider'] = self.create_timeline_slider()
        layout.addWidget(self.widgets['timeline_slider'])

        playback_layout = self.create_playback_controls()
        self.layouts['playback'] = playback_layout
        layout.addLayout(playback_layout)

        file_layout = self.create_file_selection()
        self.layouts['file'] = file_layout
        layout.addLayout(file_layout)

        settings_layout = self.create_settings_panel()
        self.layouts['settings'] = settings_layout
        layout.addLayout(settings_layout)

        self.widgets['progress_bar'] = self.create_progress_bar()
        layout.addWidget(self.widgets['progress_bar'])

        self.widgets['status_label'] = self.create_status_label()
        layout.addWidget(self.widgets['status_label'])

        self.widgets['log_area'] = self.create_log_area()
        layout.addWidget(self.widgets['log_area'])

        return central_widget

    def create_status_header(self):
        """Create the CUDA status header"""
        cuda_status = QLabel(
            f"🚀 CUDA Available: {'✓ YES' if self.parent.cuda_available else '✗ NO'} | "
            f"GPU: {torch.cuda.get_device_name(0) if self.parent.cuda_available else 'N/A'} | "
            f"📊 Preview: 1080p Internal • Dynamic Scaling | "
            f"✅ Enhanced Smoothing & FPS Responsiveness"
        )
        cuda_status.setStyleSheet(
            f"color: {'#4CAF50' if self.parent.cuda_available else '#f44336'}; "
            f"font-weight: bold; font-size: 12px; padding: 8px; background-color: #3c3c3c; "
            f"border-radius: 5px; margin: 5px;"
        )
        return cuda_status

    def create_preview_area(self):
        """Create the video preview area"""
        self.parent.preview_label = QLabel(
            "📹 No video loaded - Select a video file to begin\n\n"
            "🎯 Preview Resolution: 1080p (Internal) • Dynamic Display Scaling\n"
            "⚡ Performance: Optimized OpenCV Rendering\n"
            "✨ NEW: Enhanced Frame Time Smoothing & Faster FPS Updates"
        )
        self.parent.preview_label.setStyleSheet(
            'background-color: #1a1a1a; color: #cccccc; border: 2px solid #555; '
            'font-size: 14px; padding: 20px;'
        )
        self.parent.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.parent.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        min_width = 640
        min_height = int(min_width * 9 / 16)  # 360
        self.parent.preview_label.setMinimumSize(min_width, min_height)
        return self.parent.preview_label

    def create_timeline_slider(self):
        """Create the timeline slider"""
        self.parent.timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self.parent.timeline_slider.setEnabled(False)
        self.parent.timeline_slider.sliderMoved.connect(self.parent.scrub_video)
        self.parent.timeline_slider.setStyleSheet(
            "QSlider::groove:horizontal { border: 1px solid #555; height: 8px; "
            "background: #3c3c3c; border-radius: 4px; } "
            "QSlider::handle:horizontal { background: #4CAF50; border: 1px solid #333; "
            "width: 18px; border-radius: 9px; margin: -5px 0; }"
        )
        return self.parent.timeline_slider

    def create_playback_controls(self):
        """Create playback control buttons with centered segment selection"""
        playback_layout = QHBoxLayout()

        # Left: Play button
        self.parent.play_button = QPushButton('▶️ Play')
        self.parent.play_button.clicked.connect(self.parent.toggle_playback)
        self.parent.play_button.setEnabled(False)
        self.parent.play_button.setStyleSheet(
            "font-size: 14px; padding: 8px 16px; background-color: #4CAF50; "
            "color: white; border: none; border-radius: 5px; font-weight: bold;"
        )
        playback_layout.addWidget(self.parent.play_button)

        # Add some space
        playback_layout.addSpacing(20)

        # Center: Segment Selection (200px wide section)
        segment_container = QFrame()
        segment_container.setFixedWidth(600)  # Fixed width container for centering
        segment_container.setStyleSheet("""
            QFrame {
                background-color: #2f2f2f;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 2px;
            }
        """)
        
        segment_layout = QHBoxLayout(segment_container)
        segment_layout.setContentsMargins(8, 4, 8, 4)
        segment_layout.setSpacing(8)
        
        # Segment label
        segment_label = QLabel("🎯")
        segment_label.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 14px; background: transparent; border: none;")
        segment_label.setFixedWidth(20)
        segment_layout.addWidget(segment_label)
        
        # Main Segment Button (200px wide as requested)
        self.parent.segment_btn = QPushButton("📍 Set Start Point")
        self.parent.segment_btn.setEnabled(False)
        self.parent.segment_btn.setFixedWidth(200)
        self.parent.segment_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px; padding: 6px 12px; 
                background-color: #2E7D32; color: white; 
                border: none; border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #4CAF50; }
            QPushButton:disabled { background-color: #404040; color: #666; }
        """)
        self.parent.segment_btn.clicked.connect(self.parent.handle_segment_button)
        segment_layout.addWidget(self.parent.segment_btn)
        
        # Clear Selection Button
        self.parent.clear_selection_btn = QPushButton("🗑️")
        self.parent.clear_selection_btn.setEnabled(False)
        self.parent.clear_selection_btn.setFixedWidth(32)
        self.parent.clear_selection_btn.setStyleSheet("""
            QPushButton {
                font-size: 12px; padding: 6px 8px; 
                background-color: #757575; color: white; 
                border: none; border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { background-color: #9E9E9E; }
            QPushButton:disabled { background-color: #404040; color: #666; }
        """)
        self.parent.clear_selection_btn.clicked.connect(self.parent.clear_selection)
        segment_layout.addWidget(self.parent.clear_selection_btn)
        
        # Segment Info Label - compact version
        self.parent.segment_info_label = QLabel("No segment")
        self.parent.segment_info_label.setStyleSheet("""
            QLabel {
                color: #aaaaaa; font-size: 11px; padding: 6px 8px;
                background-color: #1a1a1a; border-radius: 3px;
                border: 1px solid #444;
            }
        """)
        segment_layout.addWidget(self.parent.segment_info_label)
        
        # Add stretch within segment container
        segment_layout.addStretch()
        
        playback_layout.addWidget(segment_container)

        # Add some space
        playback_layout.addSpacing(20)

        # Right: Analysis button
        self.parent.analyze_button = QPushButton('🎯 Start FPS Analysis')
        self.parent.analyze_button.clicked.connect(self.parent.toggle_analysis)
        self.parent.analyze_button.setStyleSheet(
            "font-weight: bold; font-size: 16px; padding: 12px 24px; "
            "background-color: #4CAF50; color: white; border: none; border-radius: 8px;"
        )
        playback_layout.addWidget(self.parent.analyze_button)

        return playback_layout

    def create_file_selection(self):
        """Create file input/output selection"""
        file_layout = QHBoxLayout()

        # Input file section
        file_layout.addWidget(QLabel('📥 Input Video:'))
        self.parent.input_edit = QLineEdit()
        self.parent.input_edit.setPlaceholderText("Select input video file...")
        file_layout.addWidget(self.parent.input_edit)

        input_browse = QPushButton('📁 Browse...')
        input_browse.clicked.connect(self.parent.browse_input)
        file_layout.addWidget(input_browse)

        # Output file section
        file_layout.addWidget(QLabel('📤 Output Video:'))
        self.parent.output_edit = QLineEdit()
        self.parent.output_edit.setPlaceholderText("Output file will be auto-generated...")
        file_layout.addWidget(self.parent.output_edit)

        output_browse = QPushButton('📁 Browse...')
        output_browse.clicked.connect(self.parent.browse_output)
        file_layout.addWidget(output_browse)

        return file_layout

    def create_settings_panel(self):
        """Create settings panel with proper widget cleanup - UPDATED with new frame time standards"""
        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(15)

        # Hidden checkboxes for functionality
        self.parent.use_cuda_checkbox = QCheckBox()
        self.parent.use_cuda_checkbox.setChecked(self.parent.cuda_available)
        self.parent.use_cuda_checkbox.setEnabled(self.parent.cuda_available)
        self.parent.use_cuda_checkbox.setVisible(False)

        self.parent.show_frametime_checkbox = QCheckBox()
        self.parent.show_frametime_checkbox.setChecked(True)
        self.parent.show_frametime_checkbox.setVisible(False)

        # Output resolution
        settings_layout.addWidget(QLabel('📺 Output Resolution:'))
        self.parent.resolution_combo = CustomComboBox(self.parent)
        self.parent.resolution_combo.setMinimumWidth(180)
        resolutions = [
            ('720p (1280x720)', (1280, 720)),
            ('1080p (1920x1080)', (1920, 1080)),
            ('1440p (2560x1440)', (2560, 1440)),
            ('2160p/4K (3840x2160)', (3840, 2160))
        ]
        for name, res in resolutions:
            self.parent.resolution_combo.addItem(name, res)
        self.parent.resolution_combo.setCurrentIndex(1)  # Default to 1080p
        settings_layout.addWidget(self.parent.resolution_combo)

        # ✅ NEW: Bitrate with OpenCV/FFmpeg distinction
        settings_layout.addWidget(QLabel('📊 Bitrate:'))
        self.parent.bitrate_combo = CustomComboBox(self.parent)
        self.parent.bitrate_combo.setEditable(False)  # No manual editing
        self.parent.bitrate_combo.setMinimumWidth(140)
        self.parent.bitrate_combo.setMaximumWidth(140)
        
        # Clear distinction between OpenCV and FFmpeg
        bitrate_options = [
            ('OpenCV (Auto)', 'opencv'),
            ('40 Mbps', '40'),
            ('60 Mbps', '60'),
            ('80 Mbps', '80'), 
            ('100 Mbps', '100'),
            ('120 Mbps', '120')
        ]
        
        for name, value in bitrate_options:
            self.parent.bitrate_combo.addItem(name, value)
        
        self.parent.bitrate_combo.setCurrentIndex(2)  # Default: 60 Mbps
        
        # Helpful tooltip
        self.parent.bitrate_combo.setToolTip(
            "📊 Bitrate Control Methods:\n\n"
            "🔧 OpenCV (Auto):\n"
            "• Fast encoding\n"
            "• Automatic quality control\n"
            "• ~30-50 Mbps typical output\n\n"
            "🎬 40-120 Mbps (FFmpeg):\n"
            "• Exact bitrate control\n"
            "• Professional quality\n"
            "• Requires FFmpeg installation"
        )
        
        settings_layout.addWidget(self.parent.bitrate_combo)
        
        # Method label
        self.parent.bitrate_method_label = QLabel('Method: FFmpeg (60 Mbps)')
        self.parent.bitrate_method_label.setStyleSheet(
            "color: #4CAF50; font-size: 10px; font-style: italic; padding: 2px;"
        )
        settings_layout.addWidget(self.parent.bitrate_method_label)
        
        # Connect to update method label
        self.parent.bitrate_combo.currentTextChanged.connect(self.update_bitrate_method_label)

        # ✅ UPDATED: Frame time scale with new standards
        settings_layout.addWidget(QLabel('⏱️ Frame Time Scale:'))
        self.parent.frametime_scale_combo = CustomComboBox(self.parent)
        self.parent.frametime_scale_combo.setMinimumWidth(180)
        
        # ✅ NEW: Updated frame time scales with proper FPS targets
        frametime_scales = [
            # Standard gaming targets
            ('16.7-33.3-50ms (60/30/20 FPS)', {
                'min': 16.7, 'mid': 33.3, 'max': 50.0, 
                'labels': ['16.7', '33.3', '50.0']
            }),
            
            # High refresh rate gaming
            ('8.3-16.7-33.3ms (120/60/30 FPS)', {
                'min': 8.3, 'mid': 16.7, 'max': 33.3, 
                'labels': ['8.3', '16.7', '33.3']
            }),
            
            # Precision analysis (tight range)
            ('10-20-30ms (100/50/33 FPS)', {
                'min': 10.0, 'mid': 20.0, 'max': 30.0, 
                'labels': ['10.0', '20.0', '30.0']
            }),
            
            # Wide range for problematic content
            ('16.7-50-100ms (60/20/10 FPS)', {
                'min': 16.7, 'mid': 50.0, 'max': 100.0, 
                'labels': ['16.7', '50.0', '100.0']
            }),
            
            # Legacy standard (backward compatibility)
            ('10-35-60ms (Legacy)', {
                'min': 10, 'mid': 35, 'max': 60, 
                'labels': ['10', '35', '60']
            }),
            
            # Ultra high-end gaming (240+ FPS)
            ('4.2-8.3-16.7ms (240/120/60 FPS)', {
                'min': 4.2, 'mid': 8.3, 'max': 16.7, 
                'labels': ['4.2', '8.3', '16.7']
            })
        ]
        
        for name, scale_data in frametime_scales:
            self.parent.frametime_scale_combo.addItem(name, scale_data)
        
        # ✅ NEW: Default to the new standard (16.7-33.3-50ms)
        self.parent.frametime_scale_combo.setCurrentIndex(0)  # New standard as default
        settings_layout.addWidget(self.parent.frametime_scale_combo)

        # Detection sensitivity
        settings_layout.addWidget(QLabel('🎯 Detection Sensitivity:'))
        self.parent.sensitivity_combo = CustomComboBox(self.parent)
        self.parent.sensitivity_combo.setMinimumWidth(140)
        sensitivity_options = [
            ('Very High (0.0005)', 0.0005),
            ('High (0.001)', 0.001),
            ('Medium (0.002)', 0.002),
            ('Low (0.005)', 0.005),
            ('Very Low (0.01)', 0.01)
        ]
        for name, val in sensitivity_options:
            self.parent.sensitivity_combo.addItem(name, val)
        self.parent.sensitivity_combo.setCurrentIndex(2)  # Medium
        settings_layout.addWidget(self.parent.sensitivity_combo)

        # PNG Export Button
        self.parent.export_png_sequence_btn = QPushButton('🎬 Export PNG Alpha Sequence', self.parent)
        self.parent.export_png_sequence_btn.clicked.connect(self.parent.export_png_alpha_sequence)
        self.parent.export_png_sequence_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold; font-size: 11px; padding: 8px 12px;
                background-color: #607D8B; color: white; border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #4CAF50; }
            QPushButton:disabled { background-color: #2a2a2a; color: #666; }
        """)

        settings_layout.addStretch()
        settings_layout.addWidget(self.parent.export_png_sequence_btn)

        return settings_layout

    def create_progress_bar(self):
        """Create the progress bar"""
        self.parent.progress_bar = QProgressBar()
        self.parent.progress_bar.setVisible(False)
        self.parent.progress_bar.setStyleSheet(
            "QProgressBar { border: 2px solid #555; border-radius: 8px; "
            "text-align: center; background-color: #3c3c3c; color: #ffffff; "
            "font-weight: bold; } "
            "QProgressBar::chunk { background-color: #4CAF50; border-radius: 6px; }"
        )
        return self.parent.progress_bar

    def create_status_label(self):
        """Create the status label"""
        self.parent.status_label = QLabel("🎯 Ready - Load a video to begin • Enhanced Smoothing Active")
        self.parent.status_label.setStyleSheet(
            "color: #aaaaaa; font-style: italic; padding: 8px; "
            "background-color: #2f2f2f; border-radius: 5px; margin: 2px;"
        )
        return self.parent.status_label

    def create_log_area(self):
        """Create the log output area"""
        self.parent.log_text = QTextEdit()
        self.parent.log_text.setMaximumHeight(120)
        self.parent.log_text.setFont(QFont("Consolas", 9))
        self.parent.log_text.setStyleSheet(
            "background-color: #1e1e1e; border: 2px solid #555; color: #ffffff; "
            "border-radius: 5px; padding: 5px;"
        )
        self.parent.log_text.setPlaceholderText("🔍 Analysis log will appear here...")
        return self.parent.log_text

    def update_bitrate_method_label(self):
        """Update the bitrate method label based on current selection"""
        try:
            if not hasattr(self.parent, 'bitrate_combo') or not hasattr(self.parent, 'bitrate_method_label'):
                return
                
            current_data = self.parent.bitrate_combo.currentData()
            
            if current_data == 'opencv':
                # OpenCV automatic quality
                self.parent.bitrate_method_label.setText('Method: OpenCV (Auto)')
                self.parent.bitrate_method_label.setStyleSheet(
                    "color: #FF9800; font-size: 10px; font-style: italic; padding: 2px;"
                )
            elif isinstance(current_data, str) and current_data.isdigit():
                # FFmpeg exact bitrate
                bitrate_value = current_data
                self.parent.bitrate_method_label.setText(f'Method: FFmpeg ({bitrate_value} Mbps)')
                self.parent.bitrate_method_label.setStyleSheet(
                    "color: #4CAF50; font-size: 10px; font-style: italic; padding: 2px;"
                )
            else:
                # Fallback
                self.parent.bitrate_method_label.setText('Method: OpenCV (Auto)')
                self.parent.bitrate_method_label.setStyleSheet(
                    "color: #FF9800; font-size: 10px; font-style: italic; padding: 2px;"
                )
                
        except Exception as e:
            print(f"⚠️ Error updating bitrate method label: {e}")

    def cleanup_widgets(self):
        """Cleanup all widgets properly"""
        try:
            print("🧹 Cleaning up UI widgets...")
            for widget_name, widget in self.widgets.items():
                try:
                    if hasattr(widget, 'clicked'):
                        widget.clicked.disconnect()
                    elif hasattr(widget, 'valueChanged'):
                        widget.valueChanged.disconnect()
                    elif hasattr(widget, 'textChanged'):
                        widget.textChanged.disconnect()
                except Exception as e:
                    print(f"⚠️ Error disconnecting {widget_name}: {e}")
            self.widgets.clear()
            self.layouts.clear()
            print("✅ UI cleanup completed")
        except Exception as e:
            print(f"❌ Error during UI cleanup: {e}")

class ThemeManager:
    """Manages application themes and styling"""

    def __init__(self, parent):
        self.parent = parent

    def get_dark_theme(self):
        """Get dark theme stylesheet"""
        return """
        QMainWindow { background-color: #2b2b2b; color: #ffffff; }
        QWidget { background-color: #2b2b2b; color: #ffffff; font-family: 'Segoe UI', Arial, sans-serif; }
        QLabel { font-size: 11px; color: #ffffff; background-color: transparent; }
        QPushButton { 
            padding: 6px 12px; border: 1px solid #555; border-radius: 6px; 
            background-color: #3c3c3c; color: #ffffff; font-weight: 500;
        }
        QPushButton:hover { background-color: #4a4a4a; border-color: #777; }
        QPushButton:pressed { background-color: #333; }
        QPushButton:disabled { background-color: #2a2a2a; color: #666; border-color: #444; }
        QLineEdit { 
            padding: 6px; border: 1px solid #555; border-radius: 4px; 
            background-color: #3c3c3c; color: #ffffff; 
        }
        QLineEdit:hover { border-color: #777; }
        QLineEdit:focus { border-color: #4CAF50; }
        QComboBox, QSpinBox { 
            padding: 6px; border: 1px solid #555; border-radius: 4px; 
            background-color: #3c3c3c; color: #ffffff; 
        }
        QTextEdit { background-color: #1e1e1e; border: 1px solid #555; color: #ffffff; }
        QProgressBar { 
            border: 2px solid #555; border-radius: 8px; text-align: center; 
            background-color: #3c3c3c; color: #ffffff; font-weight: bold;
        }
        QProgressBar::chunk { background-color: #4CAF50; border-radius: 6px; }
        QCheckBox { color: #ffffff; spacing: 8px; }
        QCheckBox::indicator {
            width: 16px; height: 16px; border: 2px solid #555; border-radius: 3px; background-color: #3c3c3c;
        }
        QCheckBox::indicator:checked { background-color: #4CAF50; border-color: #4CAF50; }
        QSlider::groove:horizontal { border: 1px solid #555; height: 8px; background: #3c3c3c; border-radius: 4px; }
        QSlider::handle:horizontal { background: #4CAF50; border: 1px solid #333; width: 18px; border-radius: 9px; margin: -5px 0; }
        QSlider::handle:horizontal:hover { background: #66BB6A; }
        QMenuBar { background-color: #3c3c3c; color: #ffffff; border-bottom: 1px solid #555; padding: 2px; }
        QMenuBar::item { padding: 6px 12px; border-radius: 4px; }
        QMenuBar::item:selected { background-color: #4CAF50; }
        QMenu { background-color: #2b2b2b; color: #ffffff; border: 1px solid #555; border-radius: 6px; padding: 4px; }
        QMenu::item { padding: 6px 24px 6px 8px; border-radius: 4px; }
        QMenu::item:selected { background-color: #4CAF50; }
        QMenu::separator { height: 1px; background-color: #555; margin: 4px 8px; }
        QGroupBox {
            font-weight: bold; border: 2px solid #555; border-radius: 8px; 
            margin-top: 8px; padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin; left: 10px; padding: 0 8px 0 8px; color: #4CAF50;
        }
        QScrollBar:vertical { background-color: #3c3c3c; width: 12px; border-radius: 6px; }
        QScrollBar::handle:vertical { background-color: #555; min-height: 20px; border-radius: 6px; }
        QScrollBar::handle:vertical:hover { background-color: #777; }
        """

    def get_light_theme(self):
        """Get light theme stylesheet"""
        return """
        QMainWindow { background-color: #f5f5f5; color: #333333; }
        QWidget { background-color: #f5f5f5; color: #333333; }
        QLabel { color: #333333; background-color: transparent; }
        QPushButton { 
            padding: 6px 12px; border: 1px solid #ccc; border-radius: 6px; 
            background-color: #ffffff; color: #333333; 
        }
        QPushButton:hover { background-color: #e8e8e8; }
        QComboBox, QLineEdit, QSpinBox { 
            padding: 6px; border: 1px solid #ccc; border-radius: 4px; 
            background-color: #ffffff; color: #333333; 
        }
        QTextEdit { background-color: #ffffff; border: 1px solid #ccc; color: #333333; }
        QMenuBar { background-color: #e8e8e8; color: #333333; }
        QMenuBar::item:selected { background-color: #4CAF50; color: white; }
        QMenu { background-color: #ffffff; color: #333333; border: 1px solid #ccc; }
        QMenu::item:selected { background-color: #4CAF50; color: white; }
        """