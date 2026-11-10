# ui_manager.py

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QLineEdit, QComboBox, QProgressBar, QSizePolicy, QSlider,
                             QTextEdit, QCheckBox, QSpinBox, QFrame, QApplication, QGroupBox, QGridLayout,
                             QStyle, QStyleOptionSlider) # GEÄNDERT: QGridLayout importiert
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPen, QBrush, QPolygon
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
        # GEÄNDERT: try...finally Block zur Behebung des Memory Leaks
        try:
            if not painter.isActive():
                return
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
                painter.end() # WICHTIG: Stellt sicher, dass der Painter immer beendet wird.

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

class ClickableSlider(QSlider):
    """
    QSlider, der auf Klick direkt an die angeklickte Stelle springt.

    Warum nötig: Qt springt beim Klick auf die Rille standardmäßig nur um
    einen Page-Step weiter, statt an die Klickposition. Bei einem Video mit
    mehreren tausend Frames heißt das, den Griff von Hand hinzuziehen.

    Linksklick setzt den Wert direkt und startet zugleich das Ziehen, damit
    Klicken und Scrubben nahtlos ineinander übergehen. Das normale
    Qt-Verhalten für Mausrad und Tastatur bleibt unverändert.
    """

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._dragging = False

    def _value_from_pos(self, pos):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        style = self.style()
        groove = style.subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                      QStyle.SubControl.SC_SliderGroove, self)
        handle = style.subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                      QStyle.SubControl.SC_SliderHandle, self)
        if self.orientation() == Qt.Orientation.Horizontal:
            # Griffbreite herausrechnen, sonst liegt der Sprung um die halbe
            # Griffbreite daneben — besonders an den beiden Enden sichtbar.
            span = groove.width() - handle.width()
            rel = int(pos.x() - groove.x() - handle.width() / 2)
        else:
            span = groove.height() - handle.height()
            rel = int(pos.y() - groove.y() - handle.height() / 2)
        if span <= 0:
            return self.value()
        return QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), rel, span,
            opt.upsideDown if self.orientation() == Qt.Orientation.Vertical else False)

    def _apply(self, pos):
        val = self._value_from_pos(pos)
        if val != self.value():
            self.setValue(val)
        self.sliderMoved.emit(val)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._dragging = True
            self.setSliderDown(True)
            self._apply(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._apply(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)


def format_timecode(frames, fps):
    """Frameanzahl als mm:ss.ms bzw. h:mm:ss.ms formatieren."""
    if not fps or fps <= 0:
        return "--:--"
    total = max(0.0, frames / float(fps))
    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = int(total % 60)
    cs = int(round((total - int(total)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    if h:
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
    return f"{m:02d}:{s:02d}.{cs:02d}"


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
        status_header = self.create_status_header()
        if status_header is not None:
            self.widgets['status_header'] = status_header
            layout.addWidget(status_header)

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

        status_label = self.create_status_label()
        if status_label is not None:
            self.widgets['status_label'] = status_label
            layout.addWidget(status_label)

        self.widgets['log_area'] = self.create_log_area()
        layout.addWidget(self.widgets['log_area'])

        return central_widget

    def create_status_header(self):
        """Status header removed - was mostly hardcoded text"""
        return None

    def create_preview_area(self):
        """Create the video preview area"""
        self.parent.preview_label = QLabel(
            "📹 No video loaded - Select a video file to begin\n\n"
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
        """Timeline mit Klick-zum-Springen und Zeitanzeige"""
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self.parent.timeline_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.parent.timeline_slider.setEnabled(False)
        self.parent.timeline_slider.sliderMoved.connect(self.parent.scrub_video)
        self.parent.timeline_slider.setStyleSheet(
            "QSlider::groove:horizontal { border: 1px solid #555; height: 8px; "
            "background: #3c3c3c; border-radius: 4px; } "
            "QSlider::handle:horizontal { background: #4CAF50; border: 1px solid #333; "
            "width: 18px; border-radius: 9px; margin: -5px 0; }"
        )
        self.parent.timeline_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.parent.timeline_slider.setToolTip(
            "Klicken springt direkt an die Stelle, Ziehen scrubbt")
        row.addWidget(self.parent.timeline_slider, 1)

        self.parent.timeline_time_label = QLabel("--:-- / --:--")
        self.parent.timeline_time_label.setStyleSheet(
            "color: #cccccc; font-family: Consolas, monospace; font-size: 11px;")
        self.parent.timeline_time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.parent.timeline_time_label.setMinimumWidth(190)
        self.parent.timeline_time_label.setToolTip("Position / Gesamtlänge · Frame")
        row.addWidget(self.parent.timeline_time_label, 0)

        return container

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
        # GEÄNDERT: von QHBoxLayout zu QGridLayout für bessere Skalierbarkeit
        settings_layout = QGridLayout()
        settings_layout.setSpacing(15)

        # Hidden checkboxes for functionality
        self.parent.use_cuda_checkbox = QCheckBox()
        self.parent.use_cuda_checkbox.setChecked(self.parent.cuda_available)
        self.parent.use_cuda_checkbox.setEnabled(self.parent.cuda_available)
        self.parent.use_cuda_checkbox.setVisible(False)

        self.parent.show_frametime_checkbox = QCheckBox()
        self.parent.show_frametime_checkbox.setChecked(True)
        self.parent.show_frametime_checkbox.setVisible(False)
        
        # --- ZEILE 0 ---

        # Output resolution
        settings_layout.addWidget(QLabel('📺 Output Resolution:'), 0, 0)
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
        settings_layout.addWidget(self.parent.resolution_combo, 0, 1)

        # Bitrate with OpenCV/FFmpeg distinction
        settings_layout.addWidget(QLabel('📊 Bitrate:'), 0, 2)
        self.parent.bitrate_combo = CustomComboBox(self.parent)
        self.parent.bitrate_combo.setEditable(False)  # No manual editing
        self.parent.bitrate_combo.setMinimumWidth(140)
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
            self.parent.bitrate_combo.addItem(name, value)
        self.parent.bitrate_combo.setCurrentIndex(2)  # Default: 60 Mbps
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
        settings_layout.addWidget(self.parent.bitrate_combo, 0, 3)
        
        # FPS/Frametime graph combos and Detection controls live in Options (⚙️ Edit → Options).
        # We still create them as hidden widgets so the rest of the code can read their values.
        self.parent.fps_graph_combo = CustomComboBox(self.parent)
        fps_templates = [
            ('60-30-0 FPS (Standard)',          {'template': 'FPS-603000.png',  'max_fps': 60,  'grid_lines': [60, 30, 0]}),
            ('60-45-30 FPS (Competitive)',       {'template': 'FPS-604530.png',  'max_fps': 60,  'grid_lines': [60, 45, 30]}),
            ('60-55-50 FPS (V-Sync)',            {'template': 'FPS-605550.png',  'max_fps': 60,  'grid_lines': [60, 55, 50]}),
            ('30-15-0 FPS (Console)',            {'template': 'FPS-301500.png',  'max_fps': 30,  'grid_lines': [30, 15, 0]}),
            ('60-30-20 FPS (Low Perf)',          {'template': 'FPS-603020.png',  'max_fps': 60,  'grid_lines': [60, 30, 20]}),
            ('120-90-60 FPS (High Refresh)',     {'template': 'FPS-1209060.png', 'max_fps': 120, 'grid_lines': [120, 90, 60]}),
        ]
        for name, data in fps_templates:
            self.parent.fps_graph_combo.addItem(name, data)
        self.parent.fps_graph_combo.setCurrentIndex(0)
        self.parent.fps_graph_combo.setVisible(False)

        self.parent.frametime_combo = CustomComboBox(self.parent)
        ft_templates = [
            ('33.3-25-16.7ms (60/40/30 FPS)',   {'template': 'FT-332516.png',   'scale': {'min': 16.7, 'mid': 25.0,  'max': 33.3}}),
            ('16.7-12-8.3ms (60/83/120 FPS)',   {'template': 'FT-161208.png',   'scale': {'min': 8.3,  'mid': 12.0,  'max': 16.7}}),
            ('20-18-16.7ms (50/55/60 FPS)',     {'template': 'FT-201816.png',   'scale': {'min': 16.7, 'mid': 18.0,  'max': 20.0}}),
            ('50-33.3-16.7ms (20/30/60 FPS)',   {'template': 'FT-503316.png',   'scale': {'min': 16.7, 'mid': 33.3,  'max': 50.0}}),
            ('66.7-50-33.3ms (15/20/30 FPS)',   {'template': 'FT-665033.png',   'scale': {'min': 33.3, 'mid': 50.0,  'max': 66.7}}),
            ('16.7-33.3-100ms (60/30/10 FPS)',  {'template': 'FT-1633100.png',  'scale': {'min': 16.7, 'mid': 33.3,  'max': 100.0}}),
            ('100-66.7-33.3ms (10/15/30 FPS)',  {'template': 'FT-1006633.png',  'scale': {'min': 33.3, 'mid': 66.7,  'max': 100.0}}),
        ]
        for name, data in ft_templates:
            self.parent.frametime_combo.addItem(name, data)
        self.parent.frametime_combo.setCurrentIndex(0)
        self.parent.frametime_combo.setVisible(False)

        self.parent.sensitivity_combo = CustomComboBox(self.parent)
        for name, val in [
            ('Very High (0.015)', 0.015), ('High (0.01)', 0.01),
            ('Medium (0.005)', 0.005),    ('Low (0.002)', 0.002),
            ('Very Low (0.001)', 0.001),
        ]:
            self.parent.sensitivity_combo.addItem(name, val)
        self.parent.sensitivity_combo.setCurrentIndex(2)
        self.parent.sensitivity_combo.setVisible(False)

        self.parent.baseline_fps_combo = CustomComboBox(self.parent)
        for name, value in [
            ('Auto-detect', 0), ('20 FPS', 20), ('24 FPS', 24), ('25 FPS', 25),
            ('30 FPS', 30), ('40 FPS', 40), ('50 FPS', 50), ('60 FPS', 60),
            ('72 FPS', 72), ('90 FPS', 90), ('100 FPS', 100), ('120 FPS', 120),
        ]:
            self.parent.baseline_fps_combo.addItem(name, value)
        self.parent.baseline_fps_combo.setCurrentIndex(0)
        self.parent.baseline_fps_combo.setVisible(False)

        # Options button
        options_btn = QPushButton('⚙️ Options...')
        options_btn.setToolTip('Configure templates, detection, graph style and display (Ctrl+,)')
        options_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold; font-size: 11px; padding: 8px 14px;
                background-color: #455A64; color: white; border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #607D8B; }
        """)
        options_btn.clicked.connect(self._open_options)
        settings_layout.addWidget(options_btn, 0, 4)

        # PNG Export Button
        self.parent.export_png_sequence_btn = QPushButton('🎬 Export PNG', self.parent)
        self.parent.export_png_sequence_btn.clicked.connect(self.parent.export_png_alpha_sequence)
        self.parent.export_png_sequence_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold; font-size: 11px; padding: 8px 12px;
                background-color: #607D8B; color: white; border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #4CAF50; }
            QPushButton:disabled { background-color: #2a2a2a; color: #666; }
        """)
        settings_layout.addWidget(self.parent.export_png_sequence_btn, 1, 4)

        # Connect change handlers
        self.parent.fps_graph_combo.currentIndexChanged.connect(self.on_template_changed)
        self.parent.frametime_combo.currentIndexChanged.connect(self.on_template_changed)

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
        """Status label removed - was static/meaningless text"""
        return None

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

    def _open_options(self):
        """Open the Options dialog from the settings panel button."""
        try:
            from options_dialog import OptionsDialog
            dlg = OptionsDialog(self.parent)
            dlg.exec()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def on_template_changed(self):
        """Handle template selection changes"""
        # Update the renderer if video is loaded
        if hasattr(self.parent, 'video_cap') and self.parent.video_cap:
            self.parent.refresh_current_frame()

        # Save settings
        self.parent.save_current_settings()

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