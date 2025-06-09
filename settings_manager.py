"""
Settings Manager für FPS Analyzer
Handles persistent storage and loading of application settings
"""
import json
import os
from pathlib import Path

class SettingsManager:
    """Manages application settings persistence"""
    
    def __init__(self):
        # Settings file location
        self.settings_dir = Path.home() / ".fps_analyzer"
        self.settings_file = self.settings_dir / "settings.json"
        
        # Create settings directory if it doesn't exist
        self.settings_dir.mkdir(exist_ok=True)
        
        # Default settings
        self.default_settings = {
            # Font settings
            'fps_font_name': 'HERSHEY_SIMPLEX',
            'fps_font_size': 1.2,
            'fps_font_thickness': 2,
            'fps_font_bold': True,
            'fps_font_border': 2,
            
            'framerate_font_name': 'HERSHEY_SIMPLEX',
            'framerate_font_size': 0.6,
            'framerate_font_thickness': 1,
            'framerate_font_bold': False,
            'framerate_font_border': 1,
            
            'frametime_font_name': 'HERSHEY_SIMPLEX',
            'frametime_font_size': 0.5,
            'frametime_font_thickness': 1,
            'frametime_font_bold': False,
            'frametime_font_border': 1,
            
            # Color settings
            'framerate_color': '#00FF00',
            'frametime_color': '#00FF00',
            
            # UI settings
            'output_resolution': (1920, 1080),
            'bitrate': 60,
            'frametime_scale_index': 1,  # Standard
            'sensitivity_index': 2,      # Medium
            
            # Other settings
            'theme': 'dark',
            'ftg_position': 'bottom_right',
            'internal_resolution': (1920, 1080),
            
            # Window settings
            'window_width': 1600,
            'window_height': 1000,
            'window_maximized': False
        }
    
    def load_settings(self):
        """Load settings from file or return defaults"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    saved_settings = json.load(f)
                
                # Merge with defaults to handle missing keys
                settings = self.default_settings.copy()
                settings.update(saved_settings)
                
                print(f"✅ Settings loaded from {self.settings_file}")
                return settings
            else:
                print("📄 No settings file found, using defaults")
                return self.default_settings.copy()
                
        except Exception as e:
            print(f"❌ Could not load settings: {e}")
            print("📄 Using default settings")
            return self.default_settings.copy()
    
    def save_settings(self, settings):
        """Save settings to file"""
        try:
            # Ensure settings directory exists
            self.settings_dir.mkdir(exist_ok=True)
            
            # Convert tuple resolutions to lists for JSON serialization
            settings_to_save = settings.copy()
            if 'output_resolution' in settings_to_save and isinstance(settings_to_save['output_resolution'], tuple):
                settings_to_save['output_resolution'] = list(settings_to_save['output_resolution'])
            if 'internal_resolution' in settings_to_save and isinstance(settings_to_save['internal_resolution'], tuple):
                settings_to_save['internal_resolution'] = list(settings_to_save['internal_resolution'])
            
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings_to_save, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Settings saved to {self.settings_file}")
            return True
            
        except Exception as e:
            print(f"❌ Could not save settings: {e}")
            return False
    
    def reset_to_defaults(self):
        """Reset settings to defaults"""
        try:
            if self.settings_file.exists():
                # Backup current settings
                backup_file = self.settings_file.with_suffix('.json.backup')
                self.settings_file.rename(backup_file)
                print(f"📄 Settings backed up to {backup_file}")
            
            # Save defaults
            self.save_settings(self.default_settings)
            print("✅ Settings reset to defaults")
            return True
            
        except Exception as e:
            print(f"❌ Could not reset settings: {e}")
            return False
    
    def export_settings(self, export_path):
        """Export settings to a specific file"""
        try:
            current_settings = self.load_settings()
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(current_settings, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Settings exported to {export_path}")
            return True
            
        except Exception as e:
            print(f"❌ Could not export settings: {e}")
            return False
    
    def import_settings(self, import_path):
        """Import settings from a specific file"""
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                imported_settings = json.load(f)
            
            # Validate imported settings
            validated_settings = self.validate_settings(imported_settings)
            
            # Save validated settings
            if self.save_settings(validated_settings):
                print(f"✅ Settings imported from {import_path}")
                return True
            else:
                return False
                
        except Exception as e:
            print(f"❌ Could not import settings: {e}")
            return False
    
    def validate_settings(self, settings):
        """Validate and fix imported settings"""
        validated = self.default_settings.copy()
        
        # Update with valid imported values
        for key, value in settings.items():
            if key in validated:
                # Type checking for critical values
                if key.endswith('_resolution') and isinstance(value, list) and len(value) == 2:
                    validated[key] = tuple(value)
                elif key in ['bitrate', 'frametime_scale_index', 'sensitivity_index'] and isinstance(value, (int, float)):
                    validated[key] = int(value)
                elif key.endswith('_size') and isinstance(value, (int, float)):
                    validated[key] = float(value)
                elif key.endswith('_color') and isinstance(value, str) and value.startswith('#'):
                    validated[key] = value
                elif key in ['theme', 'ftg_position'] and isinstance(value, str):
                    validated[key] = value
                elif isinstance(value, type(validated[key])):
                    validated[key] = value
                else:
                    print(f"⚠️ Invalid value for {key}: {value}, using default")
        
        return validated
    
    def get_settings_info(self):
        """Get information about current settings"""
        info = {
            'settings_file': str(self.settings_file),
            'settings_dir': str(self.settings_dir),
            'file_exists': self.settings_file.exists(),
            'file_size': self.settings_file.stat().st_size if self.settings_file.exists() else 0,
            'last_modified': self.settings_file.stat().st_mtime if self.settings_file.exists() else None
        }
        
        return info