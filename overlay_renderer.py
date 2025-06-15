"""
Analysis Worker Module für FPS Analyzer - UPDATED WITH ENHANCED OVERLAY RENDERER
Handles video analysis in a separate thread with Enhanced Overlay Renderer integration
"""
import collections
import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont

# ✨ NEW: Import enhanced overlay renderer with better error handling
ENHANCED_RENDERER_AVAILABLE = False
try:
    from enhanced_overlay_renderer import draw_fps_overlay_with_layout, draw_fps_overlay_with_legacy_position
    ENHANCED_RENDERER_AVAILABLE = True
    print("✅ Enhanced Overlay Renderer loaded successfully!")
except ImportError as e:
    print(f"⚠️ Enhanced Overlay Renderer not found: {e}")
    print("🔄 Falling back to legacy renderer")

# ✨ SAFE: Import legacy renderer with multiple fallback attempts
LEGACY_RENDERER_AVAILABLE = False
legacy_draw_function = None

# Try different import patterns for legacy renderer
try:
    from overlay_renderer import draw_fps_overlay
    legacy_draw_function = draw_fps_overlay
    LEGACY_RENDERER_AVAILABLE = True
    print("✅ Legacy Overlay Renderer loaded (draw_fps_overlay)")
except ImportError:
    try:
        # Maybe it's called differently?
        import overlay_renderer
        if hasattr(overlay_renderer, 'draw_fps_overlay'):
            legacy_draw_function = overlay_renderer.draw_fps_overlay
            LEGACY_RENDERER_AVAILABLE = True
            print("✅ Legacy Overlay Renderer loaded (module.draw_fps_overlay)")
        else:
            print("❌ draw_fps_overlay function not found in overlay_renderer module")
            print(f"📝 Available functions: {[name for name in dir(overlay_renderer) if not name.startswith('_')]}")
    except ImportError as e:
        print(f"❌ Cannot import overlay_renderer module at all: {e}")

