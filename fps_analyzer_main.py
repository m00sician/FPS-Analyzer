#!/usr/bin/env python3

"""

FPS Analyzer - Professional FPS Analysis Tool

Updated main application with Video Comparison Feature + settings persistence and Layout Editor integration

🎯 NEW: SEGMENT SELECTION FEATURE - Analyze only selected video segments

COMPLETE VERSION with all features integrated

"""
import sys
import os
import time
import cv2

# torch ist OPTIONAL und wird nur fuer die CUDA-Erkennung gebraucht.
# Ein harter Import hier machte es faktisch zur Pflicht (2+ GB Download),
# obwohl cuda_accelerator.py es korrekt als optional behandelt — und er
# machte zugleich die ImportError-Behandlung in check_dependencies()
# unerreichbar, weil das Programm schon hier abbrach.
try:
    import torch
except ImportError:
    torch = None
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog
from PyQt6.QtCore import (Qt, QTimer, QThread, pyqtSignal,
                          QMutex, QWaitCondition)
from PyQt6.QtGui import QPixmap, QImage, QFont
# Import modules

from menu_manager import MenuManager
from ui_manager import UIManager, ThemeManager
from analysis_worker import AnalysisWorker, resize_with_aspect_ratio
from settings_manager import SettingsManager
# ✨ NEW IMPORTS für Layout Editor

from layout_manager import LayoutManager
# 🔧 FIXED: Safe import of OpenCVFontSettings

# font_manager removed — Bebas Neue is loaded directly via truetype_core

class PreviewSeeker(QThread):
    """
    Sucht Vorschau-Frames im Hintergrund und liefert immer nur den ZULETZT
    angeforderten.

    Warum nötig: `cap.set(CAP_PROP_POS_FRAMES, n)` ist bei Langzeit-GOP-Material
    teuer, weil ab dem vorigen Keyframe alles dekodiert werden muss. Gemessen
    an 1080p mit GOP 250 (Container, eine CPU):

        Frame   0 (Keyframe):    18 ms
        Frame 120:              538 ms
        Frame 250 (Keyframe):  1118 ms
        Frame 500 (Keyframe):  1101 ms

    OpenCVs Seek ist dabei NICHT keyframe-bewusst — ein Sprung auf einen
    exakten Keyframe kostet genauso viel wie mitten ins GOP. Die Kosten
    entsprechen grob 4.5 ms je dekodiertem Frame und wachsen bei 4K
    entsprechend. Ein Wechsel auf ffmpeg bringt nichts, das wurde
    gegengemessen: gleiche Größenordnung, plus Prozessstart.

    Behebbar ist deshalb nicht die Dauer eines einzelnen Seeks, sondern:
      • dass er den UI-Thread blockiert (Fenster reagiert nicht mehr und
        wirkt wie kurz vor dem Absturz)
      • dass jeder Klick einen eigenen Seek in die Warteschlange legt. Bei
        fünf Klicks wurden fünf volle Seeks nacheinander abgearbeitet,
        obwohl nur der letzte interessiert.

    Dieser Thread hält genau EINE offene Anfrage. Kommt während eines Seeks
    eine neue, wird das alte Ergebnis verworfen und gar nicht erst gesendet.
    Die Wartezeit bleibt damit die eines einzelnen Seeks, unabhängig davon,
    wie oft geklickt wurde.
    """

    frameReady = pyqtSignal(int, object)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self._path = path
        self._mutex = QMutex()
        self._cond = QWaitCondition()
        self._target = None
        self._abort = False

    def request(self, frame_number):
        self._mutex.lock()
        self._target = int(frame_number)
        self._mutex.unlock()
        self._cond.wakeOne()

    def stop(self):
        self._mutex.lock()
        self._abort = True
        self._mutex.unlock()
        self._cond.wakeAll()
        self.wait(3000)

    def run(self):
        cap = cv2.VideoCapture(self._path)
        if not cap.isOpened():
            return
        try:
            while True:
                self._mutex.lock()
                while self._target is None and not self._abort:
                    self._cond.wait(self._mutex)
                if self._abort:
                    self._mutex.unlock()
                    break
                target = self._target
                self._target = None
                self._mutex.unlock()

                cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                ok, frame = cap.read()

                # Kam inzwischen eine neuere Anfrage, ist dieses Ergebnis
                # veraltet — nicht senden, sonst flackert die Vorschau
                # durch überholte Frames.
                self._mutex.lock()
                stale = self._target is not None or self._abort
                self._mutex.unlock()
                if ok and not stale:
                    self.frameReady.emit(target, frame)
        finally:
            cap.release()


class BebasNeueFont:
    """
    Schriftobjekt für die Overlay-Texte.

    Rendert über Pillow/TrueType, sobald eine Bridge und eine Schriftdatei
    vorliegen, und sonst über cv2.putText. Der OpenCV-Weg ist kein Notnagel,
    sondern ein vollwertiger zweiter Pfad in render_text() — deshalb genügt
    EINE Klasse für beide Fälle.

    Warum sie hier und nicht mehr in initialize_font_settings steht: Die
    Klasse war früher lokal im try-Block definiert, und der except-Zweig
    griff auf eine Klasse OpenCVFontSettings zurück, die es seit dem
    Entfernen von font_manager.py nicht mehr gibt. Der Rettungspfad warf
    damit selbst einen NameError — wer das Projekt ohne Bebas Neue oder
    ohne Pillow startete, bekam statt des Fallbacks einen Absturz.
    """

    def __init__(self, font_path, font_name, size, thickness, bold,
                 border_thickness, border_color, bridge=None):
        self.font_path = font_path
        self.font_name = font_name
        self.size = size
        self.thickness = thickness
        self.bold = bold
        self.border_thickness = border_thickness
        self.border_color = border_color
        self._pillow_bridge = bridge
        self._pillow_font = None
        self._cached_size = None
        self._load_font_with_size(size)

    def _load_font_with_size(self, size):
        """Schrift in der gewünschten Größe laden (nur mit Bridge möglich)."""
        if not (self.font_path and self._pillow_bridge):
            return
        if not os.path.exists(self.font_path):
            return
        try:
            self._pillow_font = self._pillow_bridge.load_system_font(
                self.font_path, int(size))
            self._cached_size = size
        except Exception:
            # Ohne geladene Schrift greift in render_text() der OpenCV-Pfad.
            self._pillow_font = None

    def render_text(self, img, text, position, scale=1.0):
        """Text zeichnen — über TrueType wenn möglich, sonst über OpenCV."""
        if self.size != self._cached_size and self._pillow_bridge:
            self._load_font_with_size(self.size)

        if self._pillow_font and self._pillow_bridge:
            return self._pillow_bridge.render_text(
                img, text, position, self._pillow_font,
                self.text_color, self.border_color, self.border_thickness)

        font = cv2.FONT_HERSHEY_DUPLEX
        font_scale = self.size / 40.0
        cv2.putText(img, text, position, font, font_scale,
                    self.border_color, self.thickness + self.border_thickness,
                    cv2.LINE_AA)
        cv2.putText(img, text, position, font, font_scale,
                    self.text_color, self.thickness, cv2.LINE_AA)
        return img

    def is_freetype_available(self):
        return self._pillow_font is not None

    def to_qfont(self):
        """Für Qt-Vorschauen in der Oberfläche."""
        qfont = QFont("Arial", int(self.size * 0.75))
        qfont.setBold(self.bold)
        return qfont

    @property
    def text_color(self):
        return getattr(self, '_text_color', (255, 255, 255))

    @text_color.setter
    def text_color(self, value):
        self._text_color = value


