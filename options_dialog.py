"""
Options Dialog for FPS Analyzer
Centralizes all configuration that doesn't change frequently:
  - FPS / Frame Time templates
  - Detection sensitivity & Baseline FPS
  - Graph line color & thickness
  - Graph smoothing (smooth_window)
  - FPS display responsiveness (update interval)
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QPushButton,
    QLabel, QComboBox, QGroupBox, QDialogButtonBox, QColorDialog,
    QLineEdit)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor


# ---------------------------------------------------------------------------
# Small helper: a clickable colour swatch button
# ---------------------------------------------------------------------------
class ColorButton(QPushButton):
    color_changed = pyqtSignal(str)   # emits hex string like '#00FF00'

    def __init__(self, hex_color: str = '#00FF00', parent=None):
        super().__init__(parent)
        self.setFixedSize(48, 28)
        self.set_color(hex_color)
        self.clicked.connect(self._pick_color)

    # ── public API ──────────────────────────────────────────────────────────
    def set_color(self, hex_color: str):
        self._hex = hex_color
        self.setStyleSheet(
            f"background-color: {hex_color}; border: 2px solid #888; border-radius: 4px;"
        )

    def get_color(self) -> str:
        return self._hex

    # ── internal ────────────────────────────────────────────────────────────
    def _pick_color(self):
        initial = QColor(self._hex)
        picked  = QColorDialog.getColor(initial, self, "Choose colour")
        if picked.isValid():
            self.set_color(picked.name().upper())
            self.color_changed.emit(self._hex)


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------
class OptionsDialog(QDialog):
    """
    Options window.  Call `apply_to(parent)` after exec_() to push
    values back to the main analyzer window.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.analyzer = parent
        self.setWindowTitle("⚙️ Options")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setMinimumHeight(560)

        self._build_ui()
        self._load_from_analyzer()
        self._apply_theme()

    # ═══════════════════════════════════════════════════════════════════════
    # UI construction
    # ═══════════════════════════════════════════════════════════════════════
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        root.addWidget(self._section_templates())
        root.addWidget(self._section_detection())

        root.addStretch()

        # OK / Cancel / Apply
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._on_apply)
        root.addWidget(btns)

    # ── Templates ────────────────────────────────────────────────────────
    def _section_templates(self) -> QGroupBox:
        box = QGroupBox("📊 Graph Scale Values")
        layout = QGridLayout(box)
        layout.setSpacing(10)

        # FPS grid values - free text field, any number of values
        layout.addWidget(QLabel("FPS values:"), 0, 0)
        self.fps_grid_edit = QLineEdit("60,30,0")
        self.fps_grid_edit.setPlaceholderText("e.g. 60,30,0 or 60,50,40,30,20")
        self.fps_grid_edit.setToolTip(
            "Comma-separated FPS values for grid lines + labels.\n"
            "The highest value defines the scale (max_fps)."
        )
        layout.addWidget(self.fps_grid_edit, 0, 1)

        # Frame-Time grid values
        layout.addWidget(QLabel("Frame time values (ms):"), 1, 0)
        self.ft_grid_edit = QLineEdit("16.7,33.3,100")
        self.ft_grid_edit.setPlaceholderText("z.B. 16.7,33.3,100")
        self.ft_grid_edit.setToolTip(
            "Comma-separated frame time values in ms for grid lines + labels.\n"
            "Smallest value at the top, largest at the bottom."
        )
        layout.addWidget(self.ft_grid_edit, 1, 1)

        # Defaults
        defaults_btn = QPushButton("↺ Defaults (60,30,0 / 16.7,33.3,100)")
        defaults_btn.clicked.connect(self._restore_grid_defaults)
        layout.addWidget(defaults_btn, 2, 0, 1, 2)

        return box

    def _restore_grid_defaults(self):
        self.fps_grid_edit.setText("60,30,0")
        self.ft_grid_edit.setText("16.7,33.3,100")

    @staticmethod
    def _parse_grid(text: str, fallback: list) -> tuple:
        """Parses '60,x50,30' -> ([60.0, 50.0, 30.0], {50.0}).
        An x prefix marks a scale anchor without a label; its grid line is grey."""
        vals, hidden = [], set()
        try:
            for tok in text.split(','):
                tok = tok.strip()
                if not tok:
                    continue
                is_hidden = tok.lower().startswith('x')
                v = float(tok[1:] if is_hidden else tok)
                vals.append(v)
                if is_hidden:
                    hidden.add(v)
            return (vals, hidden) if vals else (list(fallback), set())
        except ValueError:
            return (list(fallback), set())

    # ── Detection ────────────────────────────────────────────────────────
    def _section_detection(self) -> QGroupBox:
        box = QGroupBox("🎯 Detection")
        layout = QGridLayout(box)
        layout.setSpacing(10)

        # Sensitivity
        layout.addWidget(QLabel("Sensitivity:"), 0, 0)
        self.sensitivity_combo = QComboBox()
        for name, val in [
            ('Very High (0.015)', 0.015),
            ('High (0.01)',       0.01),
            ('Medium (0.005)',    0.005),
            ('Low (0.002)',       0.002),
            ('Very Low (0.001)', 0.001),
        ]:
            self.sensitivity_combo.addItem(name, val)
        self.sensitivity_combo.setToolTip(
            "Controls how different two frames must be to be counted as unique.\n"
            "Higher = detects more unique frames (use for fast-paced content).\n"
            "Lower  = more tolerant of small changes (use for slow/static content)."
        )
        layout.addWidget(self.sensitivity_combo, 0, 1)

        # Baseline FPS
        layout.addWidget(QLabel("Baseline FPS:"), 0, 2)
        self.baseline_fps_combo = QComboBox()
        for name, val in [
            ('Auto-detect', 0), ('20 FPS', 20), ('24 FPS', 24), ('25 FPS', 25),
            ('30 FPS', 30), ('40 FPS', 40), ('50 FPS', 50), ('60 FPS', 60),
            ('72 FPS', 72), ('90 FPS', 90), ('100 FPS', 100), ('120 FPS', 120),
        ]:
            self.baseline_fps_combo.addItem(name, val)
        self.baseline_fps_combo.setToolTip(
            "The expected framerate of the source video.\n"
            "Auto-detect uses the video's own FPS metadata.\n"
            "Set manually if the graph starts at the wrong value."
        )
        layout.addWidget(self.baseline_fps_combo, 0, 3)

        # Fade detection
        from PyQt6.QtWidgets import QCheckBox, QSpinBox
        self.fade_check = QCheckBox("Fade / blend detection (exclude uniform transitions)")
        self.fade_check.setToolTip(
            "Detects single-colour transitions (fade to white/black) where the\n"
            "image briefly turns uniform. Such frames produce false 0 FPS spikes.\n"
            "The fade and the configured buffer before and after it are excluded\n"
            "from min/max/avg; the gap stays visible in the graph."
        )
        layout.addWidget(self.fade_check, 1, 0, 1, 2)

        # Buffer length in ms (before / after the fade)
        layout.addWidget(QLabel("Buffer before/after (ms):"), 1, 2)
        self.fade_buffer_spin = QSpinBox()
        self.fade_buffer_spin.setRange(0, 5000)
        self.fade_buffer_spin.setSingleStep(100)
        self.fade_buffer_spin.setValue(2000)
        self.fade_buffer_spin.setSuffix(" ms")
        self.fade_buffer_spin.setToolTip(
            "How much time before and after the fade is excluded as well.\n"
            "0 = only the fade frames themselves. Default 2000 ms."
        )
        layout.addWidget(self.fade_buffer_spin, 1, 3)

        # Save analysis data
        self.save_data_check = QCheckBox("Save analysis data (.fpsdata next to the video)")
        self.save_data_check.setToolTip(
            "Saves the FPS/FT analysis to a file, so the video can be\n"
            "re-rendered later with a different layout via 'Tools -> Encode from\n"
            "Analysis Data', WITHOUT analysing the whole video again."
        )
        layout.addWidget(self.save_data_check, 2, 0, 1, 4)

        # Abweichungs-Marker
        self.deviation_check = QCheckBox("Deviation marker (red block, top right)")
        self.deviation_check.setToolTip(
            "Shows a red block in the top right corner for as long as the\n"
            "footage deviates from the baseline value - that is, as soon as a\n"
            "frame is held longer than the baseline allows (with baseline 60,\n"
            "anything above 16.7 ms).\n\n"
            "This is based on the real per-frame hold times, not on the rolling\n"
            "FPS: there, a single hitch would still linger for a whole second\n"
            "and keep the marker lit far too long."
        )
        layout.addWidget(self.deviation_check, 3, 0, 1, 2)

        layout.addWidget(QLabel("Minimum display time:"), 3, 2)
        self.deviation_hold_spin = QSpinBox()
        self.deviation_hold_spin.setRange(0, 2000)
        self.deviation_hold_spin.setSingleStep(50)
        self.deviation_hold_spin.setSuffix(" ms")
        self.deviation_hold_spin.setToolTip(
            "A single dropped frame lasts only 16-33 ms and would be nearly\n"
            "invisible. The marker therefore stays up at least this long. Its\n"
            "start time is not shifted by this.\n"
            "0 = exactly as long as the deviation. Default 150 ms."
        )
        layout.addWidget(self.deviation_hold_spin, 3, 3)

        # YUV render path
        self.yuv_check = QCheckBox("YUV render path (faster, source resolution only)")
        self.yuv_check.setToolTip(
            "Hands the decoded frames over as raw YUV instead of letting the\n"
            "decoder convert them to BGR itself. That conversion is the most\n"
            "expensive single step of the decode at 4K and used to run in the\n"
            "ONE reader thread; here it runs in the render workers, in\n"
            "parallel. The encoder pipe also carries half the bytes.\n\n"
            "Measured decoder throughput at 4K: 73 instead of 53.7 fps.\n"
            "Measured fidelity: untouched image areas stay about twice as\n"
            "close to the source as on the BGR path.\n\n"
            "Only takes effect when the output resolution matches the source\n"
            "and the parallel render pass is on. Otherwise the standard path\n"
            "runs and says so in the log."
        )
        layout.addWidget(self.yuv_check, 4, 0, 1, 4)

        return box

    # ── Graph appearance ──────────────────────────────────────────────────
    # ═══════════════════════════════════════════════════════════════════════
    # Load / Save
    # ═══════════════════════════════════════════════════════════════════════
    def _load_from_analyzer(self):
        """Populate all controls from the current analyzer state."""
        a = self.analyzer

        # ── Detection ──────────────────────────────────────────────────
        if hasattr(a, 'sensitivity_combo'):
            self.sensitivity_combo.setCurrentIndex(a.sensitivity_combo.currentIndex())
        if hasattr(a, 'baseline_fps_combo'):
            self.baseline_fps_combo.setCurrentIndex(a.baseline_fps_combo.currentIndex())
        self.fade_check.setChecked(bool(getattr(a, 'fade_detection_enabled', False)))
        self.fade_buffer_spin.setValue(int(getattr(a, 'fade_buffer_ms', 2000)))
        self.save_data_check.setChecked(bool(getattr(a, 'save_analysis_data', False)))
        self.deviation_check.setChecked(bool(getattr(a, 'deviation_marker', False)))
        self.yuv_check.setChecked(bool(getattr(a, 'render_yuv', False)))
        self.deviation_hold_spin.setValue(int(getattr(a, 'deviation_marker_hold_ms', 150)))

        # Load custom grid values from the current template (if custom is active)
        try:
            fd = a.fps_graph_combo.currentData() if hasattr(a, 'fps_graph_combo') else None
            if fd and fd.get('values'):
                _h = set(fd.get('hidden', []))
                self.fps_grid_edit.setText(','.join(
                    ('x' if v in _h else '') + f"{v:g}" for v in fd['values']))
            td = a.frametime_combo.currentData() if hasattr(a, 'frametime_combo') else None
            if td and td.get('values'):
                _h = set(td.get('hidden', []))
                self.ft_grid_edit.setText(','.join(
                    ('x' if v in _h else '') + f"{v:g}" for v in td['values']))
        except Exception:
            pass

    def _apply_to_analyzer(self):
        """Push all values from the dialog back to the analyzer."""
        a = self.analyzer

        # ── Templates: inject custom grid values into the parent combos ───
        fps_vals, fps_hidden = self._parse_grid(self.fps_grid_edit.text(), [60, 30, 0])
        ft_vals,  ft_hidden  = self._parse_grid(self.ft_grid_edit.text(), [16.7, 33.3, 100])
        fps_data = {
            'template': 'custom',
            'max_fps': max(fps_vals),
            'grid_lines': fps_vals,
            'values': fps_vals,
            'hidden': sorted(fps_hidden),
        }
        ft_sorted = sorted(ft_vals)
        ft_data = {
            'template': 'custom',
            'scale': {'min': ft_sorted[0], 'max': ft_sorted[-1],
                      'mid': ft_sorted[len(ft_sorted)//2]},
            'labels': [f"{v:g}ms" for v in ft_sorted],
            'values': ft_sorted,
            'hidden': sorted(ft_hidden),
        }

        def _set_custom(combo, data, label):
            idx = combo.findText(label)
            if idx >= 0:
                combo.removeItem(idx)
            combo.addItem(label, data)
            combo.setCurrentIndex(combo.count() - 1)

        if hasattr(a, 'fps_graph_combo'):
            _set_custom(a.fps_graph_combo, fps_data,
                        f"Custom ({self.fps_grid_edit.text().strip()})")
        if hasattr(a, 'frametime_combo'):
            _set_custom(a.frametime_combo, ft_data,
                        f"Custom ({self.ft_grid_edit.text().strip()}ms)")

        # ── Detection ──────────────────────────────────────────────────
        if hasattr(a, 'sensitivity_combo'):
            a.sensitivity_combo.setCurrentIndex(self.sensitivity_combo.currentIndex())
        if hasattr(a, 'baseline_fps_combo'):
            a.baseline_fps_combo.setCurrentIndex(self.baseline_fps_combo.currentIndex())
        a.fade_detection_enabled = self.fade_check.isChecked()
        a.fade_buffer_ms = self.fade_buffer_spin.value()
        a.save_analysis_data = self.save_data_check.isChecked()
        a.deviation_marker = self.deviation_check.isChecked()
        a.render_yuv = self.yuv_check.isChecked()
        a.deviation_marker_hold_ms = self.deviation_hold_spin.value()

        # (colours, line thickness, smoothing, update interval -> Layout Editor)

        # ── Persist ────────────────────────────────────────────────────
        if hasattr(a, 'save_current_settings'):
            a.save_current_settings()

        if hasattr(a, 'refresh_current_frame'):
            a.refresh_current_frame()

        if hasattr(a, 'log'):
            a.log("✅ Options applied")

    # ═══════════════════════════════════════════════════════════════════════
    # Slots
    # ═══════════════════════════════════════════════════════════════════════
    def _on_ok(self):
        self._apply_to_analyzer()
        self.accept()

    def _on_apply(self):
        self._apply_to_analyzer()

    # ═══════════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def _odd(n: int) -> int:
        """Return the nearest odd number ≥ 1."""
        n = max(1, n)
        return n if n % 2 == 1 else n - 1

    def _apply_theme(self):
        if hasattr(self.analyzer, 'styleSheet'):
            self.setStyleSheet(self.analyzer.styleSheet())