# If no renderer is available, we have a problem
if not ENHANCED_RENDERER_AVAILABLE and not LEGACY_RENDERER_AVAILABLE:
    print("❌ CRITICAL: No overlay renderer available!")
    print("📝 Please ensure either:")
    print("   1. enhanced_overlay_renderer.py exists with draw_fps_overlay_with_layout function")
    print("   2. overlay_renderer.py exists with draw_fps_overlay function")
    raise ImportError("No overlay renderer available")

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
            self.analysis_complete.emit(False, f"Analysis failed: {str(e)}")
    
    def analyze_video(self):
        """Analyze video with FPS detection and overlay generation - UPDATED WITH ENHANCED RENDERER"""
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
            
            # ✨ Check renderer type and layout config
            has_enhanced_renderer = ENHANCED_RENDERER_AVAILABLE
            has_layout_config = 'layout_config' in self.settings
            
            renderer_info = "Enhanced Renderer ✓" if has_enhanced_renderer else "Legacy Renderer"
            layout_info = "Custom Layout ✓" if has_layout_config else "Default Layout"
            
            self.progress_update.emit(5, f"Video: {source_width}x{source_height} → {target_width}x{target_height}, {source_fps:.2f}fps")
            self.progress_update.emit(7, f"Renderer: {renderer_info}, Layout: {layout_info}")
            
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
            
            # 🔧 FPS Display Management
            displayed_fps = source_fps  # Start with source FPS
            fps_update_counter = 0  # Counter for FPS updates
            fps_update_interval = int(source_fps)  # Update FPS display every ~1 second
            fps_calculation_window = collections.deque(maxlen=60)  # 1 second window for calculation
            
            self.progress_update.emit(10, f"Starting analysis with {renderer_info} and {layout_info}...")
            
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
                
                # 🔧 FPS Display Update Logic (only every ~1 second)
                fps_calculation_window.append(effective_fps)
                fps_update_counter += 1
                
                if fps_update_counter >= fps_update_interval:
                    # Update displayed FPS only every second
                    if len(fps_calculation_window) > 0:
                        # Use average FPS from last second for smoother display
                        displayed_fps = sum(fps_calculation_window) / len(fps_calculation_window)
                    fps_update_counter = 0  # Reset counter
                
                # Convert RESIZED frame to RGB for overlay processing
                frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                
                # ✨ ENHANCED: Add FPS overlay with Enhanced Renderer or Legacy fallback
                show_frametime = self.settings.get('show_frametime', True)
                frametime_scale = self.settings.get('frametime_scale', {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']})
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
                        # Ultimate fallback to QFont
                        font_settings = {
                            'fps_font': QFont("Arial", 12),
                            'framerate_font': QFont("Arial", 10),
                            'frametime_font': QFont("Arial", 9)
                        }
                
                # ✨ ENHANCED: Use Enhanced Renderer if available, otherwise fall back to legacy
                try:
                    if ENHANCED_RENDERER_AVAILABLE and has_layout_config:
                        # 🚀 USE ENHANCED RENDERER with layout config
                        layout_config = self.settings.get('layout_config')
                        
                        print(f"🎨 ENHANCED RENDERER: Using layout config with {len(layout_config)} elements")
                        for element_id, config in layout_config.items():
                            print(f"   📍 {element_id}: ({config.get('x', 0)}, {config.get('y', 0)}) {config.get('width', 0)}x{config.get('height', 0)}")
                        
                        frame_with_overlay = draw_fps_overlay_with_layout(
                            frame_rgb, 
                            list(fps_history),          # Live graph data (every frame)
                            displayed_fps,               # Stable FPS display (only updates every second)
                            list(frame_times) if show_frametime else None,  # Live frame time graph
                            show_frametime,
                            180,  # max_len
                            global_fps_values,           # Pass global stats
                            global_frame_times,          # Pass global frame times
                            frametime_scale,             # Pass frame time scale settings
                            font_settings,               # Pass font settings
                            color_settings,              # Pass color settings
                            layout_config                # ✨ ENHANCED: Pass layout config
                        )
                        
                    elif ENHANCED_RENDERER_AVAILABLE:
                        # 🔄 USE ENHANCED RENDERER with legacy ftg_position
                        ftg_position = self.settings.get('ftg_position', 'bottom_right')
                        
                        print(f"🔄 ENHANCED RENDERER: Using legacy position mode: {ftg_position}")
                        
                        frame_with_overlay = draw_fps_overlay_with_legacy_position(
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
                            ftg_position
                        )
                        
                    else:
                        # 🔄 FALLBACK to legacy renderer
                        if not LEGACY_RENDERER_AVAILABLE:
                            raise RuntimeError("No overlay renderer available")
                            
                        ftg_position = self.settings.get('ftg_position', 'bottom_right')
                        
                        print(f"🔄 LEGACY RENDERER: Using ftg_position: {ftg_position}")
                        
                        frame_with_overlay = legacy_draw_function(
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
                    print(f"❌ ANALYSIS DEBUG: overlay rendering failed: {e}")
                    # Ultimate fallback to legacy renderer
                    if LEGACY_RENDERER_AVAILABLE:
                        ftg_position = self.settings.get('ftg_position', 'bottom_right')
                        frame_with_overlay = legacy_draw_function(
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
                    else:
                        # No renderer available, create a simple overlay
                        print("❌ No overlay renderer available, creating minimal overlay")
                        frame_with_overlay = frame_rgb.copy()
                        # Add minimal FPS text
                        import cv2
                        cv2.putText(frame_with_overlay, f"FPS: {displayed_fps:.1f}", (50, 50), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                
                # Convert back to BGR for video writer
                frame_bgr = cv2.cvtColor(frame_with_overlay, cv2.COLOR_RGB2BGR)
                out.write(frame_bgr)
                
                # Update for next iteration
                prev_frame_gray = gray
                frame_count += 1
                
                # Update progress and preview
                progress = 10 + int((frame_count / total_frames) * 85)
                
                # Status message including renderer info
                if len(recent_frames) >= 60:
                    unique_in_window = len(set(recent_frames))
                    status_msg = f"Frame {frame_count}/{total_frames} - FPS: {displayed_fps:.1f} - {renderer_info}"
                    if is_duplicate:
                        status_msg += " (Duplicate)"
                else:
                    status_msg = f"Frame {frame_count}/{total_frames} - Building window: {len(recent_frames)}/60 - {renderer_info}"
                
                self.progress_update.emit(progress, status_msg)
                
                # Send preview frame occasionally
                if frame_count % 30 == 0:
                    self.frame_preview.emit(frame_bgr)
            
            # Clean up
            cap.release()
            out.release()
            
            if not self.is_cancelled:
                final_msg = f"Analysis completed! {renderer_info} with {layout_info} applied successfully"
                self.progress_update.emit(100, final_msg)
                self.analysis_complete.emit(True, f"FPS Analysis completed with {renderer_info}!")
            else:
                self.analysis_complete.emit(False, "Analysis cancelled")
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"❌ ANALYSIS ERROR: {error_details}")
            self.analysis_complete.emit(False, f"Analysis failed: {str(e)}")