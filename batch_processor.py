"""
Batch Processor für FPS Analyzer
Handles multiple video analysis in sequence with queue management
"""
import os
import time
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QListWidget, QListWidgetItem, QProgressBar, QFileDialog, 
                             QMessageBox, QGroupBox, QGridLayout, QTextEdit, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from analysis_worker import AnalysisWorker


class BatchItem:
    """Represents a single item in the batch queue"""

    def __init__(self, input_path, output_path=None):
        self.input_path = input_path
        self.output_path = output_path or self.generate_output_path(input_path)
        self.status = "Waiting"  # Waiting, Processing, Completed, Failed
        self.progress = 0
        self.start_time = None
        self.end_time = None

    def generate_output_path(self, input_path):
        """Generate output path based on input path"""
        path_obj = Path(input_path)
        return str(path_obj.parent / f"{path_obj.stem}_fps_analysis.mp4")

    def get_duration_text(self):
        """Get duration text for completed items"""
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            return f"{minutes}m {seconds}s"
        return "N/A"

    def get_duration_seconds(self):
        """Get duration in seconds for completed items"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0


class BatchProcessorThread(QThread):
    """Thread for processing batch queue"""
    item_started = pyqtSignal(int)  # item index
    item_progress = pyqtSignal(int, int, str)  # item index, progress, message
    item_completed = pyqtSignal(int, bool, str)  # item index, success, message
    batch_completed = pyqtSignal()
    frame_preview = pyqtSignal(object)  # BGR-Frame für die Live-Vorschau

    def __init__(self, batch_items, settings):
        super().__init__()
        self.batch_items = batch_items
        self.settings = settings
        self.is_cancelled = False
        self.current_worker = None

    def cancel(self):
        """Cancel the batch processing"""
        self.is_cancelled = True
        if self.current_worker:
            self.current_worker.cancel()

    def run(self):
        """Process all items in the batch"""
        for i, item in enumerate(self.batch_items):
            if self.is_cancelled:
                break

            # Update item status
            item.status = "Processing"
            item.start_time = time.time()
            self.item_started.emit(i)

            # Create worker for this item
            self.current_worker = AnalysisWorker(item.input_path, item.output_path, self.settings)
            # Worker legt Vorschau-Frames in ein Attribut (Timer im Dialog liest es)
            self.current_worker._latest_preview = None
            def _stash_preview(fb, wk=self.current_worker):
                wk._latest_preview = fb
            try:
                self.current_worker.frame_preview.connect(_stash_preview)
            except Exception:
                pass

            # Connect signals — capture idx in default arg to avoid closure bug

            def on_progress(progress, message, idx=i):
                self.item_progress.emit(idx, progress, message)
            self.current_worker.progress_update.connect(on_progress)

            # Process item
            success = False
            error_message = ""
            try:
                self.current_worker.analyze_video()
                success = True
                item.status = "Completed"
            except Exception as e:
                error_message = str(e)
                item.status = "Failed"

            # Update completion
            item.end_time = time.time()
            self.item_completed.emit(i, success, error_message)
            if self.is_cancelled:
                break
        self.batch_completed.emit()


class BatchProcessorDialog(QDialog):
    """Dialog for batch processing multiple videos"""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_analyzer = parent
        self.setWindowTitle("📁 Batch Processor - Multiple Video Analysis")
        self.setModal(True)
        self.resize(1200, 800)

        # Batch data
        self.batch_items = []
        self.processor_thread = None
        self.is_processing = False

        # Timer for UI updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_ui)
        self.update_timer.start(500)  # Update every 500ms
        self.setup_ui()
        self.apply_theme()

    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("📁 Batch Encoder - Process Multiple Videos")
        title_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 5px; font-size: 16px;")
        layout.addWidget(title_label)

        # Create splitter for left/right layout
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - File queue
        left_widget = self.create_file_queue_widget()
        splitter.addWidget(left_widget)

        # Right side - Settings and controls
        right_widget = self.create_settings_widget()
        splitter.addWidget(right_widget)

        # Set splitter proportions (70% left, 30% right)
        splitter.setSizes([840, 360])
        layout.addWidget(splitter)

        # Bottom status and controls
        bottom_layout = self.create_bottom_controls()
        layout.addLayout(bottom_layout)

    def create_file_queue_widget(self):
        """Create the file queue widget"""
        queue_widget = QGroupBox("📋 Processing Queue")
        layout = QVBoxLayout(queue_widget)

        # File list
        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(400)
        self.file_list.setStyleSheet("""
            QListWidget {
                background-color: #2a2a2a;
                border: 2px solid #555;
                border-radius: 5px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #444;
            }
            QListWidget::item:selected {
                background-color: #4CAF50;
            }
        """)
        layout.addWidget(self.file_list)

        # File management buttons
        file_buttons_layout = QHBoxLayout()
        self.select_videos_btn = QPushButton("📁 Select Videos")
        self.select_videos_btn.clicked.connect(self.select_videos)
        file_buttons_layout.addWidget(self.select_videos_btn)
        self.select_folder_btn = QPushButton("📂 Select Folder")
        self.select_folder_btn.clicked.connect(self.select_folder)
        file_buttons_layout.addWidget(self.select_folder_btn)
        self.remove_selected_btn = QPushButton("🗑️ Remove Selected")
        self.remove_selected_btn.clicked.connect(self.remove_selected)
        file_buttons_layout.addWidget(self.remove_selected_btn)
        self.clear_queue_btn = QPushButton("🚮 Clear All")
        self.clear_queue_btn.clicked.connect(self.clear_queue)
        file_buttons_layout.addWidget(self.clear_queue_btn)
        layout.addLayout(file_buttons_layout)
        return queue_widget

    def create_settings_widget(self):
        """Create the settings widget"""
        settings_widget = QGroupBox("⚙️ Batch Settings")
        layout = QVBoxLayout(settings_widget)

        # Hinweis: alle Encode-Einstellungen kommen aus dem Hauptfenster
        info = QLabel(
            "ℹ️ Der Batch nutzt die Einstellungen aus dem Hauptfenster\n"
            "(Auflösung, Bitrate, Grid-Werte, Layout, Detection, Style).\n"
            "Zum Ändern: Hauptfenster + Layout Editor + Optionen anpassen."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaa; padding: 8px; background: rgba(255,255,255,8); border-radius: 6px;")
        layout.addWidget(info)

        # Live-Preview des aktuell verarbeiteten Frames
        from PyQt6.QtCore import Qt as _Qt
        preview_box = QGroupBox("🎬 Encode-Vorschau")
        pv_layout = QVBoxLayout(preview_box)
        self.preview_label = QLabel("Vorschau erscheint während der Verarbeitung…")
        self.preview_label.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(160)
        self.preview_label.setStyleSheet(
            "background: #111; color: #666; border: 1px solid #333; border-radius: 6px;")
        pv_layout.addWidget(self.preview_label)
        layout.addWidget(preview_box)

        # Queue statistics
        stats_group = QGroupBox("📊 Queue Statistics")
        stats_layout = QGridLayout(stats_group)
        self.total_files_label = QLabel("Total Files: 0")
        self.completed_files_label = QLabel("Completed: 0")
        self.failed_files_label = QLabel("Failed: 0")
        self.estimated_time_label = QLabel("Est. Time: N/A")
        stats_layout.addWidget(self.total_files_label, 0, 0)
        stats_layout.addWidget(self.completed_files_label, 0, 1)
        stats_layout.addWidget(self.failed_files_label, 1, 0)
        stats_layout.addWidget(self.estimated_time_label, 1, 1)
        layout.addWidget(stats_group)

        # Processing log
        log_group = QGroupBox("📝 Processing Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
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
        self.log_text.setPlaceholderText("🔍 Batch processing log will appear here...")
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_group)
        return settings_widget

    def create_bottom_controls(self):
        """Create bottom control buttons"""
        layout = QHBoxLayout()

        # Overall progress bar
        self.overall_progress = QProgressBar()
        self.overall_progress.setVisible(False)
        self.overall_progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid #555;
                border-radius: 8px;
                text-align: center;
                background-color: #3c3c3c;
                color: #ffffff;
                font-weight: bold;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 6px;
            }
        """)
        layout.addWidget(self.overall_progress)

        # Control buttons
        self.start_batch_btn = QPushButton("🚀 Start Batch")
        self.start_batch_btn.setStyleSheet("""
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
        self.start_batch_btn.clicked.connect(self.start_batch)
        layout.addWidget(self.start_batch_btn)
        self.cancel_batch_btn = QPushButton("⏹️ Cancel Batch")
        self.cancel_batch_btn.setStyleSheet("""
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
        self.cancel_batch_btn.clicked.connect(self.cancel_batch)
        self.cancel_batch_btn.setEnabled(False)
        layout.addWidget(self.cancel_batch_btn)
        self.close_btn = QPushButton("✓ Close")
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)
        return layout

    def select_videos(self):
        """Select multiple video files"""
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            'Select Video Files', 
            '', 
            'Video Files (*.mp4 *.mov *.avi *.mkv *.m4v *.webm);;All Files (*)'
        )
        for file_path in files:
            self.add_file_to_queue(file_path)

    def select_folder(self):
        """Select folder and add all video files"""
        folder = QFileDialog.getExistingDirectory(self, 'Select Folder with Videos')
        if folder:
            video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.m4v', '.webm']
            for file_path in sorted(Path(folder).rglob('*')):
                if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                    self.add_file_to_queue(str(file_path))

    def add_file_to_queue(self, file_path):
        """Add a file to the processing queue"""

        # Check if file already exists
        for item in self.batch_items:
            if item.input_path == file_path:
                self.log(f"⚠️ File already in queue: {os.path.basename(file_path)}")
                return

        # Create batch item
        batch_item = BatchItem(file_path)
        self.batch_items.append(batch_item)

        # Add to UI list
        self.update_file_list()
        self.log(f"➕ Added: {os.path.basename(file_path)}")

    def remove_selected(self):
        """Remove selected items from queue"""
        current_row = self.file_list.currentRow()
        if current_row >= 0 and current_row < len(self.batch_items):
            removed_item = self.batch_items.pop(current_row)
            self.log(f"➖ Removed: {os.path.basename(removed_item.input_path)}")
            self.update_file_list()

    def clear_queue(self):
        """Clear all items from queue"""
        if self.batch_items:
            reply = QMessageBox.question(
                self, 'Clear Queue', 
                f'Remove all {len(self.batch_items)} items from queue?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.batch_items.clear()
                self.update_file_list()
                self.log("🚮 Queue cleared")

    def start_batch(self):
        """Start batch processing"""
        if not self.batch_items:
            QMessageBox.warning(self, 'No Files', 'Please add files to the queue first.')
            return

        # ALLE Einstellungen kommen aus dem Hauptfenster — der Batch hat keine
        # eigenen Encode-Settings mehr. Grid-Werte, Auflösung, Bitrate, Layout,
        # Overlay-Style, Detection, Codec: alles über get_current_settings().
        try:
            settings = dict(self.parent_analyzer.get_current_settings())
        except Exception as e:
            print(f"⚠️ Batch: get_current_settings fehlgeschlagen ({e}), nutze Minimal-Settings")
            settings = {}
        settings.setdefault('use_cuda', getattr(self.parent_analyzer, 'cuda_available', False))
        settings.setdefault('show_frametime', True)
        settings.setdefault('ftg_position', getattr(self.parent_analyzer, 'ftg_position', 'bottom_right'))
        settings.setdefault('font_settings', {
            'fps_font': getattr(self.parent_analyzer, 'fps_font_settings', None),
            'framerate_font': getattr(self.parent_analyzer, 'framerate_font_settings', None),
            'frametime_font': getattr(self.parent_analyzer, 'frametime_font_settings', None)
        })
        settings.setdefault('color_settings', {
            'framerate_color': getattr(self.parent_analyzer, 'framerate_color', '#00FF00'),
            'frametime_color': getattr(self.parent_analyzer, 'frametime_color', '#00FF00')
        })

        # Auflösung aus dem Hauptfenster (für Layout-Umrechnung)
        resolution = settings.get('resolution')
        if not resolution and hasattr(self.parent_analyzer, 'resolution_combo'):
            resolution = self.parent_analyzer.resolution_combo.currentData()
        if not resolution:
            resolution = (1920, 1080)
        settings['resolution'] = resolution

        # Layout config — Graph-Positionen für die Batch-Auflösung
        if hasattr(self.parent_analyzer, 'layout_manager'):
            settings['layout_config'] = self.parent_analyzer.layout_manager.convert_to_overlay_positions(
                self.parent_analyzer.layout_manager.get_current_layout(),
                resolution[0],
                resolution[1]
            )

        # Graph templates — ohne diese werden die Graphen nicht gerendert.
        p = self.parent_analyzer
        if hasattr(p, 'fps_graph_combo'):
            settings['fps_graph_template'] = p.fps_graph_combo.currentData()
        if hasattr(p, 'frametime_combo'):
            settings['frametime_template'] = p.frametime_combo.currentData()

        # Start processing thread
        self.processor_thread = BatchProcessorThread(self.batch_items, settings)
        self.processor_thread.item_started.connect(self.on_item_started)
        self.processor_thread.item_progress.connect(self.on_item_progress)
        self.processor_thread.item_completed.connect(self.on_item_completed)
        self.processor_thread.batch_completed.connect(self.on_batch_completed)
        self.processor_thread.start()

        # Update UI
        self.is_processing = True
        self.start_batch_btn.setEnabled(False)
        self.cancel_batch_btn.setEnabled(True)
        self.overall_progress.setVisible(True)
        self.overall_progress.setMaximum(len(self.batch_items))
        self.overall_progress.setValue(0)
        self.log(f"🚀 Started batch processing {len(self.batch_items)} files")

    def cancel_batch(self):
        """Cancel batch processing"""
        if self.processor_thread:
            self.processor_thread.cancel()
            self.log("⏹️ Cancelling batch processing...")

    def on_item_started(self, index):
        """Handle item started signal"""
        item = self.batch_items[index]
        self.log(f"🎯 Processing: {os.path.basename(item.input_path)}")
        self.update_file_list()

    def on_item_progress(self, index, progress, message):
        """Handle item progress signal"""
        item = self.batch_items[index]
        item.progress = progress
        self.update_file_list()

    def on_item_completed(self, index, success, error_message):
        """Handle item completed signal"""
        item = self.batch_items[index]
        if success:
            self.log(f"✅ Completed: {os.path.basename(item.input_path)} ({item.get_duration_text()})")
        else:
            self.log(f"❌ Failed: {os.path.basename(item.input_path)} - {error_message}")

        # Update overall progress
        completed_count = sum(1 for item in self.batch_items if item.status in ["Completed", "Failed"])
        self.overall_progress.setValue(completed_count)
        self.update_file_list()

    def on_frame_preview(self, frame_bgr):
        """Zeigt das aktuell verarbeitete Frame skaliert in der Vorschau."""
        try:
            import cv2, numpy as np
            from PyQt6.QtGui import QImage, QPixmap
            from PyQt6.QtCore import Qt as _Qt
            if frame_bgr is None or not hasattr(frame_bgr, 'shape'):
                return
            # Kopie erzwingen (der numpy-Buffer aus dem Worker-Thread kann
            # nach dem Signal ungültig werden → QImage bräuchte gültigen Speicher)
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            rgb = np.ascontiguousarray(rgb)
            h, w = rgb.shape[:2]
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
            pw = max(1, self.preview_label.width())
            ph = max(1, self.preview_label.height())
            pix = QPixmap.fromImage(qimg).scaled(
                pw, ph,
                _Qt.AspectRatioMode.KeepAspectRatio,
                _Qt.TransformationMode.SmoothTransformation)
            self.preview_label.setText("")
            self.preview_label.setPixmap(pix)
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"Batch-Preview-Fehler: {e}")

    def on_batch_completed(self):
        """Handle batch completion"""
        self.is_processing = False
        self.start_batch_btn.setEnabled(True)
        self.cancel_batch_btn.setEnabled(False)

        # Show completion message
        completed = sum(1 for item in self.batch_items if item.status == "Completed")
        failed = sum(1 for item in self.batch_items if item.status == "Failed")
        self.log(f"🎉 Batch completed! ✅ {completed} successful, ❌ {failed} failed")
        if failed == 0:
            QMessageBox.information(self, 'Batch Complete', f'All {completed} videos processed successfully!')
        else:
            QMessageBox.warning(self, 'Batch Complete', f'Processed {completed} videos successfully.\n{failed} videos failed.')

    def update_file_list(self):
        """Update the file list display"""
        self.file_list.clear()
        for i, item in enumerate(self.batch_items):

            # Create display text
            filename = os.path.basename(item.input_path)
            status_icon = {
                "Waiting": "⏳",
                "Processing": "🔄", 
                "Completed": "✅",
                "Failed": "❌"
            }.get(item.status, "❓")
            progress_text = f" ({item.progress}%)" if item.status == "Processing" else ""
            duration_text = f" - {item.get_duration_text()}" if item.status == "Completed" else ""
            display_text = f"{status_icon} {filename}{progress_text}{duration_text}"
            list_item = QListWidgetItem(display_text)

            # Color coding
            if item.status == "Completed":
                list_item.setBackground(Qt.GlobalColor.darkGreen)
            elif item.status == "Failed":
                list_item.setBackground(Qt.GlobalColor.darkRed)
            elif item.status == "Processing":
                list_item.setBackground(Qt.GlobalColor.darkBlue)
            self.file_list.addItem(list_item)

    def update_ui(self):
        """Update UI elements periodically"""
        # Vorschau-Frame vom laufenden Worker holen (Timer läuft auf UI-Thread,
        # daher sicher zum Anzeigen — anders als Signals aus Python-Threads).
        try:
            th = getattr(self, 'processor_thread', None)
            wk = getattr(th, 'current_worker', None) if th else None
            fb = getattr(wk, '_latest_preview', None) if wk else None
            if fb is not None:
                self.on_frame_preview(fb)
        except Exception:
            pass

        if not self.batch_items:
            return

        # Update statistics
        total = len(self.batch_items)
        completed = sum(1 for item in self.batch_items if item.status == "Completed")
        failed = sum(1 for item in self.batch_items if item.status == "Failed")
        self.total_files_label.setText(f"Total Files: {total}")
        self.completed_files_label.setText(f"Completed: {completed}")
        self.failed_files_label.setText(f"Failed: {failed}")

        # Estimate remaining time (very rough)
        if self.is_processing and completed > 0:
            avg_time = sum(item.get_duration_seconds() for item in self.batch_items 
                          if item.status == "Completed") / completed
            remaining = total - completed - failed
            est_minutes = int((remaining * avg_time) / 60)
            self.estimated_time_label.setText(f"Est. Time: ~{est_minutes}m")
        else:
            self.estimated_time_label.setText("Est. Time: N/A")

    def log(self, message):
        """Add message to log"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        print(f"[BATCH] {message}")

    def apply_theme(self):
        """Apply parent theme"""
        if hasattr(self.parent_analyzer, 'current_theme'):
            self.setStyleSheet(self.parent_analyzer.styleSheet())

    def closeEvent(self, event):
        """Handle dialog close"""
        if self.is_processing:
            reply = QMessageBox.question(
                self, 'Processing Active', 
                'Batch processing is still running. Cancel and close?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                if self.processor_thread:
                    self.processor_thread.cancel()
                    self.processor_thread.wait(3000)  # Wait up to 3 seconds
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

# BatchItem.get_duration_seconds is defined directly in the class above