"""
UI Management Module für FPS Analyzer - ULTIMATE FIX with Custom Widgets
Handles all UI component creation and layout with working arrows
"""
import torch
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QLineEdit, QComboBox, QProgressBar, QSizePolicy, QSlider, 
                             QTextEdit, QCheckBox, QSpinBox, QFrame, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPen, QBrush, QPolygon
from PyQt6.QtCore import QPoint

class CustomComboBox(QComboBox):
    """Custom ComboBox with working dropdown arrow"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Remove the default dropdown arrow styling
        self.setStyleSheet("""
            QComboBox {
                padding: 6px 25px 6px 6px;
                border: 1px solid #555;
                border-radius: 4px;
                background-color: #3c3c3c;
                color: #ffffff;
            }
            QComboBox:hover {
                border-color: #777;
            }
            QComboBox:focus {
                border-color: #4CAF50;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
                border: none;
                width: 0px;
                height: 0px;
            }
        """)
    
    def paintEvent(self, event):
        super().paintEvent(event)
        
        # Draw custom arrow
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Arrow position (right side)
        rect = self.rect()
        arrow_x = rect.width() - 15
        arrow_y = rect.height() // 2
        
        # Create triangle points for down arrow ▼
        triangle = QPolygon([
            QPoint(arrow_x - 4, arrow_y - 2),
            QPoint(arrow_x + 4, arrow_y - 2),
            QPoint(arrow_x, arrow_y + 3)
        ])
        
        # Set color based on state
        if self.underMouse():
            painter.setBrush(QBrush(Qt.GlobalColor.green))
        else:
            painter.setBrush(QBrush(Qt.GlobalColor.white))
        
        painter.setPen(QPen(Qt.GlobalColor.transparent))
        painter.drawPolygon(triangle)

class CustomSpinBox(QFrame):
    """Custom SpinBox with working up/down arrows and proper value handling"""
    
    valueChanged = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.minimum_value = 1
        self.maximum_value = 50
        self.current_value = 12
        self.suffix_text = " (×0.1)"
        
        # Setup layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Value input field
        self.value_input = QLineEdit()
        self.value_input.setText(str(self.current_value))
        self.value_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #555;
                border-radius: 4px 0px 0px 4px;
                background-color: #3c3c3c;
                color: #ffffff;
                padding: 6px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
            }
        """)
        self.value_input.textChanged.connect(self.on_text_changed)
        layout.addWidget(self.value_input)
        
        # Button container
        button_frame = QFrame()
        button_frame.setFixedWidth(20)
        button_layout = QVBoxLayout(button_frame)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(0)
        
        # Up button ▲
        self.up_button = QPushButton("▲")
        self.up_button.setFixedSize(20, 16)
        self.up_button.setStyleSheet("""
            QPushButton {
                border: 1px solid #555;
                border-left: none;
                border-bottom: 1px solid #555;
                border-radius: 0px 4px 0px 0px;
                background-color: #4a4a4a;
                color: #ffffff;
                font-size: 8px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
                color: #4CAF50;
            }
            QPushButton:pressed {
                background-color: #4CAF50;
            }
        """)
        self.up_button.clicked.connect(self.increment_value)
        button_layout.addWidget(self.up_button)
        
        # Down button ▼
        self.down_button = QPushButton("▼")
        self.down_button.setFixedSize(20, 16)
        self.down_button.setStyleSheet("""
            QPushButton {
                border: 1px solid #555;
                border-left: none;
                border-top: none;
                border-radius: 0px 0px 4px 0px;
                background-color: #4a4a4a;
                color: #ffffff;
                font-size: 8px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
                color: #4CAF50;
            }
            QPushButton:pressed {
                background-color: #4CAF50;
            }
        """)
        self.down_button.clicked.connect(self.decrement_value)
        button_layout.addWidget(self.down_button)
        
        layout.addWidget(button_frame)
        
        # Overall frame styling
        self.setStyleSheet("""
            QFrame {
                background: transparent;
            }
        """)
    
    def setRange(self, minimum, maximum):
        """Set the range of valid values"""
        self.minimum_value = minimum
        self.maximum_value = maximum
    
    def setValue(self, value):
        """Set the current value"""
        value = max(self.minimum_value, min(value, self.maximum_value))
        self.current_value = value
        self.value_input.setText(str(value))
    
    def value(self):
        """Get the current value"""
        return self.current_value
    
    def setSuffix(self, suffix):
        """Set suffix text"""
        self.suffix_text = suffix
    
    def increment_value(self):
        """Increase value by 1"""
        new_value = min(self.current_value + 1, self.maximum_value)
        if new_value != self.current_value:
            self.setValue(new_value)
            self.valueChanged.emit(new_value)
    
    def decrement_value(self):
        """Decrease value by 1"""
        new_value = max(self.current_value - 1, self.minimum_value)
        if new_value != self.current_value:
            self.setValue(new_value)
            self.valueChanged.emit(new_value)
    
    def on_text_changed(self, text):
        """Handle manual text input"""
        try:
            value = int(text)
            value = max(self.minimum_value, min(value, self.maximum_value))
            if value != self.current_value:
                self.current_value = value
                self.valueChanged.emit(value)
        except ValueError:
            # Invalid input, revert to current value
            self.value_input.setText(str(self.current_value))

