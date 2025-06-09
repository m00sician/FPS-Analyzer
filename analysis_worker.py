"""
Analysis Worker Module für FPS Analyzer - WITH FIXED FPS UPDATE RATE
Handles video analysis in a separate thread to prevent GUI freezing
FPS Counter updates only every second, graphs update every frame
"""
import collections
import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont
from overlay_renderer import draw_fps_overlay

def resize_with_aspect_ratio(frame, target_width, target_height, background_color=(0, 0, 0)):
    """
    Resize frame while preserving aspect ratio and adding letterboxing/pillarboxing
    """
    h, w = frame.shape[:2]
    
    # Calculate aspect ratios
    source_aspect = w / h
    target_aspect = target_width / target_height
    
    if source_aspect > target_aspect:
        # Source is wider - fit to width, add black bars top/bottom (letterbox)
        new_width = target_width
        new_height = int(target_width / source_aspect)
        
        # Resize to fit width
        resized = cv2.resize(frame, (new_width, new_height))
        
        # Create target canvas with black background
        result = np.full((target_height, target_width, 3), background_color, dtype=np.uint8)
        
        # Center the resized frame vertically
        y_offset = (target_height - new_height) // 2
        result[y_offset:y_offset + new_height, 0:target_width] = resized
        
    else:
        # Source is taller - fit to height, add black bars left/right (pillarbox)
        new_height = target_height
        new_width = int(target_height * source_aspect)
        
        # Resize to fit height
        resized = cv2.resize(frame, (new_width, new_height))
        
        # Create target canvas with black background
        result = np.full((target_height, target_width, 3), background_color, dtype=np.uint8)
        
        # Center the resized frame horizontally
        x_offset = (target_width - new_width) // 2
        result[0:target_height, x_offset:x_offset + new_width] = resized
    
    return result

