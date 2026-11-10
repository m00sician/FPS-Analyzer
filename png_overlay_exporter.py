"""
PNG Overlay Exporter für FPS Analyzer
Exportiert eine transparente PNG-Sequenz des Overlays.

Basiert komplett auf dem aktuellen analysis_worker.py Loop —
gleiche PairDiff-Erkennung, gleiche FPS-Berechnung, gleiche Render-Pipeline.
Einziger Unterschied: Output ist PNG statt MP4, gerendert auf schwarzem Canvas
mit Alpha-Extraktion statt Video-Encoding.
"""
import os
import shutil
import collections
import queue
import threading

import cv2
import numpy as np

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QProgressBar, QFileDialog, QMessageBox)

from analysis_worker import (AnalysisWorker, AsyncFrameReader,
                              resize_with_aspect_ratio, IncrementalStats)


class PNGExportWorker(AnalysisWorker):
    """
    PNG-Export Worker — erbt die komplette Analyse-Engine von AnalysisWorker.
    Überschreibt nur den Output-Teil: statt in einen VideoWriter zu schreiben,
    wird jeder fertige Frame als RGBA-PNG in einen Unterordner gespeichert.
    """

    def __init__(self, input_file, output_dir, settings):
        # Parent braucht einen output_file Pfad — wir geben einen Dummy
        fake_output = os.path.join(output_dir, "_dummy.mp4")
        super().__init__(input_file, fake_output, settings)
        self.png_output_dir = output_dir

        # PNG-Worker-Queue: (frame_index, rgba_array)
        self._png_queue = queue.Queue(maxsize=60)
        self._png_workers = []
        self._png_export_done = False
        self.frames_exported = 0

    # ------------------------------------------------------------------
    # PNG Worker Threads
    # ------------------------------------------------------------------

    def _start_png_workers(self, n=4):
        for _ in range(n):
            t = threading.Thread(target=self._png_worker, daemon=True)
            t.start()
            self._png_workers.append(t)

    def _png_worker(self):
        while not self._png_export_done or not self._png_queue.empty():
            try:
                item = self._png_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is None:
                self._png_queue.task_done()
                break
            frame_idx, rgba = item
            path = os.path.join(self.png_output_dir, f"overlay_{frame_idx:06d}.png")
            bgra = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)
            cv2.imwrite(path, bgra, [cv2.IMWRITE_PNG_COMPRESSION, 6])
            self.frames_exported += 1
            self._png_queue.task_done()

    # ------------------------------------------------------------------
    # Alpha extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_alpha(overlay_rgb: np.ndarray) -> np.ndarray:
        """
        Konvertiert ein RGB-Overlay (auf schwarzem Hintergrund gerendert)
        zu RGBA mit korrektem Alpha-Kanal.

        Schwarz (0,0,0) → vollständig transparent.
        Alles andere → opak, proportional zur Helligkeit.

        Das ist korrekt weil der Renderer auf einem schwarzen Canvas arbeitet
        und nur die eigentlichen Overlay-Elemente zeichnet.
        """
        gray = cv2.cvtColor(overlay_rgb, cv2.COLOR_RGB2GRAY)
        rgba = np.zeros((*overlay_rgb.shape[:2], 4), dtype=np.uint8)
        rgba[:, :, :3] = overlay_rgb
        # Alpha proportional zur Helligkeit — reine schwarze Pixel = 0
        rgba[:, :, 3] = gray
        return rgba

    # ------------------------------------------------------------------
    # Main analyze_video override
    # ------------------------------------------------------------------

    def analyze_video(self):
        """
        Identischer Loop wie AnalysisWorker.analyze_video, aber:
        - Kein VideoWriter
        - Rendert auf schwarzem Canvas statt auf dem Video-Frame
        - Extrahiert Alpha und speichert als PNG
        """
        try:
            print("🎬 PNG Export: Starting...")
            self._start_png_workers(n=min(4, os.cpu_count() or 4))
            print(f"🚀 PNG Export: {len(self._png_workers)} worker threads started")

            # --- Video öffnen ---
            cap = cv2.VideoCapture(self.input_file)
            if not cap.isOpened():
                raise ValueError(f"Could not open video: {self.input_file}")

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            source_fps   = cap.get(cv2.CAP_PROP_FPS)
            print(f"📹 {total_frames} frames @ {source_fps} fps")

            # Segment
            actual_start = self.start_frame or 0
            actual_end   = self.end_frame   or total_frames
            segment_frames = actual_end - actual_start

            cap.set(cv2.CAP_PROP_POS_FRAMES, actual_start)

            # --- Baseline / Initial FPS ---
            baseline_fps = self.settings.get('baseline_fps', 0)
            initial_fps  = float(baseline_fps) if baseline_fps > 0 else source_fps
            initial_ft   = 1000.0 / initial_fps if initial_fps > 0 else 33.33

            # --- Auflösung ---
            target_width, target_height = self.settings.get('resolution', (1920, 1080))
            print(f"🎯 Target: {target_width}x{target_height}")

            # --- Analyse-Variablen (identisch mit analyze_video) ---
            fps_history  = collections.deque(maxlen=1000)
            frame_times  = collections.deque(maxlen=180)
            for _ in range(60):
                fps_history.append(initial_fps)
                frame_times.append(initial_ft)

            fps_stats       = IncrementalStats(warmup_frames=60)
            frametime_stats = IncrementalStats(warmup_frames=60)
            global_fps_values  = collections.deque(maxlen=300)
            global_frame_times = collections.deque(maxlen=300)

            displayed_fps        = initial_fps
            fps_update_counter   = 0
            fps_update_interval  = max(15, int(source_fps / 4))
            fps_calc_window      = collections.deque(maxlen=30)

            prev_frame_gray      = None
            frame_count          = 0
            current_frame_number = actual_start

            # --- Overlay-Einstellungen (einmalig lesen) ---
            show_frametime  = self.settings.get('show_frametime', True)
            frametime_scale = self.settings.get('frametime_scale', {
                'min': 16.7, 'mid': 33.3, 'max': 50.0,
                'labels': ['16.7', '33.3', '50.0']
            })
            font_settings  = self.settings.get('font_settings', {})
            color_settings = self.settings.get('color_settings', {
                'framerate_color': '#00FF00',
                'frametime_color': '#00FF00'
            })

            self.progress_update.emit(5, "Analysing video...")
            frame_reader = AsyncFrameReader(cap)

            # ----------------------------------------------------------
            # Haupt-Loop
            # ----------------------------------------------------------
            while current_frame_number < actual_end:
                if self.is_cancelled:
                    break

                ret, frame = frame_reader.next_frame()
                if not ret:
                    break

                # Resize für Overlay-Dimensionen
                frame_processed = resize_with_aspect_ratio(frame, target_width, target_height)

                # Graustufen für Duplikat-Erkennung
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # PairDiff-Erkennung (aus AnalysisWorker)
                is_duplicate = self.is_frame_duplicate_corrected(gray, prev_frame_gray)
                self.detection_window.append(not is_duplicate)

                # FPS-Berechnung (Rolling Window)
                win = len(self.detection_window)
                if win >= 4:
                    effective_fps = (sum(self.detection_window) / win) * source_fps
                    effective_fps = max(0.0, min(effective_fps, source_fps))
                else:
                    effective_fps = getattr(self, '_last_effective_fps', source_fps)
                self._last_effective_fps = effective_fps

                current_frame_time = 1000.0 / effective_fps if effective_fps > 0 else 1000.0

                # Stats
                stats_ready = (
                    frame_count > 60
                    and 1.0 < effective_fps <= source_fps * 1.05
                    and 0.5 < current_frame_time < 2000.0
                )
                if stats_ready:
                    fps_stats.update(effective_fps)
                    frametime_stats.update(current_frame_time)
                    global_fps_values.append(effective_fps)
                    global_frame_times.append(current_frame_time)

                fps_history.append(effective_fps)
                frame_times.append(current_frame_time)

                # Displayed FPS (hysterese)
                fps_calc_window.append(effective_fps)
                fps_update_counter += 1
                if fps_update_counter >= fps_update_interval:
                    displayed_fps = round(
                        sum(fps_calc_window) / len(fps_calc_window)
                    ) if fps_calc_window else displayed_fps
                    fps_update_counter = 0

                if frame_count <= 60:
                    displayed_fps = -1

                # --- Overlay auf schwarzem Canvas rendern ---
                black_canvas = np.zeros((target_height, target_width, 3), dtype=np.uint8)

                precomputed_stats = {
                    'fps':       fps_stats.get_stats(),
                    'frametime': frametime_stats.get_stats()
                }

                overlay_rgb = self.create_overlay(
                    black_canvas, fps_history, displayed_fps, frame_times,
                    show_frametime, global_fps_values, global_frame_times,
                    frametime_scale, font_settings, color_settings,
                    precomputed_stats
                )

                # Alpha extrahieren und in Queue
                rgba = self._extract_alpha(overlay_rgb)
                try:
                    self._png_queue.put((frame_count, rgba), timeout=5.0)
                except queue.Full:
                    self._png_queue.put((frame_count, rgba))

                prev_frame_gray      = gray
                frame_count         += 1
                current_frame_number += 1

                if frame_count % 30 == 0:
                    progress = 10 + int((frame_count / segment_frames) * 80)
                    self.progress_update.emit(
                        progress,
                        f"Frame {frame_count}/{segment_frames} | "
                        f"Saved: {self.frames_exported}"
                    )

            # ----------------------------------------------------------
            # Cleanup
            # ----------------------------------------------------------
            cap.release()

            self.progress_update.emit(92, "Waiting for PNG writers to finish...")
            self._png_export_done = True
            self._png_queue.join()
            for t in self._png_workers:
                t.join(timeout=10.0)

            if self.is_cancelled:
                self.analysis_complete.emit(False, "Export cancelled")
            else:
                msg = f"Exported {self.frames_exported} PNG frames to:\n{self.png_output_dir}"
                self.progress_update.emit(100, f"✅ Done — {self.frames_exported} frames")
                self.analysis_complete.emit(True, msg)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.analysis_complete.emit(False, f"Export failed: {e}")


