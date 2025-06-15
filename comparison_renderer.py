"""
Comparison Renderer für FPS Analyzer
Specialized renderer for side-by-side video comparisons with adaptive resolution support
UPDATED VERSION - Supports multiple comparison resolutions
"""
import cv2
import numpy as np
from color_manager import hex_to_bgr

def center_crop_frame(frame, target_width, target_height):
    """
    Center-crop a frame to target dimensions - ADAPTIVE VERSION
    
    Args:
        frame: Input frame (BGR)
        target_width: Target width (e.g., 640, 960, 1280, 1920)
        target_height: Target height (e.g., 720, 1080, 1440, 2160)
    
    Returns:
        Center-cropped frame at exact target dimensions
    """
    h, w = frame.shape[:2]
    
    print(f"🎯 CENTER_CROP: Input {w}x{h} → Target {target_width}x{target_height}")
    
    # Step 1: Center-crop width
    if w > target_width:
        crop_x_start = (w - target_width) // 2
        crop_x_end = crop_x_start + target_width
        frame_cropped = frame[:, crop_x_start:crop_x_end]
        print(f"✂️ WIDTH CROPPED: {w} → {target_width}")
    elif w < target_width:
        # Add padding if source is narrower
        padding_left = (target_width - w) // 2
        padding_right = target_width - w - padding_left
        frame_cropped = cv2.copyMakeBorder(
            frame, 0, 0, padding_left, padding_right, 
            cv2.BORDER_CONSTANT, value=(0, 0, 0)
        )
        print(f"📏 WIDTH PADDED: {w} → {target_width}")
    else:
        frame_cropped = frame
        print(f"✅ WIDTH MATCH: {w}")
    
    # Step 2: Handle height
    current_height = frame_cropped.shape[0]
    if current_height != target_height:
        frame_final = cv2.resize(frame_cropped, (target_width, target_height), 
                               interpolation=cv2.INTER_LANCZOS4)
        print(f"🔄 HEIGHT RESIZED: {current_height} → {target_height}")
    else:
        frame_final = frame_cropped
        print(f"✅ HEIGHT MATCH: {current_height}")
    
    print(f"✅ FINAL: {frame_final.shape[1]}x{frame_final.shape[0]}")
    return frame_final

def draw_text_with_border(img, text, position, font, font_scale, color, thickness, 
                         border_color=(0, 0, 0), border_thickness=2):
    """Helper method for anti-aliased text with border"""
    x, y = position
    line_type = cv2.LINE_AA
    
    # Draw border with multiple layers for smooth effect
    for offset in range(border_thickness, 0, -1):
        for dx in range(-offset, offset + 1):
            for dy in range(-offset, offset + 1):
                if dx != 0 or dy != 0:
                    cv2.putText(img, text, (x + dx, y + dy), font, font_scale, 
                               border_color, thickness + offset, lineType=line_type)
    
    # Draw main text with anti-aliasing
    cv2.putText(img, text, position, font, font_scale, color, thickness, lineType=line_type)

