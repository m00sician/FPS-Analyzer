"""
Layout Editor — Drag-and-Drop GUI for FPS Analyzer overlay positioning.

Features:
- 16:9 canvas scaled to preview resolution
- Drag elements by clicking their label area
- Resize elements by dragging bottom-right corner handle
- Style picker: Hard Outline / Drop Shadow / None
- Live preview updates instantly
- Apply saves to LayoutManager and invalidates CodeRenderer cache
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QSizePolicy, QWidget, QSlider,
    QCheckBox, QFrame
)
from PyQt6.QtCore import Qt, QRect, QPoint, QSize, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont
)
import copy

# ── Element definitions ────────────────────────────────────────────────────────

ELEMENTS = {
    'fps_number':           {'label': 'FPS',           'color': QColor(80, 160, 255, 200)},
    'frame_time_graph':     {'label': 'Frame Time',    'color': QColor(80, 220, 120, 200)},
    'frametime_statistics': {'label': 'FT Stats',      'color': QColor(80, 200, 100, 160)},
    'frame_rate_graph':     {'label': 'Frame Rate',    'color': QColor(255, 160, 40, 200)},
    'fps_statistics':       {'label': 'FPS Stats',     'color': QColor(255, 140, 20, 160)},
}

CANVAS_W = 1920
CANVAS_H = 1080
MIN_SIZE = 40   # px in 1080p coords


# ── Canvas Widget ──────────────────────────────────────────────────────────────

class LayoutCanvas(QWidget):
    """Interactive 16:9 canvas for drag-and-drop layout editing."""

    layout_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

        self._layout: dict = {}          # 1080p coords {id: {position, size, visible}}
        self._scale = 1.0                # canvas px per 1080p px
        self._offset = QPoint(0, 0)      # top-left of canvas in widget coords

        self._drag_id: str | None = None
        self._drag_mode: str = 'move'    # 'move' | 'resize'
        self._drag_start_mouse = QPoint()
        self._drag_start_pos = (0, 0)
        self._drag_start_size = (0, 0)

        self._hover_id: str | None = None
        self._selected_id: str | None = None

        self._handle_size = 10           # resize handle size in widget px

        # ── Live preview (real overlay rendering) ──
        self._preview_analyzer = None    # reference to the analyzer (renderer + frame)
        self._preview_bg = None          # np.ndarray: video frame (BGR) as preview background
        self._preview_pixmap = None      # rendered overlay as a QPixmap
        self._preview_enabled = False
        self._preview_dirty = True
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(60)   # Throttle: max ~16 renders/s
        self._preview_timer.timeout.connect(self._do_render_preview)

    def enable_preview(self, analyzer):
        """Enable the live preview with real overlay rendering."""
        self._preview_analyzer = analyzer
        self._preview_bg = self._grab_video_frame(analyzer)
        self._preview_enabled = self._preview_bg is not None
        self._preview_dirty = True
        self._schedule_preview()

    def _grab_video_frame(self, analyzer):
        """Fetch a real frame from the loaded video (BGR np.ndarray)."""
        try:
            import cv2
            cap = getattr(analyzer, 'video_cap', None)
            if cap is None or not cap.isOpened():
                return None
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            pos = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            # A frame from the middle (more representative than the first)
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total // 2))
            ret, frame = cap.read()
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)   # restore the position
            return frame if ret else None
        except Exception as e:
            print(f"LayoutEditor Preview: Frame-Load fehlgeschlagen: {e}")
            return None

    def _schedule_preview(self):
        """Throttle the preview render (so fast dragging does not overload it)."""
        self._preview_dirty = True
        if self._preview_enabled and not self._preview_timer.isActive():
            self._preview_timer.start()

    def _do_render_preview(self):
        """Render the real overlay with the current layout (called throttled)."""
        if not self._preview_enabled or self._preview_bg is None:
            return
        if not self._preview_dirty:
            return
        self._preview_dirty = False
        try:
            import cv2
            from PyQt6.QtGui import QImage, QPixmap
            analyzer = self._preview_analyzer
            renderer = analyzer.get_renderer_instance() if hasattr(analyzer, 'get_renderer_instance') else None
            if renderer is None:
                from code_renderer import CodeRenderer
                renderer = CodeRenderer()

            frame = self._preview_bg.copy()
            fh, fw = frame.shape[:2]

            # Convert the layout into overlay positions (1080p -> frame size)
            layout_cfg = analyzer.layout_manager.convert_to_overlay_positions(
                self._layout, fw, fh) if hasattr(analyzer, 'layout_manager') else None

            # Fetch the settings/template
            settings = analyzer.get_current_settings() if hasattr(analyzer, 'get_current_settings') else {}
            template_config = settings.get('template_config') or {
                'fps_graph_template': settings.get('fps_graph_template'),
                'frametime_template': settings.get('frametime_template'),
                'overlay_style': getattr(analyzer, 'overlay_style', {}),
                'fps_line_thickness': getattr(analyzer, 'fps_line_thickness', None),
            }
            font_settings = {
                'fps_font': getattr(analyzer, 'fps_font_settings', None),
                'framerate_font': getattr(analyzer, 'framerate_font_settings', None),
                'frametime_font': getattr(analyzer, 'frametime_font_settings', None),
            }
            color_settings = getattr(analyzer, 'color_settings', None) or {
                'framerate_color': getattr(analyzer, 'framerate_color', '#00FF00'),
                'frametime_color': getattr(analyzer, 'frametime_color', '#00FF00'),
            }

            # Static example curve (a nice dip shape)
            sample_fps = self._sample_curve()
            sample_ft  = [1000.0 / max(1, v) for v in sample_fps]
            stats = {'fps': {'avg': 58.2, 'min': 44.0, 'max': 60.0},
                     'frametime': {'avg': 17.2, 'min': 16.7, 'max': 22.7}}

            rendered = renderer.render_overlay(
                frame, list(sample_fps), sample_fps[-1],
                sample_ft, True, layout_cfg, color_settings,
                template_config, font_settings,
                list(sample_fps), list(sample_ft), stats
            )

            rgb = cv2.cvtColor(rendered, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
            self._preview_pixmap = QPixmap.fromImage(qimg)
            self.update()
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"LayoutEditor Preview-Render fehlgeschlagen: {e}")
            self._preview_enabled = False

    def _sample_curve(self):
        """Static example FPS curve with a single dip (representative)."""
        import math
        pts = []
        for i in range(180):
            if 60 <= i < 120:
                # Dip in the middle
                d = 1.0 - 0.45 * math.sin((i - 60) / 60 * math.pi)
                pts.append(60.0 * d)
            else:
                pts.append(58.0 + 2.0 * math.sin(i / 8.0))
        return pts

    # ── Layout access ──────────────────────────────────────────────────────────

    def set_layout(self, layout: dict):
        self._layout = copy.deepcopy(layout)
        self._schedule_preview()
        self.update()

    def get_layout(self) -> dict:
        return copy.deepcopy(self._layout)

    # ── Coordinate helpers ─────────────────────────────────────────────────────

    def _update_transform(self):
        """Recalculate scale/offset so canvas fills widget with correct aspect ratio."""
        ww, wh = self.width(), self.height()
        scale_x = ww / CANVAS_W
        scale_y = wh / CANVAS_H
        self._scale = min(scale_x, scale_y)
        canvas_px_w = int(CANVAS_W * self._scale)
        canvas_px_h = int(CANVAS_H * self._scale)
        self._offset = QPoint((ww - canvas_px_w) // 2, (wh - canvas_px_h) // 2)

    def _to_widget(self, x: int, y: int) -> QPoint:
        return QPoint(
            self._offset.x() + int(x * self._scale),
            self._offset.y() + int(y * self._scale)
        )

    def _to_canvas(self, p: QPoint) -> tuple[int, int]:
        x = int((p.x() - self._offset.x()) / self._scale)
        y = int((p.y() - self._offset.y()) / self._scale)
        return x, y

    def _elem_rect_widget(self, elem_id: str) -> QRect:
        d = self._layout.get(elem_id)
        if not d:
            return QRect()
        x, y = d['position']
        w, h = d['size']
        tl = self._to_widget(x, y)
        return QRect(tl, QSize(int(w * self._scale), int(h * self._scale)))

    def _hit_test(self, p: QPoint) -> tuple[str | None, str]:
        """Return (elem_id, mode) for point p. mode = 'move' | 'resize'."""
        hs = self._handle_size
        # Check in reverse order (last drawn = top)
        for elem_id in reversed(list(self._layout.keys())):
            if not self._layout[elem_id].get('visible', True):
                continue
            r = self._elem_rect_widget(elem_id)
            # Resize handle (bottom-right corner)
            handle = QRect(r.right() - hs, r.bottom() - hs, hs * 2, hs * 2)
            if handle.contains(p):
                return elem_id, 'resize'
            if r.contains(p):
                return elem_id, 'move'
        return None, 'move'

    # ── Paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        self._update_transform()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Canvas background: real overlay preview, or a fallback colour
        canvas_rect = QRect(
            self._offset,
            QSize(int(CANVAS_W * self._scale), int(CANVAS_H * self._scale))
        )
        if self._preview_enabled and self._preview_pixmap is not None:
            p.drawPixmap(canvas_rect, self._preview_pixmap)
        else:
            p.fillRect(canvas_rect, QColor(20, 35, 50))

        # Grid lines (only without a preview, otherwise they clutter the image)
        if not (self._preview_enabled and self._preview_pixmap is not None):
            p.setPen(QPen(QColor(255, 255, 255, 20), 1, Qt.PenStyle.DashLine))
            for i in range(1, 4):
                y = self._offset.y() + int(i * CANVAS_H * self._scale / 4)
                p.drawLine(canvas_rect.left(), y, canvas_rect.right(), y)
            for i in range(1, 8):
                x = self._offset.x() + int(i * CANVAS_W * self._scale / 8)
                p.drawLine(x, canvas_rect.top(), x, canvas_rect.bottom())

        # Safe area guide (50px margin in 1080p)
        margin = int(50 * self._scale)
        safe = QRect(
            canvas_rect.left() + margin, canvas_rect.top() + margin,
            canvas_rect.width() - 2 * margin, canvas_rect.height() - 2 * margin
        )
        p.setPen(QPen(QColor(255, 255, 100, 30), 1, Qt.PenStyle.DotLine))
        p.drawRect(safe)

        # Elements
        for elem_id, data in self._layout.items():
            if not data.get('visible', True):
                continue
            r = self._elem_rect_widget(elem_id)
            meta = ELEMENTS.get(elem_id, {'label': elem_id, 'color': QColor(128, 128, 128, 180)})
            color = meta['color']
            label = meta['label']
            is_selected = elem_id == self._selected_id
            is_hover = elem_id == self._hover_id

            # Fill - more subtle while the preview is active (real overlay visible)
            fill = QColor(color)
            if self._preview_enabled and self._preview_pixmap is not None:
                base_a = 40 if not is_selected else 90
                fill.setAlpha(base_a + (30 if is_hover else 0))
            elif is_selected:
                fill.setAlpha(min(255, color.alpha() + 60))
            elif is_hover:
                fill.setAlpha(min(255, color.alpha() + 30))
            p.fillRect(r, fill)

            # Border
            border_color = QColor(255, 255, 255, 200 if is_selected else 100)
            pen_width = 2 if is_selected else 1
            p.setPen(QPen(border_color, pen_width))
            p.drawRect(r)

            # Label
            font = QFont()
            font.setPixelSize(max(10, int(13 * self._scale)))
            font.setBold(True)
            p.setFont(font)
            p.setPen(QColor(255, 255, 255, 230))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)

            # Size hint
            small_font = QFont()
            small_font.setPixelSize(max(8, int(9 * self._scale)))
            p.setFont(small_font)
            p.setPen(QColor(255, 255, 255, 120))
            cx, cy = data['position']
            cw, ch = data['size']
            hint = f"{cx},{cy}  {cw}×{ch}"
            p.drawText(
                QRect(r.left() + 4, r.bottom() - int(14 * self._scale), r.width() - 8, int(14 * self._scale)),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, hint
            )

            # Resize handle
            hs = self._handle_size
            handle = QRect(r.right() - hs, r.bottom() - hs, hs * 2, hs * 2)
            p.fillRect(handle, QColor(255, 255, 255, 180 if is_selected else 80))

        # Canvas border
        p.setPen(QPen(QColor(100, 120, 140), 2))
        p.drawRect(canvas_rect)

        # Resolution label
        p.setPen(QColor(150, 170, 190))
        font = QFont()
        font.setPixelSize(11)
        p.setFont(font)
        p.drawText(canvas_rect.left() + 6, canvas_rect.top() + 15, "1920 × 1080 (preview)")

    # ── Mouse events ───────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        elem_id, mode = self._hit_test(e.pos())
        self._selected_id = elem_id
        if elem_id:
            self._drag_id = elem_id
            self._drag_mode = mode
            self._drag_start_mouse = e.pos()
            d = self._layout[elem_id]
            self._drag_start_pos = tuple(d['position'])
            self._drag_start_size = tuple(d['size'])
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag_id:
            dx = int((e.pos().x() - self._drag_start_mouse.x()) / self._scale)
            dy = int((e.pos().y() - self._drag_start_mouse.y()) / self._scale)
            d = self._layout[self._drag_id]
            if self._drag_mode == 'move':
                nx = max(0, min(CANVAS_W - d['size'][0], self._drag_start_pos[0] + dx))
                ny = max(0, min(CANVAS_H - d['size'][1], self._drag_start_pos[1] + dy))
                d['position'] = [nx, ny]
            else:  # resize
                nw = max(MIN_SIZE, self._drag_start_size[0] + dx)
                nh = max(MIN_SIZE, self._drag_start_size[1] + dy)
                # Clamp to canvas
                nw = min(nw, CANVAS_W - d['position'][0])
                nh = min(nh, CANVAS_H - d['position'][1])
                d['size'] = [nw, nh]
            self.layout_changed.emit()
            self._schedule_preview()
            self.update()
        else:
            hover_id, _ = self._hit_test(e.pos())
            if hover_id != self._hover_id:
                self._hover_id = hover_id
                self.update()
            # Cursor shape
            _, mode = self._hit_test(e.pos())
            if mode == 'resize':
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif hover_id:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, e):
        if self._drag_id:
            self._drag_id = None
            self.layout_changed.emit()

    def resizeEvent(self, _):
        self._update_transform()
        self.update()

    def get_selected_id(self) -> str | None:
        return self._selected_id


# ── Properties panel ──────────────────────────────────────────────────────────

class PropertiesPanel(QWidget):
    """Shows position/size/visibility for the selected element."""

    value_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._elem_id: str | None = None
        self._layout: dict = {}
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._title = QLabel("— select an element —")
        self._title.setStyleSheet("font-weight: bold; color: #aac; font-size: 13px;")
        layout.addWidget(self._title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #445;")
        layout.addWidget(sep)

        # Position + size fields
        grid = QWidget()
        from PyQt6.QtWidgets import QGridLayout, QSpinBox
        gl = QGridLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(4)

        self._spins = {}
        fields = [('X', 'x'), ('Y', 'y'), ('W', 'w'), ('H', 'h')]
        for row, (lbl, key) in enumerate(fields):
            gl.addWidget(QLabel(lbl), row, 0)
            spin = QSpinBox()
            spin.setRange(0, 1920)
            spin.setSingleStep(1)
            spin.valueChanged.connect(self._on_spin_changed)
            gl.addWidget(spin, row, 1)
            self._spins[key] = spin

        self._spins['x'].setRange(0, 1919)
        self._spins['y'].setRange(0, 1079)
        self._spins['w'].setRange(MIN_SIZE, 1920)
        self._spins['h'].setRange(MIN_SIZE, 1080)

        layout.addWidget(grid)

        # Visibility
        self._vis_check = QCheckBox("Visible")
        self._vis_check.setChecked(True)
        self._vis_check.stateChanged.connect(self._on_vis_changed)
        layout.addWidget(self._vis_check)

        layout.addStretch()

    def set_element(self, elem_id: str | None, layout: dict):
        self._elem_id = elem_id
        self._layout = layout
        self._updating = True
        if elem_id and elem_id in layout:
            meta = ELEMENTS.get(elem_id, {'label': elem_id, 'color': None})
            self._title.setText(meta['label'])
            d = layout[elem_id]
            self._spins['x'].setValue(d['position'][0])
            self._spins['y'].setValue(d['position'][1])
            self._spins['w'].setValue(d['size'][0])
            self._spins['h'].setValue(d['size'][1])
            self._vis_check.setChecked(d.get('visible', True))
            for s in self._spins.values():
                s.setEnabled(True)
            self._vis_check.setEnabled(True)
        else:
            self._title.setText("— select an element —")
            for s in self._spins.values():
                s.setEnabled(False)
            self._vis_check.setEnabled(False)
        self._updating = False

    def _on_spin_changed(self):
        if self._updating or not self._elem_id:
            return
        d = self._layout.get(self._elem_id)
        if not d:
            return
        d['position'] = [self._spins['x'].value(), self._spins['y'].value()]
        d['size'] = [self._spins['w'].value(), self._spins['h'].value()]
        self.value_changed.emit()

    def _on_vis_changed(self):
        if self._updating or not self._elem_id:
            return
        d = self._layout.get(self._elem_id)
        if d:
            d['visible'] = self._vis_check.isChecked()
            self.value_changed.emit()

    def sync_from_layout(self, layout: dict):
        """Update spin values from external layout change (drag)."""
        self._layout = layout
        if not self._elem_id or self._elem_id not in layout:
            return
        self._updating = True
        d = layout[self._elem_id]
        self._spins['x'].setValue(d['position'][0])
        self._spins['y'].setValue(d['position'][1])
        self._spins['w'].setValue(d['size'][0])
        self._spins['h'].setValue(d['size'][1])
        self._updating = False


# ── Style Panel ───────────────────────────────────────────────────────────────

class StylePanel(QGroupBox):
    """Text style picker: outline / shadow / glow + opacity slider."""

    style_changed = pyqtSignal(dict)

    STYLES = ['Hard Outline', 'Drop Shadow', 'None']

    def __init__(self, parent=None):
        super().__init__("Overlay Style", parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Text style
        layout.addWidget(QLabel("Text style:"))
        self._style_combo = QComboBox()
        self._style_combo.addItems(self.STYLES)
        self._style_combo.setCurrentIndex(0)   # Hard Outline default
        self._style_combo.currentIndexChanged.connect(self._on_style_change)
        layout.addWidget(self._style_combo)

        # Outline/shadow thickness - the label changes with the style
        from PyQt6.QtWidgets import QSpinBox
        self._ow_label = QLabel("Outline width (base @1080p):")
        layout.addWidget(self._ow_label)
        self._ow_spin = QSpinBox()
        self._ow_spin.setRange(0, 12)
        self._ow_spin.setValue(3)
        self._ow_spin.setSuffix(" px")
        self._ow_spin.valueChanged.connect(lambda _: self._emit())
        layout.addWidget(self._ow_spin)

        # Graph border
        layout.addWidget(QLabel("Graph border:"))
        self._border_combo = QComboBox()
        self._border_combo.addItems(['White Outline', 'Soft Glow', 'None'])
        self._border_combo.setCurrentIndex(0)
        self._border_combo.currentIndexChanged.connect(self._emit)
        layout.addWidget(self._border_combo)

        # BG opacity
        layout.addWidget(QLabel("Background opacity:"))
        opacity_row = QHBoxLayout()
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(10, 90)
        self._opacity_slider.setValue(50)
        self._opacity_label = QLabel("50%")
        self._opacity_label.setFixedWidth(36)
        self._opacity_slider.valueChanged.connect(self._on_opacity)
        opacity_row.addWidget(self._opacity_slider)
        opacity_row.addWidget(self._opacity_label)
        layout.addLayout(opacity_row)

        # ── Milchglas-Effekt (Frosted Glass) ──
        self._frost_check = QCheckBox("Frosted glass (the video behind the graph is blurred)")
        self._frost_check.setToolTip(
            "Draws the image area behind the graph blurred and darkened\n"
            "instead of a solid background. Replaces the opacity above."
        )
        self._frost_check.stateChanged.connect(lambda _: self._emit())
        layout.addWidget(self._frost_check)

        frost_blur_row = QHBoxLayout()
        frost_blur_row.addWidget(QLabel("  Blur:"))
        self._frost_blur_slider = QSlider(Qt.Orientation.Horizontal)
        self._frost_blur_slider.setRange(5, 100)
        self._frost_blur_slider.setValue(25)
        self._frost_blur_label = QLabel("25")
        self._frost_blur_label.setFixedWidth(36)
        self._frost_blur_slider.valueChanged.connect(
            lambda v: (self._frost_blur_label.setText(str(v)), self._emit()))
        frost_blur_row.addWidget(self._frost_blur_slider)
        frost_blur_row.addWidget(self._frost_blur_label)
        layout.addLayout(frost_blur_row)

        frost_dark_row = QHBoxLayout()
        frost_dark_row.addWidget(QLabel("  Abdunklung:"))
        self._frost_dark_slider = QSlider(Qt.Orientation.Horizontal)
        self._frost_dark_slider.setRange(0, 90)
        self._frost_dark_slider.setValue(35)
        self._frost_dark_label = QLabel("35%")
        self._frost_dark_label.setFixedWidth(36)
        self._frost_dark_slider.valueChanged.connect(
            lambda v: (self._frost_dark_label.setText(f"{v}%"), self._emit()))
        frost_dark_row.addWidget(self._frost_dark_slider)
        frost_dark_row.addWidget(self._frost_dark_label)
        layout.addLayout(frost_dark_row)

        # ── Graph line (moved here from Options) ─────────────────────────
        from PyQt6.QtWidgets import QSpinBox

        self._fps_color = '#00FF00'
        self._ft_color  = '#00FF00'

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("FPS:"))
        self._fps_color_btn = QPushButton()
        self._fps_color_btn.setFixedSize(40, 22)
        self._fps_color_btn.setStyleSheet(f"background: {self._fps_color}; border: 1px solid #555;")
        self._fps_color_btn.clicked.connect(lambda: self._pick_color('fps'))
        color_row.addWidget(self._fps_color_btn)
        color_row.addWidget(QLabel("FT:"))
        self._ft_color_btn = QPushButton()
        self._ft_color_btn.setFixedSize(40, 22)
        self._ft_color_btn.setStyleSheet(f"background: {self._ft_color}; border: 1px solid #555;")
        self._ft_color_btn.clicked.connect(lambda: self._pick_color('ft'))
        color_row.addWidget(self._ft_color_btn)
        layout.addWidget(QLabel("Line colours:"))
        layout.addLayout(color_row)

        layout.addWidget(QLabel("Line thickness (base @1080p):"))
        self._thick_spin = QSpinBox()
        self._thick_spin.setRange(1, 8)
        self._thick_spin.setValue(2)
        self._thick_spin.setSuffix(" px")
        layout.addWidget(self._thick_spin)

        layout.addWidget(QLabel("Graph smoothing:"))
        smooth_row = QHBoxLayout()
        self._smooth_slider = QSlider(Qt.Orientation.Horizontal)
        self._smooth_slider.setRange(1, 31)
        self._smooth_slider.setValue(9)
        self._smooth_label = QLabel("9")
        self._smooth_label.setFixedWidth(26)
        self._smooth_slider.valueChanged.connect(
            lambda v: self._smooth_label.setText(str(v | 1)))
        smooth_row.addWidget(self._smooth_slider)
        smooth_row.addWidget(self._smooth_label)
        layout.addLayout(smooth_row)

        layout.addWidget(QLabel("FPS number update (frames):"))
        interval_row = QHBoxLayout()
        self._interval_slider = QSlider(Qt.Orientation.Horizontal)
        self._interval_slider.setRange(1, 60)
        self._interval_slider.setValue(15)
        self._interval_label = QLabel("15")
        self._interval_label.setFixedWidth(26)
        self._interval_slider.valueChanged.connect(
            lambda v: self._interval_label.setText(str(v)))
        interval_row.addWidget(self._interval_slider)
        interval_row.addWidget(self._interval_label)
        layout.addLayout(interval_row)

    def _on_style_change(self):
        # Adapt the thickness field label to the style
        style = self._style_combo.currentText()
        if style == 'Drop Shadow':
            self._ow_label.setText("Shadow distance (base @1080p):")
            self._ow_spin.setEnabled(True)
        elif style == 'Hard Outline':
            self._ow_label.setText("Outline width (base @1080p):")
            self._ow_spin.setEnabled(True)
        else:  # None
            self._ow_label.setText("(no border with 'None')")
            self._ow_spin.setEnabled(False)
        self._emit()

    def _pick_color(self, which: str):
        from PyQt6.QtWidgets import QColorDialog
        from PyQt6.QtGui import QColor
        cur = self._fps_color if which == 'fps' else self._ft_color
        chosen = QColorDialog.getColor(QColor(cur), self, "Linienfarbe")
        if chosen.isValid():
            if which == 'fps':
                self._fps_color = chosen.name()
                self._fps_color_btn.setStyleSheet(f"background: {chosen.name()}; border: 1px solid #555;")
            else:
                self._ft_color = chosen.name()
                self._ft_color_btn.setStyleSheet(f"background: {chosen.name()}; border: 1px solid #555;")

    def _on_opacity(self, v):
        self._opacity_label.setText(f"{v}%")
        self._emit()

    def _emit(self):
        self.style_changed.emit(self.get_style())

    def get_style(self) -> dict:
        return {
            'text_style': self._style_combo.currentText(),
            'outline_width': self._ow_spin.value(),
            'graph_border': self._border_combo.currentText(),
            'bg_opacity': self._opacity_slider.value() / 100.0,
            'fps_color': self._fps_color,
            'ft_color': self._ft_color,
            'line_thickness': self._thick_spin.value(),
            'smooth_window': self._smooth_slider.value() | 1,
            'fps_update_interval': self._interval_slider.value(),
            'frosted_glass': self._frost_check.isChecked(),
            'frost_blur': self._frost_blur_slider.value(),
            'frost_darken': self._frost_dark_slider.value() / 100.0,
        }

    def set_style(self, style: dict):
        ts = style.get('text_style', 'Hard Outline')
        gb = style.get('graph_border', 'White Outline')
        op = int(style.get('bg_opacity', 0.5) * 100)
        idx = self.STYLES.index(ts) if ts in self.STYLES else 0
        self._style_combo.setCurrentIndex(idx)
        self._ow_spin.setValue(int(style.get('outline_width', 3)))
        bi = ['White Outline', 'Soft Glow', 'None']
        self._border_combo.setCurrentIndex(bi.index(gb) if gb in bi else 0)
        self._opacity_slider.setValue(op)
        self._frost_check.setChecked(bool(style.get('frosted_glass', False)))
        self._frost_blur_slider.setValue(int(style.get('frost_blur', 25)))
        self._frost_dark_slider.setValue(int(style.get('frost_darken', 0.35) * 100))
        self._on_style_change()
        if style.get('fps_color'):
            self._fps_color = style['fps_color']
            self._fps_color_btn.setStyleSheet(f"background: {self._fps_color}; border: 1px solid #555;")
        if style.get('ft_color'):
            self._ft_color = style['ft_color']
            self._ft_color_btn.setStyleSheet(f"background: {self._ft_color}; border: 1px solid #555;")
        self._thick_spin.setValue(int(style.get('line_thickness', 2)))
        self._smooth_slider.setValue(int(style.get('smooth_window', 9)))
        self._interval_slider.setValue(int(style.get('fps_update_interval', 15)))


# ── Main Dialog ───────────────────────────────────────────────────────────────

class LayoutEditorDialog(QDialog):
    """
    Drag-and-Drop Layout Editor.

    Usage:
        dlg = LayoutEditorDialog(parent_analyzer)
        dlg.exec()
    """

    def __init__(self, parent_analyzer):
        super().__init__(parent_analyzer)
        self.parent_analyzer = parent_analyzer
        self.setWindowTitle("Layout Editor")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(1100, 700)

        self._build_ui()
        self._load_current_layout()

        # Enable the live preview with real overlay rendering
        try:
            self._canvas.enable_preview(self.parent_analyzer)
        except Exception as e:
            print(f"LayoutEditor: could not enable the preview: {e}")

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Left sidebar ──────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)

        # Element list
        elem_group = QGroupBox("Elements")
        elem_layout = QVBoxLayout(elem_group)
        elem_layout.setSpacing(4)
        self._elem_buttons: dict[str, QPushButton] = {}
        for elem_id, meta in ELEMENTS.items():
            btn = QPushButton(meta['label'])
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{ 
                    text-align: left; padding: 4px 8px;
                    border-left: 4px solid rgba({meta['color'].red()},{meta['color'].green()},{meta['color'].blue()},200);
                }}
                QPushButton:checked {{ background: rgba(255,255,255,15); }}
            """)
            btn.clicked.connect(lambda _, eid=elem_id: self._select_element(eid))
            elem_layout.addWidget(btn)
            self._elem_buttons[elem_id] = btn
        sidebar_layout.addWidget(elem_group)

        # Properties panel
        props_group = QGroupBox("Properties")
        props_layout = QVBoxLayout(props_group)
        self._props = PropertiesPanel()
        self._props.value_changed.connect(self._on_props_changed)
        props_layout.addWidget(self._props)
        sidebar_layout.addWidget(props_group)

        sidebar_layout.addStretch()

        # ── Canvas (center) ───────────────────────────────────────────────────
        self._canvas = LayoutCanvas()
        self._canvas.layout_changed.connect(self._on_canvas_changed)

        # ── Right sidebar ─────────────────────────────────────────────────────
        right = QWidget()
        right.setFixedWidth(200)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._style_panel = StylePanel()
        self._style_panel.style_changed.connect(self._on_style_changed)
        right_layout.addWidget(self._style_panel)

        # Actions
        btn_reset = QPushButton("↺ Reset to Default")
        btn_reset.clicked.connect(self._reset_layout)
        right_layout.addWidget(btn_reset)

        # Save / load layout (file)
        io_row = QHBoxLayout()
        btn_save = QPushButton("💾 Save Layout")
        btn_save.clicked.connect(self._save_layout_file)
        btn_load = QPushButton("📂 Load Layout")
        btn_load.clicked.connect(self._load_layout_file)
        io_row.addWidget(btn_save)
        io_row.addWidget(btn_load)
        right_layout.addLayout(io_row)

        right_layout.addStretch()

        # Apply / Cancel
        btn_row = QHBoxLayout()
        btn_apply = QPushButton("✓ Apply")
        btn_apply.setDefault(True)
        btn_apply.setStyleSheet("QPushButton { background: #2a6; color: white; font-weight: bold; padding: 6px; }")
        btn_apply.clicked.connect(self._apply)

        btn_cancel = QPushButton("✕ Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_apply)
        right_layout.addLayout(btn_row)

        root.addWidget(sidebar)
        root.addWidget(self._canvas, 1)
        root.addWidget(right)

    # ── Data flow ──────────────────────────────────────────────────────────────

    def _load_current_layout(self):
        """Load layout from LayoutManager."""
        try:
            raw = self.parent_analyzer.layout_manager.get_current_layout()
            # Normalise to {id: {position: [x,y], size: [w,h], visible: bool}}
            layout = {}
            for elem_id, data in raw.items():
                pos = list(data.get('position', [50, 50]))
                size = list(data.get('size', [200, 100]))
                layout[elem_id] = {
                    'position': pos,
                    'size': size,
                    'visible': data.get('visible', True),
                }
            self._layout = layout
        except Exception as e:
            print(f"LayoutEditor: could not load layout: {e}")
            from layout_manager import LayoutManager
            lm = LayoutManager(None)
            self._layout = {
                k: {'position': list(v['position']), 'size': list(v['size']), 'visible': True}
                for k, v in lm.get_default_layout().items()
            }

        # Load the style: analyzer attributes (live) take priority over saved settings
        try:
            a = self.parent_analyzer
            saved = {}
            try:
                saved = a.settings_manager.load_settings() or {}
            except Exception:
                pass
            style = dict(saved.get('overlay_style', {}) or {})
            style.update(getattr(a, 'overlay_style', {}) or {})
            if getattr(a, 'framerate_color', None) is not None:
                style['fps_color'] = a.framerate_color
            if getattr(a, 'frametime_color', None) is not None:
                style['ft_color'] = a.frametime_color
            if getattr(a, 'fps_line_thickness', None):
                style['line_thickness'] = a.fps_line_thickness
            if getattr(a, 'graph_smooth_window', None):
                style['smooth_window'] = a.graph_smooth_window
            if getattr(a, 'fps_update_interval_setting', None):
                style['fps_update_interval'] = a.fps_update_interval_setting
            if style:
                self._style_panel.set_style(style)
        except Exception as e:
            print(f"LayoutEditor: could not load style: {e}")

        self._canvas.set_layout(self._layout)
        self._props.set_element(None, self._layout)

    def _on_canvas_changed(self):
        self._layout = self._canvas.get_layout()
        # Sync props panel if something is selected
        selected = self._canvas.get_selected_id()
        if selected != self._props._elem_id:
            self._select_element(selected)
        else:
            self._props.sync_from_layout(self._layout)

    def _on_props_changed(self):
        """Props panel changed → push to canvas."""
        self._canvas.set_layout(self._layout)

    def _on_style_changed(self, style: dict):
        """Style panel changed — Preview live aktualisieren."""
        # Push the style onto the renderer temporarily so the preview shows it
        try:
            a = self.parent_analyzer
            a.overlay_style = {
                'text_style': style.get('text_style', 'Hard Outline'),
                'outline_width': style.get('outline_width', 3),
                'graph_border': style.get('graph_border', 'White Outline'),
                'bg_opacity': style.get('bg_opacity', 0.5),
                'frosted_glass': style.get('frosted_glass', False),
                'frost_blur': style.get('frost_blur', 25),
                'frost_darken': style.get('frost_darken', 0.35),
            }
            a.fps_line_thickness = style.get('line_thickness')
            if style.get('fps_color') is not None:
                a.framerate_color = style['fps_color']
            if style.get('ft_color') is not None:
                a.frametime_color = style['ft_color']
            # Update color_settings for the preview (the renderer reads these)
            a.color_settings = {
                'framerate_color': getattr(a, 'framerate_color', '#00FF00'),
                'frametime_color': getattr(a, 'frametime_color', '#00FF00'),
            }
            # Invalidate the renderer cache so the style takes effect
            r = a.get_renderer_instance() if hasattr(a, 'get_renderer_instance') else None
            if r is not None:
                r._overlay_style = a.overlay_style
                if hasattr(r, '_bg_cache'): r._bg_cache.clear()
                if hasattr(r, '_border_cache'): r._border_cache.clear()
        except Exception as e:
            print(f"LayoutEditor: Style-Preview-Push fehlgeschlagen: {e}")
        self._canvas._schedule_preview()

    def _select_element(self, elem_id: str | None):
        # Update canvas selection
        self._canvas._selected_id = elem_id
        self._canvas.update()
        # Update button states
        for eid, btn in self._elem_buttons.items():
            btn.setChecked(eid == elem_id)
        # Update props
        self._props.set_element(elem_id, self._layout)

    def _save_layout_file(self):
        """Save layout + style as a JSON file."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        import json
        path, _ = QFileDialog.getSaveFileName(
            self, "Save layout", "layout.json", "JSON (*.json)")
        if not path:
            return
        try:
            data = {
                'layout': self._canvas.get_layout(),
                'style': self._style_panel.get_style(),
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self, "Saved", f"Layout saved:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Saving failed:\n{e}")

    def _load_layout_file(self):
        """Load layout + style from a JSON file."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        import json
        path, _ = QFileDialog.getOpenFileName(
            self, "Load layout", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            lay = data.get('layout', {})
            # Normalise (lists instead of tuples, visible default)
            self._layout = {
                k: {'position': list(v['position']), 'size': list(v['size']),
                    'visible': v.get('visible', True)}
                for k, v in lay.items()
            }
            self._canvas.set_layout(self._layout)
            self._props.set_element(None, self._layout)
            if data.get('style'):
                self._style_panel.set_style(data['style'])
            QMessageBox.information(self, "Geladen", f"Layout geladen:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Loading failed:\n{e}")

    def _reset_layout(self):
        from layout_manager import LayoutManager
        lm = LayoutManager(None)
        default = lm.get_default_layout()
        self._layout = {
            k: {'position': list(v['position']), 'size': list(v['size']), 'visible': True}
            for k, v in default.items()
        }
        self._canvas.set_layout(self._layout)
        self._props.set_element(None, self._layout)

    def _apply(self):
        """Save layout + style back to the app."""
        try:
            # Build layout in the format LayoutManager expects
            save_layout = {}
            for elem_id, data in self._layout.items():
                save_layout[elem_id] = {
                    'position': tuple(data['position']),
                    'size': tuple(data['size']),
                    'visible': data.get('visible', True),
                    'anchor': 'top_left',
                }
                # Preserve extra fields from original layout
                try:
                    orig = self.parent_analyzer.layout_manager.get_current_layout().get(elem_id, {})
                    for k, v in orig.items():
                        if k not in save_layout[elem_id]:
                            save_layout[elem_id][k] = v
                except Exception:
                    pass

            # Apply to LayoutManager
            self.parent_analyzer.layout_manager.set_current_layout(save_layout)

            # Save overlay style - as an analyzer attribute; persistence is handled
            # save_current_settings() further down
            style = self._style_panel.get_style()
            self.parent_analyzer.overlay_style = style

            # Write the graph line settings onto the analyzer
            a = self.parent_analyzer
            try:
                a.framerate_color = style['fps_color']
                a.frametime_color = style['ft_color']
                if hasattr(a, 'color_settings'):
                    a.color_settings['framerate_color'] = style['fps_color']
                    a.color_settings['frametime_color']  = style['ft_color']
                a.fps_line_thickness = style['line_thickness']
                a.graph_smooth_window = style['smooth_window']
                a.fps_update_interval_setting = style['fps_update_interval']
                if hasattr(a, 'save_current_settings'):
                    a.save_current_settings()
            except Exception as e:
                print(f"LayoutEditor: could not apply graph settings: {e}")

            # Invalidate CodeRenderer cache so new style takes effect
            try:
                renderer = self.parent_analyzer.get_renderer_instance()
                if renderer and hasattr(renderer, '_bg_cache'):
                    renderer._bg_cache.clear()
                if renderer and hasattr(renderer, '_stats_cache'):
                    renderer._stats_cache.clear()
            except Exception:
                pass

            # Also try via analysis_worker if it exists
            try:
                if hasattr(self.parent_analyzer, '_worker') and self.parent_analyzer._worker:
                    inst = getattr(self.parent_analyzer._worker, '_png_renderer_instance', None)
                    if inst:
                        if hasattr(inst, '_bg_cache'):
                            inst._bg_cache.clear()
                        if hasattr(inst, '_stats_cache'):
                            inst._stats_cache.clear()
            except Exception:
                pass

            self.parent_analyzer.log("✅ Layout updated via Layout Editor")
            self.accept()

        except Exception as e:
            import traceback
            traceback.print_exc()
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Apply Error", f"Could not apply layout:\n{e}")
