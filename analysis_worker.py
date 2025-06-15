"""
Analysis Worker Module for FPS Analyzer - ENHANCED VERSION WITH SEGMENT SUPPORT + FRAME TIME SMOOTHING
Handles video analysis with Adaptive Crop+Resize Logic, Segment Selection, and Improved Smoothing
"""
import collections
import cv2
import numpy as np
import subprocess  # ✅ ADDED
import os  # ✅ ADDED
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont

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

def adaptive_crop_and_resize(frame, target_width, target_height, comparison_mode=False):
    """
    ✨ FIXED: Adaptive Crop+Resize Logic for Comparison Mode with Proper Aspect Ratio
    """
    h, w = frame.shape[:2]
    
    if comparison_mode:
        print(f"🎯 ADAPTIVE CROP+RESIZE: Input {w}x{h} → Target {target_width}x{target_height}")
        
        # Calculate target aspect ratio
        target_aspect = target_width / target_height
        source_aspect = w / h
        
        print(f"📏 ASPECT RATIOS: Source {source_aspect:.3f}, Target {target_aspect:.3f}")
        
        # Calculate optimal crop region that matches target aspect ratio
        if source_aspect > target_aspect:
            # Source is wider - crop horizontally to match target aspect ratio
            crop_height = h
            crop_width = int(h * target_aspect)
            
            # Center the crop horizontally
            crop_x_start = (w - crop_width) // 2
            crop_x_end = crop_x_start + crop_width
            crop_y_start = 0
            crop_y_end = h
            
            print(f"✂️ HORIZONTAL CROP: {w}x{h} → {crop_width}x{crop_height} (center crop)")
            
        else:
            # Source is taller - crop vertically to match target aspect ratio
            crop_width = w
            crop_height = int(w / target_aspect)
            
            # Center the crop vertically
            crop_x_start = 0
            crop_x_end = w
            crop_y_start = (h - crop_height) // 2
            crop_y_end = crop_y_start + crop_height
            
            print(f"✂️ VERTICAL CROP: {w}x{h} → {crop_width}x{crop_height} (center crop)")
        
        # Apply the calculated crop
        frame_cropped = frame[crop_y_start:crop_y_end, crop_x_start:crop_x_end]
        cropped_h, cropped_w = frame_cropped.shape[:2]
        
        print(f"✅ CROPPED RESULT: {cropped_w}x{cropped_h}")
        
        # Now resize to exact target dimensions (should be proportional now)
        frame_final = cv2.resize(frame_cropped, (target_width, target_height), 
                               interpolation=cv2.INTER_LANCZOS4)
        
        final_h, final_w = frame_final.shape[:2]
        print(f"🔄 FINAL RESIZE: {cropped_w}x{cropped_h} → {final_w}x{final_h}")
        print(f"✅ FINAL RESULT: {final_w}x{final_h} (Aspect preserved: {final_w/final_h:.3f})")
        
        return frame_final
    
    else:
        # Standard mode: aspect ratio preserving resize
        return resize_with_aspect_ratio(frame, target_width, target_height)