# ----------------------------------------------------------------------
# Dialog
# ----------------------------------------------------------------------

class PNGExportDialog(QDialog):

    def __init__(self, parent, video_path, settings):
        super().__init__(parent)
        self.parent_window = parent
        self.video_path    = video_path
        self.settings      = settings
        self.worker        = None

        self.setWindowTitle("🎬 PNG Overlay Export")
        self.setModal(True)
        self.resize(560, 320)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(self._label(
            "🎬 PNG Overlay Export",
            "font-weight: bold; font-size: 15px; padding: 8px;"
        ))
        layout.addWidget(self._label(
            "Exportiert eine transparente PNG-Sequenz des Overlays.\n"
            "Jedes PNG enthält nur das Overlay mit Alpha-Kanal — kein Videobild.",
            "color: #aaa; padding: 6px;"
        ))
        layout.addWidget(self._label(
            f"📹 {os.path.basename(self.video_path)}",
            "padding: 4px; font-weight: bold;"
        ))

        res = self.settings.get('resolution', (1920, 1080))
        layout.addWidget(self._label(
            f"⚙️ Auflösung: {res[0]}×{res[1]}  |  "
            f"Threads: {min(4, os.cpu_count() or 4)}",
            "color: #888; padding: 4px;"
        ))

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("padding: 4px; font-family: monospace;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()

        self.start_btn = QPushButton("🚀 Export starten")
        self.start_btn.clicked.connect(self._start)
        self.start_btn.setStyleSheet("""
            QPushButton {
                font-weight: bold; font-size: 13px; padding: 9px 24px;
                background-color: #4CAF50; color: white;
                border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #66BB6A; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        btn_row.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("⏹ Abbrechen")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 9px 18px; background-color: #c0392b;
                color: white; border: none; border-radius: 6px;
            }
            QPushButton:hover { background-color: #e74c3c; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        btn_row.addWidget(self.cancel_btn)

        close_btn = QPushButton("Schließen")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    @staticmethod
    def _label(text, style=""):
        lbl = QLabel(text)
        if style:
            lbl.setStyleSheet(style)
        return lbl

    # ------------------------------------------------------------------

    def _start(self):
        output_dir = QFileDialog.getExistingDirectory(
            self, "PNG-Sequenz Speicherort",
            os.path.dirname(self.video_path)
        )
        if not output_dir:
            return

        video_stem    = os.path.splitext(os.path.basename(self.video_path))[0]
        sequence_dir  = os.path.join(output_dir, f"{video_stem}_overlay_png")

        if os.path.exists(sequence_dir):
            reply = QMessageBox.question(
                self, "Ordner existiert",
                f"Ordner existiert bereits:\n{sequence_dir}\n\nÜberschreiben?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
            shutil.rmtree(sequence_dir)

        os.makedirs(sequence_dir)

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting...")

        self.worker = PNGExportWorker(self.video_path, sequence_dir, self.settings)
        self.worker.progress_update.connect(self._on_progress)
        self.worker.analysis_complete.connect(self._on_complete)
        self.worker.frame_preview.connect(lambda _: None)  # unused but required
        self.worker.start()

    def _cancel(self):
        if self.worker:
            self.worker.cancel()
            self.status_label.setText("Cancelling...")

    def _on_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)

    def _on_complete(self, success, message):
        self.worker = None
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(100 if success else 0)

        if success:
            self.status_label.setText("✅ Export complete")
            QMessageBox.information(
                self, "Export erfolgreich", message + "\n\n"
                "Import in Premiere Pro / DaVinci Resolve:\n"
                "• Erste PNG auswählen → Image Sequence aktivieren\n"
                "• Blend Mode: Screen oder Normal mit Alpha"
            )
        else:
            self.status_label.setText(f"❌ {message}")
            if "cancelled" not in message.lower():
                QMessageBox.warning(self, "Export Fehler", message)


# ----------------------------------------------------------------------
# Einstiegspunkt (wird von fps_analyzer_main.py aufgerufen)
# ----------------------------------------------------------------------

def export_png_overlay_sequence(parent_window):
    video_path = parent_window.input_edit.text().strip()
    if not video_path or not os.path.exists(video_path):
        QMessageBox.warning(parent_window, "Fehler", "Bitte zuerst ein Video laden.")
        return
    settings = parent_window.get_current_settings()
    dialog = PNGExportDialog(parent_window, video_path, settings)
    dialog.exec()
