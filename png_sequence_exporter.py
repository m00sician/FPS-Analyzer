"""
PNG Sequence Exporter für FPS Analyzer
Exports transparent PNG alpha sequences for Adobe Premiere Pro
"""
import collections
import cv2
import numpy as np
import os
from PyQt6.QtCore import QThread, pyqtSignal
from overlay_renderer import draw_complete_overlay_transparent

class PNGSequenceExporter(QThread):
    """Worker thread for exporting PNG Alpha sequences"""
    progress_update = pyqtSignal(int, str)
    export_complete = pyqtSignal(bool, str, int)  # success, message, total_frames
    
    def __init__(self, input_file, output_dir, settings):
        super().__init__()
        self.input_file = input_file
        self.output_dir = output_dir
        self.settings = settings
        self.is_cancelled = False
        
    def cancel(self):
        """Cancel the export"""
        self.is_cancelled = True
        
    def run(self):
        """Main export function running in separate thread"""
        try:
            self.export_png_sequence()
        except Exception as e:
            self.export_complete.emit(False, str(e), 0)
    
    def export_png_sequence(self):
        """Export PNG Alpha sequence with graph overlays only"""
        try:
            # Open video
            cap = cv2.VideoCapture(self.input_file)
            if not cap.isOpened():
                raise ValueError("Could not open input video")
            
            # Get video properties
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            source_fps = cap.get(cv2.CAP_PROP_FPS)
            source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # Use output resolution from settings
            target_width, target_height = self.settings['resolution']
            
            self.progress_update.emit(5, f"🎬 Analyzing video: {total_frames} frames, {source_fps:.2f}fps")
            
            # Analysis variables (same as main analysis)
            fps_history = collections.deque(maxlen=1000)
            frame_times = collections.deque(maxlen=1000)
            prev_frame_gray = None
            frame_count = 0
            
            # Enhanced frame detection
            recent_frames = collections.deque(maxlen=60)
            consecutive_duplicates = 0
            
            # FPS Display Management (stable updates)
            displayed_fps = source_fps
            fps_update_counter = 0
            fps_update_interval = int(source_fps)
            fps_calculation_window = collections.deque(maxlen=60)
            
            self.progress_update.emit(10, "🎬 Starting PNG Alpha export with graph analysis...")
            
            while True:
                if self.is_cancelled:
                    break
                    
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Convert to grayscale for analysis
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Create frame hash for duplicate detection
                small_frame = cv2.resize(gray, (64, 64))
                frame_hash = hash(small_frame.tobytes())
                
                # Check for consecutive duplicates
                is_duplicate = False
                if prev_frame_gray is not None:
                    prev_small = cv2.resize(prev_frame_gray, (64, 64))
                    prev_hash = hash(prev_small.tobytes())
                    is_duplicate = (frame_hash == prev_hash)
                    
                    if is_duplicate:
                        consecutive_duplicates += 1
                    else:
                        consecutive_duplicates = 0
                
                # Add frame to recent frames window
                recent_frames.append(frame_hash)
                
                # Calculate FPS (same logic as main analysis)
                if len(recent_frames) >= 60:
                    unique_count = len(set(recent_frames))
                    effective_fps = unique_count
                    if effective_fps > 0:
                        frame_time = 1000.0 / effective_fps
                    else:
                        frame_time = 1000.0
                else:
                    if len(recent_frames) > 0:
                        unique_count = len(set(recent_frames))
                        effective_fps = unique_count * (60 / len(recent_frames))
                        effective_fps = min(effective_fps, source_fps)
                        frame_time = 1000.0 / max(effective_fps, 1.0)
                    else:
                        effective_fps = source_fps
                        frame_time = 1000.0 / source_fps
                
                # Store values for graphs
                fps_history.append(effective_fps)
                frame_times.append(frame_time)
                
                # FPS Display Update (stable, every second)
                fps_calculation_window.append(effective_fps)
                fps_update_counter += 1
                
                if fps_update_counter >= fps_update_interval:
                    if len(fps_calculation_window) > 0:
                        displayed_fps = sum(fps_calculation_window) / len(fps_calculation_window)
                    fps_update_counter = 0
                
                # 🎬 Generate PNG with transparent background + graphs only
                show_frametime = self.settings.get('show_frametime', True)
                frametime_scale = self.settings.get('frametime_scale', {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']})
                font_settings = self.settings.get('font_settings', {})
                color_settings = self.settings.get('color_settings', {
                    'framerate_color': '#00FF00',
                    'frametime_color': '#00FF00'
                })
                ftg_position = self.settings.get('ftg_position', 'bottom_right')
                
                # Create transparent overlay with graphs only
                try:
                    transparent_overlay = draw_graphs_only_transparent(
                        list(fps_history),
                        list(frame_times) if show_frametime else None,
                        show_frametime,
                        180,  # max_len
                        frametime_scale,
                        font_settings,
                        color_settings,
                        ftg_position,
                        target_width,
                        target_height
                    )
                    
                    # Save as PNG with alpha channel
                    frame_filename = f"graph_{frame_count:06d}.png"
                    frame_path = os.path.join(self.output_dir, frame_filename)
                    
                    # Convert RGBA to BGRA for OpenCV
                    transparent_overlay_bgra = cv2.cvtColor(transparent_overlay, cv2.COLOR_RGBA2BGRA)
                    cv2.imwrite(frame_path, transparent_overlay_bgra)
                    
                except Exception as e:
                    print(f"❌ PNG Export Error on frame {frame_count}: {e}")
                    # Create empty transparent frame as fallback
                    empty_frame = np.zeros((target_height, target_width, 4), dtype=np.uint8)
                    frame_filename = f"graph_{frame_count:06d}.png"
                    frame_path = os.path.join(self.output_dir, frame_filename)
                    cv2.imwrite(frame_path, empty_frame)
                
                # Update for next iteration
                prev_frame_gray = gray
                frame_count += 1
                
                # Update progress
                progress = 10 + int((frame_count / total_frames) * 85)
                
                if frame_count % 100 == 0:  # Update every 100 frames
                    status_msg = f"🎬 Exporting frame {frame_count}/{total_frames} - FPS: {displayed_fps:.1f}"
                    self.progress_update.emit(progress, status_msg)
            
            # Clean up
            cap.release()
            
            if not self.is_cancelled:
                self.progress_update.emit(100, f"🎬 PNG Alpha Sequence export completed: {frame_count} frames")
                self.export_complete.emit(True, self.output_dir, frame_count)
            else:
                self.export_complete.emit(False, "Export cancelled", frame_count)
                
        except Exception as e:
            self.export_complete.emit(False, f"Export failed: {str(e)}", 0)