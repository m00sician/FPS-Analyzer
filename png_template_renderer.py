"""
PNG Template Overlay Renderer - Complete Fixed Version
🚀 PERFORMANCE OPTIMIZED: Uses pre-rendered PNG templates for static elements

Key Features:
- Pre-rendered PNG templates for static UI elements
- Minimal draw calls per frame
- Aggressive caching for scaled templates
- Only dynamic elements (FPS, lines) rendered at runtime
- 10-20x performance improvement over full rendering
"""

import cv2
import numpy as np
try:
    from cuda_accelerator import get_blender as _get_blender
    _cuda_blender = _get_blender()
except Exception:
    _cuda_blender = None
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from collections import deque

# Try to import color converter
try:
    from color_manager import hex_to_bgr
except ImportError:
    def hex_to_bgr(hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to BGR"""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return (b, g, r)

@dataclass
class TemplateConfig:
    """Configuration for a PNG template"""
    filename: str
    default_position: Tuple[int, int]
    render_size: Tuple[int, int]  # Size to render at (width, height)
    anchor: str = 'top_left'  # anchor point for positioning

class PNGTemplateCache:
    """Cache for loaded and scaled PNG templates"""
    
    def __init__(self, max_cache_size: int = 50):
        self.cache = {}
        self.max_size = max_cache_size
        self.access_order = deque()
    
    def get_cache_key(self, path: str, size: Tuple[int, int]) -> str:
        """Generate cache key for template"""
        return f"{path}_{size[0]}x{size[1]}"
    
    def get(self, path: str, size: Tuple[int, int]) -> Optional[np.ndarray]:
        """Get cached template"""
        key = self.get_cache_key(path, size)
        if key in self.cache:
            # Update access order
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        return None
    
    def set(self, path: str, size: Tuple[int, int], image: np.ndarray):
        """Cache a template"""
        key = self.get_cache_key(path, size)
        
        # Remove oldest if cache is full
        if len(self.cache) >= self.max_size and key not in self.cache:
            oldest = self.access_order.popleft()
            del self.cache[oldest]
        
        self.cache[key] = image
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)

class FontSizeConfig:
    """Configuration for font sizes across different resolutions"""
    
    # FIXED: Absolute pixel sizes for each resolution
    RESOLUTION_SIZES = {
        '4K': {
            'fps_number': 120,
            'fps_label': 40,
            'stats_text': 48,
            'stats_spacing': 200,    # Diese Werte werden NICHT mehr verwendet!
            'frametime_spacing': 80, # Diese Werte werden NICHT mehr verwendet!
            'border_thickness': 2,
        },
        '1440p': {
            'fps_number': 80,
            'fps_label': 30,
            'stats_text': 36,
            'stats_spacing': 150,    # Wird ignoriert
            'frametime_spacing': 60, # Wird ignoriert
            'border_thickness': 3,
        },
        '1080p': {
            'fps_number': 60,
            'fps_label': 24,
            'stats_text': 24,
            'stats_spacing': 120,    # Wird ignoriert
            'frametime_spacing': 50, # Wird ignoriert
            'border_thickness': 1,
        },
        '720p': {
            'fps_number': 40,
            'fps_label': 18,
            'stats_text': 20,
            'stats_spacing': 80,     # Wird ignoriert
            'frametime_spacing': 30, # Wird ignoriert
            'border_thickness': 2,
        }
    }

    @staticmethod
    def get_resolution_category(width: int, height: int) -> str:
        """Get resolution category.

        Uses the HIGHER of width-based and height-based detection so that
        comparison videos (cropped to half width but full height) are not
        mis-categorised. E.g. 960x1080 has full 1080p height → '1080p',
        not '720p' which width-only detection would return.
        """
        # Width-based category
        if width >= 3840:
            cat_w = "4K"
        elif width >= 2560:
            cat_w = "1440p"
        elif width >= 1920:
            cat_w = "1080p"
        else:
            cat_w = "720p"

        # Height-based category (handles half-width comparison crops)
        if height >= 2160:
            cat_h = "4K"
        elif height >= 1440:
            cat_h = "1440p"
        elif height >= 1080:
            cat_h = "1080p"
        else:
            cat_h = "720p"

        # Return the higher of the two categories
        order = ["720p", "1080p", "1440p", "4K"]
        return cat_w if order.index(cat_w) >= order.index(cat_h) else cat_h

    @staticmethod
    def get_absolute_size(element: str, width: int, height: int) -> int:
        """Get absolute font size for specific element and resolution"""
        category = FontSizeConfig.get_resolution_category(width, height)
        return FontSizeConfig.RESOLUTION_SIZES.get(category, FontSizeConfig.RESOLUTION_SIZES['1080p']).get(element, 28)

    @staticmethod
    def get_scaled_size(element: str, width: int, height: int) -> Tuple[int, float, str]:
        """
        Get scaled size for specific element and resolution.
        Returns: (size, scale_factor, resolution_category)
        
        This method provides backward compatibility for code that expects
        a tuple of (size, scale, category) instead of just the size.
        """
        category = FontSizeConfig.get_resolution_category(width, height)
        size = FontSizeConfig.RESOLUTION_SIZES.get(category, FontSizeConfig.RESOLUTION_SIZES['1080p']).get(element, 28)
        
        # Calculate scale factor relative to 1080p base
        base_size = FontSizeConfig.RESOLUTION_SIZES['1080p'].get(element, 28)
        scale = size / base_size if base_size > 0 else 1.0
        
        return (size, scale, category)

class PNGTemplateRenderer:
    """Ultra-fast PNG template-based overlay renderer"""
    
    def __init__(self, template_dir: str = "templates"):
        self.template_dir = Path(template_dir)
        self.template_cache = PNGTemplateCache(max_cache_size=20)
        self.loaded_templates = {}
        
        # Available templates (discovered during scan)
        self.available_fps_templates = []
        self.available_ft_templates = []
        
        # Performance metrics
        self.render_times = deque(maxlen=100)
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Scan and load all templates
        self.scan_templates()
        
    
    def scan_templates(self):
        """Scan template directory for all PNG templates"""
        print("🔍 Scanning for PNG templates...")
        
        if not self.template_dir.exists():
            print(f"❌ Template directory not found: {self.template_dir}")
            print(f"   Creating directory: {self.template_dir}")
            self.template_dir.mkdir(parents=True, exist_ok=True)
            return
        
        # Scan for FPS templates
        fps_patterns = ['FPS-*.png', 'fps-*.png']
        for pattern in fps_patterns:
            for template_path in self.template_dir.glob(pattern):
                template_name = template_path.stem
                #print(f"✅ Found FPS template: {template_name}")
                self.available_fps_templates.append(template_name)
                self.load_template(template_path)
        
        # Scan for Frame Time templates
        ft_patterns = ['FT-*.png', 'ft-*.png', 'frametime-*.png']
        for pattern in ft_patterns:
            for template_path in self.template_dir.glob(pattern):
                template_name = template_path.stem
                #print(f"✅ Found Frame Time template: {template_name}")
                self.available_ft_templates.append(template_name)
                self.load_template(template_path)
        
        print(f"📊 Loaded {len(self.loaded_templates)} templates total")
    
    def load_template(self, template_path: Path):
        """Load a single PNG template"""
        try:
            template = cv2.imread(str(template_path), cv2.IMREAD_UNCHANGED)
            if template is not None:
                template_name = template_path.stem
                self.loaded_templates[template_name] = template
                h, w = template.shape[:2]
                print(f"  ✓ {template_name}: {w}x{h}")
            else:
                print(f"  ❌ Failed to load: {template_path.name}")
        except Exception as e:
            print(f"  ❌ Error loading {template_path.name}: {e}")
    
    def get_scaled_template_by_name(self, template_name: str, target_size: Tuple[int, int]) -> Optional[np.ndarray]:
        """Get scaled template by name with caching"""
        if template_name not in self.loaded_templates:
            print(f"⚠️ Template not found: {template_name}")
            return None
        
        # Check cache first
        cached = self.template_cache.get(template_name, target_size)
        if cached is not None:
            self.cache_hits += 1
            return cached
        
        self.cache_misses += 1
        
        # Scale template
        original_template = self.loaded_templates[template_name]
        scaled = cv2.resize(original_template, target_size, interpolation=cv2.INTER_LANCZOS4)
        
        # Cache it
        self.template_cache.set(template_name, target_size, scaled)
        
        return scaled
    
    def blend_template(self, base_image: np.ndarray, template: np.ndarray,
                      position: Tuple[int, int]) -> np.ndarray:
        """Alpha composite template onto base_image. Uses GPU if available."""
        x, y = position
        if x < 0 or y < 0:
            return base_image

        if template.shape[2] == 4:
            # RGBA template — use CUDA blender if available
            if _cuda_blender is not None:
                return _cuda_blender.blend(base_image, template, x, y)
            # CPU numpy fallback
            h = min(template.shape[0], base_image.shape[0] - y)
            w = min(template.shape[1], base_image.shape[1] - x)
            if h <= 0 or w <= 0:
                return base_image
            alpha = template[:h, :w, 3:4].astype(np.float32) / 255.0
            fg    = template[:h, :w, :3].astype(np.float32)
            roi   = base_image[y:y+h, x:x+w].astype(np.float32)
            base_image[y:y+h, x:x+w] = (roi * (1 - alpha) + fg * alpha).astype(np.uint8)
        else:
            h = min(template.shape[0], base_image.shape[0] - y)
            w = min(template.shape[1], base_image.shape[1] - x)
            if h > 0 and w > 0:
                base_image[y:y+h, x:x+w] = template[:h, :w]

        return base_image

    def get_scaled_line_thickness(self, base_thickness: int, target_resolution: Tuple[int, int], line_type: str = 'fps') -> int:
        """Calculate line thickness based on resolution with custom scaling per resolution"""
        width, height = target_resolution
        
        # CUSTOMIZABLE: Line thickness multipliers for each resolution
        # Adjust these values to control line thickness for each resolution tier
        if line_type == 'fps':
            thickness_multipliers = {
                '4K': 3.0,      # Deine Werte für FPS
                '1440p': 1.2,   
                '1080p': 1.5,   
                '720p': 0.8     
            }
        else:  # frametime
            thickness_multipliers = {
                '4K': 2.0,      # Andere Werte für Frame Time
                '1440p': 1.1,   
                '1080p': 1.0,   
                '720p': 0.6     
            }
        
        # Determine resolution category
        if height >= 2160:
            category = '4K'
            multiplier = thickness_multipliers['4K']
        elif height >= 1440:
            category = '1440p'
            multiplier = thickness_multipliers['1440p']
        elif height >= 1080:
            category = '1080p'
            multiplier = thickness_multipliers['1080p']
        else:
            category = '720p'
            multiplier = thickness_multipliers['720p']
        
        # Calculate final thickness
        scaled_thickness = max(1, int(base_thickness * multiplier))
        
        # Log only once per resolution category and type
        log_key = f'_thickness_logged_{category}_{line_type}'
        if not hasattr(self, log_key):
            print(f"📏 {line_type.upper()} line thickness for {category} ({width}x{height}): base={base_thickness} × {multiplier} = {scaled_thickness}")
            setattr(self, log_key, True)
            
        return scaled_thickness

    def draw_fps_line(self, img: np.ndarray, fps_history: List[float], 
                    graph_pos: Tuple[int, int], graph_size: Tuple[int, int],
                    color: Tuple[int, int, int], max_fps: float = 60) -> np.ndarray:
        """Draw FPS line graph - FIXED for template alignment with scaled thickness"""
        # FIX: Convert deque to list if necessary
        if hasattr(fps_history, '__iter__') and not isinstance(fps_history, list):
            fps_history = list(fps_history)
        
        # NEU: Skip first 60 frames
        if len(fps_history) < 60:
            return img # Zeige keine Linie während warm-up

        if len(fps_history) < 2:
            return img
        
        x, y = graph_pos
        w, h = graph_size
        
        # Get scaled line thickness based on image resolution.
        # base_thickness can be overridden via renderer.base_fps_thickness.
        base_thickness = getattr(self, 'base_fps_thickness', 2)
        line_thickness = self.get_scaled_line_thickness(base_thickness, (img.shape[1], img.shape[0]))
        
        # FPS Template specifications (original at 4K)
        template_original_width = 1840
        template_original_height = 580
        graph_area_x_offset = 10
        graph_area_y_offset = 73
        graph_area_width = 1763
        graph_area_height = 485
        
        # Calculate scale factors from template size to actual rendered size
        scale_x = w / template_original_width
        scale_y = h / template_original_height
        
        # Calculate actual graph area within the rendered template
        actual_graph_x = x + int(graph_area_x_offset * scale_x)
        actual_graph_y = y + int(graph_area_y_offset * scale_y)
        actual_graph_width = int(graph_area_width * scale_x)
        actual_graph_height = int(graph_area_height * scale_y)
        
        # WICHTIG: Begrenze die History auf die letzten 180 Frames (3 Sekunden bei 60 FPS)
        max_points = 180
        if len(fps_history) > max_points:
            fps_history = fps_history[-max_points:]  # This now works because fps_history is a list

        # Smooth the graph line with a rolling average.
        # smooth_window can be overridden at runtime via renderer.smooth_window.
        smooth_window = getattr(self, 'smooth_window', 9)
        smooth_window = max(1, smooth_window | 1)  # ensure odd, min 1
        if len(fps_history) >= smooth_window:
            half = smooth_window // 2
            smoothed = []
            for i in range(len(fps_history)):
                lo = max(0, i - half)
                hi = min(len(fps_history), i + half + 1)
                smoothed.append(sum(fps_history[lo:hi]) / (hi - lo))
            fps_history = smoothed

        # FIXED: Skaliere die X-Achse so dass immer der volle Graph-Bereich genutzt wird
        points = []
        for i, fps in enumerate(fps_history):
            # X position: spread across FULL graph width
            # WICHTIG: Teile durch max_points, nicht durch len(fps_history)
            px = actual_graph_x + int(i * actual_graph_width / max_points)
            
            # Y position: scale FPS value to graph height (inverted - high FPS at top)
            fps_normalized = min(fps / max_fps, 1.0)  # Normalize to 0-1
            py = actual_graph_y + actual_graph_height - int(fps_normalized * actual_graph_height)
            
            points.append((px, py))
        
        # Convert to numpy array for faster processing
        pts = np.array(points, dtype=np.int32)
        
        # Draw polyline with scaled thickness
        cv2.polylines(img, [pts], False, color, line_thickness, cv2.LINE_8)
        
        return img

    def draw_frametime_line(self, img: np.ndarray, frame_times: List[float],
                        graph_pos: Tuple[int, int], graph_size: Tuple[int, int],
                        color: Tuple[int, int, int], scale_min: float = 16.7,
                        scale_max: float = 50.0) -> np.ndarray:
        """Draw frame time line graph - FIXED INVERSION"""
        # FIX: Convert deque to list if necessary
        if hasattr(frame_times, '__iter__') and not isinstance(frame_times, list):
            frame_times = list(frame_times)
        
        # NEU: Skip first 60 frames
        if len(frame_times) <= 60:
            return img # Zeige keine Linie während warm-up

        if len(frame_times) < 2:
            return img
        
        x, y = graph_pos
        w, h = graph_size
        
        # Get scaled line thickness based on image resolution
        base_thickness = 2  # Thickness at 1080p
        line_thickness = self.get_scaled_line_thickness(base_thickness, (img.shape[1], img.shape[0]), 'frametime')
        
        # FT Template specifications (original at 4K)
        template_original_width = 800
        template_original_height = 360
        graph_area_x_offset = 9
        graph_area_y_offset = 51
        graph_area_width = 687
        graph_area_height = 292
        
        # Calculate scale factors from template size to actual rendered size
        scale_x = w / template_original_width
        scale_y = h / template_original_height
        
        # Calculate actual graph area within the rendered template
        actual_graph_x = x + int(graph_area_x_offset * scale_x)
        actual_graph_y = y + int(graph_area_y_offset * scale_y)
        actual_graph_width = int(graph_area_width * scale_x)
        actual_graph_height = int(graph_area_height * scale_y)
        
        # Subsample if history is very long
        if len(frame_times) > actual_graph_width:
            step = len(frame_times) // actual_graph_width
            frame_times = frame_times[::step]
        
        # Generate points within the actual graph area
        points = []
        for i, ft in enumerate(frame_times):
            # X position: spread across the graph width
            px = actual_graph_x + int(i * actual_graph_width / max(len(frame_times) - 1, 1))
            
            # Y position: scale frame time to graph height
            ft_clamped = max(scale_min, min(ft, scale_max))
            normalized = (ft_clamped - scale_min) / (scale_max - scale_min)
            
            # FIXED INVERSION: Lower frame time = lower Y position (bottom of graph)
            # This makes 16.7ms appear at the bottom and 50ms at the top
            py = actual_graph_y + actual_graph_height - int(normalized * actual_graph_height)
            
            points.append((px, py))
        
        # Convert to numpy array
        pts = np.array(points, dtype=np.int32)
        
        # Draw polyline with scaled thickness
        cv2.polylines(img, [pts], False, color, line_thickness, cv2.LINE_AA)
        
        return img

    def render_overlay(self, frame: np.ndarray, fps_history: List[float], current_fps: float,
                    frame_times: Optional[List[float]] = None,
                    show_frame_time_graph: bool = True,
                    layout_config: Optional[Dict] = None,
                    color_settings: Optional[Dict] = None,
                    template_config: Optional[Dict] = None,
                    font_settings: Optional[Dict] = None,
                    global_fps_values: Optional[List[float]] = None,
                    global_frame_times: Optional[List[float]] = None,
                    precomputed_stats: Optional[Dict] = None) -> np.ndarray:  # ← IN den Klammern, VOR ) -> np.ndarray:
        """Main rendering function - FIXED POSITION SCALING"""
        import time
        start_time = time.perf_counter()
        t_debug = {}
        
        # Start with frame copy
        t0 = time.perf_counter()
        overlay = frame.copy()
        t_debug['copy'] = time.perf_counter() - t0
        h, w = frame.shape[:2]
        
        # NEUE ZEILE: Store layout config for other methods to access
        self._current_layout_config = layout_config
        
        # Get resolution scale for position adjustments.
        # Use max() so half-width comparison videos (e.g. 960x1080) are scaled
        # based on their full height rather than their cropped width.
        position_scale = max(w / 1920, h / 1080)
        
        # Default colors
        if color_settings is None:
            color_settings = {
                'framerate_color': '#00FF00',
                'frametime_color': '#00FF00'
            }
        
        # Convert colors
        framerate_color = hex_to_bgr(color_settings.get('framerate_color', '#00FF00'))
        frametime_color = hex_to_bgr(color_settings.get('frametime_color', '#00FF00'))
        
        # Use layout config or defaults
        if layout_config is None:
            layout_config = self.get_default_layout(w, h)
        
        # Extract template info from template_config
        fps_template_name = None
        fps_max = 60
        ft_template_name = None
        ft_scale = {'min': 16.7, 'mid': 33.3, 'max': 50.0}
        
        if template_config:
            # FPS template
            fps_data = template_config.get('fps_graph_template')
            if fps_data and isinstance(fps_data, dict):
                fps_template_name = fps_data.get('template', '').replace('.png', '')
                fps_max = fps_data.get('max_fps', 60)
                # Only print once per video to avoid spam
                if not hasattr(self, '_template_logged'):
                    print(f"🎯 Using FPS template: {fps_template_name} (max: {fps_max})")
                    self._template_logged = True
            
            # Frame time template
            ft_data = template_config.get('frametime_template')
            if ft_data and isinstance(ft_data, dict):
                ft_template_name = ft_data.get('template', '').replace('.png', '')
                ft_scale = ft_data.get('scale', ft_scale)
                # Only print once per video to avoid spam
                if not hasattr(self, '_template_logged'):
                    print(f"⏱️ Using FT template: {ft_template_name} (scale: {ft_scale['min']}-{ft_scale['max']}ms)")
                    self._template_logged = True
        
        # 1. Render Frame Rate Graph
        t0 = time.perf_counter()
        if layout_config.get('frame_rate_graph', {}).get('visible', True):
            frg_config = layout_config['frame_rate_graph']
            
            if fps_template_name and fps_template_name in self.loaded_templates:
                template_size = (frg_config['width'], frg_config['height'])
                template = self.get_scaled_template_by_name(fps_template_name, template_size)
                
                if template is not None:
                    self.blend_template(overlay, template, (frg_config['x'], frg_config['y']))
                    
                    # Draw dynamic FPS line - using the template's position and size
                    self.draw_fps_line(overlay, fps_history, 
                                     (frg_config['x'], frg_config['y']), 
                                     (frg_config['width'], frg_config['height']), 
                                     framerate_color, fps_max)
            elif fps_template_name:
                # Only warn if a template name was specified but not found
                if not hasattr(self, '_fps_template_warning_logged'):
                    print(f"⚠️ FPS template not found: {fps_template_name}")
                    self._fps_template_warning_logged = True
        t_debug['fps_graph'] = time.perf_counter() - t0
        
        # 2. Render Frame Time Graph
        t0 = time.perf_counter()
        if show_frame_time_graph and frame_times and layout_config.get('frame_time_graph', {}).get('visible', True):
            ftg_config = layout_config['frame_time_graph']
            
            if ft_template_name and ft_template_name in self.loaded_templates:
                template_size = (ftg_config['width'], ftg_config['height'])
                template = self.get_scaled_template_by_name(ft_template_name, template_size)
                
                if template is not None:
                    self.blend_template(overlay, template, (ftg_config['x'], ftg_config['y']))
                    
                    # Draw dynamic frametime line - using the template's position and size
                    self.draw_frametime_line(overlay, frame_times, 
                                           (ftg_config['x'], ftg_config['y']), 
                                           (ftg_config['width'], ftg_config['height']), 
                                           frametime_color, ft_scale['min'], ft_scale['max'])
            elif ft_template_name:
                # Only warn if a template name was specified but not found
                if not hasattr(self, '_ft_template_warning_logged'):
                    print(f"⚠️ Frame time template not found: {ft_template_name}")
                    self._ft_template_warning_logged = True
        t_debug['ft_graph'] = time.perf_counter() - t0
        
        # 3. Draw dynamic elements with TrueType font support
        
        # FPS Number
        t0 = time.perf_counter()
        if layout_config.get('fps_display', {}).get('visible', True):
            fps_config = layout_config['fps_display']
            # FIXED: Scale the Y offset properly
            y_offset = int(50 * position_scale)  # Was hardcoded to 50
            fps_position = (fps_config['x'], fps_config['y'] + y_offset)
            
            # Pass font settings if available
            fps_font = font_settings.get('fps_font') if font_settings else None
            overlay = self.draw_fps_number_with_font(overlay, current_fps, fps_position, fps_font)
        t_debug['fps_number'] = time.perf_counter() - t0

        # Statistics
        t0 = time.perf_counter()
        if fps_history:
            # FPS Statistics
            if layout_config.get('fps_statistics', {}).get('visible', True):
                fps_stats_config = layout_config['fps_statistics']
                
                # Verwende vorberechnete Statistiken (O(1)!) oder berechne Fallback
                if precomputed_stats and 'fps' in precomputed_stats:
                    stats = precomputed_stats['fps']
                elif global_fps_values and len(global_fps_values) > 60:
                    recent = list(global_fps_values)[-300:]
                    stats = {'avg': sum(recent) / len(recent), 'min': min(recent), 'max': max(recent)}
                else:
                    stats = {'avg': -1, 'min': -1, 'max': -1}

                framerate_font = font_settings.get('framerate_font') if font_settings else None
                overlay = self.draw_statistics_with_font(overlay, stats, 
                                                       (fps_stats_config['x'], fps_stats_config['y']), 
                                                       'fps', framerate_font)
            
            # Frametime Statistics
            if frame_times and layout_config.get('frametime_statistics', {}).get('visible', True):
                ft_stats_config = layout_config['frametime_statistics']
                
                # Verwende vorberechnete Statistiken (O(1)!) oder berechne Fallback
                if precomputed_stats and 'frametime' in precomputed_stats:
                    stats = precomputed_stats['frametime']
                elif global_frame_times and len(global_frame_times) > 60:
                    recent = list(global_frame_times)[-300:]
                    stats = {'avg': sum(recent) / len(recent), 'min': min(recent), 'max': max(recent)}
                else:
                    stats = {'avg': -1, 'min': -1, 'max': -1}
                
                frametime_font = font_settings.get('frametime_font') if font_settings else None
                overlay = self.draw_statistics_with_font(overlay, stats, 
                                                       (ft_stats_config['x'], ft_stats_config['y']), 
                                                       'frametime', frametime_font)
        t_debug['statistics'] = time.perf_counter() - t0
        
        # Performance tracking
        render_time = (time.perf_counter() - start_time) * 1000
        self.render_times.append(render_time)
        
        # Debug timing output every 100 frames
        if not hasattr(self, '_frame_count'):
            self._frame_count = 0
        self._frame_count += 1
        if self._frame_count % 100 == 0:
            print(f"🔬 OVERLAY TIMING breakdown (frame {self._frame_count}):")
            print(f"   copy:       {t_debug.get('copy', 0)*1000:.2f}ms")
            print(f"   fps_graph:  {t_debug.get('fps_graph', 0)*1000:.2f}ms")
            print(f"   ft_graph:   {t_debug.get('ft_graph', 0)*1000:.2f}ms")
            print(f"   fps_number: {t_debug.get('fps_number', 0)*1000:.2f}ms")
            print(f"   statistics: {t_debug.get('statistics', 0)*1000:.2f}ms")
            print(f"   TOTAL:      {render_time:.2f}ms")
        
        return overlay

    def draw_fps_number_with_font(self, img: np.ndarray, fps: float, position: Tuple[int, int],
                                    font_settings: Any) -> np.ndarray:
        """Draw FPS number with TrueType support - NO LABEL"""
        if fps < 0:
            fps_text = "---"
        else:
            fps_text = f"{int(fps)}"
    
        # Get image dimensions
        h, w = img.shape[:2]
    
        # Get absolute size for this resolution
        fps_size = FontSizeConfig.get_absolute_size('fps_number', w, h)
        category = FontSizeConfig.get_resolution_category(w, h)
    
        # Apply font scale multiplier if present
        if hasattr(self, '_current_layout_config') and self._current_layout_config:
            fps_display_config = self._current_layout_config.get('fps_display', {})
            multiplier = fps_display_config.get('font_scale_multiplier', 1.0)
            if multiplier != 1.0:
                # WICHTIG: IMMER den Multiplier anwenden, nicht nur beim ersten Mal!
                fps_size = int(fps_size * multiplier)
                
                # Debug log nur einmal
                if not hasattr(self, '_multiplier_logged'):
                    print(f"🎯 Font multiplier active: {multiplier}x")
                    self._multiplier_logged = True
    
        # Check if we have TrueType font settings
        if font_settings and hasattr(font_settings, 'render_text'):
            try:
                # Only reload font if the size actually changed (avoids expensive disk I/O every frame)
                if getattr(font_settings, 'size', None) != fps_size:
                    font_settings.size = fps_size
                    if hasattr(font_settings, '_load_font_with_size'):
                        font_settings._load_font_with_size(fps_size)
                
                # Color based on FPS
                if fps >= 55:
                    color = (255, 255, 255)
                elif fps >= 30:
                    color = (255, 255, 255)
                else:
                    color = (255, 255, 255)
                
                font_settings.text_color = color
                img = font_settings.render_text(img, fps_text, position, 1.0)
                
                return img
            except Exception as e:
                print(f"⚠️ TrueType rendering failed for FPS: {e}")
        
        # Fallback to OpenCV
        return self.draw_fps_number_simple(img, fps, position, font_settings, fps_size)

    def draw_fps_number_simple(self, img: np.ndarray, fps: float, position: Tuple[int, int],
                          font_settings: Any, custom_size: Optional[int] = None) -> np.ndarray:
        """Draw FPS number only - no label"""
        if fps < 0:
            fps_text = "---"
        else:
            fps_text = f"{int(fps)}"
            
        # Get image dimensions
        h, w = img.shape[:2]
            
        # Use custom size if provided, otherwise get from config
        if custom_size:
            fps_size = custom_size
        else:
            fps_size = FontSizeConfig.get_absolute_size('fps_number', w, h)
            
        # Convert points to OpenCV scale
        font_scale = fps_size / 40.0
        thickness = max(1, int(fps_size / 20))
            
        # Simple OpenCV rendering
        font = cv2.FONT_HERSHEY_SIMPLEX
            
        # Color based on FPS
        if fps >= 55:
            color = (255, 255, 255)
        elif fps >= 30:
            color = (255, 255, 255)
        else:
            color = (255, 255, 255)
            
        # Draw with outline for better visibility
        cv2.putText(img, fps_text, position, font, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
        cv2.putText(img, fps_text, position, font, font_scale, color, thickness, cv2.LINE_AA)
            
        return img

    def draw_statistics_with_font(self, img: np.ndarray, stats: Dict[str, float],
                                position: Tuple[int, int], stat_type: str,
                                font_settings: Any) -> np.ndarray:
        """Draw statistics with TrueType support.

        OPTIMIZED: All stat labels are composited in a single Pillow ROI
        instead of one ROI conversion per label (was 6 conversions → 48ms).
        Now costs one conversion for all labels together → ~5ms.
        """
        h, w = img.shape[:2]

        text_size       = FontSizeConfig.get_absolute_size('stats_text', w, h)
        base_scale      = min(w / 1920, h / 1080)
        spacing         = int(100 * base_scale) if stat_type == 'fps' else int(120 * base_scale)
        border_thickness = FontSizeConfig.get_absolute_size('border_thickness', w, h)

        category = FontSizeConfig.get_resolution_category(w, h)
        log_key  = f'_stats_logged_{category}'
        if not hasattr(self, log_key):
            print(f"📊 {category} STATS: {w}x{h}, size={text_size}pt, spacing={spacing}px")
            setattr(self, log_key, True)

        if not (font_settings and hasattr(font_settings, 'render_text')):
            return self.draw_statistics(img, stats, position, stat_type)

        try:
            # Early-exit if stats not ready yet
            if stats.get('avg', -1) < 0:
                return img

            # Reload font only when size changes
            if getattr(font_settings, 'size', None) != text_size:
                font_settings.size = text_size
                if hasattr(font_settings, '_load_font_with_size'):
                    font_settings._load_font_with_size(text_size)
            font_settings.border_thickness = border_thickness

            # Build list of (text, x_offset) pairs
            x0, y0 = position
            x0 += 4
            if stat_type == 'fps':
                items = [
                    (f"AVG: {stats['avg']:.1f}",  0),
                    (f"MIN: {stats['min']:.1f}",  spacing),
                    (f"MAX: {stats['max']:.1f}",  spacing * 2),
                ]
            else:
                items = [
                    (f"AVG: {stats['avg']:.1f}ms", 0),
                    (f"MIN: {stats['min']:.1f}ms", spacing),
                    (f"MAX: {stats['max']:.1f}ms", spacing * 2),
                ]

            # Estimate total bounding box for ONE shared ROI
            approx_char_w = max(text_size, 10)
            max_text_len  = max(len(t) for t, _ in items)
            total_w       = spacing * 2 + max_text_len * approx_char_w + border_thickness * 2 + 16
            total_h       = text_size + border_thickness * 2 + 16

            img_h, img_w = img.shape[:2]
            roi_x1 = max(0, x0 - border_thickness - 4)
            roi_y1 = max(0, y0 - text_size - border_thickness - 4)
            roi_x2 = min(img_w, x0 + total_w)
            roi_y2 = min(img_h, y0 + total_h)

            if roi_x2 <= roi_x1 or roi_y2 <= roi_y1:
                return img

            # ONE BGR→RGB conversion for the whole stats strip
            try:
                from PIL import Image as PILImage, ImageDraw
                import cv2 as _cv2
                roi_bgr = img[roi_y1:roi_y2, roi_x1:roi_x2]
                roi_rgb = _cv2.cvtColor(roi_bgr, _cv2.COLOR_BGR2RGB)
                pil_roi = PILImage.fromarray(roi_rgb)
                draw    = ImageDraw.Draw(pil_roi)

                pil_font = getattr(font_settings, '_pillow_font', None)
                border_col = getattr(font_settings, 'border_color', (0, 0, 0))
                border_rgb = (border_col[2], border_col[1], border_col[0]) if border_col else (0, 0, 0)
                text_rgb   = (255, 255, 255)

                y_off = -int(text_size * 0.25)

                for text, x_rel in items:
                    lx = (x0 + x_rel) - roi_x1
                    ly = y0 - roi_y1 + y_off

                    if pil_font:
                        # stroke_width replaces the manual offset loop (was 24 draw calls → 1)
                        draw.text((lx, ly), text, font=pil_font, fill=text_rgb,
                                  stroke_width=border_thickness if border_thickness > 0 else 0,
                                  stroke_fill=border_rgb if border_thickness > 0 else None)
                    else:
                        draw.text((lx, ly), text, fill=text_rgb)

                # ONE RGB→BGR conversion back
                img[roi_y1:roi_y2, roi_x1:roi_x2] = _cv2.cvtColor(
                    np.array(pil_roi), _cv2.COLOR_RGB2BGR)

            except Exception as inner_e:
                print(f"⚠️ Batch stats rendering failed: {inner_e}")
                return self.draw_statistics(img, stats, position, stat_type)

            return img

        except Exception as e:
            print(f"⚠️ TrueType stats failed: {e}")
            return self.draw_statistics(img, stats, position, stat_type)


    # Updated fallback methods with the same flexible sizing
    def draw_fps_number(self, img: np.ndarray, fps: float, position: Tuple[int, int],
                    font_settings: Any, show_label: bool = True) -> np.ndarray:
        """Draw FPS number - FLEXIBLE FALLBACK VERSION WITH LABEL CONTROL"""
        fps_text = f"{int(fps)}"
        
        # Get image dimensions
        h, w = img.shape[:2]
        
        # Get scaled sizes
        fps_size, scale, category = FontSizeConfig.get_scaled_size('fps_number', w, h)
        
        # Convert points to OpenCV scale (rough approximation)
        font_scale = fps_size / 40.0  # Adjusted for OpenCV
        thickness = max(1, int(fps_size / 20))
        
        # Simple OpenCV rendering
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # Color based on FPS
        if fps >= 55:
            color = (0, 255, 0)  # Green
        elif fps >= 30:
            color = (0, 200, 255)  # Yellow
        else:
            color = (0, 50, 255)  # Red
        
        # Draw with outline for better visibility
        cv2.putText(img, fps_text, position, font, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
        cv2.putText(img, fps_text, position, font, font_scale, color, thickness, cv2.LINE_AA)

        # Add FPS label ONLY if show_label is True
        if show_label:
            label_size, _, _ = FontSizeConfig.get_scaled_size('fps_label', w, h)
            label_offset = int(fps_size * 0.8)
            label_scale = label_size / 40.0

            # Calculate text widths for centering
            fps_text_size = cv2.getTextSize(fps_text, font, font_scale, thickness)[0]
            label_text_size = cv2.getTextSize("FPS", font, label_scale, max(1, int(thickness * 0.5)))[0]

            # Center the label under the FPS number
            label_x = position[0] + (fps_text_size[0] - label_text_size[0]) // 2
            label_pos = (label_x, position[1] + label_offset)

            cv2.putText(img, "FPS", label_pos, font, label_scale, (255, 255, 255), 
                        max(1, int(thickness * 0.5)), cv2.LINE_AA)
        
        return img


    def draw_statistics(self, img: np.ndarray, stats: Dict[str, float], 
                    position: Tuple[int, int], stat_type: str = 'fps') -> np.ndarray:
        """Draw statistics text - FLEXIBLE FALLBACK VERSION"""
        # Get image dimensions
        h, w = img.shape[:2]
        
        # Get scaled sizes
        text_size, scale, category = FontSizeConfig.get_scaled_size('stats_text', w, h)
        spacing, _, _ = FontSizeConfig.get_scaled_size('stats_spacing', w, h)
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # Convert to OpenCV scale
        font_scale = text_size / 50.0
        thickness = max(1, int(text_size / 25))
        
        x, y = position
        
        if stat_type == 'fps':
            # FPS statistics
            if 'avg' in stats:
                text = f"AVG: {stats['avg']:.1f}"
                cv2.putText(img, text, (x, y), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
                x += spacing
            
            if 'min' in stats:
                text = f"MIN: {stats['min']:.1f}"
                color = (0, 255, 0) if stats['min'] >= 55 else (0, 200, 255) if stats['min'] >= 30 else (0, 100, 255)
                cv2.putText(img, text, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)
                x += spacing
            
            if 'max' in stats:
                text = f"MAX: {stats['max']:.1f}"
                cv2.putText(img, text, (x, y), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
        
        else:  # frametime
            if 'avg' in stats:
                text = f"AVG: {stats['avg']:.1f}ms"
                cv2.putText(img, text, (x, y), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
                x += spacing + 50
            
            if 'min' in stats:
                text = f"MIN: {stats['min']:.1f}ms"
                color = (0, 255, 0) if stats['min'] <= 20 else (0, 200, 255) if stats['min'] <= 35 else (0, 100, 255)
                cv2.putText(img, text, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)
                x += spacing + 50
            
            if 'max' in stats:
                text = f"MAX: {stats['max']:.1f}ms"
                color = (0, 255, 0) if stats['max'] <= 20 else (0, 200, 255) if stats['max'] <= 35 else (0, 100, 255)
                cv2.putText(img, text, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)
        
        return img
    
    def get_default_layout(self, width: int, height: int) -> Dict:
        """Get default layout configuration with proper 4K base scaling"""
        # Base layout at 1080p (our design resolution)
        base_width = 1920
        base_height = 1080
        
        # Calculate scale from base to target
        scale_x = width / base_width
        scale_y = height / base_height
        
        # Get template sizes for target resolution
        # Use max() so half-width comparison videos (e.g. 1920x2160) are not
        # penalised for their reduced width when scaling the template.
        template_scale = max(width / 3840, height / 2160)
        
        # Base positions at 1080p
        base_layout = {
            'fps_display': {
                'x': 50,
                'y': 32,
                'width': 90,
                'height': 70
            },
            'frame_rate_graph': {
                'x': 50,
                'y': 768,
                'width': int(1840 * template_scale),  # Scale from 4K template size
                'height': int(580 * template_scale)   # Scale from 4K template size
            },
            'frame_time_graph': {
                'x': 50,
                'y': 510,
                'width': int(800 * template_scale),   # Scale from 4K template size
                'height': int(360 * template_scale)   # Scale from 4K template size
            },
            'fps_statistics': {
                'x': 50,
                'y': 1024,
                'width': 325,
                'height': 20
            },
            'frametime_statistics': {
                'x': 256,
                'y': 490,
                'width': 230,
                'height': 20
            }
        }
        
        # Scale all positions (but not template sizes - they're already scaled)
        scaled_layout = {}
        for key, config in base_layout.items():
            scaled_layout[key] = {
                'x': int(config['x'] * scale_x),
                'y': int(config['y'] * scale_y),
                'width': config['width'] if 'graph' in key else int(config['width'] * scale_x),
                'height': config['height'] if 'graph' in key else int(config['height'] * scale_y),
                'visible': True
            }
        
        # Debug print for layout scaling
        if not hasattr(self, '_layout_scale_logged'):
            print(f"📐 Layout scaling: {width}x{height} from 1080p base")
            print(f"   Position scale: {scale_x:.3f}x, {scale_y:.3f}x")
            print(f"   Template scale: {template_scale:.3f}x from 4K")
            print(f"   FPS Graph: {scaled_layout['frame_rate_graph']['x']},{scaled_layout['frame_rate_graph']['y']} {scaled_layout['frame_rate_graph']['width']}x{scaled_layout['frame_rate_graph']['height']}")
            print(f"   FT Graph: {scaled_layout['frame_time_graph']['x']},{scaled_layout['frame_time_graph']['y']} {scaled_layout['frame_time_graph']['width']}x{scaled_layout['frame_time_graph']['height']}")
            self._layout_scale_logged = True
        
        return scaled_layout


# Backward compatibility wrapper
def create_png_template_renderer(template_dir: str = "templates") -> PNGTemplateRenderer:
    """Create and initialize PNG template renderer"""
    return PNGTemplateRenderer(template_dir)


# Drop-in replacement function for existing code
def draw_fps_overlay_with_png_templates(frame, fps_history, current_fps, frame_times=None,
                                       show_frame_time_graph=True, layout_config=None,
                                       color_settings=None, template_config=None,
                                       template_dir="templates", font_settings=None,
                                       global_fps_values=None, global_frame_times=None):
    """Drop-in replacement using PNG templates"""
    # Create renderer (could be cached globally for even better performance)
    if not hasattr(draw_fps_overlay_with_png_templates, '_renderer'):
        draw_fps_overlay_with_png_templates._renderer = PNGTemplateRenderer(template_dir)
    
    renderer = draw_fps_overlay_with_png_templates._renderer
    
    return renderer.render_overlay(
        frame, fps_history, current_fps, frame_times,
        show_frame_time_graph, layout_config, color_settings,
        template_config, font_settings, global_fps_values, global_frame_times
    )


# Example usage and integration
if __name__ == "__main__":
    print("🚀 PNG Template Overlay Renderer")
    print("================================")
    print("Key features:")
    print("✅ Pre-rendered PNG templates for static UI")
    print("✅ Aggressive caching of scaled templates")
    print("✅ Minimal draw calls per frame")
    print("✅ 10-20x performance improvement")
    print("\nUsage:")
    print("1. Place PNG templates in 'templates' directory")
    print("2. Replace draw_fps_overlay calls with draw_fps_overlay_with_png_templates")
    print("3. Enjoy massive performance boost!")