class UIManager:
    """Manages UI creation and layout for the FPS Analyzer"""
    
    def __init__(self, parent):
        self.parent = parent
    
    def create_main_ui(self):
        """Create the main user interface"""
        central_widget = QWidget()
        self.parent.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Add components in order
        layout.addWidget(self.create_status_header())
        layout.addWidget(self.create_preview_area())
        layout.addWidget(self.create_timeline_slider())
        layout.addLayout(self.create_playback_controls())
        layout.addLayout(self.create_file_selection())
        layout.addLayout(self.create_settings_panel())
        layout.addWidget(self.create_progress_bar())
        layout.addWidget(self.create_status_label())
        layout.addWidget(self.create_log_area())
        
        return central_widget
    
    def create_status_header(self):
        """Create the CUDA status header"""
        cuda_status = QLabel(
            f"🚀 CUDA Available: {'✓ YES' if self.parent.cuda_available else '✗ NO'} | "
            f"GPU: {torch.cuda.get_device_name(0) if self.parent.cuda_available else 'N/A'} | "
            f"📊 Preview: 1080p Internal • Dynamic Scaling"
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
            "⚡ Performance: Optimized OpenCV Rendering"
        )
        self.parent.preview_label.setStyleSheet(
            'background-color: #1a1a1a; color: #cccccc; border: 2px solid #555; '
            'font-size: 14px; padding: 20px;'
        )
        
        # Dynamic sizing
        self.parent.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.parent.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Minimum size (16:9 ratio)
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
        """Create playback control buttons"""
        playback_layout = QHBoxLayout()
        
        # Play button
        self.parent.play_button = QPushButton('▶️ Play')
        self.parent.play_button.clicked.connect(self.parent.toggle_playback)
        self.parent.play_button.setEnabled(False)
        self.parent.play_button.setStyleSheet(
            "font-size: 14px; padding: 8px 16px; background-color: #4CAF50; "
            "color: white; border: none; border-radius: 5px; font-weight: bold;"
        )
        playback_layout.addWidget(self.parent.play_button)
        
        # Spacer
        playback_layout.addStretch()
        
        # Main analysis button
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
        """Create the main settings panel with WORKING custom widgets"""
        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(15)
        
        # Create hidden checkboxes that were removed from UI but still needed for functionality
        self.parent.use_cuda_checkbox = QCheckBox()
        self.parent.use_cuda_checkbox.setChecked(self.parent.cuda_available)
        self.parent.use_cuda_checkbox.setEnabled(self.parent.cuda_available)
        self.parent.use_cuda_checkbox.setVisible(False)  # Hidden but functional
        
        self.parent.show_frametime_checkbox = QCheckBox()
        self.parent.show_frametime_checkbox.setChecked(True)
        self.parent.show_frametime_checkbox.setVisible(False)  # Hidden but functional
        
        # Output resolution with custom combobox
        settings_layout.addWidget(QLabel('📺 Output Resolution:'))
        self.parent.resolution_combo = CustomComboBox()
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
        
        # Bitrate - Custom ComboBox
        settings_layout.addWidget(QLabel('📊 Bitrate:'))
        self.parent.bitrate_combo = CustomComboBox()
        self.parent.bitrate_combo.setEditable(True)
        self.parent.bitrate_combo.setMinimumWidth(120)
        self.parent.bitrate_combo.setMaximumWidth(120)
        
        # Vordefinierte Bitrate-Optionen
        bitrate_options = ['10', '20', '40', '60', '80', '100']
        self.parent.bitrate_combo.addItems(bitrate_options)
        self.parent.bitrate_combo.setCurrentText('60')  # Standard: 60 Mbit/s
        
        # Validator für nur Zahlen
        from PyQt6.QtGui import QIntValidator
        validator = QIntValidator(5, 500)  # Erlaubt 5-500 Mbit/s
        self.parent.bitrate_combo.setValidator(validator)
        
        settings_layout.addWidget(self.parent.bitrate_combo)
        
        # Label für "Mbit/s"
        settings_layout.addWidget(QLabel('Mbit/s'))
        
        # Frame time scale with custom combobox
        settings_layout.addWidget(QLabel('⏱️ Frame Time Scale:'))
        self.parent.frametime_scale_combo = CustomComboBox()
        self.parent.frametime_scale_combo.setMinimumWidth(160)
        frametime_scales = [
            ('0-10-30ms (High FPS)', {'min': 0, 'mid': 10, 'max': 30, 'labels': ['0', '10', '30']}),
            ('10-35-60ms (Standard)', {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']}),
            ('20-30-40ms (Precision)', {'min': 20, 'mid': 30, 'max': 40, 'labels': ['20', '30', '40']}),
            ('5-20-50ms (Wide Range)', {'min': 5, 'mid': 20, 'max': 50, 'labels': ['5', '20', '50']})
        ]
        for name, scale_data in frametime_scales:
            self.parent.frametime_scale_combo.addItem(name, scale_data)
        self.parent.frametime_scale_combo.setCurrentIndex(1)  # Standard
        settings_layout.addWidget(self.parent.frametime_scale_combo)
        
        # Detection sensitivity with custom combobox
        settings_layout.addWidget(QLabel('🎯 Detection Sensitivity:'))
        self.parent.sensitivity_combo = CustomComboBox()
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
        
        # 🎬 NEW: PNG Alpha Sequence Export Button
        self.parent.export_png_sequence_btn = QPushButton('🎬 Export PNG Alpha Sequence')
        self.parent.export_png_sequence_btn.clicked.connect(self.parent.export_png_alpha_sequence)
        self.parent.export_png_sequence_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                font-size: 11px;
                padding: 8px 12px;
                background-color: #607D8B;
                color: white;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #4CAF50;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666;
            }
        """)
        

        # Stretch am Ende um gleichmäßige Verteilung zu erreichen
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
        self.parent.status_label = QLabel("🎯 Ready - Load a video to begin")
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

class ThemeManager:
    """Manages application themes and styling"""
    
    def __init__(self, parent):
        self.parent = parent
    
    def get_dark_theme(self):
        """Get dark theme stylesheet - SIMPLIFIED since we use custom widgets"""
        return """
        /* Main Window */
        QMainWindow { 
            background-color: #2b2b2b; 
            color: #ffffff; 
        }
        
        /* General Widgets */
        QWidget { 
            background-color: #2b2b2b; 
            color: #ffffff; 
            font-family: 'Segoe UI', Arial, sans-serif;
        }
        
        /* Labels */
        QLabel { 
            font-size: 11px; 
            color: #ffffff; 
            background-color: transparent; 
        }
        
        /* Buttons */
        QPushButton { 
            padding: 6px 12px; 
            border: 1px solid #555; 
            border-radius: 6px; 
            background-color: #3c3c3c; 
            color: #ffffff; 
            font-weight: 500;
        }
        QPushButton:hover { 
            background-color: #4a4a4a; 
            border-color: #777;
        }
        QPushButton:pressed { 
            background-color: #333; 
        }
        QPushButton:disabled {
            background-color: #2a2a2a;
            color: #666;
            border-color: #444;
        }
        
        /* Input Fields */
        QLineEdit { 
            padding: 6px; 
            border: 1px solid #555; 
            border-radius: 4px; 
            background-color: #3c3c3c; 
            color: #ffffff; 
        }
        QLineEdit:hover {
            border-color: #777;
        }
        QLineEdit:focus {
            border-color: #4CAF50;
        }
        
        /* Default QComboBox and QSpinBox (fallback) */
        QComboBox, QSpinBox { 
            padding: 6px; 
            border: 1px solid #555; 
            border-radius: 4px; 
            background-color: #3c3c3c; 
            color: #ffffff; 
        }
        
        /* Text Edit */
        QTextEdit { 
            background-color: #1e1e1e; 
            border: 1px solid #555; 
            color: #ffffff; 
        }
        
        /* Progress Bar */
        QProgressBar { 
            border: 2px solid #555; 
            border-radius: 8px; 
            text-align: center; 
            background-color: #3c3c3c; 
            color: #ffffff; 
            font-weight: bold;
        }
        QProgressBar::chunk { 
            background-color: #4CAF50; 
            border-radius: 6px;
        }
        
        /* Checkboxes */
        QCheckBox { 
            color: #ffffff; 
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #555;
            border-radius: 3px;
            background-color: #3c3c3c;
        }
        QCheckBox::indicator:checked {
            background-color: #4CAF50;
            border-color: #4CAF50;
        }
        
        /* Sliders */
        QSlider::groove:horizontal {
            border: 1px solid #555;
            height: 8px;
            background: #3c3c3c;
            border-radius: 4px;
        }
        QSlider::handle:horizontal {
            background: #4CAF50;
            border: 1px solid #333;
            width: 18px;
            border-radius: 9px;
            margin: -5px 0;
        }
        QSlider::handle:horizontal:hover {
            background: #66BB6A;
        }
        
        /* Menu Bar */
        QMenuBar { 
            background-color: #3c3c3c; 
            color: #ffffff; 
            border-bottom: 1px solid #555;
            padding: 2px;
        }
        QMenuBar::item {
            padding: 6px 12px;
            border-radius: 4px;
        }
        QMenuBar::item:selected { 
            background-color: #4CAF50; 
        }
        
        /* Menus */
        QMenu { 
            background-color: #2b2b2b; 
            color: #ffffff; 
            border: 1px solid #555;
            border-radius: 6px;
            padding: 4px;
        }
        QMenu::item {
            padding: 6px 24px 6px 8px;
            border-radius: 4px;
        }
        QMenu::item:selected { 
            background-color: #4CAF50; 
        }
        QMenu::separator {
            height: 1px;
            background-color: #555;
            margin: 4px 8px;
        }
        
        /* Group Boxes */
        QGroupBox {
            font-weight: bold;
            border: 2px solid #555;
            border-radius: 8px;
            margin-top: 8px;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 8px 0 8px;
            color: #4CAF50;
        }
        
        /* Scroll Bars */
        QScrollBar:vertical {
            background-color: #3c3c3c;
            width: 12px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background-color: #555;
            min-height: 20px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #777;
        }
        """
    
    def get_light_theme(self):
        """Get light theme stylesheet"""
        return """
        /* Light Theme - SIMPLIFIED */
        QMainWindow { 
            background-color: #f5f5f5; 
            color: #333333; 
        }
        
        QWidget { 
            background-color: #f5f5f5; 
            color: #333333; 
        }
        
        QLabel { 
            color: #333333; 
            background-color: transparent; 
        }
        
        QPushButton { 
            padding: 6px 12px; 
            border: 1px solid #ccc; 
            border-radius: 6px; 
            background-color: #ffffff; 
            color: #333333; 
        }
        QPushButton:hover { 
            background-color: #e8e8e8; 
        }
        
        QComboBox, QLineEdit, QSpinBox { 
            padding: 6px; 
            border: 1px solid #ccc; 
            border-radius: 4px; 
            background-color: #ffffff; 
            color: #333333; 
        }
        
        QTextEdit { 
            background-color: #ffffff; 
            border: 1px solid #ccc; 
            color: #333333; 
        }
        
        QMenuBar { 
            background-color: #e8e8e8; 
            color: #333333; 
        }
        QMenuBar::item:selected { 
            background-color: #4CAF50; 
            color: white;
        }
        
        QMenu { 
            background-color: #ffffff; 
            color: #333333; 
            border: 1px solid #ccc; 
        }
        QMenu::item:selected { 
            background-color: #4CAF50; 
            color: white;
        }
        """