def get_adaptive_layout_config(width, height, debug=False):
    """
    Get adaptive layout configuration based on comparison resolution
    FIXED VERSION - Proper scaling and positioning for all resolutions with relative stats positioning
    
    Args:
        width: Frame width (640, 960, 1280, 1920)
        height: Frame height (720, 1080, 1440, 2160)
        debug: Whether to print debug information
    
    Returns:
        Layout configuration dict with scaled positions and sizes
    """
    # Calculate scaling factors relative to 1080p comparison (960x1080)
    base_width = 960
    base_height = 1080
    
    width_scale = width / base_width
    height_scale = height / base_height
    
    # Ensure minimum scaling to prevent too small elements
    min_scale = min(width_scale, height_scale)
    safe_scale = max(min_scale, 0.5)  # Never scale below 50%
    
    if debug:
        print(f"📐 ADAPTIVE LAYOUT: {width}x{height}, Scale: {width_scale:.2f}x{height_scale:.2f}, Safe: {safe_scale:.2f}")
    
    # Base sizes (optimized for all resolutions)
    base_graph_height = min(120, int(height * 0.13))  # 13% of height, max 120px
    base_margin = max(30, int(height * 0.03))  # 3% of height, min 30px
    
    # Calculate graph position first
    graph_width = int(width * 0.80)  # Reduced from 85% to 80% for better fit
    graph_x = int((width - graph_width) // 2)
    graph_y = max(height - base_graph_height - base_margin - 40, height - 200)  # Ensure graph is always visible
    
    # ✨ FIXED: Calculate stats position RELATIVE to graph
    stats_margin = max(15, int(20 * height_scale))  # ✨ ADJUSTED: More spacing below graph
    stats_y = graph_y + base_graph_height + stats_margin
    
    # Safety check: Ensure stats don't go below screen
    max_stats_y = height - max(20, int(30 * height_scale))
    if stats_y > max_stats_y:
        stats_y = max_stats_y
        # If stats would be too low, move graph up
        graph_y = stats_y - base_graph_height - stats_margin
        if debug:
            print(f"⚠️ Layout adjusted: moved graph up to fit stats")
    
    config = {
        'fps_display': {
            'position': (int(30 * width_scale), int(50 * height_scale)),
            'font_scale': max(0.8, 1.2 * safe_scale),  # Minimum font scale
            'thickness': max(2, int(3 * safe_scale))
        },
        'fps_label': {
            'position': (int(30 * width_scale), int(85 * height_scale)),
            'font_scale': max(0.5, 0.7 * safe_scale),  # Minimum font scale
            'thickness': max(1, int(2 * safe_scale))
        },
        'graph': {
            'width': graph_width,
            'height': base_graph_height,
            'x': graph_x,
            'y': graph_y,
            'line_thickness': max(2, int(3 * safe_scale))
        },
        'stats': {
            'y': stats_y,  # ✨ Now relative to graph position
            'spacing': int(max(80, 90 * width_scale)),  # Responsive spacing with minimum
            'font_scale': max(0.3, 0.35 * safe_scale),  # Minimum font scale
            'thickness': max(1, int(1 * safe_scale))
        }
    }
    
    if debug:
        print(f"📊 LAYOUT POSITIONS:")
        print(f"   Graph: {graph_width}x{base_graph_height} at ({graph_x}, {graph_y})")
        print(f"   Stats: y={stats_y} (graph_y + {base_graph_height} + {stats_margin})")
    
    return config

def create_simplified_comparison_overlay(frame_rgb, fps_history, displayed_fps, 
                                       video_name="Video", global_fps_values=None,
                                       font_settings=None, color_settings=None, debug=False):
    """
    Create simplified overlay for comparison videos with adaptive resolution support
    
    Only includes:
    - FPS Number (top-left)
    - FPS Graph (center-bottom)
    - Statistics (under graph)
    
    Args:
        frame_rgb: RGB frame (variable resolution: 640x720, 960x1080, 1280x1440, 1920x2160)
        fps_history: List of FPS values
        displayed_fps: Current FPS value
        video_name: Name of the video
        global_fps_values: All FPS values for statistics
        font_settings: Font configuration
        color_settings: Color configuration
        debug: Whether to print debug information
    
    Returns:
        Frame with simplified overlay scaled to frame resolution
    """
    h, w, _ = frame_rgb.shape
    overlay = frame_rgb.copy()
    
    if debug:
        print(f"🎨 COMPARISON OVERLAY: Rendering for {w}x{h}")
    
    # Get adaptive layout configuration
    layout = get_adaptive_layout_config(w, h, debug=debug)
    
    # Get settings with fallbacks
    if font_settings is None:
        font_settings = {}
    if color_settings is None:
        color_settings = {'framerate_color': '#00FF00'}
    
    # Extract font settings
    fps_font_settings = font_settings.get('fps_font')
    framerate_font_settings = font_settings.get('framerate_font')
    
    # Framerate color
    framerate_color = hex_to_bgr(color_settings.get('framerate_color', '#00FF00'))
    
    # **1. FPS NUMBER (Top-Left) - ADAPTIVE**
    fps_text = f"{displayed_fps:.1f}"
    
    # Adaptive font properties for FPS number
    if fps_font_settings and hasattr(fps_font_settings, 'get_opencv_font'):
        fps_font = fps_font_settings.get_opencv_font()
        fps_scale = layout['fps_display']['font_scale']
        fps_thickness = layout['fps_display']['thickness']
        fps_border = max(1, int(fps_font_settings.border_thickness * min(w/960, h/1080)))
    else:
        fps_font = cv2.FONT_HERSHEY_SIMPLEX
        fps_scale = layout['fps_display']['font_scale']
        fps_thickness = layout['fps_display']['thickness']
        fps_border = 2
    
    # Color coding based on FPS
    if displayed_fps >= 55:
        fps_color = (0, 255, 0)  # Green
    elif displayed_fps >= 30:
        fps_color = (0, 200, 255)  # Orange
    else:
        fps_color = (0, 50, 255)  # Red
    
    # Draw FPS number
    fps_pos = layout['fps_display']['position']
    draw_text_with_border(overlay, fps_text, fps_pos, fps_font, fps_scale, 
                         fps_color, fps_thickness, border_thickness=fps_border)
    
    # Draw "FPS" label
    label_pos = layout['fps_label']['position']
    draw_text_with_border(overlay, "FPS", label_pos, fps_font, layout['fps_label']['font_scale'], 
                         (255, 255, 255), layout['fps_label']['thickness'], border_thickness=fps_border)

    # **2. FPS GRAPH (Center-Bottom) - ADAPTIVE**
    if len(fps_history) >= 2:
        # Adaptive graph dimensions
        graph_config = layout['graph']
        graph_width = graph_config['width']
        graph_height = graph_config['height']
        graph_x = graph_config['x']
        graph_y = graph_config['y']
        line_thickness = graph_config['line_thickness']
        
        if debug:
            print(f"📊 GRAPH: {graph_width}x{graph_height} at ({graph_x}, {graph_y})")
        
        # Background with transparency
        background_overlay = overlay.copy()
        cv2.rectangle(background_overlay, (graph_x-8, graph_y-8), 
                     (graph_x + graph_width + 8, graph_y + graph_height + 8), 
                     (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.75, background_overlay, 0.25, 0, overlay)
        
        # Border
        cv2.rectangle(overlay, (graph_x-8, graph_y-8), 
                     (graph_x + graph_width + 8, graph_y + graph_height + 8), 
                     (100, 100, 100), 2)
        
        # Grid lines
        max_fps = 60
        grid_values = [60, 45, 30, 15, 0]
        
        for fps_val in grid_values:
            y_pos = graph_y + graph_height - int((fps_val / max_fps) * graph_height)
            line_color = (80, 80, 80) if fps_val == 30 else (60, 60, 60)
            grid_line_thickness = 2 if fps_val == 30 else 1
            cv2.line(overlay, (graph_x, y_pos), (graph_x + graph_width, y_pos), 
                    line_color, grid_line_thickness)
        
        # Grid labels - adaptive font
        if framerate_font_settings and hasattr(framerate_font_settings, 'get_opencv_font'):
            grid_font = framerate_font_settings.get_opencv_font()
            grid_scale = framerate_font_settings.size * 0.8 * min(w/960, h/1080)
            grid_thickness = max(1, framerate_font_settings.get_effective_thickness() - 1)
            grid_border = max(1, framerate_font_settings.border_thickness - 1)
        else:
            grid_font = cv2.FONT_HERSHEY_SIMPLEX
            grid_scale = 0.5 * min(w/960, h/1080)
            grid_thickness = 1
            grid_border = 1
        
        for fps_val in [60, 30, 0]:
            y_pos = graph_y + graph_height - int((fps_val / max_fps) * graph_height)
            label_x = graph_x + graph_width + int(10 * w/960)
            draw_text_with_border(overlay, f"{fps_val}", (label_x, y_pos + 5), 
                                 grid_font, grid_scale, (255, 255, 255), grid_thickness, 
                                 border_thickness=grid_border)
        
        # Graph title
        title_y = graph_y - int(20 * h/1080)
        draw_text_with_border(overlay, "FRAME RATE", (graph_x, title_y), 
                             grid_font, grid_scale * 1.2, (255, 255, 255), grid_thickness + 1, 
                             border_thickness=grid_border)
        
        # FPS line - adaptive thickness
        max_len = 180
        hist = list(fps_history)[-max_len:] if len(fps_history) > max_len else list(fps_history)
        
        if len(hist) >= 2:
            fps_points = []
            for i, fps_val in enumerate(hist):
                progress = i / (len(hist) - 1) if len(hist) > 1 else 0
                x = graph_x + int(graph_width * progress)
                y = graph_y + graph_height - int((min(fps_val, max_fps) / max_fps) * graph_height)
                fps_points.append((x, y))
            
            # Draw line segments with adaptive thickness
            for i in range(len(fps_points) - 1):
                cv2.line(overlay, fps_points[i], fps_points[i + 1], framerate_color, 
                        line_thickness, cv2.LINE_AA)
            
            # Draw current point
            if fps_points:
                current_point = fps_points[-1]
                point_radius = max(3, int(4 * min(w/960, h/1080)))
                cv2.circle(overlay, current_point, point_radius, framerate_color, -1)
                cv2.circle(overlay, current_point, point_radius + 2, (255, 255, 255), 2)
    
    # **3. FPS STATISTICS (Under Frame Rate Graph) - ADAPTIVE**
    if len(fps_history) >= 2 and global_fps_values and len(global_fps_values) > 0:
        stats_config = layout['stats']
        stats_y = stats_config['y']
        stats_spacing = stats_config['spacing']
        stats_font_scale = stats_config['font_scale']
        stats_thickness = stats_config['thickness']
        
        avg_fps = sum(global_fps_values) / len(global_fps_values)
        min_fps = min(global_fps_values)
        max_fps = max(global_fps_values)
        
        # Draw stats horizontally under graph with adaptive spacing
        graph_x = layout['graph']['x']
        
        draw_text_with_border(overlay, f"AVG: {avg_fps:.1f}", (graph_x, stats_y), 
                            fps_font, stats_font_scale, (255, 255, 255), stats_thickness, border_thickness=1)
        draw_text_with_border(overlay, f"MIN: {min_fps:.1f}", (graph_x + stats_spacing, stats_y), 
                            fps_font, stats_font_scale, (255, 255, 255), stats_thickness, border_thickness=1)
        draw_text_with_border(overlay, f"MAX: {max_fps:.1f}", (graph_x + stats_spacing * 2, stats_y), 
                            fps_font, stats_font_scale, (255, 255, 255), stats_thickness, border_thickness=1)
    
    return overlay

def draw_graphs_only_transparent(fps_history, frame_times, show_frametime, max_len,
                                frametime_scale, font_settings, color_settings, 
                                ftg_position, width, height):
    """
    Draw graphs only on transparent background for PNG export with adaptive resolution
    
    Args:
        fps_history: List of FPS values
        frame_times: List of frame time values (can be None)
        show_frametime: Whether to show frame time graph
        max_len: Maximum length of history
        frametime_scale: Frame time scale settings
        font_settings: Font configuration
        color_settings: Color configuration
        ftg_position: Position for frame time graph
        width: Canvas width (adaptive)
        height: Canvas height (adaptive)
    
    Returns:
        RGBA image with transparent background
    """
    # Create transparent canvas (RGBA)
    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    
    print(f"🎬 PNG EXPORT: Creating transparent overlay for {width}x{height}")
    
    # Get adaptive layout configuration
    layout = get_adaptive_layout_config(width, height)
    
    # Only draw FPS graph for comparison mode (simplified)
    if len(fps_history) >= 2:
        # Adaptive graph dimensions
        graph_config = layout['graph']
        graph_width = graph_config['width']
        graph_height = graph_config['height']
        graph_x = graph_config['x']
        graph_y = graph_config['y']
        line_thickness = graph_config['line_thickness']
        
        # Framerate color
        framerate_color = hex_to_bgr(color_settings.get('framerate_color', '#00FF00'))
        
        # FPS line
        hist = fps_history[-max_len:] if len(fps_history) > max_len else fps_history
        
        if len(hist) >= 2:
            fps_points = []
            max_fps = 60
            
            for i, fps_val in enumerate(hist):
                progress = i / (len(hist) - 1) if len(hist) > 1 else 0
                x = graph_x + int(graph_width * progress)
                y = graph_y + graph_height - int((min(fps_val, max_fps) / max_fps) * graph_height)
                fps_points.append((x, y))
            
            # Draw line on RGBA canvas with adaptive thickness
            for i in range(len(fps_points) - 1):
                color_rgba = (*framerate_color, 255)  # Full opacity
                cv2.line(canvas, fps_points[i], fps_points[i + 1], color_rgba, line_thickness, cv2.LINE_AA)
    
    return canvas

# Export function for PNG sequences (comparison mode with adaptive resolution)
def export_comparison_png_sequence(input_file, output_dir, video_name, settings):
    """
    Export PNG sequence for comparison video with adaptive resolution support
    
    Args:
        input_file: Input video path
        output_dir: Output directory
        video_name: Name of the video
        settings: Analysis settings (includes comparison_resolution)
    
    Returns:
        (success, message, frame_count)
    """
    import collections
    import os
    
    try:
        # Get comparison resolution from settings
        comparison_resolution = settings.get('comparison_resolution', (960, 1080))
        resolution_name = settings.get('resolution_name', '1080p')
        target_width, target_height = comparison_resolution
        
        print(f"🎬 PNG EXPORT: {resolution_name} ({target_width}x{target_height})")
        
        # Open video
        cap = cv2.VideoCapture(input_file)
        if not cap.isOpened():
            raise ValueError("Could not open input video")
        
        # Get video properties
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        source_fps = cap.get(cv2.CAP_PROP_FPS)
        
        # Analysis variables
        fps_history = collections.deque(maxlen=1000)
        prev_frame_gray = None
        frame_count = 0
        recent_frames = collections.deque(maxlen=60)
        
        # Create output subdirectory with resolution info
        png_output_dir = os.path.join(output_dir, f"{video_name}_{resolution_name}_png_sequence")
        os.makedirs(png_output_dir, exist_ok=True)
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Center-crop frame to target resolution
            frame_cropped = center_crop_frame(frame, target_width, target_height)
            
            # Analysis (same as main analysis)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small_frame = cv2.resize(gray, (64, 64))
            frame_hash = hash(small_frame.tobytes())
            
            recent_frames.append(frame_hash)
            
            # Calculate FPS
            if len(recent_frames) >= 60:
                unique_count = len(set(recent_frames))
                effective_fps = unique_count
            else:
                if len(recent_frames) > 0:
                    unique_count = len(set(recent_frames))
                    effective_fps = unique_count * (60 / len(recent_frames))
                    effective_fps = min(effective_fps, source_fps)
                else:
                    effective_fps = source_fps
            
            fps_history.append(effective_fps)
            
            # Create transparent overlay with adaptive resolution
            transparent_overlay = draw_graphs_only_transparent(
                list(fps_history), None, False, 180,
                settings.get('frametime_scale', {}),
                settings.get('font_settings', {}),
                settings.get('color_settings', {}),
                'bottom_center', target_width, target_height
            )
            
            # Save PNG with resolution info in filename
            frame_filename = f"{video_name}_{resolution_name}_graph_{frame_count:06d}.png"
            frame_path = os.path.join(png_output_dir, frame_filename)
            cv2.imwrite(frame_path, transparent_overlay)
            
            frame_count += 1
            prev_frame_gray = gray
        
        cap.release()
        return True, png_output_dir, frame_count
        
    except Exception as e:
        return False, str(e), 0