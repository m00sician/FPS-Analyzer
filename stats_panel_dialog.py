"""
Configuration window for the stats panel.

Layout:

    TITLE:  [ Text ................................ ] [Colour]
    ─────────────────────────────────────────────────────────
    [ADD BOX]
    [ Console ............ ] [Colour]  [ Version ..... ] [Colour]  <- fixed
    [ Text ..... ] [<->][Colour][Del]  [ Text .... ] [<->][Colour][Del]
    ...
    ─────────────────────────────────────────────────────────
    FPS COLOUR: [ ]       FT COLOUR: [ ]
    ─────────────────────────────────────────────────────────
    [ PREVIEW ]    [START ENCODE] [CANCEL ENCODE]
                   [LOAD ANALYSIS DATA]
                   [CLOSE]

Field rules (implemented and tested in LayoutModel):
  • The first row (console + version) is fixed: it cannot be deleted or
    widened.
  • Below it, at most MAX_EXTRA_LINES rows.
  • Each row holds either ONE wide field or TWO narrow ones.
  • That yields every combination from 3 wide fields to 6 narrow ones,
    and everything in between.
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QLineEdit, QPushButton, QWidget,
                             QFrame, QColorDialog, QMessageBox, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QImage

from stats_panel import (default_config, normalize_config, MAX_EXTRA_LINES,
                         render_panel, panel_size, clear_cache)


# ══════════════════════════════════════════════════════════════════════════
# Layout logic (Qt-free, so it can be tested on its own)
# ══════════════════════════════════════════════════════════════════════════

class LayoutModel:
    """
    Manages the extra fields below the fixed console/version row.

    Internal representation: a list of rows, each row a list holding one or
    two field dicts {'text','color','wide'}.
    """

    def __init__(self, lines=None):
        self.lines = [list(l) for l in (lines or [])]

    # ── Queries ─────────────────────────────────────────────────────────
    def field_count(self):
        return sum(len(l) for l in self.lines)

    def can_add(self):
        """A free slot is either half of the last row, or a whole new row."""
        if self.lines and len(self.lines[-1]) == 1 and not self.lines[-1][0]['wide']:
            return True
        return len(self.lines) < MAX_EXTRA_LINES

    def can_widen(self, li, fi):
        """
        Widening works when the field sits alone in its row, or when its
        partner can be moved down into a row of its own.
        """
        if not (0 <= li < len(self.lines)):
            return False
        if self.lines[li][fi].get('wide'):
            return True          # switching back is always possible
        if len(self.lines[li]) == 1:
            return True
        return len(self.lines) < MAX_EXTRA_LINES

    # ── Mutations ───────────────────────────────────────────────────────
    def add(self, text='', color='#FFFFFF'):
        f = {'text': text, 'color': color, 'wide': False}
        if self.lines and len(self.lines[-1]) == 1 and not self.lines[-1][0]['wide']:
            self.lines[-1].append(f)
            return True
        if len(self.lines) < MAX_EXTRA_LINES:
            self.lines.append([f])
            return True
        return False

    def remove(self, li, fi):
        if not (0 <= li < len(self.lines) and 0 <= fi < len(self.lines[li])):
            return False
        self.lines[li].pop(fi)
        if not self.lines[li]:
            self.lines.pop(li)
        return True

    def toggle_wide(self, li, fi):
        if not self.can_widen(li, fi):
            return False
        line = self.lines[li]
        f = line[fi]
        if f['wide']:
            f['wide'] = False
            return True
        if len(line) == 1:
            f['wide'] = True
            return True
        # Move the partner into its own row directly below
        partner = line[1 - fi]
        f['wide'] = True
        self.lines[li] = [f]
        self.lines.insert(li + 1, [partner])
        return True

    def to_list(self):
        return [[dict(f) for f in line] for line in self.lines]


# ══════════════════════════════════════════════════════════════════════════
# Qt interface
# ══════════════════════════════════════════════════════════════════════════

def _swatch_style(color):
    return (f"background-color: {color}; border: 1px solid #888;")


class ColorButton(QPushButton):
    """Small colour picker."""
    colorChanged = pyqtSignal(str)

    def __init__(self, color='#FFFFFF', parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(28, 24)
        self.setStyleSheet(_swatch_style(color))
        self.setToolTip("Choose colour")
        self.clicked.connect(self._pick)

    def color(self):
        return self._color

    def setColor(self, c):
        self._color = c
        self.setStyleSheet(_swatch_style(c))

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, "Choose colour")
        if c.isValid():
            self.setColor(c.name().upper())
            self.colorChanged.emit(self._color)


class StatsPanelDialog(QDialog):
    """Window for composing and previewing the stats panel."""

    def __init__(self, analyzer, parent=None):
        super().__init__(parent)
        self.analyzer = analyzer
        self.setWindowTitle("Stats-Panel")
        self.setMinimumWidth(720)

        cfg = normalize_config(getattr(analyzer, 'stats_panel_config', None)
                               or default_config())
        self.model = LayoutModel(cfg['extra_lines'])
        self._cfg = cfg

        root = QVBoxLayout(self)

        # ── Titel ────────────────────────────────────────────────────────
        row = QHBoxLayout()
        row.addWidget(QLabel("TITEL:"))
        self.title_edit = QLineEdit(cfg['title']['text'])
        self.title_edit.setPlaceholderText("Game title")
        self.title_edit.textChanged.connect(self._refresh_preview)
        row.addWidget(self.title_edit, 1)
        self.title_color = ColorButton(cfg['title']['color'])
        self.title_color.colorChanged.connect(self._refresh_preview)
        row.addWidget(self.title_color)
        root.addLayout(row)
        root.addWidget(self._hline())

        # ── Felder ───────────────────────────────────────────────────────
        self.add_btn = QPushButton("ADD BOX")
        self.add_btn.setToolTip(
            f"Adds a text field. It goes next to the last field, or into a\n"
            f"new row if that one is full. At most {MAX_EXTRA_LINES} rows\n"
            f"= up to {MAX_EXTRA_LINES*2} narrow fields.")
        self.add_btn.clicked.connect(self._add_field)
        root.addWidget(self.add_btn, 0, Qt.AlignmentFlag.AlignLeft)

        # Fixed row: console + version
        fixed = QHBoxLayout()
        self.console_edit = QLineEdit(cfg['console']['text'])
        self.console_edit.setPlaceholderText("Console")
        self.console_edit.textChanged.connect(self._refresh_preview)
        self.console_color = ColorButton(cfg['console']['color'])
        self.console_color.colorChanged.connect(self._refresh_preview)
        self.version_edit = QLineEdit(cfg['version']['text'])
        self.version_edit.setPlaceholderText("Version")
        self.version_edit.textChanged.connect(self._refresh_preview)
        self.version_color = ColorButton(cfg['version']['color'])
        self.version_color.colorChanged.connect(self._refresh_preview)
        for w in (self.console_edit, self.console_color,
                  self.version_edit, self.version_color):
            fixed.addWidget(w, 1 if isinstance(w, QLineEdit) else 0)
        for w in (self.console_edit, self.version_edit):
            w.setToolTip("Fixed field - cannot be deleted or widened.")
        root.addLayout(fixed)

        # Dynamische Felder
        self.fields_host = QWidget()
        self.fields_layout = QGridLayout(self.fields_host)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.fields_host)
        root.addWidget(self._hline())

        # ── Graphfarben ─────────────────────────────────────────────────
        colors = QHBoxLayout()
        colors.addWidget(QLabel("FPS COLOUR:"))
        self.fps_color = ColorButton(cfg['fps_color'])
        self.fps_color.colorChanged.connect(self._refresh_preview)
        colors.addWidget(self.fps_color)
        colors.addSpacing(30)
        colors.addWidget(QLabel("FT COLOUR:"))
        self.ft_color = ColorButton(cfg['ft_color'])
        self.ft_color.colorChanged.connect(self._refresh_preview)
        colors.addWidget(self.ft_color)
        colors.addStretch(1)
        root.addLayout(colors)
        root.addWidget(self._hline())

        # ── Vorschau + Aktionen ─────────────────────────────────────────
        bottom = QHBoxLayout()
        self.preview = QLabel("Preview")
        self.preview.setMinimumSize(360, 260)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background:#1e1e1e; border:1px solid #555;")
        bottom.addWidget(self.preview, 1)

        btns = QVBoxLayout()
        self.start_btn = QPushButton("START ENCODE")
        self.start_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.start_btn.clicked.connect(self._start_encode)
        self.cancel_btn = QPushButton("CANCEL ENCODE")
        self.cancel_btn.clicked.connect(self._cancel_encode)
        self.load_btn = QPushButton("LOAD ANALYSIS DATA")
        self.load_btn.clicked.connect(self._load_data)
        self.close_btn = QPushButton("CLOSE")
        self.close_btn.clicked.connect(self.accept)
        for b in (self.start_btn, self.cancel_btn, self.load_btn, self.close_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        bottom.addLayout(btns)
        root.addLayout(bottom)

        self._rebuild_fields()

    # ── Helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _hline():
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet("color:#555;")
        return f

    def _clear_layout(self, lay):
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)

    def _rebuild_fields(self):
        """Rebuild the field widgets from the model."""
        self._clear_layout(self.fields_layout)
        for li, line in enumerate(self.model.lines):
            wide = len(line) == 1 and line[0].get('wide')
            for fi, f in enumerate(line):
                cell = self._make_field(li, fi, f)
                if wide:
                    self.fields_layout.addWidget(cell, li, 0, 1, 2)
                else:
                    self.fields_layout.addWidget(cell, li, fi)
        self.add_btn.setEnabled(self.model.can_add())
        self._refresh_preview()

    def _make_field(self, li, fi, f):
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)

        edit = QLineEdit(f.get('text', ''))
        edit.setPlaceholderText("ENTER TEXT")
        edit.textChanged.connect(lambda t, l=li, i=fi: self._set_text(l, i, t))
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay.addWidget(edit, 1)

        wide_btn = QPushButton("↔")
        wide_btn.setFixedSize(28, 24)
        wide_btn.setCheckable(True)
        wide_btn.setChecked(bool(f.get('wide')))
        wide_btn.setEnabled(self.model.can_widen(li, fi))
        wide_btn.setToolTip(
            "Stretch the field across the full width.\n"
            "A partner field moves down into a row of its own -\n"
            "only possible while a row is still free."
            if self.model.can_widen(li, fi) else
            "Not possible: this would need a free row.")
        wide_btn.clicked.connect(lambda _, l=li, i=fi: self._toggle_wide(l, i))
        lay.addWidget(wide_btn)

        col = ColorButton(f.get('color', '#FFFFFF'))
        col.colorChanged.connect(lambda c, l=li, i=fi: self._set_color(l, i, c))
        lay.addWidget(col)

        del_btn = QPushButton("🗑")
        del_btn.setFixedSize(28, 24)
        del_btn.setToolTip("Remove field")
        del_btn.clicked.connect(lambda _, l=li, i=fi: self._remove(l, i))
        lay.addWidget(del_btn)
        return box

    # ── Model mutations ─────────────────────────────────────────────────
    def _set_text(self, li, fi, t):
        try:
            self.model.lines[li][fi]['text'] = t
        except (IndexError, KeyError):
            return
        self._refresh_preview()

    def _set_color(self, li, fi, c):
        try:
            self.model.lines[li][fi]['color'] = c
        except (IndexError, KeyError):
            return
        self._refresh_preview()

    def _add_field(self):
        if not self.model.add():
            QMessageBox.information(
                self, "No room left",
                f"At most {MAX_EXTRA_LINES} rows are possible "
                f"(up to {MAX_EXTRA_LINES*2} narrow fields).")
            return
        self._rebuild_fields()

    def _remove(self, li, fi):
        self.model.remove(li, fi)
        self._rebuild_fields()

    def _toggle_wide(self, li, fi):
        self.model.toggle_wide(li, fi)
        self._rebuild_fields()

    # ── Configuration ───────────────────────────────────────────────────
    def build_config(self, enabled=True):
        return normalize_config({
            'enabled': enabled,
            'title': {'text': self.title_edit.text(),
                      'color': self.title_color.color()},
            'console': {'text': self.console_edit.text(),
                        'color': self.console_color.color()},
            'version': {'text': self.version_edit.text(),
                        'color': self.version_color.color()},
            'extra_lines': self.model.to_list(),
            'fps_color': self.fps_color.color(),
            'ft_color': self.ft_color.color(),
            'stat_color': self._cfg.get('stat_color', '#BBBBBB'),
            'geometry': self._cfg.get('geometry'),
        })

    def _refresh_preview(self):
        """Render the panel small and show it in the preview area."""
        try:
            import numpy as np
            cfg = self.build_config(enabled=True)
            clear_cache()
            w, h = panel_size(cfg, 1.0)
            canvas = np.full((h + 24, w + 24, 3), 30, dtype=np.uint8)
            fps_seq = getattr(self.analyzer, '_preview_fps_seq', None)
            ft_seq = getattr(self.analyzer, '_preview_ft_seq', None)
            stats = None
            if not fps_seq:
                # Demo curve while no analysis is loaded
                fps_seq = [58 - (i % 13) for i in range(400)]
                ft_seq = [1000.0 / max(1, v) for v in fps_seq]
            vals = [v for v in fps_seq if v]
            if vals:
                stats = {'fps': {'avg': sum(vals) / len(vals),
                                 'min': min(vals), 'max': max(vals)}}
            cfg2 = dict(cfg)
            geo = dict(cfg['geometry']); geo['x'] = 12; geo['y'] = 12
            cfg2['geometry'] = geo
            render_panel(canvas, cfg2, fps_seq, ft_seq, len(fps_seq) // 2,
                         stats=stats, source_fps=60.0)
            img = QImage(canvas.data, canvas.shape[1], canvas.shape[0],
                         canvas.strides[0], QImage.Format.Format_RGB888)
            self.preview.setPixmap(QPixmap.fromImage(img.copy()))
        except Exception as e:
            self.preview.setText(f"Preview not available:\n{e}")

    # ── Actions ─────────────────────────────────────────────────────────
    def _apply_to_analyzer(self, enabled):
        cfg = self.build_config(enabled=enabled)
        self.analyzer.stats_panel_config = cfg
        clear_cache()
        if hasattr(self.analyzer, 'save_current_settings'):
            try:
                self.analyzer.save_current_settings()
            except Exception:
                pass
        return cfg

    def _start_encode(self):
        """
        Start the encode. In the main window `toggle_analysis` is the single
        entry point: it starts an encode when none runs, and cancels the one
        that does. Hence the check first - otherwise this button would kill a
        running encode instead of starting a new one.
        """
        self._apply_to_analyzer(True)
        w = getattr(self.analyzer, 'analysis_worker', None)
        if w is not None and w.isRunning():
            QMessageBox.information(
                self, "Encode already running",
                "An encode is already running. The settings have been saved "
                "and will apply to the next run.")
            return
        fn = getattr(self.analyzer, 'toggle_analysis', None)
        if callable(fn):
            self.accept()
            fn()
        else:
            QMessageBox.information(self, "Applied",
                                    "Settings saved.")

    def _cancel_encode(self):
        w = getattr(self.analyzer, 'analysis_worker', None)
        if w is not None and w.isRunning():
            fn = getattr(self.analyzer, 'toggle_analysis', None)
            if callable(fn):
                fn()          # cancels and resets the interface
            else:
                w.cancel()
            QMessageBox.information(self, "Cancelled",
                                    "The running encode was cancelled.")
        else:
            QMessageBox.information(self, "No encode running",
                                    "There is no encode running right now.")

    def _load_data(self):
        """Load saved .fpsdata and encode it (Tools -> Encode from analysis data)."""
        self._apply_to_analyzer(True)
        fn = getattr(self.analyzer, 'encode_from_data', None)
        if callable(fn):
            self.accept()
            fn()
            return
        QMessageBox.information(
            self, "Not available",
            "This action lives in the menu under 'Tools -> Encode from analysis data'.")