class AnalysisWorker(QThread):
    """Worker thread for FPS analysis to prevent GUI freezing"""
    progress_update = pyqtSignal(int, str)
    frame_preview = pyqtSignal(np.ndarray)
    analysis_complete = pyqtSignal(bool, str)
    
    def __init__(self, input_file, output_file, settings):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.settings = settings
        self.is_cancelled = False
        
    def cancel(self):
        """Cancel the analysis"""
        self.is_cancelled = True
        
    def run(self):
        """Main analysis function running in separate thread"""
        try:
            self.analyze_video()
        except Exception as e:
            self.analysis_complete.emit(False, str(e))
    
    def analyze_video(self):
        """Analyze video with FPS detection and overlay generation - FIXED FPS UPDATE RATE"""
        try:
            # Open video directly with OpenCV for better control
            cap = cv2.VideoCapture(self.input_file)
            if not cap.isOpened():
                raise ValueError("Could not open input video")
            
            # Get video properties
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            source_fps = cap.get(cv2.CAP_PROP_FPS)
            source_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            source_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            target_width, target_height = self.settings['resolution']
            
            # Calculate aspect ratios for info
            source_aspect = source_width / source_height
            target_aspect = target_width / target_height
            
            self.progress_update.emit(5, f"Video: {source_width}x{source_height} (AR: {source_aspect:.2f}) → {target_width}x{target_height} (AR: {target_aspect:.2f}), {source_fps:.2f}fps, {total_frames} frames")
            
            # Setup video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(self.output_file, fourcc, source_fps, (target_width, target_height))
            
            if not out.isOpened():
                raise ValueError("Could not create output video writer")
            
            # Analysis variables
            fps_history = collections.deque(maxlen=1000)
            frame_times = collections.deque(maxlen=1000)
            prev_frame_gray = None
            frame_count = 0
            
            # Global statistics for the entire video
            global_fps_values = []  # Store ALL FPS values for accurate min/max
            global_frame_times = []  # Store ALL frame times for accurate min/max
            
            # Enhanced frame detection
            recent_frames = collections.deque(maxlen=60)  # Store last 60 frames
            consecutive_duplicates = 0
            max_consecutive_duplicates = 0
            
            # 🔧 NEW: FPS Display Management
            displayed_fps = source_fps  # Start with source FPS
            fps_update_counter = 0  # Counter for FPS updates
            fps_update_interval = int(source_fps)  # Update FPS display every ~1 second
            fps_calculation_window = collections.deque(maxlen=60)  # 1 second window for calculation
            
            self.progress_update.emit(10, "Starting frame-by-frame analysis with aspect ratio preservation...")
            
            while True:
                if self.is_cancelled:
                    break
                    
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Resize frame to target resolution WITH ASPECT RATIO PRESERVATION
                frame_resized = resize_with_aspect_ratio(frame, target_width, target_height)
                
                # Convert to grayscale for analysis (use original frame for accurate analysis)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Create robust frame hash (use original resolution for consistent analysis)
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
                        max_consecutive_duplicates = max(max_consecutive_duplicates, consecutive_duplicates)
                    else:
                        consecutive_duplicates = 0
                
                # Add this frame to recent frames window
                recent_frames.append(frame_hash)
                
                # Calculate instantaneous FPS for graphs (every frame)
                if len(recent_frames) >= 60:  # We have a full second worth of frames
                    unique_count = len(set(recent_frames))
                    effective_fps = unique_count  # Unique frames in last 60 container frames = FPS
                    
                    # Calculate correct frame time: 1000ms / effective_fps
                    if effective_fps > 0:
                        frame_time = 1000.0 / effective_fps
                    else:
                        frame_time = 1000.0  # Fallback
                else:
                    # Not enough frames yet, estimate based on current data
                    if len(recent_frames) > 0:
                        unique_count = len(set(recent_frames))
                        # Scale to full second estimate
                        effective_fps = unique_count * (60 / len(recent_frames))
                        effective_fps = min(effective_fps, source_fps)
                        frame_time = 1000.0 / max(effective_fps, 1.0)
                    else:
                        effective_fps = source_fps
                        frame_time = 1000.0 / source_fps
                
                # Store values for graphs (every frame update)
                fps_history.append(effective_fps)
                frame_times.append(frame_time)
                
                # Store values for global statistics (entire video)
                global_fps_values.append(effective_fps)
                global_frame_times.append(frame_time)
                
                # 🔧 NEW: FPS Display Update Logic (only every ~1 second)
                fps_calculation_window.append(effective_fps)
                fps_update_counter += 1
                
                if fps_update_counter >= fps_update_interval:
                    # Update displayed FPS only every second
                    if len(fps_calculation_window) > 0:
                        # Use average FPS from last second for smoother display
                        displayed_fps = sum(fps_calculation_window) / len(fps_calculation_window)
                    fps_update_counter = 0  # Reset counter
                    print(f"🎯 FPS Display Updated: {displayed_fps:.1f} (based on {len(fps_calculation_window)} frames)")
                
                # Convert RESIZED frame to RGB for overlay processing
                frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                
                # Add FPS overlay with global statistics and font settings
                show_frametime = self.settings.get('show_frametime', True)
                frametime_scale = self.settings.get('frametime_scale', {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']})
                font_settings = self.settings.get('font_settings', {})
                color_settings = self.settings.get('color_settings', {
                    'framerate_color': '#00FF00',
                    'frametime_color': '#00FF00'
                })
                ftg_position = self.settings.get('ftg_position', 'bottom_right')
                
                # Fallback font settings if none provided
                if not font_settings:
                    try:
                        from font_manager import OpenCVFontSettings
                        font_settings = {
                            'fps_font': OpenCVFontSettings('HERSHEY_SIMPLEX', 1.2, 2, True, 2),
                            'framerate_font': OpenCVFontSettings('HERSHEY_SIMPLEX', 0.6, 1, False, 1),
                            'frametime_font': OpenCVFontSettings('HERSHEY_SIMPLEX', 0.5, 1, False, 1)
                        }
                    except ImportError:
                        # Ultimate fallback to QFont
                        font_settings = {
                            'fps_font': QFont("Arial", 12),
                            'framerate_font': QFont("Arial", 10),
                            'frametime_font': QFont("Arial", 9)
                        }
                
                # Call draw_fps_overlay with STABLE displayed_fps but live graphs
                try:
                    frame_with_overlay = draw_fps_overlay(
                        frame_rgb, 
                        list(fps_history),  # Live graph data (every frame)
                        displayed_fps,      # 🔧 STABLE FPS display (only updates every second)
                        list(frame_times) if show_frametime else None,  # Live frame time graph
                        show_frametime,
                        180,  # max_len
                        global_fps_values,  # Pass global stats
                        global_frame_times,  # Pass global frame times
                        frametime_scale,  # Pass frame time scale settings
                        font_settings,  # Pass font settings
                        color_settings,  # Pass color settings
                        ftg_position  # Pass Frame Time Graph position
                    )
                except Exception as e:
                    print(f"❌ ANALYSIS DEBUG: draw_fps_overlay failed: {e}")
                    import traceback
                    traceback.print_exc()
                    raise e
                
                # Convert back to BGR for video writer
                frame_bgr = cv2.cvtColor(frame_with_overlay, cv2.COLOR_RGB2BGR)
                out.write(frame_bgr)
                
                # Update for next iteration
                prev_frame_gray = gray
                frame_count += 1
                
                # Update progress and preview
                progress = 10 + int((frame_count / total_frames) * 85)
                
                # Status message including aspect ratio info
                if len(recent_frames) >= 60:
                    unique_in_window = len(set(recent_frames))
                    status_msg = f"Frame {frame_count}/{total_frames} - FPS: {displayed_fps:.1f} (stable) - AR Preserved ✓"
                    if is_duplicate:
                        status_msg += " (Duplicate)"
                    status_msg += f" | Unique in last 60: {unique_in_window}"
                else:
                    status_msg = f"Frame {frame_count}/{total_frames} - Building window: {len(recent_frames)}/60 - AR Preserved ✓"
                
                self.progress_update.emit(progress, status_msg)
                
                # Send preview frame occasionally
                if frame_count % 30 == 0:
                    self.frame_preview.emit(frame_bgr)
            
            # Clean up
            cap.release()
            out.release()
            
            if not self.is_cancelled:
                final_msg = f"Analysis completed! Aspect ratio preserved: {source_width}x{source_height} → {target_width}x{target_height}"
                self.progress_update.emit(100, final_msg)
                self.analysis_complete.emit(True, "FPS Analysis completed successfully with aspect ratio preservation!")
            else:
                self.analysis_complete.emit(False, "Analysis cancelled")
                
        except Exception as e:
            self.analysis_complete.emit(False, f"Analysis failed: {str(e)}")