"""
Update FPS Analyzer to use TrueType Font Rendering
This script updates the FPS Analyzer code to use the DirectTTFRenderer
and FontBridge for TrueType font rendering with zero OpenCV fallbacks.
"""

import os
import sys
import re
import shutil
from datetime import datetime

def backup_file(file_path):
    """Create a backup of a file"""
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.{timestamp}.bak"
    
    try:
        shutil.copy2(file_path, backup_path)
        print(f"✅ Backup created: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to create backup: {e}")
        return False

def update_fps_analyzer_main(file_path):
    """Update fps_analyzer_main.py to use TrueType fonts"""
    if not backup_file(file_path):
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add import for TTFontSettings
        import_pattern = r'import torch\n'
        import_replacement = 'import torch\nfrom font_bridge import TTFontSettings, create_default_font_settings\n'
        content = re.sub(import_pattern, import_replacement, content)
        
        # Replace font initialization in initialize_font_settings
        font_init_pattern = r'def initialize_font_settings\(self, saved_settings\):.*?self\._initialize_legacy_fonts\(saved_settings\)'
        font_init_replacement = """def initialize_font_settings(self, saved_settings):
        \"\"\"🎨 TrueType font initialization with zero OpenCV fallbacks\"\"\"
        try:
            print("🎨 Initializing TrueType Font System...")
            
            # Use FontBridge to create default font settings
            font_settings = create_default_font_settings()
            
            # Configure fonts from saved settings
            self.fps_font_settings = font_settings['fps_font']
            self.framerate_font_settings = font_settings['framerate_font']  
            self.frametime_font_settings = font_settings['frametime_font']
            
            # Apply saved settings if available
            if hasattr(saved_settings, 'get'):
                # FPS font settings
                fps_size = saved_settings.get('fps_font_size', 32)
                self.fps_font_settings.size = fps_size
                self.fps_font_settings.bold = saved_settings.get('fps_font_bold', True)
                self.fps_font_settings.thickness = saved_settings.get('fps_font_thickness', 3)
                self.fps_font_settings.border_thickness = saved_settings.get('fps_font_border', 3)
                
                # Framerate font settings
                framerate_size = saved_settings.get('framerate_font_size', 16)
                self.framerate_font_settings.size = framerate_size
                self.framerate_font_settings.bold = saved_settings.get('framerate_font_bold', False)
                self.framerate_font_settings.thickness = saved_settings.get('framerate_font_thickness', 2)
                self.framerate_font_settings.border_thickness = saved_settings.get('framerate_font_border', 2)
                
                # Frametime font settings
                frametime_size = saved_settings.get('frametime_font_size', 14)
                self.frametime_font_settings.size = frametime_size
                self.frametime_font_settings.bold = saved_settings.get('frametime_font_bold', False)
                self.frametime_font_settings.thickness = saved_settings.get('frametime_font_thickness', 1)
                self.frametime_font_settings.border_thickness = saved_settings.get('frametime_font_border', 1)
            
            # Status summary
            print(f"✅ TrueType Font Settings initialized successfully:")
            print(f"   • FPS Font: {self.fps_font_settings.font_name}, Size: {self.fps_font_settings.size}")
            print(f"   • Framerate Font: {self.framerate_font_settings.font_name}, Size: {self.framerate_font_settings.size}")
            print(f"   • Frametime Font: {self.frametime_font_settings.font_name}, Size: {self.frametime_font_settings.size}")
            
        except Exception as e:
            print(f"⚠️ Error initializing TrueType font settings: {e}")
            print("🔄 Creating basic TrueType font settings")
            
            # Create basic TrueType font settings
            font_settings = create_default_font_settings()
            self.fps_font_settings = font_settings['fps_font']
            self.framerate_font_settings = font_settings['framerate_font']
            self.frametime_font_settings = font_settings['frametime_font']"""
        
        content = re.sub(font_init_pattern, font_init_replacement, content, flags=re.DOTALL)
        
        # Remove legacy font initialization
        legacy_pattern = r'def _initialize_legacy_fonts.*?def'
        content = re.sub(legacy_pattern, 'def', content, flags=re.DOTALL)
        
        # Update save_current_settings method to store TrueType font settings
        save_settings_pattern = r'def save_current_settings\(self\):.*?self\.settings_manager\.save_settings\(settings\)'
        save_settings_replacement = """def save_current_settings(self):
        \"\"\"🔧 ENHANCED: Save current settings including TrueType font settings\"\"\"
        try:
            # Get current bitrate value properly
            current_bitrate = 60  # fallback
            if hasattr(self, 'bitrate_combo'):
                bitrate_data = self.bitrate_combo.currentData()
                if bitrate_data == 'opencv':
                    current_bitrate = 'opencv'
                elif isinstance(bitrate_data, str) and bitrate_data.isdigit():
                    current_bitrate = int(bitrate_data)
                else:
                    current_bitrate = 60

            # Store TrueType font settings
            settings = {
                # TrueType font settings
                'fps_font_name': self.fps_font_settings.font_name,
                'fps_font_path': getattr(self.fps_font_settings, 'font_path', None),
                'fps_font_size': self.fps_font_settings.size,
                'fps_font_thickness': self.fps_font_settings.thickness,
                'fps_font_bold': self.fps_font_settings.bold,
                'fps_font_border': self.fps_font_settings.border_thickness,

                'framerate_font_name': self.framerate_font_settings.font_name,
                'framerate_font_path': getattr(self.framerate_font_settings, 'font_path', None),
                'framerate_font_size': self.framerate_font_settings.size,
                'framerate_font_thickness': self.framerate_font_settings.thickness,
                'framerate_font_bold': self.framerate_font_settings.bold,
                'framerate_font_border': self.framerate_font_settings.border_thickness,

                'frametime_font_name': self.frametime_font_settings.font_name,
                'frametime_font_path': getattr(self.frametime_font_settings, 'font_path', None),
                'frametime_font_size': self.frametime_font_settings.size,
                'frametime_font_thickness': self.frametime_font_settings.thickness,
                'frametime_font_bold': self.frametime_font_settings.bold,
                'frametime_font_border': self.frametime_font_settings.border_thickness,

                # Color settings
                'framerate_color': self.framerate_color,
                'frametime_color': self.frametime_color,

                # UI settings
                'output_resolution': self.resolution_combo.currentData() if hasattr(self, 'resolution_combo') else (1920, 1080),
                'bitrate': current_bitrate,
                'frametime_scale_index': self.frametime_scale_combo.currentIndex() if hasattr(self, 'frametime_scale_combo') else 1,
                'sensitivity_index': self.sensitivity_combo.currentIndex() if hasattr(self, 'sensitivity_combo') else 2,

                # Other settings
                'theme': self.current_theme,
                'ftg_position': getattr(self, 'ftg_position', 'bottom_right'),
                'internal_resolution': self.internal_resolution,

                # Layout settings
                'custom_layout': self.layout_manager.get_current_layout() if hasattr(self, 'layout_manager') else None,
                
                # Font system info
                'font_system_version': 'ttf_direct_renderer',
                'ttf_renderer_active': True
            }

            self.settings_manager.save_settings(settings)
            
            self.log(f"✅ Settings saved successfully with TrueType font configuration")

        except Exception as e:
            self.log(f"❌ Could not save settings: {e}")"""
        
        content = re.sub(save_settings_pattern, save_settings_replacement, content, flags=re.DOTALL)
        
        # Update show_font_preview method
        font_preview_pattern = r'def show_font_preview\(self\):.*?except Exception as e:.*?QMessageBox\.warning\(self, \'Font Preview Error\', f\'Font preview error: {str\(e\)}\'\)'
        font_preview_replacement = """def show_font_preview(self):
        \"\"\"🎨 Show TrueType font preview dialog\"\"\"
        try:
            # Get current frame if video is loaded
            current_frame = None
            if self.video_cap and self.video_cap.isOpened():
                current_pos = self.video_cap.get(cv2.CAP_PROP_POS_FRAMES)
                ret, frame = self.video_cap.read()
                if ret:
                    current_frame = frame
                    self.video_cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, current_pos - 1))

            # Import font preview dialog
            from font_manager import FontPreviewDialog
            
            # Open preview dialog
            preview_dialog = FontPreviewDialog(self, current_frame)
            preview_dialog.show()

            self.log("🎨 TrueType Font preview opened!")

        except ImportError as e:
            self.log(f"❌ Could not open font preview: {e}")
            QMessageBox.warning(self, 'Font Preview Error', 
                               f'Could not open font preview:\\n{str(e)}\\n\\nPlease check that font_manager.py is available.')
        except Exception as e:
            self.log(f"❌ Font preview error: {e}")
            QMessageBox.warning(self, 'Font Preview Error', f'Font preview error: {str(e)}')"""
        
        content = re.sub(font_preview_pattern, font_preview_replacement, content, flags=re.DOTALL)
        
        # Update select_opencv_fonts method
        select_fonts_pattern = r'def select_opencv_fonts\(self\):.*?except Exception as e:.*?QMessageBox\.warning\(self, \'Font Selection Error\', f\'Error opening font selection:\\n{str\(e\)}\'\)'
        select_fonts_replacement = """def select_opencv_fonts(self):
        \"\"\"🎨 Open TrueType Font Selection Dialog\"\"\"
        try:
            # Import font selection dialog
            from font_manager import OpenCVFontSelectionDialog
            from PyQt6.QtWidgets import QDialog

            # Open dialog
            dialog = OpenCVFontSelectionDialog(self, self.fps_font_settings, 
                                             self.framerate_font_settings, self.frametime_font_settings)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                fps_settings, framerate_settings, frametime_settings = dialog.get_selected_settings()

                # Update font settings
                self.fps_font_settings = fps_settings
                self.framerate_font_settings = framerate_settings
                self.frametime_font_settings = frametime_settings

                self.log(f"✅ TrueType Fonts updated:")
                self.log(f"  • FPS: {fps_settings.font_name}, Size: {fps_settings.size}")
                self.log(f"  • Framerate: {framerate_settings.font_name}, Size: {framerate_settings.size}")
                self.log(f"  • Frametime: {frametime_settings.font_name}, Size: {frametime_settings.size}")

                # Save settings
                self.save_current_settings()
        except Exception as e:
            self.log(f"❌ Font selection error: {e}")
            QMessageBox.warning(self, 'Font Selection Error', f'Error opening font selection:\\n{str(e)}')"""
        
        content = re.sub(select_fonts_pattern, select_fonts_replacement, content, flags=re.DOTALL)
        
        # Update get_current_settings to ensure TrueType fonts
        get_settings_pattern = r'def get_current_settings\(self\):.*?return settings'
        get_settings_replacement = """def get_current_settings(self):
        \"\"\"Extract current settings from UI widgets with TrueType font enforcement\"\"\"
        try:
            # ✅ FIXED: Bitrate - handle OpenCV vs FFmpeg correctly
            bitrate_widget = self.bitrate_combo
            if hasattr(bitrate_widget, 'currentData'):
                bitrate_data = bitrate_widget.currentData()
                if bitrate_data == 'opencv':
                    bitrate_value = 'opencv'  # Keep as string
                elif isinstance(bitrate_data, str) and bitrate_data.isdigit():
                    bitrate_value = int(bitrate_data)  # Convert to int
                else:
                    bitrate_value = 60  # Fallback
            else:
                bitrate_value = 60

            # Resolution
            resolution_widget = self.resolution_combo
            if hasattr(resolution_widget, 'currentData'):
                resolution = resolution_widget.currentData()
            else:
                resolution = (1920, 1080)

            # Frame time scale
            frametime_widget = self.frametime_scale_combo
            if hasattr(frametime_widget, 'currentData'):
                frametime_scale = frametime_widget.currentData()
            else:
                frametime_scale = {'min': 16.7, 'mid': 33.3, 'max': 50.0, 'labels': ['16.7', '33.3', '50.0']}

            # Detection sensitivity
            sensitivity_widget = self.sensitivity_combo
            if hasattr(sensitivity_widget, 'currentData'):
                diff_threshold = sensitivity_widget.currentData()
            else:
                diff_threshold = 0.002

            # Ensure we have TrueType font settings
            if not hasattr(self, 'fps_font_settings') or not hasattr(self.fps_font_settings, 'render_text'):
                from font_bridge import create_default_font_settings
                font_settings = create_default_font_settings()
                self.fps_font_settings = font_settings['fps_font']
                self.framerate_font_settings = font_settings['framerate_font']
                self.frametime_font_settings = font_settings['frametime_font']

            settings = {
                'resolution': resolution,
                'bitrate': bitrate_value,
                'use_cuda': self.use_cuda_checkbox.isChecked() and self.cuda_available,
                'show_frametime': self.show_frametime_checkbox.isChecked(),
                'frametime_scale': frametime_scale,
                'diff_threshold': diff_threshold,
                'ftg_position': getattr(self, 'ftg_position', 'bottom_right'),
                'font_settings': {
                    'fps_font': self.fps_font_settings,
                    'framerate_font': self.framerate_font_settings,
                    'frametime_font': self.frametime_font_settings
                },
                'color_settings': {
                    'framerate_color': self.framerate_color,
                    'frametime_color': self.frametime_color
                },
                'layout_config': self.layout_manager.convert_to_overlay_positions(
                    self.layout_manager.get_current_layout(),
                    resolution[0],
                    resolution[1]
                ),
                'start_frame': self.start_frame,
                'end_frame': self.end_frame,
                'ttf_renderer_active': True
            }

            # Save current settings for next session
            self.save_current_settings()

            return settings

        except Exception as e:
            self.log(f"❌ Error extracting settings: {e}")
            import traceback
            traceback.print_exc()
            return self.get_fallback_settings()"""
        
        content = re.sub(get_settings_pattern, get_settings_replacement, content, flags=re.DOTALL)
        
        # Update get_fallback_settings to use TrueType fonts
        fallback_pattern = r'def get_fallback_settings\(self\):.*?return \{.*?\}'
        fallback_replacement = """def get_fallback_settings(self):
        \"\"\"Fallback settings with TrueType fonts when extraction fails\"\"\"
        try:
            # Create default TrueType font settings
            from font_bridge import create_default_font_settings
            font_settings = create_default_font_settings()
            
            return {
                'resolution': (1920, 1080),
                'bitrate': 60,
                'use_cuda': False,
                'show_frametime': True,
                'frametime_scale': {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']},
                'diff_threshold': 0.002,
                'ftg_position': 'bottom_right',
                'font_settings': font_settings,
                'color_settings': {
                    'framerate_color': self.framerate_color,
                    'frametime_color': self.frametime_color
                },
                'layout_config': self.layout_manager.convert_to_overlay_positions(
                    self.layout_manager.get_default_layout(),
                    1920, 1080
                ),
                'start_frame': None,
                'end_frame': None,
                'ttf_renderer_active': True
            }
        except Exception as e:
            print(f"❌ Fatal error creating fallback settings: {e}")
            # Ultimate emergency fallback
            return {
                'resolution': (1920, 1080),
                'bitrate': 60,
                'use_cuda': False,
                'show_frametime': True,
                'frametime_scale': {'min': 10, 'mid': 35, 'max': 60, 'labels': ['10', '35', '60']},
                'diff_threshold': 0.002,
                'ftg_position': 'bottom_right'
            }"""
        
        content = re.sub(fallback_pattern, fallback_replacement, content, flags=re.DOTALL)
        
        # Write updated content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Updated {file_path}")
        return True
    
    except Exception as e:
        print(f"❌ Failed to update {file_path}: {e}")
        return False

