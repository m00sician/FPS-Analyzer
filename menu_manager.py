"""
Menu Management Module für FPS Analyzer - FIXED ABOUT TEXT
Handles all menu creation and menu actions with corrected branding
"""
import cv2
from PyQt6.QtWidgets import QDialog, QMessageBox
from PyQt6.QtGui import QAction

class MenuManager:
    """Manages all menus and menu actions for the FPS Analyzer"""
    
    def __init__(self, parent):
        self.parent = parent
        self.menubar = parent.menuBar()
    
    def create_all_menus(self):
        """Create all menus for the application"""
        self.create_file_menu()
        self.create_view_menu()
        self.create_edit_menu()
        self.create_help_menu()
    
    def create_file_menu(self):
        """Create File menu with batch processor"""
        file_menu = self.menubar.addMenu('📁 Datei')
        
        # Load Video
        load_video_action = QAction('📹 Video laden...', self.parent)
        load_video_action.setShortcut('Ctrl+O')
        load_video_action.triggered.connect(self.parent.browse_input)
        file_menu.addAction(load_video_action)
        
        # ✨ NEW: Batch Processor
        batch_processor_action = QAction('📦 Batch Processor...', self.parent)
        batch_processor_action.setShortcut('Ctrl+B')
        batch_processor_action.triggered.connect(self.open_batch_processor)
        file_menu.addAction(batch_processor_action)
        
        file_menu.addSeparator()
        
        # Export Settings
        export_settings_action = QAction('💾 Einstellungen exportieren...', self.parent)
        export_settings_action.triggered.connect(self.export_settings)
        file_menu.addAction(export_settings_action)
        
        # Import Settings
        import_settings_action = QAction('📂 Einstellungen importieren...', self.parent)
        import_settings_action.triggered.connect(self.import_settings)
        file_menu.addAction(import_settings_action)
        
        file_menu.addSeparator()
        
        # Recent Files (TODO: Implement)
        recent_menu = file_menu.addMenu('🕒 Zuletzt verwendet')
        recent_menu.addAction('(Noch keine Dateien)')
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = QAction('❌ Programm beenden', self.parent)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.parent.close)
        file_menu.addAction(exit_action)
    
    def create_view_menu(self):
        """Create View menu"""
        view_menu = self.menubar.addMenu('👁️ View')
        
        # Preview Resolution Submenu
        self.create_preview_resolution_menu(view_menu)
        
        # Preview Quality Submenu
        self.create_preview_quality_menu(view_menu)
        
        view_menu.addSeparator()
        
        # UI Elements
        self.parent.log_action = QAction('📜 Log anzeigen', self.parent)
        self.parent.log_action.setCheckable(True)
        self.parent.log_action.setChecked(True)
        self.parent.log_action.triggered.connect(self.parent.toggle_log_visibility)
        view_menu.addAction(self.parent.log_action)
        
        # Full Screen (TODO: Implement)
        fullscreen_action = QAction('🖥️ Vollbild', self.parent)
        fullscreen_action.setShortcut('F11')
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fullscreen_action)
        
        view_menu.addSeparator()
        
        # Theme Selection
        theme_menu = view_menu.addMenu('🎨 Design')
        
        dark_theme_action = QAction('🌙 Dark Theme', self.parent)
        dark_theme_action.setCheckable(True)
        dark_theme_action.setChecked(True)
        dark_theme_action.triggered.connect(lambda: self.parent.apply_theme("dark"))
        theme_menu.addAction(dark_theme_action)
        
        light_theme_action = QAction('☀️ Light Theme', self.parent)
        light_theme_action.setCheckable(True)
        light_theme_action.triggered.connect(lambda: self.parent.apply_theme("light"))
        theme_menu.addAction(light_theme_action)
    
    def create_preview_resolution_menu(self, parent_menu):
        """Create Preview Internal Resolution submenu"""
        internal_res_menu = parent_menu.addMenu('🔍 Preview Internal Resolution')
        
        resolutions = [
            ('720p (1280x720)', 1280, 720),
            ('1080p (1920x1080)', 1920, 1080),
            ('1440p (2560x1440)', 2560, 1440),
            ('4K (3840x2160)', 3840, 2160)
        ]
        
        self.parent.resolution_actions = []
        for name, width, height in resolutions:
            action = QAction(name, self.parent)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, w=width, h=height: self.parent.set_internal_resolution(w, h))
            if width == 1920 and height == 1080:  # 1080p default
                action.setChecked(True)
            internal_res_menu.addAction(action)
            self.parent.resolution_actions.append(action)
    
    def create_preview_quality_menu(self, parent_menu):
        """Create Preview Quality submenu"""
        quality_menu = parent_menu.addMenu('⚙️ Preview Quality')
        
        quality_options = [
            ('⚡ Fastest (Nearest)', cv2.INTER_NEAREST),
            ('🏃 Fast (Linear)', cv2.INTER_LINEAR),
            ('👍 Good (Cubic)', cv2.INTER_CUBIC),
            ('✨ Best (Lanczos)', cv2.INTER_LANCZOS4)
        ]
        
        self.parent.quality_actions = []
        for name, interpolation in quality_options:
            action = QAction(name, self.parent)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, interp=interpolation: self.parent.set_preview_quality(interp))
            if interpolation == cv2.INTER_LANCZOS4:  # Lanczos default
                action.setChecked(True)
            quality_menu.addAction(action)
            self.parent.quality_actions.append(action)
    
    def create_edit_menu(self):
        """Create Edit menu"""
        edit_menu = self.menubar.addMenu('✏️ Bearbeiten')
        
        # Hardware Settings
        self.parent.cuda_action = QAction('🚀 Use CUDA Acceleration', self.parent)
        self.parent.cuda_action.setCheckable(True)
        self.parent.cuda_action.setChecked(self.parent.cuda_available)
        self.parent.cuda_action.setEnabled(self.parent.cuda_available)
        self.parent.cuda_action.triggered.connect(self.parent.toggle_cuda)
        edit_menu.addAction(self.parent.cuda_action)
        
        # Display Settings
        self.parent.frametime_action = QAction('📊 Show Frame Time Graph', self.parent)
        self.parent.frametime_action.setCheckable(True)
        self.parent.frametime_action.setChecked(True)
        self.parent.frametime_action.triggered.connect(self.parent.toggle_frametime_graph)
        edit_menu.addAction(self.parent.frametime_action)
        
        edit_menu.addSeparator()
        
        # FONT PREVIEW
        font_preview_action = QAction('🎨 Live Font Preview', self.parent)
        font_preview_action.triggered.connect(self.parent.show_font_preview)
        edit_menu.addAction(font_preview_action)
        
        # FRAME TIME GRAPH POSITION
        ftg_position_menu = edit_menu.addMenu('📍 FTG Position')
        
        positions = [
            ("🔽 Unten Links (Über Frame Rate Graph)", "bottom_left"),
            ("🔽 Unten Rechts (Standard Position)", "bottom_right"),
            ("🔼 Oben Rechts", "top_right")
        ]
        
        self.parent.ftg_position_actions = []
        current_position = getattr(self.parent, 'ftg_position', 'bottom_right')
        
        for text, value in positions:
            action = QAction(text, self.parent)
            action.setCheckable(True)
            action.setChecked(value == current_position)
            action.triggered.connect(lambda checked, pos=value: self.set_ftg_position(pos))
            ftg_position_menu.addAction(action)
            self.parent.ftg_position_actions.append((action, value))
        
        edit_menu.addSeparator()
    
    def create_help_menu(self):
        """Create Help menu"""
        help_menu = self.menubar.addMenu('❓ Hilfe')
        
        # Keyboard Shortcuts
        shortcuts_action = QAction('⌨️ Keyboard Shortcuts', self.parent)
        shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcuts_action)
        
        # Documentation
        docs_action = QAction('📖 Documentation', self.parent)
        docs_action.triggered.connect(self.show_documentation)
        help_menu.addAction(docs_action)
        
        help_menu.addSeparator()
        
        # System Info
        sysinfo_action = QAction('💻 System Info', self.parent)
        sysinfo_action.triggered.connect(self.show_system_info)
        help_menu.addAction(sysinfo_action)
        
        # Check for Updates
        update_action = QAction('🔄 Check for Updates', self.parent)
        update_action.triggered.connect(self.check_updates)
        help_menu.addAction(update_action)
        
        help_menu.addSeparator()
        
        # About
        about_action = QAction('ℹ️ About FPS Analyzer', self.parent)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    # ✨ NEW: Batch Processor Menu Action
    def open_batch_processor(self):
        """Open the batch processor dialog"""
        try:
            from batch_processor import BatchProcessorDialog
            dialog = BatchProcessorDialog(self.parent)
            dialog.exec()
        except ImportError as e:
            QMessageBox.warning(self.parent, 'Import Error', 
                              f'Could not load batch processor:\n{str(e)}')
    
    # Menu Action Implementations
    def export_settings(self):
        """Export current settings to file"""
        try:
            import json
            from PyQt6.QtWidgets import QFileDialog
            
            settings = {
                'fps_font': {
                    'font_name': self.parent.fps_font_settings.font_name,
                    'size': self.parent.fps_font_settings.size,
                    'thickness': self.parent.fps_font_settings.thickness,
                    'bold': self.parent.fps_font_settings.bold,
                    'border_thickness': self.parent.fps_font_settings.border_thickness
                },
                'framerate_font': {
                    'font_name': self.parent.framerate_font_settings.font_name,
                    'size': self.parent.framerate_font_settings.size,
                    'thickness': self.parent.framerate_font_settings.thickness,
                    'bold': self.parent.framerate_font_settings.bold,
                    'border_thickness': self.parent.framerate_font_settings.border_thickness
                },
                'frametime_font': {
                    'font_name': self.parent.frametime_font_settings.font_name,
                    'size': self.parent.frametime_font_settings.size,
                    'thickness': self.parent.frametime_font_settings.thickness,
                    'bold': self.parent.frametime_font_settings.bold,
                    'border_thickness': self.parent.frametime_font_settings.border_thickness
                },
                'colors': {
                    'framerate_color': self.parent.framerate_color,
                    'frametime_color': self.parent.frametime_color
                },
                'preview': {
                    'internal_resolution': self.parent.internal_resolution,
                    'preview_quality': self.parent.preview_quality
                }
            }
            
            file_path, _ = QFileDialog.getSaveFileName(
                self.parent, 'Export Settings', 'fps_analyzer_settings.json',
                'JSON Files (*.json);;All Files (*)')
            
            if file_path:
                with open(file_path, 'w') as f:
                    json.dump(settings, f, indent=2)
                self.parent.log(f"✓ Settings exported to {file_path}")
                QMessageBox.information(self.parent, 'Export Successful', 
                                      f'Settings exported successfully to:\n{file_path}')
        except Exception as e:
            self.parent.log(f"✗ Export failed: {e}")
            QMessageBox.warning(self.parent, 'Export Failed', f'Could not export settings:\n{str(e)}')
    
    def import_settings(self):
        """Import settings from file"""
        try:
            import json
            from PyQt6.QtWidgets import QFileDialog
            from font_manager import OpenCVFontSettings
            
            file_path, _ = QFileDialog.getOpenFileName(
                self.parent, 'Import Settings', '',
                'JSON Files (*.json);;All Files (*)')
            
            if file_path:
                with open(file_path, 'r') as f:
                    settings = json.load(f)
                
                # Apply font settings
                if 'fps_font' in settings:
                    fps = settings['fps_font']
                    self.parent.fps_font_settings = OpenCVFontSettings(
                        fps['font_name'], fps['size'], fps['thickness'], 
                        fps['bold'], fps['border_thickness']
                    )
                
                if 'framerate_font' in settings:
                    fr = settings['framerate_font']
                    self.parent.framerate_font_settings = OpenCVFontSettings(
                        fr['font_name'], fr['size'], fr['thickness'], 
                        fr['bold'], fr['border_thickness']
                    )
                
                if 'frametime_font' in settings:
                    ft = settings['frametime_font']
                    self.parent.frametime_font_settings = OpenCVFontSettings(
                        ft['font_name'], ft['size'], ft['thickness'], 
                        ft['bold'], ft['border_thickness']
                    )
                
                # Apply color settings
                if 'colors' in settings:
                    colors = settings['colors']
                    self.parent.framerate_color = colors.get('framerate_color', '#00FF00')
                    self.parent.frametime_color = colors.get('frametime_color', '#00FF00')
                
                # Apply preview settings
                if 'preview' in settings:
                    preview = settings['preview']
                    if 'internal_resolution' in preview:
                        res = preview['internal_resolution']
                        self.parent.set_internal_resolution(res[0], res[1])
                
                self.parent.log(f"✓ Settings imported from {file_path}")
                QMessageBox.information(self.parent, 'Import Successful', 
                                      f'Settings imported successfully from:\n{file_path}')
        except Exception as e:
            self.parent.log(f"✗ Import failed: {e}")
            QMessageBox.warning(self.parent, 'Import Failed', f'Could not import settings:\n{str(e)}')
    
    def toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.parent.isFullScreen():
            self.parent.showNormal()
        else:
            self.parent.showFullScreen()
    
    def show_shortcuts(self):
        """Show keyboard shortcuts"""
        shortcuts_text = """Keyboard Shortcuts:

📁 File Operations:
Ctrl+O - Load Video
Ctrl+B - Open Batch Processor
Ctrl+Q - Quit Application

🎬 Playback:
Space - Play/Pause (when video loaded)
F11 - Toggle Fullscreen

⚙️ Analysis:
F5 - Start/Stop FPS Analysis
Esc - Cancel Analysis

🎨 Preview:
F2 - Live Font Preview

💡 Interface:
F1 - Show this help
Ctrl+, - Open Settings"""
        
        QMessageBox.information(self.parent, 'Keyboard Shortcuts', shortcuts_text)
    
    def show_documentation(self):
        """Show documentation"""
        doc_text = """📖 FPS Analyzer Documentation

🎯 Quick Start:
1. Load a video file (File → Load Video)
2. Configure output settings (resolution, bitrate)
3. Use Live Font Preview to test font settings
4. Adjust font and color settings if desired
5. Click 'Start FPS Analysis' to begin

📦 Batch Processing:
1. Open File → Batch Processor
2. Add multiple videos or select folder
3. Configure batch settings
4. Click 'Start Batch' for automatic processing

📊 Features:
• Real-time FPS detection and analysis
• Professional overlay generation
• Live font preview system
• Customizable fonts and colors
• Frame time analysis
• Hardware acceleration support
• Aspect ratio preservation
• Batch processing support
• Settings persistence

⚙️ Advanced Options:
• Detection sensitivity adjustment
• Multiple preview quality settings
• Custom frame time scales
• Export/Import settings

For more detailed documentation, visit our website or check the README file."""
        
        QMessageBox.information(self.parent, 'Documentation', doc_text)
    
    def show_system_info(self):
        """Show system information"""
        import torch
        import cv2
        import platform
        
        sys_info = f"""💻 System Information:

🖥️ System: {platform.system()} {platform.release()}
🐍 Python: {platform.python_version()}
📹 OpenCV: {cv2.__version__}
🔥 PyTorch: {torch.__version__}
🚀 CUDA Available: {'Yes' if torch.cuda.is_available() else 'No'}"""
        
        if torch.cuda.is_available():
            try:
                gpu_name = torch.cuda.get_device_name(0)
                sys_info += f"\n🎮 GPU: {gpu_name}"
            except:
                sys_info += f"\n🎮 GPU: CUDA Device 0"
        
        sys_info += f"""

📊 Current Settings:
• Preview Resolution: {self.parent.internal_resolution[0]}x{self.parent.internal_resolution[1]}
• Preview Quality: {self.get_quality_name()}"""
        
        QMessageBox.information(self.parent, 'System Information', sys_info)
    
    def check_updates(self):
        """Check for updates"""
        QMessageBox.information(self.parent, 'Check for Updates', 
                               '🔄 Update checking is not implemented yet.\n\n'
                               'Please check the project repository for the latest version.')
    
    def set_ftg_position(self, position):
        """Set Frame Time Graph position and update menu checkmarks"""
        self.parent.ftg_position = position
        self.parent.log(f"✓ Frame Time Graph position set to: {position}")
        
        # Update checkmarks
        for action, pos in self.parent.ftg_position_actions:
            action.setChecked(pos == position)
        
        # Save settings
        self.parent.save_current_settings()
    
    def get_quality_name(self):
        """Get current quality setting name"""
        quality_map = {
            cv2.INTER_NEAREST: 'Fastest',
            cv2.INTER_LINEAR: 'Fast',
            cv2.INTER_CUBIC: 'Good',
            cv2.INTER_LANCZOS4: 'Best'
        }
        return quality_map.get(self.parent.preview_quality, 'Unknown')
    
    def show_about(self):
        """🔧 FIXED: Show about dialog with corrected branding"""
        about_text = """🎯 FPS Analyzer v2.3

A professional FPS analysis tool for video content.

✨ Key Features:
• Live font preview system with background selector
• Batch processing for multiple videos
• Enhanced UI with custom widgets
• Settings persistence (auto-save/load)

🎬 Inspired by Digital Foundry, made available to everyone

Created with ❤️ using:
• Python & PyQt6
• OpenCV for video processing
• PyTorch for GPU acceleration

Features:
✨ Real-time FPS detection
📊 Frame time analysis
🎨 Live font preview system
📦 Batch processing support
🖼️ Aspect ratio preservation
🚀 GPU acceleration support
💾 Settings import/export
🎯 Professional overlay generation

© 2024 FPS Analyzer Team
Licensed under MIT License"""
        
        QMessageBox.about(self.parent, 'About FPS Analyzer', about_text)