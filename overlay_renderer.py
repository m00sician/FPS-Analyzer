"""
Overlay Rendering Module für FPS Analyzer - FIXED FTG POSITION & STATS
Handles the FPS overlay generation with corrected Frame Time Graph positioning
"""
import cv2
import numpy as np
from color_manager import hex_to_bgr

def draw_text_with_border(img, text, position, font, font_scale, color, thickness, border_color=(0, 0, 0), border_thickness=2):
    """Draw text with black border for better visibility - IMPROVED SMOOTHING"""
    x, y = position
    
    # 🎨 IMPROVED: Better anti-aliasing with LINE_AA
    line_type = cv2.LINE_AA  # Anti-aliased rendering for smoother text
    
    # Draw border (black outline) with multiple layers for smoother effect
    border_offsets = []
    for dx in range(-border_thickness, border_thickness + 1):
        for dy in range(-border_thickness, border_thickness + 1):
            if dx != 0 or dy != 0:  # Skip center
                border_offsets.append((dx, dy))
    
    # Sort offsets by distance for better layering
    border_offsets.sort(key=lambda offset: offset[0]**2 + offset[1]**2)
    
    # Draw border with gradual thickness
    for dx, dy in border_offsets:
        cv2.putText(img, text, (x + dx, y + dy), font, font_scale, border_color, 
                   thickness + 1, lineType=line_type)
    
    # Draw main text with anti-aliasing
    cv2.putText(img, text, position, font, font_scale, color, thickness, lineType=line_type)

def get_opencv_font_from_name(font_name):
    """Convert font name to OpenCV font constant"""
    font_mapping = {
        'Arial': cv2.FONT_HERSHEY_SIMPLEX,
        'Times New Roman': cv2.FONT_HERSHEY_COMPLEX,
        'Courier New': cv2.FONT_HERSHEY_DUPLEX,
        'Helvetica': cv2.FONT_HERSHEY_SIMPLEX,
        'Verdana': cv2.FONT_HERSHEY_PLAIN,
        'Georgia': cv2.FONT_HERSHEY_COMPLEX,
        'Consolas': cv2.FONT_HERSHEY_DUPLEX,
        'Bebas Neue': cv2.FONT_HERSHEY_COMPLEX,
        'Roboto': cv2.FONT_HERSHEY_SIMPLEX,
        'Open Sans': cv2.FONT_HERSHEY_PLAIN,
        'Orbitron': cv2.FONT_HERSHEY_COMPLEX,
        'Exo 2': cv2.FONT_HERSHEY_TRIPLEX,
        # OpenCV font names direkt
        'HERSHEY_SIMPLEX': cv2.FONT_HERSHEY_SIMPLEX,
        'HERSHEY_PLAIN': cv2.FONT_HERSHEY_PLAIN,
        'HERSHEY_DUPLEX': cv2.FONT_HERSHEY_DUPLEX,
        'HERSHEY_COMPLEX': cv2.FONT_HERSHEY_COMPLEX,
        'HERSHEY_TRIPLEX': cv2.FONT_HERSHEY_TRIPLEX,
        'HERSHEY_COMPLEX_SMALL': cv2.FONT_HERSHEY_COMPLEX_SMALL,
        'HERSHEY_SCRIPT_SIMPLEX': cv2.FONT_HERSHEY_SCRIPT_SIMPLEX,
        'HERSHEY_SCRIPT_COMPLEX': cv2.FONT_HERSHEY_SCRIPT_COMPLEX
    }
    
    return font_mapping.get(font_name, cv2.FONT_HERSHEY_SIMPLEX)

def get_opencv_font_scale_from_qfont(qfont, base_scale=1.0):
    """Convert QFont to OpenCV font scale"""
    if hasattr(qfont, 'pointSize'):  # QFont
        point_size = qfont.pointSize()
        if point_size <= 0:
            point_size = 12  # fallback
        
        # Scaling formula for readability
        scale = (point_size / 12.0) * base_scale
        return max(0.4, min(scale, 3.0))  # Reasonable range
    else:  # OpenCVFontSettings - use size directly
        return qfont.size * base_scale if hasattr(qfont, 'size') else base_scale

def get_opencv_font_thickness_from_qfont(qfont, base_thickness=1):
    """Get OpenCV font thickness based on QFont weight or OpenCVFontSettings"""
    if hasattr(qfont, 'weight'):  # QFont
        weight = qfont.weight()
        # QFont weights: Light=25, Normal=50, DemiBold=63, Bold=75, Black=87
        if weight >= 75:  # Bold
            return base_thickness + 2
        elif weight >= 63:  # DemiBold
            return base_thickness + 1
        else:  # Normal/Light
            return base_thickness
    elif hasattr(qfont, 'get_effective_thickness'):  # OpenCVFontSettings
        return qfont.get_effective_thickness()
    else:
        return base_thickness