def update_analysis_worker(file_path):
    """Update analysis_worker.py to use TrueType fonts"""
    if not backup_file(file_path):
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add import for TTFontSettings
        import_pattern = r'from PyQt6.QtGui import QFont\n'
        import_replacement = 'from PyQt6.QtGui import QFont\nfrom font_bridge import TTFontSettings, create_default_font_settings\n'
        content = re.sub(import_pattern, import_replacement, content)
        
        # Update the create_overlay method to force TrueType
        create_overlay_pattern = r'def create_overlay\(self, frame_rgb, fps_history, displayed_fps, frame_times, show_frametime, .*?return overlay'
        create_overlay_replacement = """def create_overlay(self, frame_rgb, fps_history, displayed_fps, frame_times, show_frametime, 
                    global_fps_values, global_frame_times, frametime_scale, font_settings, color_settings):
        \"\"\"Create FPS overlay with TrueType font rendering - NO OpenCV fallbacks\"\"\"
        
        # 🔍 DEBUG: Verify TrueType font settings
        if font_settings is None or not all(hasattr(font, 'render_text') for font in font_settings.values()):
            print("🔍 WARNING: Missing or invalid font settings - creating TrueType fonts")
            try:
                # Create new TrueType font settings
                font_settings = create_default_font_settings()
                
                # Apply color settings if available
                if color_settings:
                    if 'framerate_color' in color_settings:
                        font_settings['framerate_font'].text_color = color_settings['framerate_color']
                    if 'frametime_color' in color_settings:
                        font_settings['frametime_font'].text_color = color_settings['frametime_color']
            except Exception as e:
                print(f"❌ TrueType font creation failed: {e}")
                # Create minimal emergency settings
                font_settings = create_default_font_settings()
        
        # 🔍 DEBUG: Enhanced diagnostics for font settings
        print(f"🔍 DEBUG create_overlay: FPS={displayed_fps:.1f}, Font-Settings: {font_settings is not None}")
        for font_type, settings in font_settings.items():
            if hasattr(settings, 'font_name'):
                print(f"   • {font_type}: {settings.font_name}")
        
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
        
        # ✨ ULTIMATE FALLBACK: Minimal overlay with TrueType fonts
        print("⚠️ All renderers failed, using minimal TrueType overlay")
        try:
            # Create blank overlay
            overlay = frame_rgb.copy()
            
            # Get TrueType font settings
            try:
                fps_font = font_settings.get('fps_font')
                if not hasattr(fps_font, 'render_text'):
                    # Create new TrueType font
                    fps_font = TTFontSettings(
                        font_name="arial",
                        size=32,
                        thickness=3,
                        bold=True,
                        border_thickness=3,
                        text_color=(0, 255, 0),
                        border_color=(0, 0, 0)
                    )
            except:
                # Emergency font creation
                fps_font = TTFontSettings()
                fps_font.text_color = (0, 255, 0)
            
            # Render FPS with TrueType font
            overlay = fps_font.render_text(
                overlay, 
                f"FPS: {displayed_fps:.1f}", 
                (50, 50)
            )
            
            # Add minimal message
            try:
                emergency_font = TTFontSettings(
                    font_name="arial",
                    size=16,
                    thickness=2,
                    text_color=(255, 255, 0)
                )
                overlay = emergency_font.render_text(
                    overlay,
                    "TrueType Emergency Mode",
                    (50, 100)
                )
            except:
                pass
            
            return overlay
            
        except Exception as e:
            print(f"❌ Even minimal TrueType rendering failed: {e}")
            # This should never happen but just in case
            return frame_rgb"""
        
        content = re.sub(create_overlay_pattern, create_overlay_replacement, content, flags=re.DOTALL)
        
        # Write updated content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Updated {file_path}")
        return True
    
    except Exception as e:
        print(f"❌ Failed to update {file_path}: {e}")
        return False