class FPSAnalyzer(QMainWindow):
    """Main FPS Analyzer Application with Video Comparison Feature + settings persistence and Layout Editor + Segment Selection"""
    def __init__(self):

        super().__init__()
        self._initializing = True
        self.setWindowTitle('🎯 FPS Analyzer')

        self.resize(1600, 1000)
        # Core properties

        self.video_cap = None
        self.preview_seeker = None      # Hintergrund-Seek fuer die Vorschau
        self._last_preview_frame = None # zuletzt angezeigter Frame (Neuzeichnen ohne Decode)
        self._pending_seek_frame = None # noch nicht auf video_cap angewandte Position

        self.playback_timer = QTimer(self)

        self.playback_timer.timeout.connect(self.next_frame)

        self.analysis_worker = None

        self.cuda_available = bool(torch is not None and torch.cuda.is_available())
        # 🎯 NEW: Segment Selection variables

        self.start_frame = None

        self.end_frame = None

        self.total_frames = 0

        self.video_fps = 30.0  # Default FPS

        self.segment_state = 0  # 0=set_start, 1=set_end, 2=complete
        # Preview settings

        self.internal_resolution = (1920, 1080)

        self.preview_quality = cv2.INTER_LANCZOS4
        # Settings Manager for persistence

        self.settings_manager = SettingsManager()
        # ✨ NEW: Layout Manager for custom element positioning

        self.layout_manager = LayoutManager(self.settings_manager)
        # Load saved settings

        saved_settings = self.settings_manager.load_settings()
        self._saved_use_cuda = saved_settings.get('use_cuda', False) and self.cuda_available  # Respect hardware availability
        # ✨ NEW: Load saved layout

        saved_layout = saved_settings.get('custom_layout', None)

        if saved_layout:

            self.layout_manager.set_current_layout(saved_layout)

        # Layout-Editor-Einstellungen wiederherstellen
        self.overlay_style = saved_settings.get('overlay_style', {}) or {}
        self.fade_detection_enabled = saved_settings.get('fade_detection', False)
        self.fade_buffer_ms = saved_settings.get('fade_buffer_ms', 2000)
        self.save_analysis_data = saved_settings.get('save_analysis_data', False)
        self.deviation_marker = saved_settings.get('deviation_marker', False)
        self.stats_panel_config = saved_settings.get('stats_panel_config')
        self.deviation_marker_hold_ms = saved_settings.get('deviation_marker_hold_ms', 150)
        self.fps_line_thickness = saved_settings.get('fps_line_thickness')
        self.graph_smooth_window = saved_settings.get('graph_smooth_window', 1)
        self.fps_update_interval_setting = saved_settings.get('fps_update_interval')

            # 🎯 NEW: Load saved segment settings - REMOVED (video-specific)

        # self.start_frame = saved_settings.get('last_start_frame', None)

        # self.end_frame = saved_settings.get('last_end_frame', None)

        self.start_frame = None

        self.end_frame = None
        # Set initial segment state 

        self.segment_state = 0  # Always start fresh
        # 🔧 FIXED: Font settings initialization with fallback

        self.initialize_font_settings(saved_settings)
        # Legacy QFont compatibility

        self.fps_font = QFont("Arial", 12)

        self.framerate_font = QFont("Arial", 10)

        self.frametime_font = QFont("Arial", 9)
        # Color settings - Load from saved settings

        self.framerate_color = saved_settings.get('framerate_color', '#00FF00')

        self.frametime_color = saved_settings.get('frametime_color', '#00FF00')
        # Theme - Load from saved settings

        self.current_theme = saved_settings.get('theme', 'dark')
        # Initialize components

        self.setup_application()



        
    def get_bebas_font_path(self):
        """Get Bebas Neue font path with multiple fallbacks"""
        possible_paths = [
            # Windows paths
            "C:/Windows/Fonts/BebasNeue-Regular.ttf",
            "C:/Windows/Fonts/BebasNeue.ttf",
            # Relative paths
            os.path.join(os.path.dirname(__file__), "fonts", "BebasNeue-Regular.ttf"),
            # Linux/Mac paths
            "/usr/share/fonts/truetype/bebas/BebasNeue-Regular.ttf",
            os.path.expanduser("~/.fonts/BebasNeue-Regular.ttf")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                    return path
        
        print("⚠️ Bebas Neue font not found, will use fallback")
        return None

    def initialize_font_settings(self, saved_settings):
        """
        Die drei Overlay-Schriften anlegen.

        Eine Bridge wird nur gesetzt, wenn Pillow UND truetype_core
        verfügbar sind. Fehlt eines davon, bekommt BebasNeueFont bridge=None
        und zeichnet über OpenCV weiter — der Start bricht nicht ab.
        """
        bridge = None
        try:
            from truetype_core import PillowOpenCVBridge, PILLOW_AVAILABLE
            if PILLOW_AVAILABLE:
                bridge = PillowOpenCVBridge()
            else:
                print("⚠️ Pillow nicht verfügbar — Overlay-Schrift über OpenCV")
        except Exception as e:
            print(f"⚠️ TrueType-Setup nicht möglich ({e}) — Overlay-Schrift über OpenCV")

        bebas_font_path = self.get_bebas_font_path()

        self.fps_font_settings = BebasNeueFont(
            font_path=bebas_font_path, font_name='BebasNeue-Regular',
            size=60, thickness=3, bold=True,
            border_thickness=3, border_color=(0, 0, 0), bridge=bridge)

        self.framerate_font_settings = BebasNeueFont(
            font_path=bebas_font_path, font_name='BebasNeue-Regular',
            size=40, thickness=2, bold=False,
            border_thickness=2, border_color=(0, 0, 0), bridge=bridge)

        self.frametime_font_settings = BebasNeueFont(
            font_path=bebas_font_path, font_name='BebasNeue-Regular',
            size=40, thickness=2, bold=False,
            border_thickness=2, border_color=(0, 0, 0), bridge=bridge)

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
        self._initializing = False

    def load_ui_settings(self):
        """Load saved UI settings into widgets - COMPLETE VERSION"""
        saved_settings = self.settings_manager.load_settings()
        try:
            # WICHTIG: Signale blockieren während dem Laden, um save_current_settings() nicht auszulösen
            widgets_to_block = [
                'resolution_combo', 'bitrate_combo', 'fps_graph_combo', 
                'frametime_combo', 'sensitivity_combo', 'baseline_fps_combo'
            ]
            
            # Signale blockieren
            for widget_name in widgets_to_block:
                if hasattr(self, widget_name):
                    getattr(self, widget_name).blockSignals(True)
            
            # Load resolution setting
            saved_resolution = saved_settings.get('output_resolution', (1920, 1080))
            for i in range(self.resolution_combo.count()):
                if self.resolution_combo.itemData(i) == saved_resolution:
                    self.resolution_combo.setCurrentIndex(i)
                    break
            
            # Load bitrate setting with proper opencv/prores handling
            saved_bitrate = saved_settings.get('bitrate', '60')
            saved_bitrate_str = str(saved_bitrate)
            
            for i in range(self.bitrate_combo.count()):
                item_data = self.bitrate_combo.itemData(i)
                if str(item_data) == saved_bitrate_str:
                    self.bitrate_combo.setCurrentIndex(i)
                    break
            
            # Load baseline FPS setting
            saved_baseline_fps = saved_settings.get('baseline_fps', 0)
            if hasattr(self, 'baseline_fps_combo'):
                for i in range(self.baseline_fps_combo.count()):
                    if self.baseline_fps_combo.itemData(i) == saved_baseline_fps:
                        self.baseline_fps_combo.setCurrentIndex(i)
                        break

            # Load FPS graph template
            saved_fps_template = saved_settings.get('fps_graph_template')
            if saved_fps_template and hasattr(self, 'fps_graph_combo'):
                if saved_fps_template.get('template') == 'custom':
                    # Custom-Eintrag neu erzeugen (existiert nach Neustart nicht mehr)
                    vals = saved_fps_template.get('values', [60, 30, 0])
                    hid = set(saved_fps_template.get('hidden', []))
                    lbl = 'Custom (' + ','.join(('x' if v in hid else '') + f"{v:g}" for v in vals) + ')'
                    self.fps_graph_combo.addItem(lbl, saved_fps_template)
                    self.fps_graph_combo.setCurrentIndex(self.fps_graph_combo.count() - 1)
                else:
                    for i in range(self.fps_graph_combo.count()):
                        template_data = self.fps_graph_combo.itemData(i)
                        if template_data and template_data.get('template') == saved_fps_template.get('template'):
                            self.fps_graph_combo.setCurrentIndex(i)
                            break
            
            # Load frametime template
            saved_ft_template = saved_settings.get('frametime_template')
            if saved_ft_template and hasattr(self, 'frametime_combo'):
                if saved_ft_template.get('template') == 'custom':
                    vals = saved_ft_template.get('values', [16.7, 33.3, 100])
                    hid = set(saved_ft_template.get('hidden', []))
                    lbl = 'Custom (' + ','.join(('x' if v in hid else '') + f"{v:g}" for v in vals) + 'ms)'
                    self.frametime_combo.addItem(lbl, saved_ft_template)
                    self.frametime_combo.setCurrentIndex(self.frametime_combo.count() - 1)
                else:
                    for i in range(self.frametime_combo.count()):
                        template_data = self.frametime_combo.itemData(i)
                        if template_data and template_data.get('template') == saved_ft_template.get('template'):
                            self.frametime_combo.setCurrentIndex(i)
                            break
            
            # Load sensitivity setting
            saved_sensitivity_index = saved_settings.get('sensitivity_index', 2)
            if 0 <= saved_sensitivity_index < self.sensitivity_combo.count():
                self.sensitivity_combo.setCurrentIndex(saved_sensitivity_index)
            
            # Load checkbox settings
            if hasattr(self, 'show_frametime_checkbox'):
                self.show_frametime_checkbox.setChecked(saved_settings.get('show_frametime', True))
            
            if hasattr(self, 'use_cuda_checkbox'):
                saved_cuda = saved_settings.get('use_cuda', False)
                self.use_cuda_checkbox.setChecked(saved_cuda and self.cuda_available)
                self._saved_use_cuda = saved_cuda  # NEU: Aktualisiere den gespeicherten Wert

            # Load preview settings
            saved_internal_res = saved_settings.get('internal_resolution', (1920, 1080))
            self.internal_resolution = saved_internal_res
            
            # Signale wieder aktivieren
            for widget_name in widgets_to_block:
                if hasattr(self, widget_name):
                    getattr(self, widget_name).blockSignals(False)
            
            # Update segment display if segments are loaded
            if self.start_frame is not None or self.end_frame is not None:
                self.update_segment_display()
                
        except Exception as e:
            # Signale im Fehlerfall auch wieder aktivieren
            for widget_name in ['resolution_combo', 'bitrate_combo', 'fps_graph_combo', 
                            'frametime_combo', 'sensitivity_combo', 'baseline_fps_combo']:
                if hasattr(self, widget_name):
                    getattr(self, widget_name).blockSignals(False)
            self.log(f"⚠️ Could not load some UI settings: {e}")

    def save_current_settings(self):
        """Save current settings including TrueType font paths and templates"""
        if getattr(self, '_initializing', True):
            return
        try:
            # Get current bitrate value properly
            current_bitrate = self.bitrate_combo.currentData() if hasattr(self, 'bitrate_combo') else '60'
            
            # Get current template selections
            fps_template = self.fps_graph_combo.currentData() if hasattr(self, 'fps_graph_combo') else None
            frametime_template = self.frametime_combo.currentData() if hasattr(self, 'frametime_combo') else None
            
            # Collect all settings
            settings = {
                # Font settings (existing)
                'fps_font_name': self.fps_font_settings.font_name,
                'fps_font_path': getattr(self.fps_font_settings, 'font_path', None),
                'fps_font_size': self.fps_font_settings.size,
                'fps_font_thickness': self.fps_font_settings.thickness,
                'fps_font_bold': self.fps_font_settings.bold,
                'fps_font_border': getattr(self.fps_font_settings, 'border_thickness', 2),
                
                'framerate_font_name': self.framerate_font_settings.font_name,
                'framerate_font_path': getattr(self.framerate_font_settings, 'font_path', None),
                'framerate_font_size': self.framerate_font_settings.size,
                'framerate_font_thickness': self.framerate_font_settings.thickness,
                'framerate_font_bold': self.framerate_font_settings.bold,
                'framerate_font_border': getattr(self.framerate_font_settings, 'border_thickness', 2),
                
                'frametime_font_name': self.frametime_font_settings.font_name,
                'frametime_font_path': getattr(self.frametime_font_settings, 'font_path', None),
                'frametime_font_size': self.frametime_font_settings.size,
                'frametime_font_thickness': self.frametime_font_settings.thickness,
                'frametime_font_bold': self.frametime_font_settings.bold,
                'frametime_font_border': getattr(self.frametime_font_settings, 'border_thickness', 2),
                
                # Template settings - SAVE THE COMPLETE DATA
                'fps_graph_template': fps_template,
                'frametime_template': frametime_template,
                
                # Color settings
                'framerate_color': self.framerate_color,
                'frametime_color': self.frametime_color,
                
                # UI settings
                'output_resolution': self.resolution_combo.currentData() if hasattr(self, 'resolution_combo') else (1920, 1080),
                'bitrate': current_bitrate,
                'sensitivity_index': self.sensitivity_combo.currentIndex() if hasattr(self, 'sensitivity_combo') else 2,
                
                # Other settings
                'theme': self.current_theme,
                'ftg_position': getattr(self, 'ftg_position', 'bottom_right'),
                'internal_resolution': self.internal_resolution,
                'show_frametime': self.show_frametime_checkbox.isChecked() if hasattr(self, 'show_frametime_checkbox') else True,
                'use_cuda': self.use_cuda_checkbox.isChecked() if hasattr(self, 'use_cuda_checkbox') else self.cuda_available,
                
                # Layout settings
                'custom_layout': self.layout_manager.get_current_layout() if hasattr(self, 'layout_manager') else None,
                
                #Baseline FPS
                'baseline_fps': self.baseline_fps_combo.currentData() if hasattr(self, 'baseline_fps_combo') else 0,

                # Layout-Editor-Einstellungen
                'overlay_style': getattr(self, 'overlay_style', {}) or {},
                'fade_detection': getattr(self, 'fade_detection_enabled', False),
                'fade_buffer_ms': getattr(self, 'fade_buffer_ms', 2000),
                'save_analysis_data': getattr(self, 'save_analysis_data', False),
                'deviation_marker': getattr(self, 'deviation_marker', False),
                'stats_panel_config': getattr(self, 'stats_panel_config', None),
                'source_fps': getattr(self, 'video_fps', 60.0) or 60.0,
                'deviation_marker_hold_ms': getattr(self, 'deviation_marker_hold_ms', 150),
                'fps_line_thickness': getattr(self, 'fps_line_thickness', None),
                'graph_smooth_window': getattr(self, 'graph_smooth_window', 1),
                'fps_update_interval': getattr(self, 'fps_update_interval_setting', None),

                # Enhanced font system info
                'font_system_version': '2.0_freetype',
                'freetype_available': getattr(self.fps_font_settings, 'is_freetype_available', lambda: False)()
            }
            
            self.settings_manager.save_settings(settings)
            
            # Enhanced status message
            font_status = "TrueType" if settings.get('freetype_available', False) else "Standard"
            
        except Exception as e:
            self.log(f"❌ Could not save enhanced settings: {e}")

    # ==========================================

    # 🎯 NEW: SEGMENT SELECTION METHODS

    # ==========================================
    def handle_segment_button(self):
        """🎯 NEW: Handle the main segment button - toggles between start/end"""

        if not self.video_cap or not self.video_cap.isOpened():

            self.log("⚠️ No video loaded")

            return
        current_frame = self.current_preview_frame()
        if self.segment_state == 0:

            # Set start point

            self.start_frame = current_frame

            self.segment_state = 1

            time_str = self.frame_to_time_string(current_frame)

            self.log(f"📍 Start point set at frame {current_frame} ({time_str})")
        elif self.segment_state == 1:

            # Set end point

            if current_frame <= self.start_frame:

                QMessageBox.warning(self, 'Invalid Selection', 
                                   f'End point must be after start point!\n\n'
                                   f'Start: {self.frame_to_time_string(self.start_frame)}\n'
                                   f'Current: {self.frame_to_time_string(current_frame)}\n\n'
                                   f'Please seek to a frame after the start point.')

                return
            self.end_frame = current_frame

            self.segment_state = 2

            time_str = self.frame_to_time_string(current_frame)

            duration_frames = self.end_frame - self.start_frame

            duration_time = self.frame_to_time_string(duration_frames)

            self.log(f"📍 End point set at frame {current_frame} ({time_str})")

            self.log(f"📊 Segment duration: {duration_frames} frames ({duration_time})")
        # Update UI

        self.update_segment_display()

        self.update_segment_buttons()
        # Don't save settings on every segment change - too frequent
    def clear_selection(self):

        """Clear segment selection"""
        self.start_frame = None
        self.end_frame = None
        self.segment_state = 0
        self.update_segment_display()
        self.update_segment_buttons()
        self.log("🗑️ Segment selection cleared")
        # Don't save settings - segments are video-specific
    def frame_to_time_string(self, frame_number):
        """Convert frame number to time string (MM:SS or HH:MM:SS)"""

        if frame_number < 0:

            return "00:00"
        seconds = frame_number / self.video_fps

        hours = int(seconds // 3600)

        minutes = int((seconds % 3600) // 60)

        seconds = int(seconds % 60)
        if hours > 0:

            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        else:

            return f"{minutes:02d}:{seconds:02d}"
    def update_segment_display(self):

        """Update segment info display"""
        if not hasattr(self, 'segment_info_label'):
            return  # UI not ready yet
        if self.start_frame is None and self.end_frame is None:
            self.segment_info_label.setText("No segment")
            self.segment_info_label.setStyleSheet("""
                QLabel {
                    color: #aaaaaa; font-size: 11px; padding: 6px 8px;
                    background-color: #1a1a1a; border-radius: 3px;
                    border: 1px solid #444;
                }
            """)

            return
        if self.start_frame is not None and self.end_frame is not None:

            # Full selection

            start_time = self.frame_to_time_string(self.start_frame)

            end_time = self.frame_to_time_string(self.end_frame)

            duration_frames = self.end_frame - self.start_frame

            duration_time = self.frame_to_time_string(duration_frames)
            # Calculate percentage of total video

            percentage = (duration_frames / self.total_frames * 100) if self.total_frames > 0 else 0
            text = f"{start_time} → {end_time} ({percentage:.0f}%)"

            self.segment_info_label.setText(text)

            self.segment_info_label.setStyleSheet("""

                QLabel {

                    color: #4CAF50; font-size: 11px; padding: 6px 8px; font-weight: bold;

                    background-color: #1a1a1a; border-radius: 3px;

                    border: 1px solid #4CAF50;

                }

            """)
        elif self.start_frame is not None:

            # Only start set

            start_time = self.frame_to_time_string(self.start_frame)
            text = f"Start: {start_time}"
            self.segment_info_label.setText(text)
            self.segment_info_label.setStyleSheet("""
                QLabel {
                    color: #FF9800; font-size: 11px; padding: 6px 8px; font-weight: bold;
                    background-color: #1a1a1a; border-radius: 3px;
                    border: 1px solid #FF9800;
                }
            """)
    def update_segment_buttons(self):

        """🎯 NEW: Update segment button state and labels"""
        if not hasattr(self, 'segment_btn'):
            return  # UI not ready yet
        if self.segment_state == 0:

            # Ready to set start

            self.segment_btn.setText("📍 Set Start Point")
            self.segment_btn.setStyleSheet("""
                QPushButton {
                    font-size: 12px; padding: 6px 12px; 
                    background-color: #2E7D32; color: white; 
                    border: none; border-radius: 4px; font-weight: bold;
                }
                QPushButton:hover { background-color: #4CAF50; }
                QPushButton:disabled { background-color: #404040; color: #666; }
            """)

            self.segment_btn.setEnabled(True)
        elif self.segment_state == 1:

            # Ready to set end

            start_time = self.frame_to_time_string(self.start_frame) if self.start_frame is not None else "00:00"

            self.segment_btn.setText(f"📍 Set End Point")

            self.segment_btn.setStyleSheet("""

                QPushButton {

                    font-size: 12px; padding: 6px 12px; 

                    background-color: #C62828; color: white; 

                    border: none; border-radius: 4px; font-weight: bold;

                }

                QPushButton:hover { background-color: #f44336; }

                QPushButton:disabled { background-color: #404040; color: #666; }

            """)
            self.segment_btn.setEnabled(True)
        elif self.segment_state == 2:

            # Selection complete

            duration_frames = self.end_frame - self.start_frame if (self.start_frame is not None and self.end_frame is not None) else 0
            duration_time = self.frame_to_time_string(duration_frames)
            self.segment_btn.setText(f"✅ Complete ({duration_time})")
            self.segment_btn.setStyleSheet("""
                QPushButton {
                    font-size: 12px; padding: 6px 12px; 
                    background-color: #4CAF50; color: white; 
                    border: 1px solid #66BB6A; border-radius: 4px; font-weight: bold;
                }
                QPushButton:hover { background-color: #66BB6A; }
                QPushButton:disabled { background-color: #404040; color: #666; }
            """)

            self.segment_btn.setEnabled(False)  # Disabled when complete
        # Enable/disable clear button

        has_selection = self.start_frame is not None or self.end_frame is not None

        self.clear_selection_btn.setEnabled(has_selection)
    def enable_segment_controls(self, enable=True):

        """Enable or disable segment controls when video is loaded/unloaded"""
        if not hasattr(self, 'segment_btn'):
            return  # UI not ready yet
        if enable:

            # Only enable main button if not in complete state

            self.segment_btn.setEnabled(self.segment_state != 2)
        else:
            self.segment_btn.setEnabled(False)
        # Clear button depends on selection

        has_selection = self.start_frame is not None or self.end_frame is not None
        self.clear_selection_btn.setEnabled(enable and has_selection)
    # ==========================================

    # END OF SEGMENT SELECTION METHODS

    # ===== BATCH PROCESSOR =====

    def open_batch_processor(self):
        """Open batch processor dialog"""

        try:

            from batch_processor import BatchProcessorDialog
            dialog = BatchProcessorDialog(self)

            dialog.exec()
            self.log("📦 Batch Processor opened")
        except ImportError as e:

            self.log(f"❌ Could not open Batch Processor: {e}")

    def open_stats_panel_dialog(self):
        """
        Stats-Panel-Fenster öffnen (Tools → Stats-Panel).

        Das Panel ist ein alternativer Anzeigemodus: eine abgerundete,
        halbtransparente Box mit Titel, FPS-Zahl, Statistik, beiden Graphen
        und frei belegbaren Textfeldern. Konfiguration und Vorschau laufen
        vollständig in diesem Fenster; beim Encode wird sie über die
        Settings an den Worker gereicht.
        """
        try:
            from stats_panel_dialog import StatsPanelDialog
            # Falls schon eine Analyse vorliegt, die echten Verläufe für die
            # Vorschau bereitstellen statt des Demo-Verlaufs.
            w = getattr(self, 'analysis_worker', None)
            if w is not None:
                self._preview_fps_seq = getattr(w, '_full_fps_seq', None)
                self._preview_ft_seq = getattr(w, '_full_ft_seq', None)
            dlg = StatsPanelDialog(self, self)
            dlg.exec()
            self.log("🧩 Stats-Panel-Einstellungen übernommen")
        except Exception as e:
            self.log(f"❌ Stats-Panel konnte nicht geöffnet werden: {e}")

    def run_resolution_analysis(self):
        """Auflösungs-Analyse (experimentell): schätzt die interne
        Renderauflösung eines Videos per FFT-Cutoff-Analyse."""
        try:
            from PyQt6.QtWidgets import QFileDialog, QMessageBox
            from PyQt6.QtCore import QThread, pyqtSignal

            path, _ = QFileDialog.getOpenFileName(
                self, "Video für Auflösungs-Analyse wählen",
                "", "Videos (*.mp4 *.mkv *.mov *.avi);;Alle Dateien (*)")
            if not path:
                return

            self.log(f"📐 Auflösungs-Analyse startet: {path}")
            self.log("   (experimentell — Schärfefilter/Rekonstruktion "
                     "können das Ergebnis verfälschen)")

            class _ResProbeWorker(QThread):
                done = pyqtSignal(str)
                prog = pyqtSignal(int, int)

                def __init__(w, video_path):
                    super().__init__()
                    w.video_path = video_path

                def run(w):
                    try:
                        from resolution_estimator import probe_video
                        _, report = probe_video(
                            w.video_path, samples=40,
                            progress_cb=lambda i, n: w.prog.emit(i, n))
                        w.done.emit(report)
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        w.done.emit(f"❌ Analyse fehlgeschlagen: {e}")

            self._res_probe_worker = _ResProbeWorker(path)
            self._res_probe_worker.prog.connect(
                lambda i, n: self.log(f"📐 Messe Frame {i}/{n}...")
                if i % 10 == 0 else None)

            def _on_done(report):
                print(report)          # volle Tabelle in die Konsole
                for line in report.split("\n")[:8]:
                    self.log(line)     # Zusammenfassung ins UI-Log
                summary = "\n".join(report.split("\n")[:8])
                QMessageBox.information(
                    self, "Auflösungs-Analyse (experimentell)",
                    summary + "\n\n(Vollständige Einzelwerte in der Konsole)")

            self._res_probe_worker.done.connect(_on_done)
            self._res_probe_worker.start()
        except Exception as e:
            self.log(f"❌ Auflösungs-Analyse: {e}")

            QMessageBox.warning(self, 'Batch Processor Error', 
                               f'Could not open Batch Processor:\n{str(e)}\n\nPlease check that batch_processor.py is available.')

        except Exception as e:

            self.log(f"❌ Batch Processor error: {e}")

            QMessageBox.warning(self, 'Batch Processor Error', f'Batch Processor error:\n{str(e)}')
    # ===== VIDEO COMPARISON =====

    def get_renderer_instance(self):
        """Return the active CodeRenderer instance if available (for cache invalidation)."""
        try:
            if hasattr(self, 'analysis_worker') and self.analysis_worker:
                return getattr(self.analysis_worker, '_png_renderer_instance', None)
        except Exception:
            pass
        return None

    def open_comparison_creator(self):

        """Open video comparison creator dialog"""
        try:
            from comparison_creator import ComparisonCreatorDialog
            dialog = ComparisonCreatorDialog(self)
            dialog.exec()
            self.log("📊 Video Comparison Creator opened")
        except ImportError as e:
            self.log(f"❌ Could not open Comparison Creator: {e}")
            QMessageBox.warning(self, 'Comparison Creator Error', 
                               f'Could not open Video Comparison Creator:\n{str(e)}\n\nPlease check that comparison_creator.py is available.')
        except Exception as e:
            self.log(f"❌ Comparison Creator error: {e}")
            QMessageBox.warning(self, 'Comparison Creator Error', f'Comparison Creator error:\n{str(e)}')
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

        if hasattr(self, 'resolution_actions'):
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

        if hasattr(self, 'quality_actions'):

            for action in self.quality_actions:

                action.setChecked(interpolation in [cv2.INTER_NEAREST, cv2.INTER_LINEAR, cv2.INTER_CUBIC, cv2.INTER_LANCZOS4] and 
                                str(interpolation) in action.text())
        self.refresh_current_frame()

        self.save_current_settings()
    def refresh_current_frame(self):

        """Refresh currently displayed frame"""
        # Aus dem zwischengespeicherten Frame neu zeichnen. Vorher wurde hier
        # aus video_cap gelesen — das steht seit dem Hintergrund-Scrubbing
        # nicht mehr auf der angezeigten Position, sodass bei jedem
        # Fenster-Resize ein falscher Frame erschien. Nebeneffekt: Neuzeichnen
        # kostet jetzt gar keinen Decode mehr.
        cached = getattr(self, '_last_preview_frame', None)
        if cached is not None:
            self.display_frame(cached)
            return
        if getattr(self, 'preview_seeker', None) is not None:
            self.preview_seeker.request(self.current_preview_frame())
            return
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
        if hasattr(self, 'cuda_action'):
            is_enabled = self.cuda_action.isChecked()
            self.use_cuda_checkbox.setChecked(is_enabled)
        elif hasattr(self, 'use_cuda_checkbox'):
            # Toggle direkt die Checkbox wenn keine Action existiert
            current = self.use_cuda_checkbox.isChecked()
            self.use_cuda_checkbox.setChecked(not current)
        
        # Settings speichern damit CUDA beim nächsten Start aktiv bleibt
        self.save_current_settings()
        
        # Status im Log anzeigen
        cuda_status = "ENABLED 🚀" if self.use_cuda_checkbox.isChecked() else "DISABLED"
        self.log(f"CUDA Acceleration: {cuda_status}")
    def toggle_frametime_graph(self):

        """Toggle frametime graph"""
        is_enabled = self.frametime_action.isChecked()
        self.show_frametime_checkbox.setChecked(is_enabled)
    # ===== FONT PREVIEW SYSTEM =====

    # ===== PNG ALPHA SEQUENCE EXPORT =====

    def export_png_alpha_sequence(self):
        """🎬 Export PNG Alpha Sequence für Premiere Pro - NEUE SIMPLE VERSION"""
        try:
            # Den neuen einfachen Exporter importieren
            from png_overlay_exporter import export_png_overlay_sequence
            
            # Einfach die Funktion aufrufen - sie kümmert sich um alles
            export_png_overlay_sequence(self)
            
            self.log("🎬 PNG Overlay Exporter geöffnet")
            
        except ImportError as e:
            self.log(f"❌ PNG Export nicht verfügbar: {e}")
            QMessageBox.warning(self, 'Export Error', 
                f'PNG Overlay Export nicht verfügbar:\n{str(e)}\n\n'
                'Bitte stellen Sie sicher, dass png_overlay_exporter.py vorhanden ist.')
        except Exception as e:
            self.log(f"❌ PNG Export Fehler: {e}")
            QMessageBox.warning(self, 'Export Error', f'PNG Export Fehler:\n{str(e)}')

    def on_png_export_progress(self, progress, message):
        """Handle PNG export progress"""

        #self.status_label.setText(message)

        if progress % 100 == 0:  # Log every 100 frames

            self.log(message)
    def on_png_export_complete(self, success, message, total_frames):

        """Handle PNG export completion"""
        self.png_exporter = None
        self.export_png_sequence_btn.setEnabled(True)
        self.export_png_sequence_btn.setText('🎬 Export PNG Alpha Sequence')
        if success:
            #self.log(f"✅ PNG Alpha Sequence exported successfully!")
            self.log(f"📊 Total frames: {total_frames}")
            self.log("✅ PNG sequence exported successfully")
            completion_msg = (f'🎬 PNG Alpha Sequence exported successfully!\n\n'
                            f'📁 Location: {message}\n'
                            f'📊 Total frames: {total_frames}\n'
                            f'🎞️ Ready for Adobe Premiere Pro!\n\n'
                            f'In Premiere: File → Import → Select first PNG → Check "Image Sequence"')
            QMessageBox.information(self, 'Export Complete', completion_msg)
        else:
            #self.log(f"❌ PNG export failed: {message}")
            self.log("❌ PNG export failed")
            QMessageBox.critical(self, 'Export Failed', f'❌ PNG Export failed:\n\n{message}')
    # ===== FONT SELECTION =====

    def get_current_settings(self):
        """Extract current settings from UI widgets - FIXED with proper template handling"""
        try:
            # Bitrate handling
            bitrate_widget = self.bitrate_combo
            if hasattr(bitrate_widget, 'currentData'):
                bitrate_data = bitrate_widget.currentData()
                
                # Keep string values as strings (opencv, prores)
                # Only convert numeric strings to int
                if isinstance(bitrate_data, str):
                    if bitrate_data in ['opencv', 'prores']:
                        bitrate_value = bitrate_data
                    elif bitrate_data.isdigit():
                        bitrate_value = int(bitrate_data)
                    else:
                        bitrate_value = 60  # Fallback
                else:
                    bitrate_value = bitrate_data
            else:
                bitrate_value = 60

            # Resolution
            resolution_widget = self.resolution_combo
            if hasattr(resolution_widget, 'currentData'):
                resolution = resolution_widget.currentData()
            else:
                resolution = (1920, 1080)
            
            # Get template selections - FIXED
            fps_template = None
            frametime_template = None
            frametime_scale = {'min': 16.7, 'mid': 33.3, 'max': 50.0, 'labels': ['16.7', '33.3', '50.0']}  # Default

            if hasattr(self, 'fps_graph_combo'):
                fps_data = self.fps_graph_combo.currentData()
                fps_template = fps_data
            
            if hasattr(self, 'frametime_combo'):
                ft_data = self.frametime_combo.currentData()
                frametime_template = ft_data
                
                # FIXED: Extract scale data properly and ensure labels exist
                if ft_data and isinstance(ft_data, dict) and 'scale' in ft_data:
                    frametime_scale = ft_data['scale']
                    # Ensure labels exist
                    if 'labels' not in frametime_scale:
                        ft_min = frametime_scale.get('min', 16.7)
                        ft_mid = frametime_scale.get('mid', 33.3)
                        ft_max = frametime_scale.get('max', 50.0)
                        frametime_scale['labels'] = [f"{ft_min:.1f}", f"{ft_mid:.1f}", f"{ft_max:.1f}"]

            # Detection sensitivity
            sensitivity_widget = self.sensitivity_combo
            if hasattr(sensitivity_widget, 'currentData'):
                diff_threshold = sensitivity_widget.currentData()
            else:
                diff_threshold = 0.002

            # Get baseline FPS with detailed logging
            baseline_fps = 0
            try:
                if hasattr(self, 'baseline_fps_combo'):
                    baseline_fps = self.baseline_fps_combo.currentData()
                    current_text = self.baseline_fps_combo.currentText()
                    self.log(f"🎮 Baseline FPS: {current_text} ({baseline_fps} fps)")
            except Exception as e:
                self.log(f"⚠️ Could not get baseline FPS: {e}")
                baseline_fps = 0

            settings = {
                'resolution': resolution,
                'bitrate': bitrate_value,
                'use_cuda': self.settings_manager.load_settings().get('use_cuda', False) and self.cuda_available,
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
                },
                'layout_config': self.layout_manager.convert_to_overlay_positions(
                    self.layout_manager.get_current_layout(),
                    resolution[0],
                    resolution[1]
                ),
                'start_frame': self.start_frame,
                'end_frame': self.end_frame,
                'fps_graph_template': fps_template,
                'frametime_template': frametime_template,
                'baseline_fps': baseline_fps,
                'overlay_style': getattr(self, 'overlay_style', {}) or {},
                'fade_detection': getattr(self, 'fade_detection_enabled', False),
                'fade_buffer_ms': getattr(self, 'fade_buffer_ms', 2000),
                'save_analysis_data': getattr(self, 'save_analysis_data', False),
                'deviation_marker': getattr(self, 'deviation_marker', False),
                'stats_panel_config': getattr(self, 'stats_panel_config', None),
                'source_fps': getattr(self, 'video_fps', 60.0) or 60.0,
                'deviation_marker_hold_ms': getattr(self, 'deviation_marker_hold_ms', 150),
                'fps_line_thickness': getattr(self, 'fps_line_thickness', None),
                'graph_smooth_window': getattr(self, 'graph_smooth_window', 1),
                'fps_update_interval': getattr(self, 'fps_update_interval_setting', None)
            }

            # Debug print
            
            # Save current settings for next session
            self.save_current_settings()
            return settings
            
        except Exception as e:
            self.log(f"❌ Error extracting settings: {e}")
            return self.get_fallback_settings()

    def get_fallback_settings(self):

        """Fallback settings when extraction fails"""
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
            },
            'layout_config': self.layout_manager.convert_to_overlay_positions(
                self.layout_manager.get_default_layout(),
                1920, 1080
            ),
            'start_frame': None,
            'end_frame': None
        }
    # ===== VIDEO HANDLING =====

    def browse_input(self):
        """Browse for input video file"""

        file_path, _ = QFileDialog.getOpenFileNames(

            self, 'Select Input Video', '', 

            'Video Files (*.mp4 *.mov *.avi *.mkv *.m4v *.webm);;All Files (*)')
        if file_path:

            file_path = file_path[0]  # Take first file

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
        """Load video for preview - ERWEITERT mit Segment Support"""

        try:

            self.log(f"📹 Loading video: {os.path.basename(file_path)}")
            # Laufenden Vorschau-Thread des alten Videos beenden, bevor das
            # Capture freigegeben wird
            if getattr(self, 'preview_seeker', None) is not None:
                try:
                    self.preview_seeker.stop()
                except Exception:
                    pass
                self.preview_seeker = None
            self._pending_seek_frame = None
            self._last_preview_frame = None
            if self.video_cap:

                self.video_cap.release()
            if not os.path.exists(file_path):

                raise ValueError(f"File not found: {file_path}")
            file_size = os.path.getsize(file_path) / (1024*1024)

            self.log(f"📊 File size: {file_size:.1f} MB")
            # ⚡ Performance info for large files

            if file_size > 10000:  # > 10 GB
                self.log("⚠️ Large file detected - playback may be slow due to high resolution/bitrate")
                self.log("💡 Tip: Use segment selection to focus on specific parts for better performance")
            video_info = self.get_video_info(file_path)

            if video_info:

                aspect_ratio = video_info['width'] / video_info['height']

                self.log(f"📺 Video: {video_info['width']}x{video_info['height']} (AR: {aspect_ratio:.2f}), "
                         f"{video_info['fps']:.2f} fps, {video_info['frame_count']} frames")
                # ⚡ Performance warnings for high resolution videos
                if video_info['width'] >= 3840:  # 4K or higher
                    self.log("⚠️ 4K+ resolution detected - playback may be slow")

                # 🎯 NEW: Store video properties for segment calculations

                self.total_frames = video_info['frame_count']
                self.video_fps = video_info['fps']
            self.video_cap = cv2.VideoCapture(file_path)

            if not self.video_cap.isOpened():
                raise ValueError("Could not open video file")
            frame_count = int(self.video_cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # Absichern: total_frames/video_fps werden oben nur gesetzt, wenn
            # die Video-Info gelesen werden konnte. Die Zeitanzeige braucht
            # beide Werte, deshalb hier notfalls aus dem Capture nachziehen.
            if not getattr(self, 'total_frames', 0):
                self.total_frames = frame_count
            if not getattr(self, 'video_fps', 0):
                _f = self.video_cap.get(cv2.CAP_PROP_FPS)
                self.video_fps = _f if _f and _f > 0 else 0

            self.timeline_slider.setMaximum(frame_count - 1)
            self.timeline_slider.setEnabled(True)
            self.timeline_slider.setValue(0)
            self.update_timeline_time(0)

            # Vorschau-Thread für dieses Video starten
            self.preview_seeker = PreviewSeeker(file_path, self)
            self.preview_seeker.frameReady.connect(self.on_preview_frame)
            self.preview_seeker.start()
            self.play_button.setEnabled(True)
            # 🎯 NEW: Enable segment controls when video is loaded + CLEAR PREVIOUS SEGMENTS

            self.clear_selection()  # Clear any previous segments from other videos
            self.enable_segment_controls(True)
            ret, frame = self.video_cap.read()

            if ret:

                self.display_frame(frame)
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            # 🎯 NEW: Update segment display for new video

            self.update_segment_display()
            self.update_segment_buttons()
            #self.status_label.setText(f"✓ Video loaded: {os.path.basename(file_path)} - Segment controls enabled")
        except Exception as e:
            error_msg = f'Could not load video: {str(e)}'
            QMessageBox.warning(self, 'Video Load Error', error_msg)
            self.log(f"✗ ERROR: {error_msg}")
            self.log("✗ Error loading video")
            # 🎯 NEW: Disable segment controls on error

            self.enable_segment_controls(False)
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
    def current_preview_frame(self):
        """
        Aktuell gewählte Frame-Position.

        Einzige Quelle der Wahrheit ist der Timeline-Slider, NICHT
        `video_cap.get(CAP_PROP_POS_FRAMES)`. Seit das Scrubben im
        Hintergrund läuft, wird das Haupt-Capture beim Klicken bewusst nicht
        mehr bewegt — es steht dann noch auf der alten Position. Wer von dort
        liest, bekommt einen veralteten Wert (typisch: 0), und darauf ist die
        Segment-Auswahl hereingefallen.
        """
        try:
            v = int(self.timeline_slider.value())
        except Exception:
            v = 0
        total = int(getattr(self, 'total_frames', 0) or 0)
        if total > 0:
            v = min(v, total - 1)
        return max(0, v)

    def display_frame(self, frame):
        """Display frame with dynamic scaling and aspect ratio preservation"""

        try:
            # Für Neuzeichnen (z.B. Fenstergröße) merken — spart einen
            # kompletten Seek, der sonst je Resize-Event anfiele.
            self._last_preview_frame = frame

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
            # Beim Scrubben wird die Position des Haupt-Captures bewusst NICHT
            # gesetzt (das ist der teure Seek). Hier ist er unvermeidbar, aber
            # er fällt nur einmal beim Start der Wiedergabe an.
            _pend = getattr(self, '_pending_seek_frame', None)
            if _pend is not None:
                self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, _pend)
                self._pending_seek_frame = None
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
            self.update_timeline_time(current_frame)
            self.display_frame(frame)
        else:
            self.toggle_playback()
    def update_timeline_time(self, frame_number=None):
        """
        Zeitanzeige neben der Timeline aktualisieren:
        Position / Gesamtlänge sowie die Framenummer.
        """
        lbl = getattr(self, 'timeline_time_label', None)
        if lbl is None:
            return
        try:
            from ui_manager import format_timecode
            total = int(getattr(self, 'total_frames', 0) or 0)
            fps = float(getattr(self, 'video_fps', 0) or 0)
            if total <= 0 or fps <= 0:
                lbl.setText("--:-- / --:--")
                return
            if frame_number is None:
                frame_number = self.timeline_slider.value()
            frame_number = max(0, min(int(frame_number), total - 1))
            lbl.setText(f"{format_timecode(frame_number, fps)} / "
                        f"{format_timecode(total, fps)}   "
                        f"[{frame_number} / {total - 1}]")
        except Exception:
            pass

    def scrub_video(self, frame_number):

        """
        Vorschau an eine Position setzen — ohne den UI-Thread zu blockieren.

        Die Zeitanzeige wird sofort aktualisiert (kostet nichts), das
        eigentliche Suchen übernimmt der PreviewSeeker im Hintergrund.
        Die Position des Haupt-Captures wird NICHT hier gesetzt: genau das
        war der teure Teil. Sie wird erst nachgezogen, wenn die Wiedergabe
        gestartet wird (siehe toggle_playback).
        """
        self._pending_seek_frame = int(frame_number)
        self.update_timeline_time(frame_number)
        if getattr(self, 'preview_seeker', None) is not None:
            self.preview_seeker.request(frame_number)
        elif self.video_cap:
            # Fallback, falls der Seeker nicht laufen sollte
            self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ret, frame = self.video_cap.read()
            if ret:
                self.display_frame(frame)

    def on_preview_frame(self, frame_number, frame):
        """Ergebnis des Hintergrund-Seeks anzeigen (läuft im UI-Thread)."""
        try:
            self.display_frame(frame)
        except Exception as e:
            print(f"⚠️ Vorschau konnte nicht angezeigt werden: {e}")
    # ===== FPS ANALYSIS =====

    def toggle_analysis(self):
        """Start or stop FPS analysis - ERWEITERT mit Segment Support"""

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
            self.log("❌ Analysis cancelled")
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
        # 🎯 NEW: Segment validation and confirmation

        segment_mode = False
        if self.start_frame is not None or self.end_frame is not None:

            # Validate complete segment selection

            if self.start_frame is None:

                QMessageBox.warning(self, 'Incomplete Selection', 
                                   'Please set a start point or clear the selection to analyze the full video.')
                return
            if self.end_frame is None:

                QMessageBox.warning(self, 'Incomplete Selection', 
                                   'Please set an end point or clear the selection to analyze the full video.')
                return
            # Calculate segment info

            duration_frames = self.end_frame - self.start_frame
            duration_time = self.frame_to_time_string(duration_frames)
            percentage = (duration_frames / self.total_frames * 100) if self.total_frames > 0 else 0
            # Ask for confirmation

            reply = QMessageBox.question(self, 'Segment Analysis', 
                                       f'🎯 Analyze selected segment only?\n\n'
                                       f'📍 Start: {self.frame_to_time_string(self.start_frame)}\n'
                                       f'📍 End: {self.frame_to_time_string(self.end_frame)}\n'
                                       f'⏱️ Duration: {duration_time} ({duration_frames} frames)\n'
                                       f'📊 Percentage: {percentage:.1f}% of total video\n\n'
                                       f'The output video will contain only this segment.',
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
            segment_mode = True
        # Get settings (this also saves them and includes layout config and segment info)

        settings = self.get_current_settings()
        # Start analysis

        if segment_mode:

            self.log(f"🎯 Starting SEGMENT FPS Analysis...")
            self.log(f"📍 Segment: frames {self.start_frame}-{self.end_frame} ({self.frame_to_time_string(self.end_frame - self.start_frame)})")
        else:
            self.log(f"🎯 Starting FULL FPS Analysis...")
        self.log(f"📊 Settings: {settings['resolution']}, {settings['bitrate']}")
        # 🎯 NEW: Pass segment info to AnalysisWorker

        # Fallback: add segment info to settings

        settings['segment_start_frame'] = self.start_frame
        settings['segment_end_frame'] = self.end_frame

        self.analysis_worker = AnalysisWorker(input_file, output_file, settings)

        # Set segment parameters separately to maintain compatibility

        if hasattr(self.analysis_worker, 'set_segment_range'):

            self.analysis_worker.set_segment_range(self.start_frame, self.end_frame)
        else:
            # Fallback: add segment info to settings

            settings['segment_start_frame'] = self.start_frame
            settings['segment_end_frame'] = self.end_frame
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
        if segment_mode:
            self.log("🚀 Starting segment analysis...")
        else:
            self.log("🚀 Starting full analysis...")
        self.analysis_worker.start()
    def encode_from_data(self):
        """Lädt gespeicherte Analyse-Daten (.fpsdata) und encodet OHNE Neuanalyse."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        import json, os

        if self.analysis_worker and self.analysis_worker.isRunning():
            QMessageBox.warning(self, "Läuft bereits", "Es läuft bereits eine Analyse.")
            return

        data_path, _ = QFileDialog.getOpenFileName(
            self, "Analyse-Daten laden", "", "FPS-Daten (*.fpsdata)")
        if not data_path:
            return

        try:
            with open(data_path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Daten konnten nicht gelesen werden:\n{e}")
            return

        source_video = data.get('source_video')
        if not source_video or not os.path.exists(source_video):
            # Original-Video manuell wählen falls Pfad nicht stimmt
            QMessageBox.information(self, "Video wählen",
                "Das Originalvideo aus den Daten wurde nicht gefunden.\n"
                "Bitte wähle es manuell aus.")
            source_video, _ = QFileDialog.getOpenFileName(
                self, "Originalvideo wählen", "", "Video (*.mp4 *.mkv *.avi *.mov)")
            if not source_video:
                return

        output_file, _ = QFileDialog.getSaveFileName(
            self, "Ausgabe speichern", "", "Video (*.mp4)")
        if not output_file:
            return

        settings = self.get_current_settings()
        settings['load_analysis_data'] = data_path
        settings['save_analysis_data'] = False   # nicht erneut speichern

        self.analysis_worker = AnalysisWorker(source_video, output_file, settings)
        self.analysis_worker.progress_update.connect(self.on_progress_update)
        self.analysis_worker.frame_preview.connect(self.on_frame_preview)
        self.analysis_worker.analysis_complete.connect(self.on_analysis_complete)

        self.analyze_button.setText('⏹️ Cancel Analysis')
        self.analyze_button.setStyleSheet(
            "font-weight: bold; font-size: 16px; padding: 12px 24px; "
            "background-color: #f44336; color: white; border: none; border-radius: 8px;"
        )
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.log(f"📂 Encode aus Analyse-Daten: {os.path.basename(data_path)} (keine Neuanalyse)")
        self.analysis_worker.start()

    def on_progress_update(self, progress, message):

        """Handle progress updates"""
        self.progress_bar.setValue(progress)
        #self.status_label.setText(message)
        if progress % 10 == 0 or "FPS:" in message or "Layout Applied" in message or "Segment" in message:
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
            mode_str = "segment" if (self.start_frame is not None and self.end_frame is not None) else "full"
            self.log(f"✅ FPS Analysis ({mode_str}) completed successfully!")
            #self.status_label.setText(f"✅ Analysis ({mode_str}) completed successfully")
            output_file = self.output_edit.text()
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file) / (1024*1024)
                if mode_str == "segment":
                    duration_time = self.frame_to_time_string(self.end_frame - self.start_frame)
                    completion_msg = (f'🎉 Segment FPS Analysis completed successfully!\n\n'
                                    f'📁 Output file: {os.path.basename(output_file)}\n'
                                    f'📊 File size: {file_size:.1f} MB\n'
                                    f'🎯 Analyzed segment: {duration_time}\n'
                                    f'🎨 Custom layout applied\n\n'
                                    f'The analyzed video contains only the selected segment!')
                else:
                    completion_msg = (f'🎉 FPS Analysis completed successfully!\n\n'
                                    f'📁 Output file: {os.path.basename(output_file)}\n'
                                    f'📊 File size: {file_size:.1f} MB\n'
                                    f'🎨 Custom layout applied\n\n'
                                    f'The analyzed video is ready to use!')
                QMessageBox.information(self, 'Analysis Complete', completion_msg)
        else:
            self.log(f"❌ Analysis failed: {message}")
            #self.status_label.setText("❌ Analysis failed")
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
        if getattr(self, 'preview_seeker', None) is not None:
            try:
                self.preview_seeker.stop()
            except Exception:
                pass
            self.preview_seeker = None
        if self.video_cap:
            self.video_cap.release()
        event.accept()
# ===== APPLICATION SETUP =====
def check_dependencies():
    """Check required dependencies"""

    missing_deps = []
    try:

        pass


    except ImportError:

        missing_deps.append("opencv-python")
    try:

        import torch


        if torch.cuda.is_available():
            pass  # CUDA available — logged by cuda_accelerator module
        else:
            print("⚠️ CUDA not available - will use CPU")

    except ImportError:

        missing_deps.append("torch")
    try:

        pass


    except ImportError:

        missing_deps.append("numpy")
    return len(missing_deps) == 0, missing_deps
def main():

    """🚀 ENHANCED: Main application entry point with TrueType status"""
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
    # Font is hardcoded to Bebas Neue via truetype_core
    freetype_status = "✅ Bebas Neue (hardcoded)"
    system_fonts = 1
    # Create and show main window

    window = FPSAnalyzer()
    window.show()
    # Enhanced success messages

    # Run application

    sys.exit(app.exec())
if __name__ == '__main__':
    main()
