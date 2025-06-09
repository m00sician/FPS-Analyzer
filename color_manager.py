"""
Color Management Module für FPS Analyzer
Handles color selection dialogs and color conversion utilities
"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QColorDialog, QMessageBox
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

class ColorSelectionDialog(QDialog):
    """Dialog for selecting custom colors for frame rate and frame time lines"""
    
    def __init__(self, parent, current_framerate_color, current_frametime_color):
        super().__init__(parent)
        self.setWindowTitle("Color Selection")
        self.setModal(True)
        self.resize(400, 200)
        
        # Store current colors
        self.framerate_color = current_framerate_color
        self.frametime_color = current_frametime_color
        
        self.setup_ui()
        
        # Apply parent theme
        if hasattr(parent, 'current_theme'):
            self.setStyleSheet(parent.styleSheet())
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Create grid for color selections
        grid_layout = QGridLayout()
        
        # Frame Rate Color Selection
        grid_layout.addWidget(QLabel("Frame Rate Line Color:"), 0, 0)
        
        self.framerate_color_edit = QLineEdit()
        self.framerate_color_edit.setText(self.framerate_color)
        self.framerate_color_edit.setPlaceholderText("#00FF00")
        grid_layout.addWidget(self.framerate_color_edit, 0, 1)
        
        self.framerate_color_btn = QPushButton("Choose Color")
        self.framerate_color_btn.clicked.connect(self.choose_framerate_color)
        grid_layout.addWidget(self.framerate_color_btn, 0, 2)
        
        # Frame Time Color Selection
        grid_layout.addWidget(QLabel("Frame Time Line Color:"), 1, 0)
        
        self.frametime_color_edit = QLineEdit()
        self.frametime_color_edit.setText(self.frametime_color)
        self.frametime_color_edit.setPlaceholderText("#00FF00")
        grid_layout.addWidget(self.frametime_color_edit, 1, 1)
        
        self.frametime_color_btn = QPushButton("Choose Color")
        self.frametime_color_btn.clicked.connect(self.choose_frametime_color)
        grid_layout.addWidget(self.frametime_color_btn, 1, 2)
        
        layout.addLayout(grid_layout)
        
        # Color preview
        preview_layout = QHBoxLayout()
        preview_layout.addWidget(QLabel("Preview:"))
        
        self.framerate_preview = QLabel("Frame Rate")
        self.framerate_preview.setMinimumHeight(30)
        self.framerate_preview.setStyleSheet(f"background-color: {self.framerate_color}; border: 1px solid #555; color: white; text-align: center;")
        preview_layout.addWidget(self.framerate_preview)
        
        self.frametime_preview = QLabel("Frame Time")
        self.frametime_preview.setMinimumHeight(30)
        self.frametime_preview.setStyleSheet(f"background-color: {self.frametime_color}; border: 1px solid #555; color: white; text-align: center;")
        preview_layout.addWidget(self.frametime_preview)
        
        layout.addLayout(preview_layout)
        
        # Connect text changes to preview updates
        self.framerate_color_edit.textChanged.connect(self.update_previews)
        self.frametime_color_edit.textChanged.connect(self.update_previews)
        
        # Preset colors
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Presets:"))
        
        presets = [
            ("Green", "#00FF00"),
            ("Red", "#FF0000"),
            ("Blue", "#0080FF"),
            ("Yellow", "#FFFF00"),  # Will be styled with black text
            ("Purple", "#8000FF"),
            ("Orange", "#FF8000"),
            ("Cyan", "#00FFFF"),
            ("Pink", "#FF00FF")
        ]
        
        for name, color in presets:
            btn = QPushButton(name)
            btn.setMaximumWidth(60)
            # Special styling for Yellow button (black text)
            if name == "Yellow":
                btn.setStyleSheet(f"background-color: {color}; color: black; border: 1px solid #333;")
            else:
                btn.setStyleSheet(f"background-color: {color}; color: white; border: 1px solid #333;")
            btn.clicked.connect(lambda checked, c=color: self.set_both_colors(c))
            preset_layout.addWidget(btn)
        
        layout.addLayout(preset_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        reset_button = QPushButton("Reset to Default")
        reset_button.clicked.connect(self.reset_colors)
        button_layout.addWidget(reset_button)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        ok_button.setDefault(True)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
    
    def choose_framerate_color(self):
        """Open color dialog for framerate color"""
        color = QColorDialog.getColor(QColor(self.framerate_color_edit.text()), self, "Choose Frame Rate Color")
        if color.isValid():
            self.framerate_color_edit.setText(color.name())
    
    def choose_frametime_color(self):
        """Open color dialog for frametime color"""
        color = QColorDialog.getColor(QColor(self.frametime_color_edit.text()), self, "Choose Frame Time Color")
        if color.isValid():
            self.frametime_color_edit.setText(color.name())
    
    def set_both_colors(self, color):
        """Set both colors to the same value"""
        self.framerate_color_edit.setText(color)
        self.frametime_color_edit.setText(color)
    
    def reset_colors(self):
        """Reset to default colors"""
        self.framerate_color_edit.setText("#00FF00")
        self.frametime_color_edit.setText("#00FF00")
    
    def update_previews(self):
        """Update color previews"""
        try:
            framerate_color = self.framerate_color_edit.text()
            if QColor(framerate_color).isValid():
                self.framerate_preview.setStyleSheet(f"background-color: {framerate_color}; border: 1px solid #555; color: white; text-align: center;")
        except:
            pass
        
        try:
            frametime_color = self.frametime_color_edit.text()
            if QColor(frametime_color).isValid():
                self.frametime_preview.setStyleSheet(f"background-color: {frametime_color}; border: 1px solid #555; color: white; text-align: center;")
        except:
            pass
    
    def get_selected_colors(self):
        """Return the selected colors"""
        return self.framerate_color_edit.text(), self.frametime_color_edit.text()

def hex_to_bgr(hex_color):
    """Convert hex color to BGR tuple for OpenCV - FIXED VERSION"""
    try:
        # Remove # if present
        hex_color = hex_color.lstrip('#')
        
        # Handle 3-digit hex (e.g., #RGB -> #RRGGBB)
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])
        
        # Convert to RGB first
        if len(hex_color) == 6:
            # Parse as RGB directly
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16) 
            b = int(hex_color[4:6], 16)
            rgb = (r, g, b)
            
            # ⚠️ CRITICAL FIX: OpenCV uses RGB, not BGR for cv2.putText colors!
            # Despite the function name, we return RGB for OpenCV text rendering
            print(f"🎨 Color conversion: #{hex_color.upper()} -> RGB{rgb}")
            return rgb  # Return RGB, not BGR!
        else:
            raise ValueError(f"Invalid hex color length: {len(hex_color)}")
    except Exception as e:
        print(f"❌ Error converting color {hex_color}: {e}")
        # Return green as fallback (RGB format)
        return (0, 255, 0)