def update_enhanced_overlay_renderer(file_path):
    """Update enhanced_overlay_renderer.py to use TrueType fonts"""
    if not backup_file(file_path):
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add import for TTFontSettings
        import_pattern = r'import numpy as np\n'
        import_replacement = 'import numpy as np\nfrom font_bridge import TTFontSettings, create_default_font_settings\n'
        content = re.sub(import_pattern, import_replacement, content)
        
        # Update the draw_text_with_border method to force TrueType
        text_method_pattern = r'def draw_text_with_border\(self, img, text, position, font, font_scale, color, thickness, .*?return img  # Return original image as last resort'
        text_method_replacement = """def draw_text_with_border(self, img, text, position, font, font_scale, color, thickness, 
                        border_color=(0, 0, 0), border_thickness=2):
        \"\"\"Enhanced text rendering with GUARANTEED TrueType font support - NO OpenCV fallbacks\"\"\"
        try:
            # Check if we have enhanced font settings
            if hasattr(font, 'render_text'):
                # Use enhanced font rendering
                effective_scale = self.scale_factor * self.resolution_scale
                
                # Set text color for enhanced rendering
                font.text_color = color
                if border_thickness > 0:
                    font.border_color = border_color
                    font.border_thickness = border_thickness
                
                # Render with TrueType font
                return font.render_text(img, text, position, effective_scale)
            else:
                # Convert to TTFontSettings on the fly
                tt_font = TTFontSettings(
                    font_name="arial",
                    size=24 * font_scale,
                    thickness=thickness,
                    bold=False,
                    border_thickness=border_thickness,
                    border_color=border_color,
                    text_color=color
                )
                
                # Render with TrueType font
                effective_scale = self.scale_factor * self.resolution_scale
                return tt_font.render_text(img, text, position, effective_scale)
        except Exception as e:
            print(f"❌ TrueType text rendering failed: {e}")
            print(f"Text: '{text}', Position: {position}")
            import traceback
            traceback.print_exc()
            
            # Create emergency TrueType rendering - NEVER fall back to OpenCV
            try:
                emergency_font = TTFontSettings()
                emergency_font.text_color = color
                emergency_font.border_color = border_color
                emergency_font.border_thickness = border_thickness
                return emergency_font.render_text(img, text, position, 1.0)
            except Exception as e2:
                print(f"❌ Emergency TrueType rendering also failed: {e2}")
                # Return original image as absolute last resort
                return img"""
        
        content = re.sub(text_method_pattern, text_method_replacement, content, flags=re.DOTALL)
        
        # Remove the _legacy_text_rendering method
        legacy_pattern = r'def _legacy_text_rendering\(self, img, text, position, font, font_scale, .*?return img'
        legacy_replacement = """def _legacy_text_rendering(self, img, text, position, font, font_scale, 
                                             color, thickness, border_color, border_thickness):
        \"\"\"Legacy method replaced with TrueType rendering\"\"\"
        # Create TrueType font
        tt_font = TTFontSettings(
            font_name="arial",
            size=24 * font_scale,
            thickness=thickness,
            bold=False,
            border_thickness=border_thickness,
            border_color=border_color,
            text_color=color
        )
        
        # Render with TrueType font
        effective_scale = self.scale_factor * self.resolution_scale
        return tt_font.render_text(img, text, position, effective_scale)"""
        
        content = re.sub(legacy_pattern, legacy_replacement, content, flags=re.DOTALL)
        
        # Update the _convert_to_enhanced_fonts method
        convert_fonts_pattern = r'def _convert_to_enhanced_fonts\(self, font_settings\):.*?return enhanced_settings'
        convert_fonts_replacement = """def _convert_to_enhanced_fonts(self, font_settings):
        \"\"\"Convert legacy font settings to enhanced font settings with TrueType\"\"\"
        if not font_settings:
            return self._get_default_enhanced_fonts()
        
        # Create TrueType font settings
        enhanced_settings = {}
        
        # Check each font and ensure it's a TrueType font
        for font_type, settings in font_settings.items():
            if hasattr(settings, 'render_text'):
                # Already TrueType compatible
                enhanced_settings[font_type] = settings
            else:
                # Convert to TrueType
                try:
                    size = getattr(settings, 'size', 24)
                    thickness = getattr(settings, 'thickness', 2)
                    bold = getattr(settings, 'bold', False)
                    border_thickness = getattr(settings, 'border_thickness', 2)
                    
                    # Create new TrueType font
                    enhanced_settings[font_type] = TTFontSettings(
                        font_name="arial",
                        size=size,
                        thickness=thickness,
                        bold=bold,
                        border_thickness=border_thickness,
                        text_color=(255, 255, 255),
                        border_color=(0, 0, 0)
                    )
                    print(f"✅ Converted {font_type} to TrueType font")
                except Exception as e:
                    print(f"❌ Failed to convert {font_type} to TrueType: {e}")
                    # Use default TrueType font
                    enhanced_settings[font_type] = TTFontSettings()
        
        return enhanced_settings"""
        
        content = re.sub(convert_fonts_pattern, convert_fonts_replacement, content, flags=re.DOTALL)
        
        # Update the _get_default_enhanced_fonts method
        default_fonts_pattern = r'def _get_default_enhanced_fonts\(self\):.*?return \{.*?\}'
        default_fonts_replacement = """def _get_default_enhanced_fonts(self):
        \"\"\"Get default TrueType font settings\"\"\"
        return create_default_font_settings()"""
        
        content = re.sub(default_fonts_pattern, default_fonts_replacement, content, flags=re.DOTALL)
        
        # Write updated content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Updated {file_path}")
        return True
    
    except Exception as e:
        print(f"❌ Failed to update {file_path}: {e}")
        return False