class AnalysisWorker(QThread):
    """Worker thread for FPS analysis with enhanced comparison support and segment selection"""
    progress_update = pyqtSignal(int, str)
    frame_preview = pyqtSignal(np.ndarray)
    analysis_complete = pyqtSignal(bool, str)
    
    def __init__(self, input_file, output_file, settings):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.settings = settings
        self.is_cancelled = False
        
        # 🎯 NEW: Extract segment information from settings
        self.start_frame = settings.get('segment_start_frame', None)
        self.end_frame = settings.get('segment_end_frame', None)
        
        # ✨ DYNAMIC: Import renderers INSIDE the worker to avoid circular imports
        self.enhanced_renderer = None
        self.legacy_renderer = None
        self.setup_renderers()
        
        # 🎯 ENHANCED: FPS stabilization for smoother graphs (reduced buffer size for more responsiveness)
        self.fps_stabilization_buffer = collections.deque(maxlen=6)  # ✅ REDUCED: Was 10, now 6 for faster response
        
        # 🆕 NEW: Frame Time stabilization for smoother graphs
        self.frametime_stabilization_buffer = collections.deque(maxlen=8)  # Frame time stabilization
        
    def stabilize_fps(self, raw_fps, source_fps):
        """🎯 ENHANCED: Intelligent FPS stabilization for up to 120 FPS - MORE RESPONSIVE"""
        # Add to buffer
        self.fps_stabilization_buffer.append(raw_fps)
        
        # ✅ IMPROVED: Reduced minimum data requirement for faster response
        if len(self.fps_stabilization_buffer) < 3:  # Was 5, now 3
            return round(raw_fps)
        
        # Calculate average of recent values
        avg_fps = sum(self.fps_stabilization_buffer) / len(self.fps_stabilization_buffer)
        
        # ✅ ENHANCED: Define FPS targets based on source FPS range
        if source_fps <= 60:
            common_fps_targets = [24, 25, 30, 50, 60]
            tolerance = 1.5
        else:  # 60-120 FPS range
            common_fps_targets = [30, 60, 72, 90, 100, 120]
            tolerance = 2.0  # Slightly wider tolerance for higher FPS
        
        # Find the closest target FPS
        closest_target = min(common_fps_targets, key=lambda x: abs(x - avg_fps))
        
        # ✅ IMPROVED: Snap to target if within tolerance
        if abs(avg_fps - closest_target) <= tolerance:
            return closest_target
        
        # Otherwise, use smoothed rounding
        # If most recent values are close to each other, use the mode
        recent_rounded = [round(fps) for fps in list(self.fps_stabilization_buffer)[-4:]]  # Use last 4 instead of 5
        
        # Find most common rounded value in recent history
        from collections import Counter
        fps_counts = Counter(recent_rounded)
        most_common_fps = fps_counts.most_common(1)[0][0]
        
        # ✅ IMPROVED: Lower threshold for faster stabilization
        if fps_counts[most_common_fps] >= 2:  # Was 3, now 2
            return most_common_fps
        
        # Fallback: simple rounding
        return round(avg_fps)
    
    def stabilize_frame_time(self, raw_frame_time):
        """🆕 NEW: Intelligent Frame Time stabilization for smoother graphs"""
        # Add to buffer
        self.frametime_stabilization_buffer.append(raw_frame_time)
        
        # If we don't have enough data, return rounded value
        if len(self.frametime_stabilization_buffer) < 4:
            return round(raw_frame_time, 1)
        
        # Calculate average of recent values
        avg_ft = sum(self.frametime_stabilization_buffer) / len(self.frametime_stabilization_buffer)
        
        # Define common frame time targets for snapping (corresponding to common FPS)
        # 16.67ms = 60 FPS, 33.33ms = 30 FPS, 41.67ms = 24 FPS, 50ms = 20 FPS
        common_ft_targets = [16.67, 20.0, 33.33, 41.67, 50.0, 66.67]  # 60, 50, 30, 24, 20, 15 FPS
        
        # Find the closest target frame time
        closest_target = min(common_ft_targets, key=lambda x: abs(x - avg_ft))
        
        # If we're within ±1.5ms of a common target, snap to it for stability
        if abs(avg_ft - closest_target) <= 1.5:
            return round(closest_target, 1)
        
        # Otherwise, use smoothed averaging
        # Calculate weighted average (more weight on recent values)
        weights = [1, 1.5, 2, 2.5]  # More weight on recent values
        if len(self.frametime_stabilization_buffer) >= 4:
            recent_values = list(self.frametime_stabilization_buffer)[-4:]
            weighted_avg = sum(val * weight for val, weight in zip(recent_values, weights)) / sum(weights)
        else:
            weighted_avg = avg_ft
        
        # Round to 1 decimal place for cleaner display
        return round(weighted_avg, 1)
        
    def setup_renderers(self):
        """Setup overlay renderers dynamically"""
        print("🔧 Setting up overlay renderers...")
        
        # Try to import Enhanced Renderer
        try:
            import enhanced_overlay_renderer
            self.enhanced_renderer = enhanced_overlay_renderer
            print("✅ Enhanced Overlay Renderer loaded!")
            
            # Also set legacy_renderer if enhanced_overlay_renderer.draw_fps_overlay is available
            if hasattr(enhanced_overlay_renderer, 'draw_fps_overlay'):
                self.legacy_renderer = enhanced_overlay_renderer.draw_fps_overlay
                print("✅ Enhanced draw_fps_overlay function set as legacy_renderer!")
            else:
                print("⚠️ draw_fps_overlay not found in enhanced_overlay_renderer")
                
        except ImportError as e:
            print(f"⚠️ Enhanced Overlay Renderer not available: {e}")
            self.enhanced_renderer = None
        
        # Try to import Legacy Renderer only if not already set
        if not hasattr(self, 'legacy_renderer') or self.legacy_renderer is None:
            try:
                import overlay_renderer
                print(f"📝 Checking overlay_renderer module...")
                available_functions = [name for name in dir(overlay_renderer) if not name.startswith('_') and callable(getattr(overlay_renderer, name))]
                print(f"📋 Available functions: {available_functions}")
                
                if hasattr(overlay_renderer, 'draw_fps_overlay'):
                    self.legacy_renderer = overlay_renderer.draw_fps_overlay
                    print("✅ Legacy draw_fps_overlay function found!")
                elif hasattr(overlay_renderer, 'draw_fps_overlay_with_legacy_position'):
                    # Fallback: Use the alternative function
                    self.legacy_renderer = overlay_renderer.draw_fps_overlay_with_legacy_position
                    print("✅ Using draw_fps_overlay_with_legacy_position as fallback!")
                else:
                    print("❌ No compatible renderer function found in overlay_renderer")
                    
            except ImportError as e:
                print(f"❌ Cannot import overlay_renderer: {e}")
                
        # If no renderer is available, use minimal renderer
        if not hasattr(self, 'enhanced_renderer') or self.enhanced_renderer is None:
            if not hasattr(self, 'legacy_renderer') or self.legacy_renderer is None:
                print("⚠️ No renderer available - using minimal renderer")
    
    def set_segment_range(self, start_frame, end_frame):
        """Set segment range for analysis"""
        self.start_frame = start_frame
        self.end_frame = end_frame
        
    def cancel(self):
        """Cancel the analysis"""
        self.is_cancelled = True
        
    def run(self):
        """Main analysis function running in separate thread"""
        try:
            self.analyze_video()
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"❌ ANALYSIS ERROR: {error_details}")
            self.analysis_complete.emit(False, f"Analysis failed: {str(e)}")
    
    def create_overlay(self, frame_rgb, fps_history, displayed_fps, frame_times, show_frametime, 
                        global_fps_values, global_frame_times, frametime_scale, font_settings, color_settings):
        """Create FPS overlay using available renderer - FIXED"""
        
        # FIXED: Enhanced fallback font settings
        if not font_settings:
            print("⚠️ No font settings provided, creating robust defaults")
            try:
                from font_manager import OpenCVFontSettings
                font_settings = {
                    'fps_font': OpenCVFontSettings('HERSHEY_SIMPLEX', 32, 3, True, border_thickness=3),
                    'framerate_font': OpenCVFontSettings('HERSHEY_SIMPLEX', 16, 2, False, border_thickness=2),
                    'frametime_font': OpenCVFontSettings('HERSHEY_SIMPLEX', 14, 1, False, border_thickness=1)
                }
                print("✅ Created default OpenCVFontSettings")
            except ImportError:
                # Robust fallback that will work even if font_manager is missing
                try:
                    print("⚠️ Trying alternative font import method")
                    # Try different import paths
                    import sys, os
                    script_dir = os.path.dirname(os.path.abspath(__file__))
                    if script_dir not in sys.path:
                        sys.path.append(script_dir)
                    
                    try:
                        # Try direct import of FallbackFontSettings from enhanced_overlay_renderer
                        from enhanced_overlay_renderer import EnhancedFontSettings
                        font_settings = {
                            'fps_font': EnhancedFontSettings('HERSHEY_SIMPLEX', 32, 3, True, border_thickness=3),
                            'framerate_font': EnhancedFontSettings('HERSHEY_SIMPLEX', 16, 2, False, border_thickness=2),
                            'frametime_font': EnhancedFontSettings('HERSHEY_SIMPLEX', 14, 1, False, border_thickness=1)
                        }
                        print("✅ Created fallback EnhancedFontSettings")
                    except ImportError:
                        # Ultimate fallback - use PyQt QFont (will force OpenCV rendering)
                        from PyQt6.QtGui import QFont
                        font_settings = {
                            'fps_font': QFont("Arial", 12, QFont.Weight.Bold),
                            'framerate_font': QFont("Arial", 10),
                            'frametime_font': QFont("Arial", 9)
                        }
                        print("⚠️ Using QFont fallback (OpenCV rendering)")
                except Exception as e:
                    print(f"❌ All font loading methods failed: {e}")
                    # Create minimal font dictionary with basic attributes
                    class MinimalFont:
                        def __init__(self, name, size, bold=False):
                            self.font_name = name
                            self.size = size
                            self.bold = bold
                    
                    font_settings = {
                        'fps_font': MinimalFont('HERSHEY_SIMPLEX', 32, True),
                        'framerate_font': MinimalFont('HERSHEY_SIMPLEX', 16),
                        'frametime_font': MinimalFont('HERSHEY_SIMPLEX', 14)
                    }
                    print("⚠️ Using minimal font settings (basic OpenCV)")
        
        # FIXED: Ensure color settings are valid
        if not color_settings:
            color_settings = {
                'framerate_color': '#00FF00',
                'frametime_color': '#00FF00'
            }
        
        # ✨ TRY Enhanced Renderer first (if available and layout config exists)
        if self.enhanced_renderer and 'layout_config' in self.settings:
            try:
                layout_config = self.settings['layout_config']
                print(f"🎨 Using Enhanced Renderer with {len(layout_config)} layout elements")
                
                return self.enhanced_renderer.draw_fps_overlay_with_layout(
                    frame_rgb, 
                    list(fps_history),
                    displayed_fps,
                    list(frame_times) if show_frametime else None,
                    show_frametime,
                    180,  # max_len
                    global_fps_values,
                    global_frame_times,
                    frametime_scale,
                    font_settings,
                    color_settings,
                    layout_config
                )
            except Exception as e:
                print(f"❌ Enhanced Renderer failed: {e}")
                import traceback
                traceback.print_exc()
        
        # ✨ TRY Enhanced Renderer with legacy positioning
        if self.enhanced_renderer:
            try:
                ftg_position = self.settings.get('ftg_position', 'bottom_right')
                print(f"🔄 Using Enhanced Renderer with legacy positioning: {ftg_position}")
                
                return self.enhanced_renderer.draw_fps_overlay_with_legacy_position(
                    frame_rgb, 
                    list(fps_history),
                    displayed_fps,
                    list(frame_times) if show_frametime else None,
                    show_frametime,
                    180,
                    global_fps_values,
                    global_frame_times,
                    frametime_scale,
                    font_settings,
                    color_settings,
                    ftg_position
                )
            except Exception as e:
                print(f"❌ Enhanced Renderer (legacy mode) failed: {e}")
                import traceback
                traceback.print_exc()
        
        # ✨ FALLBACK to Legacy Renderer
        if self.legacy_renderer:
            try:
                ftg_position = self.settings.get('ftg_position', 'bottom_right')
                print(f"🔄 Using Legacy Renderer with ftg_position: {ftg_position}")
                
                return self.legacy_renderer(
                    frame_rgb, 
                    list(fps_history),
                    displayed_fps,
                    list(frame_times) if show_frametime else None,
                    show_frametime,
                    180,
                    global_fps_values,
                    global_frame_times,
                    frametime_scale,
                    font_settings,
                    color_settings,
                    ftg_position
                )
            except Exception as e:
                print(f"❌ Legacy Renderer failed: {e}")
                import traceback
                traceback.print_exc()
        
        # ✨ ULTIMATE FALLBACK: Simple FPS text
        print("⚠️ All renderers failed, using simple FPS overlay")
        overlay = frame_rgb.copy()
        try:
            # FIXED: Improved fallback rendering that will always work
            import cv2
            # Draw simple FPS text
            cv2.putText(overlay, f"FPS: {displayed_fps:.1f}", (50, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 255, 0), 3, cv2.LINE_AA)
            cv2.putText(overlay, "Minimal Overlay Mode", (50, 100), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 0), 2, cv2.LINE_AA)
            
            # Draw minimal framerate graph if needed
            if len(fps_history) > 2:
                graph_x = 50
                graph_y = 150
                graph_width = 300
                graph_height = 100
                
                # Draw box
                cv2.rectangle(overlay, (graph_x, graph_y), 
                            (graph_x + graph_width, graph_y + graph_height), 
                            (80, 80, 80), 1)
                
                # Draw FPS line (simplified)
                points = []
                for i, fps_val in enumerate(fps_history[-graph_width:]):
                    x = graph_x + i
                    scaled_fps = min(fps_val, 120)  # Cap at 120 FPS
                    y = graph_y + graph_height - int((scaled_fps / 120) * graph_height)
                    points.append((x, y))
                
                # Draw line segments
                for i in range(len(points) - 1):
                    cv2.line(overlay, points[i], points[i + 1], (0, 255, 0), 1, cv2.LINE_AA)
                
                # Add label
                cv2.putText(overlay, "FRAME RATE", (graph_x, graph_y - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
            
            return overlay
        except Exception as e:
            print(f"❌ Even minimal rendering failed: {e}")
            # Return original frame as absolute last resort
            return frame_rgb
    
    def check_ffmpeg(self):
        """✅ FIXED: Check if FFmpeg is available"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=2)
            return True
        except:
            return False

    def ffmpeg_exact_bitrate(self, input_file, output_file, bitrate_mbps):
        """✅ FIXED: Convert with EXACT bitrate using FFmpeg"""
        try:
            cmd = [
                'ffmpeg', '-i', input_file, '-y',
                '-c:v', 'libx264',
                '-b:v', f'{bitrate_mbps}M',        # Target
                '-minrate', f'{bitrate_mbps}M',    # Min = target
                '-maxrate', f'{bitrate_mbps}M',    # Max = target  
                '-bufsize', f'{bitrate_mbps*2}M',  # Buffer
                '-preset', 'medium',
                '-movflags', '+faststart',
                output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            return result.returncode == 0
            
        except Exception as e:
            print(f"FFmpeg error: {e}")
            return False

    def analyze_video(self):
        """🎯 FIXED: Analyze video with SEGMENT SUPPORT + IMPROVED RESPONSIVENESS"""
        
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
            
            # ✅ ENHANCED: Use comparison_resolution if in comparison mode
            if self.settings.get('comparison_mode', False):
                target_width, target_height = self.settings.get('comparison_resolution', (960, 1080))
                resolution_name = self.settings.get('resolution_name', '1080p')
                print(f"🎯 COMPARISON MODE: Using {resolution_name} ({target_width}x{target_height})")
            else:
                target_width, target_height = self.settings['resolution']
                print(f"📺 STANDARD MODE: Using {target_width}x{target_height}")
            
            # 🎯 NEW: SEGMENT PROCESSING
            actual_start = self.start_frame or 0
            actual_end = self.end_frame or total_frames
            
            # Validation
            actual_start = max(0, actual_start)
            actual_end = min(total_frames, actual_end)
            
            if actual_start >= actual_end:
                raise ValueError("Invalid segment: start >= end")
            
            segment_frames = actual_end - actual_start
            is_segment_mode = (self.start_frame is not None and self.end_frame is not None)
            
            # Log segment info
            if is_segment_mode:
                start_time = actual_start / source_fps
                end_time = actual_end / source_fps
                duration = segment_frames / source_fps
                self.progress_update.emit(5, f"🎯 SEGMENT MODE: {start_time:.1f}s - {end_time:.1f}s (Duration: {duration:.1f}s)")
                self.progress_update.emit(7, f"🎯 Processing {segment_frames} frames ({actual_start} to {actual_end})")
            else:
                self.progress_update.emit(5, f"📺 FULL VIDEO MODE: {total_frames} frames")
            
            # Status info
            renderer_info = "Enhanced" if self.enhanced_renderer else "Legacy" if self.legacy_renderer else "Minimal"
            layout_info = "Custom Layout ✓" if 'layout_config' in self.settings else "Default Layout"
            
            mode_info = f"Segment Mode ({segment_frames} frames)" if is_segment_mode else "Full Video Mode"
            
            self.progress_update.emit(10, f"Mode: {mode_info}, Renderer: {renderer_info}, Layout: {layout_info}")
            
            # ✅ UPDATED: Handle OpenCV vs FFmpeg bitrate logic
            target_bitrate = self.settings.get('bitrate', 60)
            
            if target_bitrate == 'opencv':
                # OpenCV automatic quality
                fourcc = cv2.VideoWriter_fourcc(*'H264')  # Good OpenCV codec
                use_ffmpeg_postprocess = False
                print("🔧 Using OpenCV automatic quality control")
            elif isinstance(target_bitrate, int) and target_bitrate >= 40:
                # FFmpeg exact bitrate
                fourcc = cv2.VideoWriter_fourcc(*'avc1')  # High quality for FFmpeg processing
                use_ffmpeg_postprocess = True
                print(f"🎬 Using FFmpeg for exact {target_bitrate} Mbps control")
            else:
                # Fallback
                fourcc = cv2.VideoWriter_fourcc(*'H264')
                use_ffmpeg_postprocess = False
                target_bitrate = 'opencv'  # Normalize fallback
                print("⚠️ Fallback to OpenCV automatic quality")
            out = cv2.VideoWriter(self.output_file, fourcc, source_fps, (target_width, target_height))
            
            if not out.isOpened():
                raise ValueError("Could not create output video writer")
            
            # 🎯 NEW: SEEK TO START FRAME
            cap.set(cv2.CAP_PROP_POS_FRAMES, actual_start)
            print(f"🎯 Seeking to start frame: {actual_start}")
            
            # Analysis variables
            fps_history = collections.deque(maxlen=1000)
            frame_times = collections.deque(maxlen=1000)
            prev_frame_gray = None
            frame_count = 0
            
            # Global statistics for the entire segment
            global_fps_values = []
            global_frame_times = []
            
            # ✅ FIXED: Define fps_calculation_method BEFORE using it
            # Enhanced frame detection for up to 120 FPS
            if source_fps <= 60:
                detection_window_size = 60
                fps_calculation_method = "standard"
            elif source_fps <= 120:
                detection_window_size = 120
                fps_calculation_method = "extended"
            else:  # Cap at 120 FPS for practical video analysis
                detection_window_size = 120
                fps_calculation_method = "extended"
                print(f"⚠️ Source FPS ({source_fps:.1f}) exceeds 120 - capping detection at 120 FPS")
            
            print(f"🎯 FPS DETECTION: Source={source_fps:.1f}, Window={detection_window_size}, Method={fps_calculation_method}")
            
            # Enhanced frame detection with dynamic window
            recent_frames = collections.deque(maxlen=detection_window_size)
            consecutive_duplicates = 0
            
            # ✅ IMPROVED: More responsive FPS Display Management
            displayed_fps = source_fps
            fps_update_counter = 0
            fps_update_interval = max(15, int(source_fps / 4))  # ✅ NEW: Update 4 times per second instead of once
            fps_calculation_window = collections.deque(maxlen=30)  # ✅ REDUCED: Was 60, now 30 for faster response
            
            self.progress_update.emit(15, f"Starting analysis with {renderer_info} renderer ({fps_calculation_method} mode)...")
            
            current_frame_number = actual_start
            
            while current_frame_number < actual_end:
                if self.is_cancelled:
                    break
                    
                ret, frame = cap.read()
                if not ret:
                    print(f"⚠️ Could not read frame {current_frame_number}, stopping")
                    break
                
                # ✨ ENHANCED: Adaptive processing based on mode
                if self.settings.get('comparison_mode', False):
                    # Comparison mode: Use adaptive crop+resize
                    frame_processed = adaptive_crop_and_resize(
                        frame, target_width, target_height, comparison_mode=True
                    )
                else:
                    # Standard mode: Resize with aspect ratio preservation
                    frame_processed = resize_with_aspect_ratio(frame, target_width, target_height)

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
                    else:
                        consecutive_duplicates = 0
                
                # Add this frame to recent frames window
                recent_frames.append(frame_hash)
                
                # ✅ FIXED: Multi-method FPS calculation for up to 120 FPS
                if fps_calculation_method == "standard":
                    # Standard method (up to 60 FPS)
                    if len(recent_frames) >= 60:
                        unique_count = len(set(recent_frames))
                        effective_fps = unique_count
                        
                        if effective_fps > 0:
                            raw_frame_time = 1000.0 / effective_fps
                        else:
                            raw_frame_time = 1000.0
                    else:
                        if len(recent_frames) > 0:
                            unique_count = len(set(recent_frames))
                            effective_fps = unique_count * (60 / len(recent_frames))
                            effective_fps = min(effective_fps, source_fps)
                            raw_frame_time = 1000.0 / max(effective_fps, 1.0)
                        else:
                            effective_fps = source_fps
                            raw_frame_time = 1000.0 / source_fps
                            
                elif fps_calculation_method == "extended":
                    # Extended method (60-120 FPS)
                    if len(recent_frames) >= 60:
                        unique_count = len(set(recent_frames))
                        
                        # Scale based on window utilization and source FPS
                        if len(recent_frames) >= 120:
                            # Full window - direct calculation
                            effective_fps = unique_count
                        else:
                            # Partial window - scale up
                            window_ratio = len(recent_frames) / detection_window_size
                            effective_fps = unique_count / window_ratio
                        
                        # Cap at source FPS for sanity
                        effective_fps = min(effective_fps, source_fps)
                        
                        if effective_fps > 0:
                            raw_frame_time = 1000.0 / effective_fps
                        else:
                            raw_frame_time = 1000.0
                    else:
                        # Fallback for initial frames
                        if len(recent_frames) > 0:
                            unique_count = len(set(recent_frames))
                            scale_factor = detection_window_size / len(recent_frames)
                            effective_fps = unique_count * scale_factor
                            effective_fps = min(effective_fps, source_fps)
                            raw_frame_time = 1000.0 / max(effective_fps, 1.0)
                        else:
                            effective_fps = source_fps
                            raw_frame_time = 1000.0 / source_fps
                else:
                    # Fallback to standard method
                    if len(recent_frames) >= 60:
                        unique_count = len(set(recent_frames))
                        effective_fps = unique_count
                        raw_frame_time = 1000.0 / max(effective_fps, 1.0)
                    else:
                        effective_fps = source_fps
                        raw_frame_time = 1000.0 / source_fps
                
                # 🎯 ENHANCED: Intelligent stabilization for smoother graphs
                effective_fps = self.stabilize_fps(effective_fps, source_fps)
                smooth_frame_time = self.stabilize_frame_time(raw_frame_time)  # ✅ NEW: Frame time stabilization
                
                # Store values for graphs
                fps_history.append(effective_fps)
                frame_times.append(smooth_frame_time)  # ✅ USING STABILIZED FRAME TIME
                
                # Store values for global statistics
                global_fps_values.append(effective_fps)
                global_frame_times.append(smooth_frame_time)  # ✅ USING STABILIZED FRAME TIME
                
                # ✅ IMPROVED: More responsive FPS Display Update Logic
                fps_calculation_window.append(effective_fps)
                fps_update_counter += 1
                
                if fps_update_counter >= fps_update_interval:
                    if len(fps_calculation_window) > 0:
                        # Use stabilized rounding for cleaner display
                        displayed_fps = round(sum(fps_calculation_window) / len(fps_calculation_window))
                    fps_update_counter = 0

                # Prepare overlay settings
                show_frametime = self.settings.get('show_frametime', True)
                
                # ✅ NEW: Updated frame time scale with new standards (will be overridden by UI settings later)
                frametime_scale = self.settings.get('frametime_scale', {
                    'min': 16.7, 'mid': 33.3, 'max': 50.0,  # 60fps, 30fps, 20fps
                    'labels': ['16.7', '33.3', '50.0']
                })
                
                font_settings = self.settings.get('font_settings', {})
                color_settings = self.settings.get('color_settings', {
                    'framerate_color': '#00FF00',
                    'frametime_color': '#00FF00'
                })
                
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
                        from PyQt6.QtGui import QFont
                        font_settings = {
                            'fps_font': QFont("Arial", 12),
                            'framerate_font': QFont("Arial", 10),
                            'frametime_font': QFont("Arial", 9)
                        }

                # Convert PROCESSED frame to RGB for overlay processing
                frame_rgb = cv2.cvtColor(frame_processed, cv2.COLOR_BGR2RGB)
                
                # **COMPARISON MODE: Simplified UI**
                if self.settings.get('comparison_mode', False) and self.settings.get('simplified_ui', False):
                    try:
                        from comparison_renderer import create_simplified_comparison_overlay
                        frame_with_overlay = create_simplified_comparison_overlay(
                            frame_rgb, fps_history, displayed_fps,
                            self.settings.get('video_name', 'Video'),
                            global_fps_values, font_settings, color_settings
                        )
                    except ImportError:
                        print("⚠️ Comparison renderer not available, using standard overlay")
                        frame_with_overlay = self.create_overlay(
                            frame_rgb, fps_history, displayed_fps, frame_times, show_frametime,
                            global_fps_values, global_frame_times, frametime_scale, 
                            font_settings, color_settings
                        )
                else:
                    # ✨ CREATE OVERLAY with available renderer (standard mode)
                    frame_with_overlay = self.create_overlay(
                        frame_rgb, fps_history, displayed_fps, frame_times, show_frametime,
                        global_fps_values, global_frame_times, frametime_scale, 
                        font_settings, color_settings
                    )
                
                # Convert back to BGR for video writer
                frame_bgr = cv2.cvtColor(frame_with_overlay, cv2.COLOR_RGB2BGR)
                out.write(frame_bgr)
                
                # Update for next iteration
                prev_frame_gray = gray
                frame_count += 1
                current_frame_number += 1
                
                # Update progress and preview
                if is_segment_mode:
                    segment_progress = frame_count / segment_frames
                    progress = 15 + int(segment_progress * 70)  # 15-85%
                else:
                    progress = 15 + int((frame_count / total_frames) * 70)
                
                # Status message with smoothing info and FPS method
                mode_str = f"Segment ({frame_count}/{segment_frames})" if is_segment_mode else f"Full ({frame_count}/{total_frames})"
                if len(recent_frames) >= 60:
                    status_msg = f"Frame {current_frame_number} - FPS: {displayed_fps:.0f} FT: {smooth_frame_time:.1f}ms ({fps_calculation_method}) - {mode_str} - {renderer_info}"
                    if is_duplicate:
                        status_msg += " (Duplicate)"
                else:
                    status_msg = f"Frame {current_frame_number} - Building: {len(recent_frames)}/{detection_window_size} ({fps_calculation_method}) - {mode_str}"
                
                self.progress_update.emit(progress, status_msg)
                
                # Send preview frame occasionally
                if frame_count % 30 == 0:
                    self.frame_preview.emit(frame_bgr)
            
            # Clean up
            cap.release()
            out.release()
            
            # ✅ UPDATED: FFmpeg post-processing only for numeric bitrates ≥40
            print(f"🔍 DEBUG: target_bitrate = {target_bitrate}")
            print(f"🔍 DEBUG: use_ffmpeg_postprocess = {use_ffmpeg_postprocess}")
            print(f"🔍 DEBUG: check_ffmpeg() = {self.check_ffmpeg()}")
            
            if use_ffmpeg_postprocess and self.check_ffmpeg():
                print(f"🎬 FFmpeg post-processing: {target_bitrate} Mbps")
                temp_file = self.output_file.replace('.mp4', '_temp.mp4')
                os.rename(self.output_file, temp_file)
                
                self.progress_update.emit(95, f"🎬 Applying {target_bitrate} Mbps with FFmpeg...")
                
                if self.ffmpeg_exact_bitrate(temp_file, self.output_file, target_bitrate):
                    os.remove(temp_file)
                    self.progress_update.emit(100, f"✅ {target_bitrate} Mbps EXACT bitrate applied!")
                else:
                    os.rename(temp_file, self.output_file)
                    self.progress_update.emit(100, f"⚠️ FFmpeg failed, using OpenCV output")
            else:
                if target_bitrate == 'opencv':
                    self.progress_update.emit(100, "✅ OpenCV automatic quality applied!")
                else:
                    self.progress_update.emit(100, f"⚠️ FFmpeg not available, using OpenCV fallback")

            if not self.is_cancelled:
                mode_info = f"Segment Mode ({segment_frames} frames)" if is_segment_mode else f"Full Video Mode ({total_frames} frames)"
                final_msg = f"Analysis completed! {renderer_info} renderer with {layout_info} - {mode_info} (Enhanced Smoothing)"
                self.progress_update.emit(100, final_msg)
                self.analysis_complete.emit(True, f"🎯 FPS Analysis completed with {renderer_info} renderer! ({mode_info})")
            else:
                self.analysis_complete.emit(False, "Analysis cancelled")
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"❌ ANALYSIS ERROR: {error_details}")
            self.analysis_complete.emit(False, f"Analysis failed: {str(e)}")