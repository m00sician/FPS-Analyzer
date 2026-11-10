"""
Konfigurationsfenster für das Stats-Panel.

Aufbau nach der Skizze:

    TITEL:  [ Text ................................ ] [Farbe]
    ─────────────────────────────────────────────────────────
    [ADD BOX]
    [ Konsole ............ ] [Farbe]   [ Version ..... ] [Farbe]   ← fest
    [ Text ..... ] [↔][Farbe][🗑]      [ Text .... ] [↔][Farbe][🗑]
    ...
    ─────────────────────────────────────────────────────────
    FPS FARBE: [ ]        FT FARBE: [ ]
    ─────────────────────────────────────────────────────────
    [ VORSCHAU ]   [START ENCODE] [CANCEL ENCODE]
                   [ANALYSE-DATEN LADEN]
                   [SCHLIESSEN]

Belegungsregeln (siehe LayoutModel, dort auch getestet):
  • Die erste Zeile (Konsole + Version) ist fest: nicht löschbar, nicht
    verbreiterbar.
  • Darunter höchstens MAX_EXTRA_LINES Zeilen.
  • Jede Zeile enthält entweder EIN breites oder ZWEI schmale Felder.
  • Daraus ergeben sich alle Kombinationen von 3 breiten bis 6 schmalen
    Feldern und allem dazwischen.
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QLineEdit, QPushButton, QWidget,
                             QFrame, QColorDialog, QMessageBox, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QImage

from stats_panel import (default_config, normalize_config, MAX_EXTRA_LINES,
                         render_panel, panel_size, clear_cache)


# ══════════════════════════════════════════════════════════════════════════
# Layout-Logik (ohne Qt, damit einzeln testbar)
# ══════════════════════════════════════════════════════════════════════════

class LayoutModel:
    """
    Verwaltet die Zusatzfelder unter der festen Konsole/Version-Zeile.

    Interne Darstellung: Liste von Zeilen, jede Zeile eine Liste mit einem
    oder zwei Feld-Dicts {'text','color','wide'}.
    """

    def __init__(self, lines=None):
        self.lines = [list(l) for l in (lines or [])]

    # ── Abfragen ────────────────────────────────────────────────────────
    def field_count(self):
        return sum(len(l) for l in self.lines)

    def can_add(self):
        """Frei ist entweder ein halber Platz in der letzten Zeile oder eine neue Zeile."""
        if self.lines and len(self.lines[-1]) == 1 and not self.lines[-1][0]['wide']:
            return True
        return len(self.lines) < MAX_EXTRA_LINES

    def can_widen(self, li, fi):
        """
        Breit machen geht, wenn das Feld allein in seiner Zeile steht, oder
        wenn der Partner in eine neue Zeile ausweichen kann.
        """
        if not (0 <= li < len(self.lines)):
            return False
        if self.lines[li][fi].get('wide'):
            return True          # zurückschalten geht immer
        if len(self.lines[li]) == 1:
            return True
        return len(self.lines) < MAX_EXTRA_LINES

    # ── Änderungen ──────────────────────────────────────────────────────
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
        # Partner in eine eigene Zeile direkt darunter verschieben
        partner = line[1 - fi]
        f['wide'] = True
        self.lines[li] = [f]
        self.lines.insert(li + 1, [partner])
        return True

    def to_list(self):
        return [[dict(f) for f in line] for line in self.lines]


# ══════════════════════════════════════════════════════════════════════════
# Qt-Oberfläche
# ══════════════════════════════════════════════════════════════════════════

def _swatch_style(color):
    return (f"background-color: {color}; border: 1px solid #888;")


class ColorButton(QPushButton):
    """Kleiner Farbwähler."""
    colorChanged = pyqtSignal(str)

    def __init__(self, color='#FFFFFF', parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(28, 24)
        self.setStyleSheet(_swatch_style(color))
        self.setToolTip("Farbe wählen")
        self.clicked.connect(self._pick)

    def color(self):
        return self._color

    def setColor(self, c):
        self._color = c
        self.setStyleSheet(_swatch_style(c))

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self, "Farbe wählen")
        if c.isValid():
            self.setColor(c.name().upper())
            self.colorChanged.emit(self._color)


class StatsPanelDialog(QDialog):
    """Fenster zum Zusammenstellen und Vorschauen des Stats-Panels."""

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
        self.title_edit.setPlaceholderText("Spielname")
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
            f"Fügt ein Textfeld hinzu. Es landet neben dem letzten Feld,\n"
            f"sonst in einer neuen Zeile. Maximal {MAX_EXTRA_LINES} Zeilen\n"
            f"= bis zu {MAX_EXTRA_LINES*2} schmale Felder.")
        self.add_btn.clicked.connect(self._add_field)
        root.addWidget(self.add_btn, 0, Qt.AlignmentFlag.AlignLeft)

        # Feste Zeile: Konsole + Version
        fixed = QHBoxLayout()
        self.console_edit = QLineEdit(cfg['console']['text'])
        self.console_edit.setPlaceholderText("Konsole")
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
            w.setToolTip("Festes Feld — nicht löschbar und nicht verbreiterbar.")
        root.addLayout(fixed)

        # Dynamische Felder
        self.fields_host = QWidget()
        self.fields_layout = QGridLayout(self.fields_host)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.fields_host)
        root.addWidget(self._hline())

        # ── Graphfarben ─────────────────────────────────────────────────
        colors = QHBoxLayout()
        colors.addWidget(QLabel("FPS FARBE:"))
        self.fps_color = ColorButton(cfg['fps_color'])
        self.fps_color.colorChanged.connect(self._refresh_preview)
        colors.addWidget(self.fps_color)
        colors.addSpacing(30)
        colors.addWidget(QLabel("FT FARBE:"))
        self.ft_color = ColorButton(cfg['ft_color'])
        self.ft_color.colorChanged.connect(self._refresh_preview)
        colors.addWidget(self.ft_color)
        colors.addStretch(1)
        root.addLayout(colors)
        root.addWidget(self._hline())

        # ── Vorschau + Aktionen ─────────────────────────────────────────
        bottom = QHBoxLayout()
        self.preview = QLabel("Vorschau")
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
        self.load_btn = QPushButton("ANALYSE-DATEN LADEN")
        self.load_btn.clicked.connect(self._load_data)
        self.close_btn = QPushButton("SCHLIESSEN")
        self.close_btn.clicked.connect(self.accept)
        for b in (self.start_btn, self.cancel_btn, self.load_btn, self.close_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        bottom.addLayout(btns)
        root.addLayout(bottom)

        self._rebuild_fields()

    # ── Hilfen ──────────────────────────────────────────────────────────
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
        """Feld-Widgets aus dem Modell neu aufbauen."""
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
            "Feld über die ganze Breite ziehen.\n"
            "Ein Partnerfeld rutscht dabei in eine eigene Zeile —\n"
            "das geht nur, solange noch eine Zeile frei ist."
            if self.model.can_widen(li, fi) else
            "Nicht möglich: dafür müsste eine Zeile frei sein.")
        wide_btn.clicked.connect(lambda _, l=li, i=fi: self._toggle_wide(l, i))
        lay.addWidget(wide_btn)

        col = ColorButton(f.get('color', '#FFFFFF'))
        col.colorChanged.connect(lambda c, l=li, i=fi: self._set_color(l, i, c))
        lay.addWidget(col)

        del_btn = QPushButton("🗑")
        del_btn.setFixedSize(28, 24)
        del_btn.setToolTip("Feld entfernen")
        del_btn.clicked.connect(lambda _, l=li, i=fi: self._remove(l, i))
        lay.addWidget(del_btn)
        return box

    # ── Modell-Änderungen ───────────────────────────────────────────────
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
                self, "Kein Platz mehr",
                f"Es sind höchstens {MAX_EXTRA_LINES} Zeilen möglich "
                f"(also bis zu {MAX_EXTRA_LINES*2} schmale Felder).")
            return
        self._rebuild_fields()

    def _remove(self, li, fi):
        self.model.remove(li, fi)
        self._rebuild_fields()

    def _toggle_wide(self, li, fi):
        self.model.toggle_wide(li, fi)
        self._rebuild_fields()

    # ── Konfiguration ───────────────────────────────────────────────────
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
        """Panel klein rendern und im Vorschaufeld zeigen."""
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
                # Demo-Verlauf, solange keine Analyse geladen ist
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
            self.preview.setText(f"Vorschau nicht möglich:\n{e}")

    # ── Aktionen ────────────────────────────────────────────────────────
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
        Encode starten. `toggle_analysis` ist im Hauptfenster der eine
        Einstiegspunkt: läuft nichts, startet es — läuft etwas, bricht es ab.
        Deshalb hier vorher prüfen, sonst würde der Knopf einen laufenden
        Encode abwürgen statt einen neuen zu starten.
        """
        self._apply_to_analyzer(True)
        w = getattr(self.analyzer, 'analysis_worker', None)
        if w is not None and w.isRunning():
            QMessageBox.information(
                self, "Encode läuft bereits",
                "Es läuft bereits ein Encode. Die Einstellungen sind "
                "gespeichert und gelten ab dem nächsten Lauf.")
            return
        fn = getattr(self.analyzer, 'toggle_analysis', None)
        if callable(fn):
            self.accept()
            fn()
        else:
            QMessageBox.information(self, "Übernommen",
                                    "Einstellungen gespeichert.")

    def _cancel_encode(self):
        w = getattr(self.analyzer, 'analysis_worker', None)
        if w is not None and w.isRunning():
            fn = getattr(self.analyzer, 'toggle_analysis', None)
            if callable(fn):
                fn()          # bricht ab und setzt die Oberfläche zurück
            else:
                w.cancel()
            QMessageBox.information(self, "Abgebrochen",
                                    "Der laufende Encode wurde abgebrochen.")
        else:
            QMessageBox.information(self, "Kein Encode aktiv",
                                    "Es läuft gerade kein Encode.")

    def _load_data(self):
        """Gespeicherte .fpsdata laden und encoden (Tools → Aus Analyse-Daten)."""
        self._apply_to_analyzer(True)
        fn = getattr(self.analyzer, 'encode_from_data', None)
        if callable(fn):
            self.accept()
            fn()
            return
        QMessageBox.information(
            self, "Nicht verfügbar",
            "Diese Funktion liegt im Menü unter 'Tools → Aus Analyse-Daten encoden'.")
