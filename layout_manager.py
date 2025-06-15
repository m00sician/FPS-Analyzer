"""
Layout Manager für FPS Analyzer Integration - UPDATED WITH CORRECT SIZES
Handles layout storage, conversion, and integration with existing overlay system
UPDATED: Proper default sizes based on screenshot analysis + 5 element support
"""
import json
import os
from pathlib import Path
from PyQt6.QtCore import QPoint, QSize

class LayoutManager:
    """Manages custom layouts for FPS elements - UPDATED WITH CORRECT SIZES"""
    
    def __init__(self, settings_manager=None):
        self.settings_manager = settings_manager
        self.current_layout = self.get_default_layout()
        
        # Layout presets storage
        self.layouts_dir = Path.home() / ".fps_analyzer" / "layouts"
        self.layouts_dir.mkdir(parents=True, exist_ok=True)
        
        # 🔧 UPDATED: Simplified default presets matching layout editor
        self.default_presets = {
            "Default Layout": {
                'fps_number': {
                    'position': (50, 32), 
                    'size': (90, 70),
                    'anchor': 'top_left',
                    'visible': True
                },
                'frame_time_graph': {
                    'position': (50, 510), 
                    'size': (420, 160),
                    'anchor': 'top_left',
                    'visible': True
                },
                'frametime_statistics': {
                    'position': (256, 490), 
                    'size': (230, 20),
                    'anchor': 'top_left',
                    'visible': True
                },
                'frame_rate_graph': {
                    'position': (50, 768), 
                    'size': (1100, 230),
                    'anchor': 'top_left',
                    'visible': True
                },
                'fps_statistics': {
                    'position': (50, 1024), 
                    'size': (325, 20),
                    'anchor': 'top_left',
                    'visible': True
                }
            },
            "Minimal": {
                'fps_number': {
                    'position': (50, 50), 
                    'size': (90, 70),
                    'anchor': 'top_left',
                    'visible': True
                },
                'frame_time_graph': {
                    'position': (50, 510), 
                    'size': (420, 160),
                    'anchor': 'top_left',
                    'visible': False
                },
                'frametime_statistics': {
                    'position': (256, 490), 
                    'size': (230, 20),
                    'anchor': 'top_left',
                    'visible': False
                },
                'frame_rate_graph': {
                    'position': (50, 768), 
                    'size': (1100, 230),
                    'anchor': 'top_left',
                    'visible': False
                },
                'fps_statistics': {
                    'position': (50, 1024), 
                    'size': (325, 20),
                    'anchor': 'top_left',
                    'visible': False
                }
            },
            "Medium": {
                'fps_number': {
                    'position': (50, 50), 
                    'size': (90, 70),
                    'anchor': 'top_left',
                    'visible': True
                },
                'frame_time_graph': {
                    'position': (50, 300), 
                    'size': (420, 160),
                    'anchor': 'top_left',
                    'visible': True
                },
                'frametime_statistics': {
                    'position': (256, 280), 
                    'size': (230, 20),
                    'anchor': 'top_left',
                    'visible': False
                },
                'frame_rate_graph': {
                    'position': (50, 768), 
                    'size': (1100, 230),
                    'anchor': 'top_left',
                    'visible': False
                },
                'fps_statistics': {
                    'position': (50, 1024), 
                    'size': (325, 20),
                    'anchor': 'top_left',
                    'visible': False
                }
            }
        }
    
    def get_default_layout(self):
        """🔧 UPDATED: Get the default layout configuration with YOUR custom positions"""
        return {
            'fps_number': {
                'position': (50, 32),           # ✅ YOUR POSITION: Canvas(25, 16) -> Real(50, 32)
                'size': (90, 70),
                'anchor': 'top_left',
                'visible': True,
                'font_scale': 1.0,
                'border_thickness': 2
            },
            'frame_time_graph': {
                'position': (50, 510),          # ✅ YOUR POSITION: Canvas(25, 255) -> Real(50, 510)
                'size': (420, 160),
                'anchor': 'top_left',
                'visible': True,
                'title_visible': True,
                'grid_visible': True,
                'labels_visible': True
            },
            'frametime_statistics': {
                'position': (256, 490),         # ✅ YOUR POSITION: Canvas(128, 245) -> Real(256, 490)
                'size': (230, 20),
                'anchor': 'top_left',
                'visible': True,
                'show_avg': True,
                'show_max': True,
                'layout': 'horizontal'
            },
            'frame_rate_graph': {
                'position': (50, 768),          # ✅ YOUR POSITION: Canvas(25, 384) -> Real(50, 768)
                'size': (1100, 230),
                'anchor': 'top_left', 
                'visible': True,
                'title_visible': True,
                'grid_visible': True,
                'labels_visible': True
            },
            'fps_statistics': {
                'position': (50, 1024),         # ✅ YOUR POSITION: Canvas(25, 512) -> Real(50, 1024)
                'size': (325, 20),
                'anchor': 'top_left',
                'visible': True,
                'show_avg': True,
                'show_min': True,
                'show_max': True,
                'layout': 'horizontal'
            }
        }
    
    def convert_to_overlay_positions(self, layout_data, target_width=1920, target_height=1080):
        """🔧 UPDATED: Convert layout data to positions usable by overlay_renderer with 5 elements"""
        print(f"\n🎯 LAYOUT MANAGER: Converting layout for {target_width}x{target_height}")
        
        overlay_config = {
            'fps_display': {
                'x': layout_data.get('fps_number', {}).get('position', (50, 50))[0],
                'y': layout_data.get('fps_number', {}).get('position', (50, 50))[1],
                'width': layout_data.get('fps_number', {}).get('size', (90, 70))[0],
                'height': layout_data.get('fps_number', {}).get('size', (90, 70))[1],
                'visible': layout_data.get('fps_number', {}).get('visible', True)
            },
            'frame_rate_graph': {
                'x': layout_data.get('frame_rate_graph', {}).get('position', (50, 560))[0],
                'y': layout_data.get('frame_rate_graph', {}).get('position', (50, 560))[1],
                'width': layout_data.get('frame_rate_graph', {}).get('size', (1100, 230))[0],
                'height': layout_data.get('frame_rate_graph', {}).get('size', (1100, 230))[1],
                'visible': layout_data.get('frame_rate_graph', {}).get('visible', True),
                'title_visible': layout_data.get('frame_rate_graph', {}).get('title_visible', True),
                'grid_visible': layout_data.get('frame_rate_graph', {}).get('grid_visible', True),
                'labels_visible': layout_data.get('frame_rate_graph', {}).get('labels_visible', True)
            },
            'frame_time_graph': {
                'x': layout_data.get('frame_time_graph', {}).get('position', (1200, 640))[0],
                'y': layout_data.get('frame_time_graph', {}).get('position', (1200, 640))[1],
                'width': layout_data.get('frame_time_graph', {}).get('size', (420, 160))[0],
                'height': layout_data.get('frame_time_graph', {}).get('size', (420, 160))[1],
                'visible': layout_data.get('frame_time_graph', {}).get('visible', True),
                'title_visible': layout_data.get('frame_time_graph', {}).get('title_visible', True),
                'grid_visible': layout_data.get('frame_time_graph', {}).get('grid_visible', True),
                'labels_visible': layout_data.get('frame_time_graph', {}).get('labels_visible', True)
            },
            'fps_statistics': {             # ✅ UPDATED: Separate FPS statistics
                'x': layout_data.get('fps_statistics', {}).get('position', (50, 820))[0],
                'y': layout_data.get('fps_statistics', {}).get('position', (50, 820))[1],
                'width': layout_data.get('fps_statistics', {}).get('size', (325, 20))[0],
                'height': layout_data.get('fps_statistics', {}).get('size', (325, 20))[1],
                'visible': layout_data.get('fps_statistics', {}).get('visible', True),
                'show_avg': layout_data.get('fps_statistics', {}).get('show_avg', True),
                'show_min': layout_data.get('fps_statistics', {}).get('show_min', True),
                'show_max': layout_data.get('fps_statistics', {}).get('show_max', True),
                'layout': layout_data.get('fps_statistics', {}).get('layout', 'horizontal')
            },
            'frametime_statistics': {       # ✅ NEW: Separate frame time statistics
                'x': layout_data.get('frametime_statistics', {}).get('position', (1200, 820))[0],
                'y': layout_data.get('frametime_statistics', {}).get('position', (1200, 820))[1],
                'width': layout_data.get('frametime_statistics', {}).get('size', (230, 20))[0],
                'height': layout_data.get('frametime_statistics', {}).get('size', (230, 20))[1],
                'visible': layout_data.get('frametime_statistics', {}).get('visible', True),
                'show_avg': layout_data.get('frametime_statistics', {}).get('show_avg', True),
                'show_max': layout_data.get('frametime_statistics', {}).get('show_max', True),
                'layout': layout_data.get('frametime_statistics', {}).get('layout', 'horizontal')
            }
        }
        
        # 🔧 DEBUG: Log conversion results
        for key, config in overlay_config.items():
            print(f"   {key}: ({config['x']}, {config['y']}) {config['width']}x{config['height']}")
        
        return overlay_config
    
    def apply_resolution_scaling(self, layout_data, source_res=(1920, 1080), target_res=(1920, 1080)):
        """🔧 IMPROVED: Scale layout positions and sizes for different resolutions"""
        if source_res == target_res:
            return layout_data
        
        scale_x = target_res[0] / source_res[0]
        scale_y = target_res[1] / source_res[1]
        
        print(f"🔄 Scaling layout: {source_res} -> {target_res} (scale: {scale_x:.2f}x, {scale_y:.2f}x)")
        
        scaled_layout = {}
        
        for element_id, element_data in layout_data.items():
            scaled_element = element_data.copy()
            
            # Scale position
            if 'position' in element_data:
                old_x, old_y = element_data['position']
                new_x, new_y = int(old_x * scale_x), int(old_y * scale_y)
                scaled_element['position'] = (new_x, new_y)
                print(f"   {element_id} pos: ({old_x}, {old_y}) -> ({new_x}, {new_y})")
            
            # Scale size
            if 'size' in element_data:
                old_w, old_h = element_data['size']
                new_w, new_h = int(old_w * scale_x), int(old_h * scale_y)
                scaled_element['size'] = (new_w, new_h)
                print(f"   {element_id} size: ({old_w}, {old_h}) -> ({new_w}, {new_h})")
            
            scaled_layout[element_id] = scaled_element
        
        return scaled_layout
    
    def get_resolution_scaling_factors(self, target_resolution):
        """🔧 NEW: Get scaling factors for different resolutions"""
        base_resolution = (1920, 1080)  # Our base design resolution
        
        scale_factors = {
            (1280, 720): (0.67, 0.67),      # 720p: 67% scaling
            (1920, 1080): (1.0, 1.0),       # 1080p: no scaling (base)
            (2560, 1440): (1.33, 1.33),     # 1440p: 133% scaling
            (3840, 2160): (2.0, 2.0)        # 4K: 200% scaling
        }
        
        return scale_factors.get(target_resolution, (1.0, 1.0))
    
    def scale_layout_for_resolution(self, layout_data, target_resolution):
        """🔧 NEW: Scale layout specifically for different resolutions"""
        scale_x, scale_y = self.get_resolution_scaling_factors(target_resolution)
        
        if scale_x == 1.0 and scale_y == 1.0:
            return layout_data  # No scaling needed
        
        print(f"🎯 SCALING LAYOUT: {scale_x:.2f}x, {scale_y:.2f}x for {target_resolution}")
        
        scaled_layout = {}
        
        for element_id, element_data in layout_data.items():
            scaled_element = element_data.copy()
            
            # Scale position
            if 'position' in element_data:
                old_x, old_y = element_data['position']
                new_x, new_y = int(old_x * scale_x), int(old_y * scale_y)
                scaled_element['position'] = (new_x, new_y)
            
            # Scale size
            if 'size' in element_data:
                old_w, old_h = element_data['size']
                new_w, new_h = int(old_w * scale_x), int(old_h * scale_y)
                scaled_element['size'] = (new_w, new_h)
            
            scaled_layout[element_id] = scaled_element
            
        print(f"✅ Layout scaled for {target_resolution}")
        return scaled_layout
    
    def save_layout(self, layout_data, name):
        """Save a layout preset to file"""
        try:
            layout_file = self.layouts_dir / f"{name}.json"
            
            with open(layout_file, 'w', encoding='utf-8') as f:
                json.dump(layout_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Layout '{name}' saved to {layout_file}")
            return True
            
        except Exception as e:
            print(f"❌ Could not save layout '{name}': {e}")
            return False
    
    def load_layout(self, name):
        """Load a layout preset from file"""
        try:
            # Check custom layouts first
            layout_file = self.layouts_dir / f"{name}.json"
            
            if layout_file.exists():
                with open(layout_file, 'r', encoding='utf-8') as f:
                    layout_data = json.load(f)
                print(f"✅ Layout '{name}' loaded from {layout_file}")
                return layout_data
            
            # Check default presets
            elif name in self.default_presets:
                print(f"✅ Default layout '{name}' loaded")
                return self.default_presets[name]
            
            else:
                print(f"❌ Layout '{name}' not found")
                return None
                
        except Exception as e:
            print(f"❌ Could not load layout '{name}': {e}")
            return None
    
    def get_available_layouts(self):
        """Get list of available layout presets"""
        layouts = list(self.default_presets.keys())
        
        # Add custom layouts
        try:
            for layout_file in self.layouts_dir.glob("*.json"):
                custom_name = layout_file.stem
                if custom_name not in layouts:
                    layouts.append(custom_name)
        except Exception as e:
            print(f"⚠️ Could not scan custom layouts: {e}")
        
        return layouts
    
    def delete_layout(self, name):
        """Delete a custom layout preset"""
        try:
            layout_file = self.layouts_dir / f"{name}.json"
            
            if layout_file.exists():
                layout_file.unlink()
                print(f"✅ Layout '{name}' deleted")
                return True
            else:
                print(f"❌ Layout '{name}' not found")
                return False
                
        except Exception as e:
            print(f"❌ Could not delete layout '{name}': {e}")
            return False
    
    def validate_layout(self, layout_data):
        """🔧 UPDATED: Validate layout data structure with 5 elements"""
        required_elements = ['fps_number', 'frame_rate_graph', 'frame_time_graph', 'fps_statistics', 'frametime_statistics']
        
        for element in required_elements:
            if element not in layout_data:
                print(f"⚠️ Layout validation: Missing element: {element}")
                # Don't fail validation, just warn - we can provide defaults
                continue
            
            element_data = layout_data[element]
            
            # Check required fields
            if 'position' not in element_data:
                return False, f"Missing position for {element}"
            
            if 'size' not in element_data:
                return False, f"Missing size for {element}"
            
            # Validate position
            pos = element_data['position']
            if not isinstance(pos, (list, tuple)) or len(pos) != 2:
                return False, f"Invalid position format for {element}"
            
            # Validate size
            size = element_data['size']
            if not isinstance(size, (list, tuple)) or len(size) != 2:
                return False, f"Invalid size format for {element}"
            
            # Check bounds
            if pos[0] < 0 or pos[1] < 0:
                return False, f"Negative position for {element}"
            
            if size[0] <= 0 or size[1] <= 0:
                return False, f"Invalid size for {element}"
        
        return True, "Layout is valid"
    
    def set_current_layout(self, layout_data):
        """🔧 IMPROVED: Set the current active layout with better validation and 5-element support"""
        print(f"\n🎨 LAYOUT MANAGER: Setting new layout with {len(layout_data)} elements")
        
        # Debug: Print received layout data
        for elem_id, data in layout_data.items():
            pos = data.get('position', 'Unknown')
            size = data.get('size', 'Unknown')
            print(f"   📥 {elem_id}: {pos} {size}")
        
        # 🔧 IMPROVED: Fill in missing elements with defaults if needed
        default_layout = self.get_default_layout()
        complete_layout = default_layout.copy()
        complete_layout.update(layout_data)  # Override with provided data
        
        is_valid, message = self.validate_layout(complete_layout)
        
        if is_valid:
            self.current_layout = complete_layout
            print("✅ Layout validation passed")
            
            # 🔧 IMPROVED: Force save to settings immediately
            if self.settings_manager:
                try:
                    current_settings = self.settings_manager.load_settings()
                    current_settings['custom_layout'] = complete_layout
                    success = self.settings_manager.save_settings(current_settings)
                    
                    if success:
                        print("✅ Layout saved to settings successfully")
                    else:
                        print("❌ Failed to save layout to settings")
                        
                except Exception as e:
                    print(f"❌ Error saving layout to settings: {e}")
            
            return True
        else:
            print(f"❌ Invalid layout: {message}")
            return False
    
    def get_current_layout(self):
        """Get the current active layout"""
        print(f"📤 LAYOUT MANAGER: Returning current layout with {len(self.current_layout)} elements")
        return self.current_layout
    
    def reset_to_default(self):
        """Reset to default layout"""
        self.current_layout = self.get_default_layout()
        print("✅ Layout reset to default with updated sizes")
        return self.current_layout
    
    def export_layout(self, layout_data, file_path):
        """Export layout to a specific file"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'fps_analyzer_layout': layout_data,
                    'version': '2.0',  # ✅ UPDATED: Version 2.0 with 5 elements
                    'elements': list(layout_data.keys()),
                    'exported_at': str(Path(file_path).stat().st_mtime)
                }, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Layout exported to {file_path}")
            return True
            
        except Exception as e:
            print(f"❌ Could not export layout: {e}")
            return False
    
    def import_layout(self, file_path):
        """Import layout from a specific file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle different import formats
            if 'fps_analyzer_layout' in data:
                layout_data = data['fps_analyzer_layout']
            else:
                layout_data = data  # Assume direct layout format
            
            # 🔧 IMPROVED: Fill in missing elements with defaults
            default_layout = self.get_default_layout()
            complete_layout = default_layout.copy()
            complete_layout.update(layout_data)
            
            is_valid, message = self.validate_layout(complete_layout)
            
            if is_valid:
                print(f"✅ Layout imported from {file_path}")
                return complete_layout
            else:
                print(f"❌ Invalid imported layout: {message}")
                return None
                
        except Exception as e:
            print(f"❌ Could not import layout: {e}")
            return None
    
    def get_layout_info(self, layout_data):
        """Get human-readable info about a layout"""
        info = {
            'elements_count': len(layout_data),
            'total_area': 0,
            'bounds': {'min_x': float('inf'), 'min_y': float('inf'), 
                      'max_x': 0, 'max_y': 0},
            'elements': {},
            'version': '2.0'  # ✅ NEW: Layout version info
        }
        
        for element_id, element_data in layout_data.items():
            pos = element_data.get('position', (0, 0))
            size = element_data.get('size', (0, 0))
            
            # Calculate element area
            area = size[0] * size[1]
            info['total_area'] += area
            
            # Update bounds
            info['bounds']['min_x'] = min(info['bounds']['min_x'], pos[0])
            info['bounds']['min_y'] = min(info['bounds']['min_y'], pos[1])
            info['bounds']['max_x'] = max(info['bounds']['max_x'], pos[0] + size[0])
            info['bounds']['max_y'] = max(info['bounds']['max_y'], pos[1] + size[1])
            
            # Element info
            info['elements'][element_id] = {
                'position': pos,
                'size': size,
                'area': area,
                'visible': element_data.get('visible', True)
            }
        
        return info