def draw_fps_overlay(frame, fps_history, current_fps, frame_times=None, show_frame_time_graph=True, 
                    max_len=180, global_fps_values=None, global_frame_times=None, 
                    frametime_scale=None, font_settings=None, color_settings=None, ftg_position="bottom_right"):
    """Enhanced FPS overlay with CORRECTED FTG positioning and stats placement"""
    h, w, _ = frame.shape
    overlay = frame.copy()
    
    # Scale factor based on resolution (1080p as baseline)
    scale_factor = min(w / 1920, h / 1080)
    scale_factor = max(0.5, min(scale_factor, 2.0))
    
    # Extract font settings
    fps_font_settings = font_settings.get('fps_font') if font_settings else None
    framerate_font_settings = font_settings.get('framerate_font') if font_settings else None
    frametime_font_settings = font_settings.get('frametime_font') if font_settings else None
    
    # FPS Font Processing
    try:
        if hasattr(fps_font_settings, 'get_opencv_font') and hasattr(fps_font_settings, 'font_name'):
            fps_opencv_font = fps_font_settings.get_opencv_font()
            fps_font_scale = fps_font_settings.size * scale_factor
            fps_font_thickness = fps_font_settings.get_effective_thickness()
            fps_border_thickness = fps_font_settings.border_thickness
        elif hasattr(fps_font_settings, 'family'):
            fps_opencv_font = get_opencv_font_from_name(fps_font_settings.family())
            fps_font_scale = get_opencv_font_scale_from_qfont(fps_font_settings, scale_factor * 1.2)
            fps_font_thickness = get_opencv_font_thickness_from_qfont(fps_font_settings, 2)
            fps_border_thickness = 2
        else:
            fps_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
            fps_font_scale = 1.2 * scale_factor
            fps_font_thickness = 3
            fps_border_thickness = 2
    except Exception as e:
        fps_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
        fps_font_scale = 1.2 * scale_factor
        fps_font_thickness = 3
        fps_border_thickness = 2
    
    # Framerate Font Processing
    try:
        if hasattr(framerate_font_settings, 'get_opencv_font') and hasattr(framerate_font_settings, 'font_name'):
            framerate_opencv_font = framerate_font_settings.get_opencv_font()
            framerate_font_scale = framerate_font_settings.size * scale_factor
            framerate_font_thickness = framerate_font_settings.get_effective_thickness()
            framerate_border_thickness = framerate_font_settings.border_thickness
        elif hasattr(framerate_font_settings, 'family'):
            framerate_opencv_font = get_opencv_font_from_name(framerate_font_settings.family())
            framerate_font_scale = get_opencv_font_scale_from_qfont(framerate_font_settings, scale_factor * 0.8)
            framerate_font_thickness = get_opencv_font_thickness_from_qfont(framerate_font_settings, 1)
            framerate_border_thickness = 1
        else:
            framerate_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
            framerate_font_scale = 0.6 * scale_factor
            framerate_font_thickness = 1
            framerate_border_thickness = 1
    except Exception as e:
        framerate_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
        framerate_font_scale = 0.6 * scale_factor
        framerate_font_thickness = 1
        framerate_border_thickness = 1
    
    # Frametime Font Processing
    try:
        if hasattr(frametime_font_settings, 'get_opencv_font') and hasattr(frametime_font_settings, 'font_name'):
            frametime_opencv_font = frametime_font_settings.get_opencv_font()
            frametime_font_scale = frametime_font_settings.size * scale_factor
            frametime_font_thickness = frametime_font_settings.get_effective_thickness()
            frametime_border_thickness = frametime_font_settings.border_thickness
        elif hasattr(frametime_font_settings, 'family'):
            frametime_opencv_font = get_opencv_font_from_name(frametime_font_settings.family())
            frametime_font_scale = get_opencv_font_scale_from_qfont(frametime_font_settings, scale_factor * 0.8)
            frametime_font_thickness = get_opencv_font_thickness_from_qfont(frametime_font_settings, 1)
            frametime_border_thickness = 1
        else:
            frametime_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
            frametime_font_scale = 0.5 * scale_factor
            frametime_font_thickness = 1
            frametime_border_thickness = 1
    except Exception as e:
        frametime_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
        frametime_font_scale = 0.5 * scale_factor
        frametime_font_thickness = 1
        frametime_border_thickness = 1
    
    # Color settings
    if color_settings is None:
        color_settings = {
            'framerate_color': '#00FF00',
            'frametime_color': '#00FF00'
        }
    
    framerate_color_hex = color_settings.get('framerate_color', '#00FF00')
    frametime_color_hex = color_settings.get('frametime_color', '#00FF00')
    
    # Get RGB colors
    framerate_color_rgb = hex_to_bgr(framerate_color_hex)
    frametime_color_rgb = hex_to_bgr(frametime_color_hex)
    
    # Current FPS display in top-left corner
    fps_display_x = int(30 * scale_factor)
    fps_display_y = int(70 * scale_factor)
    
    # Large FPS number with color coding
    fps_color = (0, 255, 0) if current_fps >= 55 else (0, 200, 255) if current_fps >= 30 else (0, 50, 255)
    draw_text_with_border(overlay, f"{current_fps:.1f}", 
                         (fps_display_x, fps_display_y - int(10 * scale_factor)),
                         fps_opencv_font, fps_font_scale, fps_color, fps_font_thickness, 
                         border_thickness=fps_border_thickness)
    draw_text_with_border(overlay, "FPS", 
                         (fps_display_x, fps_display_y + int(20 * scale_factor)),
                         fps_opencv_font, fps_font_scale * 0.6, (255, 255, 255), fps_font_thickness,
                         border_thickness=fps_border_thickness)
    
    # Graph dimensions
    base_graph_width = 1090
    base_graph_height = 200
    graph_width = int(base_graph_width * scale_factor)
    graph_height = int(base_graph_height * scale_factor)
    
    # Framerate graph position
    fps_graph_x = int(50 * scale_factor)
    fps_graph_y = h - graph_height - int(50 * scale_factor)
    
    # Draw framerate graph background
    background_overlay = overlay.copy()
    cv2.rectangle(background_overlay, (fps_graph_x - int(10 * scale_factor), fps_graph_y - int(20 * scale_factor)), 
                 (fps_graph_x + graph_width + int(10 * scale_factor), fps_graph_y + graph_height + int(20 * scale_factor)), 
                 (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.7, background_overlay, 0.3, 0, overlay)
    
    # Graph border
    cv2.rectangle(overlay, (fps_graph_x - int(10 * scale_factor), fps_graph_y - int(20 * scale_factor)), 
                 (fps_graph_x + graph_width + int(10 * scale_factor), fps_graph_y + graph_height + int(20 * scale_factor)), 
                 (100, 100, 100), max(1, int(2 * scale_factor)))
    
    # Frame Rate graph title
    draw_text_with_border(overlay, "FRAME RATE", 
                         (fps_graph_x, fps_graph_y - int(25 * scale_factor)),
                         framerate_opencv_font, framerate_font_scale * 1.2, (255, 255, 255), framerate_font_thickness,
                         border_thickness=framerate_border_thickness)
    
    # Draw horizontal grid lines and labels
    fps_grid_values = [60, 45, 30, 15, 0]
    fps_labels_left = [60, 30, 0]
    
    for fps_val in fps_grid_values:
        y_pos = fps_graph_y + graph_height - int((fps_val / 60.0) * graph_height)
        line_color = (60, 60, 60) if fps_val not in [30] else (80, 80, 80)
        cv2.line(overlay, (fps_graph_x, y_pos), (fps_graph_x + graph_width, y_pos), 
                line_color, max(1, int(1 * scale_factor)))
        
        if fps_val in fps_labels_left:
            # Frame Rate labels (60, 30, 0) - positioned on lines
            draw_text_with_border(overlay, f"{fps_val}", 
                                 (fps_graph_x + graph_width + int(5 * scale_factor), y_pos + int(5 * scale_factor)),
                                 framerate_opencv_font, framerate_font_scale * 0.8, (255, 255, 255), framerate_font_thickness, 
                                 border_thickness=framerate_border_thickness)
    
    # Draw framerate line
    hist = fps_history[-max_len:] if len(fps_history) > max_len else fps_history
    if len(hist) >= 2:
        fps_points = []
        for i, fps_val in enumerate(hist):
            progress = i / (max_len - 1) if max_len > 1 else 0
            x = fps_graph_x + int(graph_width * progress)
            y = fps_graph_y + graph_height - int((min(fps_val, 60) / 60.0) * graph_height)
            fps_points.append((x, y))
        
        for i in range(len(fps_points) - 1):
            cv2.line(overlay, fps_points[i], fps_points[i + 1], framerate_color_rgb, max(2, int(3 * scale_factor)))
    
    # 🔧 FIXED: Frame Time graph with corrected positioning and stats
    ft_graph_x = 0  # Initialize variables to avoid UnboundLocalError
    ft_graph_y = 0
    ft_graph_width = 0
    ft_graph_height = 0
    
    if show_frame_time_graph and frame_times and len(frame_times) >= 2:
        ft_graph_width = int(400 * scale_factor)
        ft_graph_height = int(120 * scale_factor)
        
        # Position based on ftg_position setting
        if ftg_position == "bottom_left":
            # 🔧 CORRECTED: 30 pixels higher as requested
            ft_graph_x = fps_graph_x  # Same X as Frame Rate graph
            ft_graph_y = fps_graph_y - ft_graph_height - int(70 * scale_factor)  # 30px higher than before
            print(f"🔧 FTG Position: bottom_left - X:{ft_graph_x}, Y:{ft_graph_y} (30px higher)")
        elif ftg_position == "top_right":
            # Top right position
            ft_graph_x = w - ft_graph_width - int(50 * scale_factor)
            ft_graph_y = int(50 * scale_factor)
        else:  # "bottom_right" (default)
            # Standard bottom right position
            ft_graph_x = w - ft_graph_width - int(50 * scale_factor)
            ft_graph_y = h - ft_graph_height - int(50 * scale_factor)
        
        if frametime_scale is None:
            frametime_scale = {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']}
        
        ft_min = frametime_scale['min']
        ft_mid = frametime_scale['mid'] 
        ft_max = frametime_scale['max']
        ft_labels = frametime_scale['labels']
        
        # Draw frame time graph background
        background_overlay = overlay.copy()
        cv2.rectangle(background_overlay, (ft_graph_x - int(10 * scale_factor), ft_graph_y - int(20 * scale_factor)), 
                     (ft_graph_x + ft_graph_width + int(10 * scale_factor), ft_graph_y + ft_graph_height + int(20 * scale_factor)), 
                     (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.7, background_overlay, 0.3, 0, overlay)
        
        cv2.rectangle(overlay, (ft_graph_x - int(10 * scale_factor), ft_graph_y - int(20 * scale_factor)), 
                     (ft_graph_x + ft_graph_width + int(10 * scale_factor), ft_graph_y + ft_graph_height + int(20 * scale_factor)), 
                     (100, 100, 100), max(1, int(1 * scale_factor)))
        
        # Frame time graph title
        draw_text_with_border(overlay, "FRAME TIME", 
                             (ft_graph_x, ft_graph_y - int(25 * scale_factor)),
                             frametime_opencv_font, frametime_font_scale * 1.1, (255, 255, 255), frametime_font_thickness,
                             border_thickness=frametime_border_thickness)
        
        # Grid lines and labels
        ft_grid_lines = [ft_min, ft_mid, ft_max]
        for i, (ft_val, label) in enumerate(zip(ft_grid_lines, ft_labels)):
            y_pos = ft_graph_y + ft_graph_height - int(((ft_val - ft_min) / (ft_max - ft_min)) * ft_graph_height)
            line_color = (60, 60, 60) if ft_val != ft_mid else (80, 80, 80)
            cv2.line(overlay, (ft_graph_x, y_pos), (ft_graph_x + ft_graph_width, y_pos), 
                    line_color, max(1, int(1 * scale_factor)))
            
            draw_text_with_border(overlay, f"{label}ms", 
                                 (ft_graph_x + ft_graph_width + int(5 * scale_factor), y_pos + int(5 * scale_factor)),
                                 frametime_opencv_font, frametime_font_scale * 0.7, (255, 255, 255), frametime_font_thickness, 
                                 border_thickness=frametime_border_thickness)
        
        # Draw frame time line
        ft_hist = frame_times[-max_len:] if len(frame_times) > max_len else frame_times
        if len(ft_hist) >= 2:
            ft_points = []
            for i, ft_val in enumerate(ft_hist):
                progress = i / (max_len - 1) if max_len > 1 else 0
                x = ft_graph_x + int(ft_graph_width * progress)
                clamped_ft = min(max(ft_val, ft_min), ft_max)
                y = ft_graph_y + ft_graph_height - int(((clamped_ft - ft_min) / (ft_max - ft_min)) * ft_graph_height)
                ft_points.append((x, y))
            
            for i in range(len(ft_points) - 1):
                cv2.line(overlay, ft_points[i], ft_points[i + 1], frametime_color_rgb, max(2, int(3 * scale_factor)))
    
    # Statistics
    if len(hist) > 0:
        stats_x = fps_graph_x
        stats_y = fps_graph_y + graph_height + int(35 * scale_factor)
        
        if global_fps_values and len(global_fps_values) > 0:
            avg_fps = sum(global_fps_values) / len(global_fps_values)
            min_fps = min(global_fps_values)
            max_fps = max(global_fps_values)
        else:
            avg_fps = sum(hist[-60:]) / min(60, len(hist))
            min_fps = min(hist[-60:]) if len(hist) >= 60 else min(hist)
            max_fps = max(hist[-60:]) if len(hist) >= 60 else max(hist)
        
        stats_font_size = framerate_font_scale * 0.8
        draw_text_with_border(overlay, f"AVG: {avg_fps:.1f}", 
                             (stats_x, stats_y),
                             framerate_opencv_font, stats_font_size, (255, 255, 255), framerate_font_thickness, 
                             border_thickness=framerate_border_thickness)
        draw_text_with_border(overlay, f"MIN: {min_fps:.1f}", 
                             (stats_x + int(120 * scale_factor), stats_y),
                             framerate_opencv_font, stats_font_size, (255, 255, 255), framerate_font_thickness, 
                             border_thickness=framerate_border_thickness)
        draw_text_with_border(overlay, f"MAX: {max_fps:.1f}", 
                             (stats_x + int(240 * scale_factor), stats_y),
                             framerate_opencv_font, stats_font_size, (255, 255, 255), framerate_font_thickness, 
                             border_thickness=framerate_border_thickness)
        
        # 🔧 FIXED: Frame time statistics - Position based on FTG location
        if show_frame_time_graph and frame_times and len(frame_times) > 0:
            # Calculate frame time stats
            if global_frame_times and len(global_frame_times) > 0:
                ft_avg = sum(global_frame_times) / len(global_frame_times)
                ft_max_recent = max(global_frame_times)
            else:
                ft_avg = sum(frame_times[-60:]) / min(60, len(frame_times))
                ft_max_recent = max(frame_times[-60:]) if len(frame_times) >= 60 else max(frame_times)
            
            # 🎯 SMART POSITIONING: Stats follow the Frame Time Graph position
            if ftg_position == "bottom_left" and show_frame_time_graph and ft_graph_x > 0:
                # 🎨 Position stats UNDER the Frame Time Graph when it's bottom-left AND graph is shown
                ft_stats_x = ft_graph_x  # Align with FTG
                ft_stats_y = ft_graph_y + ft_graph_height + int(35 * scale_factor)  # Below FTG
                print(f"🎨 FTG Stats: bottom_left position - X:{ft_stats_x}, Y:{ft_stats_y}")
            else:
                # For other positions or when FTG is not shown, keep stats in bottom right corner
                ft_stats_x = w - int(350 * scale_factor)
                ft_stats_y = h - int(20 * scale_factor)
            
            ft_stats_font_size = frametime_font_scale * 0.8
            draw_text_with_border(overlay, f"AVG: {ft_avg:.1f}ms", 
                                 (ft_stats_x, ft_stats_y),
                                 frametime_opencv_font, ft_stats_font_size, (255, 255, 255), frametime_font_thickness, 
                                 border_thickness=frametime_border_thickness)
            draw_text_with_border(overlay, f"MAX: {ft_max_recent:.1f}ms", 
                                 (ft_stats_x + int(140 * scale_factor), ft_stats_y),
                                 frametime_opencv_font, ft_stats_font_size, (255, 255, 255), frametime_font_thickness, 
                                 border_thickness=frametime_border_thickness)
    
    return overlay

def draw_complete_overlay_transparent(fps_history, current_fps, frame_times=None, show_frame_time_graph=True, 
                                    max_len=180, global_fps_values=None, global_frame_times=None,
                                    frametime_scale=None, font_settings=None, color_settings=None, 
                                    ftg_position="bottom_right", width=1920, height=1080):
    """🎬 NEW: Draw COMPLETE overlay on transparent background for PNG Alpha export"""
    
    # Create transparent background (RGBA)
    overlay = np.zeros((height, width, 4), dtype=np.uint8)
    
    # Scale factor based on resolution (1080p as baseline)
    scale_factor = min(width / 1920, height / 1080)
    scale_factor = max(0.5, min(scale_factor, 2.0))
    
    # Extract font settings
    fps_font_settings = font_settings.get('fps_font') if font_settings else None
    framerate_font_settings = font_settings.get('framerate_font') if font_settings else None
    frametime_font_settings = font_settings.get('frametime_font') if font_settings else None
    
    # FPS Font Processing (with fallbacks)
    try:
        if hasattr(fps_font_settings, 'get_opencv_font') and hasattr(fps_font_settings, 'font_name'):
            fps_opencv_font = fps_font_settings.get_opencv_font()
            fps_font_scale = fps_font_settings.size * scale_factor
            fps_font_thickness = fps_font_settings.get_effective_thickness()
            fps_border_thickness = fps_font_settings.border_thickness
        else:
            fps_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
            fps_font_scale = 1.2 * scale_factor
            fps_font_thickness = 3
            fps_border_thickness = 2
    except:
        fps_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
        fps_font_scale = 1.2 * scale_factor
        fps_font_thickness = 3
        fps_border_thickness = 2
    
    # Framerate Font Processing
    try:
        if hasattr(framerate_font_settings, 'get_opencv_font') and hasattr(framerate_font_settings, 'font_name'):
            framerate_opencv_font = framerate_font_settings.get_opencv_font()
            framerate_font_scale = framerate_font_settings.size * scale_factor
            framerate_font_thickness = framerate_font_settings.get_effective_thickness()
            framerate_border_thickness = framerate_font_settings.border_thickness
        else:
            framerate_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
            framerate_font_scale = 0.6 * scale_factor
            framerate_font_thickness = 1
            framerate_border_thickness = 1
    except:
        framerate_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
        framerate_font_scale = 0.6 * scale_factor
        framerate_font_thickness = 1
        framerate_border_thickness = 1
    
    # Frametime Font Processing
    try:
        if hasattr(frametime_font_settings, 'get_opencv_font') and hasattr(frametime_font_settings, 'font_name'):
            frametime_opencv_font = frametime_font_settings.get_opencv_font()
            frametime_font_scale = frametime_font_settings.size * scale_factor
            frametime_font_thickness = frametime_font_settings.get_effective_thickness()
            frametime_border_thickness = frametime_font_settings.border_thickness
        else:
            frametime_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
            frametime_font_scale = 0.5 * scale_factor
            frametime_font_thickness = 1
            frametime_border_thickness = 1
    except:
        frametime_opencv_font = cv2.FONT_HERSHEY_SIMPLEX
        frametime_font_scale = 0.5 * scale_factor
        frametime_font_thickness = 1
        frametime_border_thickness = 1
    
    # Color settings
    if color_settings is None:
        color_settings = {'framerate_color': '#00FF00', 'frametime_color': '#00FF00'}
    
    framerate_color_rgb = hex_to_bgr(color_settings.get('framerate_color', '#00FF00'))
    frametime_color_rgb = hex_to_bgr(color_settings.get('frametime_color', '#00FF00'))
    
    # Convert RGB to RGBA (add alpha channel)
    framerate_color_rgba = (*framerate_color_rgb, 255)
    frametime_color_rgba = (*frametime_color_rgb, 255)
    
    # Helper function for transparent text with border
    def draw_text_with_border_rgba(img, text, position, font, font_scale, color_rgba, thickness, border_color_rgba=(0, 0, 0, 255), border_thickness=2):
        x, y = position
        line_type = cv2.LINE_AA
        
        # Draw border
        for dx in range(-border_thickness, border_thickness + 1):
            for dy in range(-border_thickness, border_thickness + 1):
                if dx != 0 or dy != 0:
                    cv2.putText(img, text, (x + dx, y + dy), font, font_scale, border_color_rgba, 
                               thickness + 1, lineType=line_type)
        
        # Draw main text
        cv2.putText(img, text, position, font, font_scale, color_rgba, thickness, lineType=line_type)
    
    # 🎯 CURRENT FPS DISPLAY (top-left corner)
    fps_display_x = int(30 * scale_factor)
    fps_display_y = int(70 * scale_factor)
    
    # Large FPS number with color coding
    fps_color = (0, 255, 0, 255) if current_fps >= 55 else (0, 200, 255, 255) if current_fps >= 30 else (0, 50, 255, 255)
    draw_text_with_border_rgba(overlay, f"{current_fps:.1f}", 
                              (fps_display_x, fps_display_y - int(10 * scale_factor)),
                              fps_opencv_font, fps_font_scale, fps_color, fps_font_thickness, 
                              border_thickness=fps_border_thickness)
    draw_text_with_border_rgba(overlay, "FPS", 
                              (fps_display_x, fps_display_y + int(20 * scale_factor)),
                              fps_opencv_font, fps_font_scale * 0.6, (255, 255, 255, 255), fps_font_thickness,
                              border_thickness=fps_border_thickness)
    
    # 📊 GRAPH DIMENSIONS
    base_graph_width = 1090
    base_graph_height = 200
    graph_width = int(base_graph_width * scale_factor)
    graph_height = int(base_graph_height * scale_factor)
    
    # Framerate graph position
    fps_graph_x = int(50 * scale_factor)
    fps_graph_y = height - graph_height - int(50 * scale_factor)
    
    # 🎨 FRAMERATE GRAPH BACKGROUND BOX
    cv2.rectangle(overlay, 
                 (fps_graph_x - int(10 * scale_factor), fps_graph_y - int(20 * scale_factor)), 
                 (fps_graph_x + graph_width + int(10 * scale_factor), fps_graph_y + graph_height + int(20 * scale_factor)), 
                 (20, 20, 20, 200), -1)  # Semi-transparent dark background
    
    # Graph border
    cv2.rectangle(overlay, 
                 (fps_graph_x - int(10 * scale_factor), fps_graph_y - int(20 * scale_factor)), 
                 (fps_graph_x + graph_width + int(10 * scale_factor), fps_graph_y + graph_height + int(20 * scale_factor)), 
                 (100, 100, 100, 255), max(1, int(2 * scale_factor)))
    
    # 📝 FRAME RATE GRAPH TITLE
    draw_text_with_border_rgba(overlay, "FRAME RATE", 
                              (fps_graph_x, fps_graph_y - int(25 * scale_factor)),
                              framerate_opencv_font, framerate_font_scale * 1.2, (255, 255, 255, 255), framerate_font_thickness,
                              border_thickness=framerate_border_thickness)
    
    # 📏 HORIZONTAL GRID LINES AND LABELS
    fps_grid_values = [60, 45, 30, 15, 0]
    fps_labels_left = [60, 30, 0]
    
    for fps_val in fps_grid_values:
        y_pos = fps_graph_y + graph_height - int((fps_val / 60.0) * graph_height)
        line_color = (100, 100, 100, 255) if fps_val not in [30] else (120, 120, 120, 255)  # Lighter grid
        cv2.line(overlay, (fps_graph_x, y_pos), (fps_graph_x + graph_width, y_pos), 
                line_color, max(1, int(1 * scale_factor)))
        
        if fps_val in fps_labels_left:
            # Frame Rate labels
            draw_text_with_border_rgba(overlay, f"{fps_val}", 
                                      (fps_graph_x + graph_width + int(5 * scale_factor), y_pos + int(5 * scale_factor)),
                                      framerate_opencv_font, framerate_font_scale * 0.8, (255, 255, 255, 255), framerate_font_thickness, 
                                      border_thickness=framerate_border_thickness)
    
    # 📈 FRAMERATE LINE
    hist = fps_history[-max_len:] if len(fps_history) > max_len else fps_history
    if len(hist) >= 2:
        fps_points = []
        for i, fps_val in enumerate(hist):
            progress = i / (max_len - 1) if max_len > 1 else 0
            x = fps_graph_x + int(graph_width * progress)
            y = fps_graph_y + graph_height - int((min(fps_val, 60) / 60.0) * graph_height)
            fps_points.append((x, y))
        
        for i in range(len(fps_points) - 1):
            cv2.line(overlay, fps_points[i], fps_points[i + 1], framerate_color_rgba, 
                    max(2, int(3 * scale_factor)), lineType=cv2.LINE_AA)
    
    # 📊 FRAME TIME GRAPH
    ft_graph_x = 0
    ft_graph_y = 0
    ft_graph_width = 0
    ft_graph_height = 0
    
    if show_frame_time_graph and frame_times and len(frame_times) >= 2:
        ft_graph_width = int(400 * scale_factor)
        ft_graph_height = int(120 * scale_factor)
        
        # Position based on ftg_position setting
        if ftg_position == "bottom_left":
            ft_graph_x = fps_graph_x
            ft_graph_y = fps_graph_y - ft_graph_height - int(80 * scale_factor)
        elif ftg_position == "top_right":
            ft_graph_x = width - ft_graph_width - int(50 * scale_factor)
            ft_graph_y = int(50 * scale_factor)
        else:  # "bottom_right" (default)
            ft_graph_x = width - ft_graph_width - int(50 * scale_factor)
            ft_graph_y = height - ft_graph_height - int(50 * scale_factor)
        
        if frametime_scale is None:
            frametime_scale = {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']}
        
        ft_min = frametime_scale['min']
        ft_mid = frametime_scale['mid'] 
        ft_max = frametime_scale['max']
        ft_labels = frametime_scale['labels']
        
        # 🎨 FRAME TIME GRAPH BACKGROUND BOX
        cv2.rectangle(overlay, 
                     (ft_graph_x - int(10 * scale_factor), ft_graph_y - int(20 * scale_factor)), 
                     (ft_graph_x + ft_graph_width + int(10 * scale_factor), ft_graph_y + ft_graph_height + int(20 * scale_factor)), 
                     (20, 20, 20, 200), -1)  # Semi-transparent dark background
        
        cv2.rectangle(overlay, 
                     (ft_graph_x - int(10 * scale_factor), ft_graph_y - int(20 * scale_factor)), 
                     (ft_graph_x + ft_graph_width + int(10 * scale_factor), ft_graph_y + ft_graph_height + int(20 * scale_factor)), 
                     (100, 100, 100, 255), max(1, int(1 * scale_factor)))
        
        # 📝 FRAME TIME GRAPH TITLE
        draw_text_with_border_rgba(overlay, "FRAME TIME", 
                                  (ft_graph_x, ft_graph_y - int(25 * scale_factor)),
                                  frametime_opencv_font, frametime_font_scale * 1.1, (255, 255, 255, 255), frametime_font_thickness,
                                  border_thickness=frametime_border_thickness)
        
        # 📏 GRID LINES AND LABELS
        ft_grid_lines = [ft_min, ft_mid, ft_max]
        for i, (ft_val, label) in enumerate(zip(ft_grid_lines, ft_labels)):
            y_pos = ft_graph_y + ft_graph_height - int(((ft_val - ft_min) / (ft_max - ft_min)) * ft_graph_height)
            line_color = (100, 100, 100, 255) if ft_val != ft_mid else (120, 120, 120, 255)  # Lighter grid
            cv2.line(overlay, (ft_graph_x, y_pos), (ft_graph_x + ft_graph_width, y_pos), 
                    line_color, max(1, int(1 * scale_factor)))
            
            draw_text_with_border_rgba(overlay, f"{label}ms", 
                                      (ft_graph_x + ft_graph_width + int(5 * scale_factor), y_pos + int(5 * scale_factor)),
                                      frametime_opencv_font, frametime_font_scale * 0.7, (255, 255, 255, 255), frametime_font_thickness, 
                                      border_thickness=frametime_border_thickness)
        
        # 📈 FRAME TIME LINE
        ft_hist = frame_times[-max_len:] if len(frame_times) > max_len else frame_times
        if len(ft_hist) >= 2:
            ft_points = []
            for i, ft_val in enumerate(ft_hist):
                progress = i / (max_len - 1) if max_len > 1 else 0
                x = ft_graph_x + int(ft_graph_width * progress)
                clamped_ft = min(max(ft_val, ft_min), ft_max)
                y = ft_graph_y + ft_graph_height - int(((clamped_ft - ft_min) / (ft_max - ft_min)) * ft_graph_height)
                ft_points.append((x, y))
            
            for i in range(len(ft_points) - 1):
                cv2.line(overlay, ft_points[i], ft_points[i + 1], frametime_color_rgba, 
                        max(2, int(3 * scale_factor)), lineType=cv2.LINE_AA)
    
    # 📊 STATISTICS
    if len(hist) > 0:
        stats_x = fps_graph_x
        stats_y = fps_graph_y + graph_height + int(35 * scale_factor)
        
        if global_fps_values and len(global_fps_values) > 0:
            avg_fps = sum(global_fps_values) / len(global_fps_values)
            min_fps = min(global_fps_values)
            max_fps = max(global_fps_values)
        else:
            avg_fps = sum(hist[-60:]) / min(60, len(hist))
            min_fps = min(hist[-60:]) if len(hist) >= 60 else min(hist)
            max_fps = max(hist[-60:]) if len(hist) >= 60 else max(hist)
        
        stats_font_size = framerate_font_scale * 0.8
        draw_text_with_border_rgba(overlay, f"AVG: {avg_fps:.1f}", 
                                  (stats_x, stats_y),
                                  framerate_opencv_font, stats_font_size, (255, 255, 255, 255), framerate_font_thickness, 
                                  border_thickness=framerate_border_thickness)
        draw_text_with_border_rgba(overlay, f"MIN: {min_fps:.1f}", 
                                  (stats_x + int(120 * scale_factor), stats_y),
                                  framerate_opencv_font, stats_font_size, (255, 255, 255, 255), framerate_font_thickness, 
                                  border_thickness=framerate_border_thickness)
        draw_text_with_border_rgba(overlay, f"MAX: {max_fps:.1f}", 
                                  (stats_x + int(240 * scale_factor), stats_y),
                                  framerate_opencv_font, stats_font_size, (255, 255, 255, 255), framerate_font_thickness, 
                                  border_thickness=framerate_border_thickness)
        
        # 📊 FRAME TIME STATISTICS
        if show_frame_time_graph and frame_times and len(frame_times) > 0:
            if global_frame_times and len(global_frame_times) > 0:
                ft_avg = sum(global_frame_times) / len(global_frame_times)
                ft_max_recent = max(global_frame_times)
            else:
                ft_avg = sum(frame_times[-60:]) / min(60, len(frame_times))
                ft_max_recent = max(frame_times[-60:]) if len(frame_times) >= 60 else max(frame_times)
            
            # Smart positioning for frame time stats
            if ftg_position == "bottom_left" and show_frame_time_graph and ft_graph_x > 0:
                ft_stats_x = ft_graph_x
                ft_stats_y = ft_graph_y + ft_graph_height + int(35 * scale_factor)
            else:
                ft_stats_x = width - int(350 * scale_factor)
                ft_stats_y = height - int(20 * scale_factor)
            
            ft_stats_font_size = frametime_font_scale * 0.8
            draw_text_with_border_rgba(overlay, f"AVG: {ft_avg:.1f}ms", 
                                      (ft_stats_x, ft_stats_y),
                                      frametime_opencv_font, ft_stats_font_size, (255, 255, 255, 255), frametime_font_thickness, 
                                      border_thickness=frametime_border_thickness)
            draw_text_with_border_rgba(overlay, f"MAX: {ft_max_recent:.1f}ms", 
                                      (ft_stats_x + int(140 * scale_factor), ft_stats_y),
                                      frametime_opencv_font, ft_stats_font_size, (255, 255, 255, 255), frametime_font_thickness, 
                                      border_thickness=frametime_border_thickness)
    
    return overlay