def install_files():
    """Install the TrueType renderer files"""
    files_to_install = [
        ('direct_ttf_renderer.py', 'direct_ttf_renderer.py'),
        ('font_bridge.py', 'font_bridge.py')
    ]
    
    for source, dest in files_to_install:
        if not os.path.exists(source):
            print(f"❌ Source file not found: {source}")
            continue
        
        try:
            shutil.copy2(source, dest)
            print(f"✅ Installed {dest}")
        except Exception as e:
            print(f"❌ Failed to install {dest}: {e}")

def main():
    """Main function"""
    print("========================================")
    print("  FPS Analyzer TrueType Font Update")
    print("========================================")
    print("This script will update FPS Analyzer to use TrueType fonts")
    print("with zero fallbacks to OpenCV fonts.")
    print()
    print("FILES THAT WILL BE MODIFIED:")
    print("  - fps_analyzer_main.py")
    print("  - analysis_worker.py")
    print("  - enhanced_overlay_renderer.py")
    print()
    print("NEW FILES THAT WILL BE INSTALLED:")
    print("  - direct_ttf_renderer.py")
    print("  - font_bridge.py")
    print()
    print("All modified files will be backed up before changes.")
    print("========================================")
    
    confirm = input("Do you want to continue? (y/n): ")
    if confirm.lower() != 'y':
        print("Update cancelled.")
        return
    
    # Install new files
    print("\nInstalling new files...")
    install_files()
    
    # Update existing files
    print("\nUpdating existing files...")
    update_fps_analyzer_main('fps_analyzer_main.py')
    update_analysis_worker('analysis_worker.py')
    update_enhanced_overlay_renderer('enhanced_overlay_renderer.py')
    
    print("\n========================================")
    print("  Update Complete")
    print("========================================")
    print("TrueType font rendering has been installed and configured.")
    print("Please run test_ttf_rendering.py to verify the installation.")
    print()
    print("If you encounter any issues, the original files have been")
    print("backed up with a timestamp extension (*.bak).")
    print("========================================")

if __name__ == "__main__":
    main()
