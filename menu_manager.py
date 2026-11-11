"""
Menu Manager for FPS Analyzer - ENHANCED with Adaptive Video Comparison Feature
Handles all menu creation and actions including the enhanced comparison creator
"""
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtGui import QAction, QKeySequence
import cv2

class MenuManager:
    """Manages all application menus and actions"""
    
    def __init__(self, parent):
        self.parent = parent
        self.menubar = None
        
        # Store action references for dynamic updates
        self.resolution_actions = []
        self.quality_actions = []
        
    def create_all_menus(self):
        """Create all application menus"""
        self.menubar = self.parent.menuBar()
        
        self.create_file_menu()
        self.create_view_menu()
        self.create_tools_menu()
        self.create_help_menu()
    
    def create_file_menu(self):
        """Create File menu with Enhanced Comparison feature"""
        file_menu = self.menubar.addMenu('📁 &File')
        
        # Open Video
        open_action = QAction('📹 &Open Video...', self.parent)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.setStatusTip('Open a video file for analysis')
        open_action.triggered.connect(self.parent.browse_input)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        # Export Options
        export_menu = file_menu.addMenu('🎬 &Export')
        
        # PNG Alpha Sequence
        png_export_action = QAction('🎬 PNG Alpha &Sequence...', self.parent)
        png_export_action.setStatusTip('Export PNG sequence for Premiere Pro')
        png_export_action.triggered.connect(self.parent.export_png_alpha_sequence)
        export_menu.addAction(png_export_action)
        
        file_menu.addSeparator()
        
        # Recent Files (placeholder)
        recent_menu = file_menu.addMenu('🕐 &Recent Files')
        recent_menu.addAction('(No recent files)')
        recent_menu.setEnabled(False)
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = QAction('🚪 E&xit', self.parent)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.setStatusTip('Exit the application')
        exit_action.triggered.connect(self.parent.close)
        file_menu.addAction(exit_action)
    
    def create_view_menu(self):
        """Create View menu"""
        view_menu = self.menubar.addMenu('👁️ &View')
        
        # Theme Selection
        theme_menu = view_menu.addMenu('🎨 &Theme')
        
        # Dark Theme
        dark_action = QAction('🌙 &Dark Theme', self.parent)
        dark_action.setCheckable(True)
        dark_action.setChecked(self.parent.current_theme == 'dark')
        dark_action.triggered.connect(lambda: self.parent.apply_theme('dark'))
        theme_menu.addAction(dark_action)
        
        # Light Theme
        light_action = QAction('☀️ &Light Theme', self.parent)
        light_action.setCheckable(True)
        light_action.setChecked(self.parent.current_theme == 'light')
        light_action.triggered.connect(lambda: self.parent.apply_theme('light'))
        theme_menu.addAction(light_action)
        
        view_menu.addSeparator()
        
        # Preview Settings
        preview_menu = view_menu.addMenu('📺 &Preview')
        
        # Internal Resolution
        resolution_menu = preview_menu.addMenu('📏 Internal &Resolution')
        
        resolutions = [
            ('720p (1280x720)', 1280, 720),
            ('1080p (1920x1080)', 1920, 1080),
            ('1440p (2560x1440)', 2560, 1440),
            ('4K (3840x2160)', 3840, 2160)
        ]
        
        for name, width, height in resolutions:
            action = QAction(name, self.parent)
            action.setCheckable(True)
            action.setChecked(self.parent.internal_resolution == (width, height))
            action.triggered.connect(lambda checked, w=width, h=height: self.parent.set_internal_resolution(w, h))
            resolution_menu.addAction(action)
            self.resolution_actions.append(action)
        
        # Preview Quality
        quality_menu = preview_menu.addMenu('🎯 Preview &Quality')
        
        qualities = [
            ('Fastest (Nearest)', cv2.INTER_NEAREST),
            ('Fast (Linear)', cv2.INTER_LINEAR),
            ('Good (Cubic)', cv2.INTER_CUBIC),
            ('Best (Lanczos)', cv2.INTER_LANCZOS4)
        ]
        
        for name, interpolation in qualities:
            action = QAction(name, self.parent)
            action.setCheckable(True)
            action.setChecked(self.parent.preview_quality == interpolation)
            action.triggered.connect(lambda checked, interp=interpolation: self.parent.set_preview_quality(interp))
            quality_menu.addAction(action)
            self.quality_actions.append(action)
        
        view_menu.addSeparator()
        
        # Log Visibility
        self.log_action = QAction('📝 Show &Log', self.parent)
        self.log_action.setCheckable(True)
        self.log_action.setChecked(True)
        self.log_action.triggered.connect(self.parent.toggle_log_visibility)
        view_menu.addAction(self.log_action)
    
    def create_tools_menu(self):
        """Create Tools menu"""
        tools_menu = self.menubar.addMenu('🔧 &Tools')
        
        # CUDA toggle lives directly in the Tools menu (no Analysis submenu any more)
        if self.parent.cuda_available:
            self.cuda_action = QAction('🚀 Use &CUDA', self.parent)
            self.cuda_action.setCheckable(True)
            self.cuda_action.setChecked(True)
            self.cuda_action.triggered.connect(self.parent.toggle_cuda)
            tools_menu.addAction(self.cuda_action)
            
            tools_menu.addSeparator()
        
        # Batch Processing
        if hasattr(self.parent, 'open_batch_processor'):
            batch_action = QAction('📦 &Batch Processor...', self.parent)
            batch_action.setShortcut(QKeySequence('Ctrl+B'))
            batch_action.triggered.connect(self.parent.open_batch_processor)
            tools_menu.addAction(batch_action)

        # Resolution analysis (experimental)
        if hasattr(self.parent, 'run_resolution_analysis'):
            res_action = QAction('📐 &Resolution Analysis (experimental)...', self.parent)
            res_action.setStatusTip('Estimate a video\'s internal render resolution (FFT based)')
            res_action.triggered.connect(self.parent.run_resolution_analysis)
            tools_menu.addAction(res_action)
        
        # Options
        options_action = QAction('⚙️ &Options...', self.parent)
        options_action.setShortcut(QKeySequence('Ctrl+,'))
        options_action.setStatusTip('Configure templates, detection and graph values')
        options_action.triggered.connect(self.open_options)
        tools_menu.addAction(options_action)

        # Layout Editor
        layout_editor_action = QAction('🎨 &Layout Editor...', self.parent)
        layout_editor_action.setShortcut(QKeySequence('Ctrl+L'))
        layout_editor_action.setStatusTip('Edit overlay layout with drag-and-drop')
        layout_editor_action.triggered.connect(self.open_layout_editor)
        tools_menu.addAction(layout_editor_action)

        # Stats-Panel
        if hasattr(self.parent, 'open_stats_panel_dialog'):
            stats_panel_action = QAction('🧩 &Stats-Panel...', self.parent)
            stats_panel_action.setShortcut(QKeySequence('Ctrl+P'))
            stats_panel_action.setStatusTip(
                'Alternative display mode: info box with title, FPS, graphs and text fields')
            stats_panel_action.triggered.connect(self.parent.open_stats_panel_dialog)
            tools_menu.addAction(stats_panel_action)

        # Video Comparison
        comparison_action = QAction('📊 Video &Comparison...', self.parent)
        comparison_action.setShortcut(QKeySequence('Ctrl+Shift+V'))
        comparison_action.setStatusTip('Create side-by-side video comparison with adaptive resolution')
        comparison_action.triggered.connect(self.open_comparison_creator)
        tools_menu.addAction(comparison_action)

        tools_menu.addSeparator()

        # Encode from saved analysis data
        encode_data_action = QAction('📂 Encode from Analysis &Data...', self.parent)
        encode_data_action.setStatusTip('Load saved .fpsdata and encode it - without re-analysing')
        encode_data_action.triggered.connect(self.parent.encode_from_data)
        tools_menu.addAction(encode_data_action)

        tools_menu.addSeparator()
        
        # System Information
        sysinfo_action = QAction('💻 System &Information...', self.parent)
        sysinfo_action.triggered.connect(self.show_system_info)
        tools_menu.addAction(sysinfo_action)
    
    def create_help_menu(self):
        """Create Help menu"""
        help_menu = self.menubar.addMenu('❓ &Help')
        
        # Keyboard Shortcuts
        shortcuts_action = QAction('⌨️ &Keyboard Shortcuts...', self.parent)
        shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcuts_action)
        
        help_menu.addSeparator()
        
        # About
        about_action = QAction('ℹ️ &About FPS Analyzer...', self.parent)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        # About Qt
        about_qt_action = QAction('🎨 About &Qt...', self.parent)
        about_qt_action.triggered.connect(lambda: QMessageBox.aboutQt(self.parent))
        help_menu.addAction(about_qt_action)
    
    # **ENHANCED: Comparison Creator Method**
    def open_comparison_creator(self):
        """Open the enhanced video comparison creator dialog"""
        try:
            from comparison_creator import ComparisonCreatorDialog
            
            dialog = ComparisonCreatorDialog(self.parent)
            dialog.exec()
            
            self.parent.log("📊 Enhanced Video Comparison Creator opened with adaptive resolution support")
            
        except ImportError as e:
            self.parent.log(f"❌ Could not open Comparison Creator: {e}")
            QMessageBox.warning(
                self.parent, 'Comparison Creator Error',
                f'Could not open Video Comparison Creator:\n{str(e)}\n\n'
                'Please check that comparison_creator.py is available.'
            )
        except Exception as e:
            self.parent.log(f"❌ Comparison Creator error: {e}")
            QMessageBox.warning(
                self.parent, 'Comparison Creator Error',
                f'Error opening Comparison Creator:\n{str(e)}'
            )
    
    def open_options(self):
        """Open the Options dialog"""
        try:
            from options_dialog import OptionsDialog
            dlg = OptionsDialog(self.parent)
            dlg.exec()
        except Exception as e:
            import traceback
            traceback.print_exc()
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self.parent, 'Options Error', f'Could not open Options:\n{e}')

    def open_layout_editor(self):
        """Open the drag-and-drop layout editor."""
        try:
            from layout_editor import LayoutEditorDialog
            dlg = LayoutEditorDialog(self.parent)
            dlg.exec()
        except Exception as e:
            import traceback
            traceback.print_exc()
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self.parent, 'Layout Editor Error', f'Could not open Layout Editor:\n{e}')

    def open_settings(self):
        """Open application settings dialog"""
        QMessageBox.information(
            self.parent, 'Settings',
            'Settings dialog is not yet implemented.\n\n'
            'Use the toolbar settings and menu options for now.'
        )
    
    def show_system_info(self):
        """Show system information dialog"""
        try:
            import torch
        except ImportError:
            torch = None   # optional, see fps_analyzer_main
        import cv2
        import sys
        from PyQt6.QtCore import QT_VERSION_STR
        from PyQt6 import PYQT_VERSION_STR
        
        info = f"""🖥️ System Information

📊 Application: FPS Analyzer v2.4 (Enhanced Comparison)
🐍 Python: {sys.version.split()[0]}
🎨 Qt: {QT_VERSION_STR}
🪟 PyQt6: {PYQT_VERSION_STR}
📹 OpenCV: {cv2.__version__}
🔥 PyTorch: {torch.__version__ if torch else 'not installed'}

🚀 CUDA Available: {'✓ YES' if (torch and torch.cuda.is_available()) else '✗ NO'}

📊 NEW FEATURES:
✓ Video Comparison Creator with Adaptive Resolution
✓ Support for 720p, 1080p, 1440p, 4K Comparison
✓ Center-Crop with Intelligent Sizing
✓ Simplified Comparison UI
✓ Adaptive Layout System"""
        
        if torch and torch.cuda.is_available():
            info += f"\n💾 GPU: {torch.cuda.get_device_name(0)}"
            info += f"\n🎯 CUDA Devices: {torch.cuda.device_count()}"
        
        QMessageBox.information(self.parent, 'System Information', info)
    
    def show_shortcuts(self):
        """Show keyboard shortcuts dialog"""
        shortcuts = """⌨️ Keyboard Shortcuts

📁 File Operations:
• Ctrl+O - Open Video
• Ctrl+Shift+C - Create Comparison (Enhanced)
• Ctrl+B - Batch Processor
• Ctrl+Q - Exit

✏️ Editing:
• Ctrl+L - Layout Editor

👁️ View:
• F11 - Fullscreen (if supported)

🎬 Playback:
• Space - Play/Pause (when video loaded)
• Left/Right - Frame Step (when paused)

🎯 Analysis:
• Enter - Start/Stop Analysis
• Esc - Cancel Analysis

📊 NEW Comparison:
• Ctrl+Shift+V - Video Comparison (Tools menu)"""
        
        QMessageBox.information(self.parent, 'Keyboard Shortcuts', shortcuts)
    
    def show_about(self):
        """Show about dialog"""
        about_text = """🎯 FPS Analyzer - Professional Video Analysis v2.4

🚀 Features:
• Advanced FPS Detection & Analysis
• Professional Video Overlays
• **ENHANCED: Adaptive Video Comparison with Multi-Resolution Support**
  - 720p Comparison (640x720)
  - 1080p Comparison (960x1080) [Standard]
  - 1440p Comparison (1280x1440)
  - 4K Comparison (1920x2160)
• Custom Layout Editor with Drag & Drop
• Smart Snapping System
• OpenCV Font System with Live Preview
• Batch Processing
• PNG Alpha Sequence Export
• CUDA Acceleration Support
• Aspect Ratio Preservation
• Settings Persistence

💻 Built with:
• Python & PyQt6
• OpenCV for Video Processing
• PyTorch for CUDA Support

🎨 Created for Professional Video Analysis

© 2024 FPS Analysis Tools
Licensed under MIT License

🆕 What's New in v2.4:
• Adaptive Resolution Support for Video Comparison
• Center-Crop with Intelligent Resizing
• Resolution-Aware Layout System
• Enhanced PNG Export for Multiple Resolutions"""
        
        QMessageBox.about(self.parent, 'About FPS Analyzer', about_text)