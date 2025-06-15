"""
Layout Editor für FPS Analyzer - WITH INDIVIDUAL ELEMENT CONTROLS
Allows users to freely position FPS elements with individual controls for each element
UPDATED: Fixed resize, individual controls, new default positions, simplified presets
"""
import json
import math
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QFrame, QComboBox, QCheckBox, QSpinBox, QGroupBox, 
                             QGridLayout, QSlider, QMessageBox, QApplication, QScrollArea,
                             QWidget, QFileDialog)
from PyQt6.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPixmap

class DraggableElement(QFrame):
    """Draggable UI element representing FPS display components - FIXED RESIZE + BETTER HANDLES"""
    
    position_changed = pyqtSignal(str, QPoint, QSize)  # element_id, position, size
    
    def __init__(self, element_id, display_name, initial_pos, initial_size, parent=None):
        super().__init__(parent)
        self.element_id = element_id
        self.display_name = display_name
        self.is_dragging = False
        self.drag_start_pos = QPoint()
        self.is_resizing = False
        self.resize_handle_size = 12  # 🔧 BIGGER resize handle
        self.min_size = QSize(30, 20)  # 🔧 SMALLER minimum size
        
        # 🔧 CRITICAL FIX: Don't use setFixedSize, use resize
        self.resize(initial_size)
        self.move(initial_pos)
        self.setup_styling()
        
        # Enable mouse tracking for resize handles
        self.setMouseTracking(True)
        
        print(f"🎯 DraggableElement created: {element_id} at {initial_pos} size {initial_size}")
    
    def setup_styling(self):
        """Setup visual styling for the element"""
        colors = {
            'fps_number': '#4CAF50',
            'frame_rate_graph': '#2196F3', 
            'frame_time_graph': '#FF9800',
            'fps_statistics': '#9C27B0',
            'frametime_statistics': '#E91E63'
        }
        
        # Better element ID matching
        color = '#666666'  # Default
        for key, element_color in colors.items():
            if key in self.element_id:
                color = element_color
                break
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border: 2px solid #333;
                border-radius: 8px;
                color: white;
                font-weight: bold;
            }}
            QFrame:hover {{
                border-color: #FFF;
                box-shadow: 0px 0px 10px rgba(255,255,255,0.3);
            }}
        """)
        
        # Add label
        self.label = QLabel(self.display_name, self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("border: none; background: transparent; font-size: 9px;")
        self.label.resize(self.size())
    
    def resizeEvent(self, event):
        """🔧 CRITICAL FIX: Handle resize event properly"""
        super().resizeEvent(event)
        if hasattr(self, 'label'):
            self.label.resize(self.size())
        
        # 🔧 CRITICAL: Emit position_changed signal when resizing
        if hasattr(self, 'element_id'):  # Ensure initialization is complete
            self.position_changed.emit(self.element_id, self.pos(), self.size())
            print(f"🔧 RESIZE EVENT: {self.element_id} resized to {self.size()}")
    
    def paintEvent(self, event):
        """Custom paint event to show BETTER resize handles"""
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 🔧 IMPROVED: Much more visible resize handle
        handle_rect = QRect(
            self.width() - self.resize_handle_size,
            self.height() - self.resize_handle_size,
            self.resize_handle_size,
            self.resize_handle_size
        )
        
        # Draw resize handle with MUCH better visibility
        painter.fillRect(handle_rect, QColor(255, 255, 255, 230))
        painter.setPen(QPen(QColor(0, 0, 0), 2))
        painter.drawRect(handle_rect)
        
        # Draw resize icon (diagonal lines)
        painter.setPen(QPen(QColor(100, 100, 100), 2))
        for i in range(3, self.resize_handle_size - 3, 3):
            painter.drawLine(
                self.width() - i - 1, 
                self.height() - 3,
                self.width() - 3, 
                self.height() - i - 1
            )
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging and resizing"""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is on resize handle
            handle_rect = QRect(
                self.width() - self.resize_handle_size,
                self.height() - self.resize_handle_size,
                self.resize_handle_size,
                self.resize_handle_size
            )
            
            if handle_rect.contains(event.position().toPoint()):
                self.is_resizing = True
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                print(f"🔧 RESIZE START: {self.element_id}")
            else:
                self.is_dragging = True
                self.drag_start_pos = event.position().toPoint()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                print(f"🔧 DRAG START: {self.element_id}")
    
    def mouseMoveEvent(self, event):
        """🔧 ULTIMATE FIX: Handle mouse move for dragging and resizing"""
        if self.is_dragging:
            # Calculate new position
            delta = event.position().toPoint() - self.drag_start_pos
            new_pos = self.pos() + delta
            
            # Apply snapping if parent has snap functionality
            if hasattr(self.parent(), 'apply_snapping'):
                new_pos = self.parent().apply_snapping(new_pos, self.size())
            
            self.move(new_pos)
            self.position_changed.emit(self.element_id, new_pos, self.size())
            
        elif self.is_resizing:
            # 🔧 ULTIMATE FIX: Calculate size from element's top-left corner
            mouse_pos = event.position().toPoint()
            
            # New size calculation: mouse position relative to element's top-left
            new_width = max(mouse_pos.x(), self.min_size.width())
            new_height = max(mouse_pos.y(), self.min_size.height())
            
            # Ensure minimum size constraints
            final_width = max(new_width, self.min_size.width())
            final_height = max(new_height, self.min_size.height())
            
            new_size = QSize(int(final_width), int(final_height))
            
            print(f"🔧 RESIZE MOVE: {self.element_id} mouse({mouse_pos.x()}, {mouse_pos.y()}) -> size({new_size.width()}, {new_size.height()})")
            
            # 🔧 CRITICAL: Only resize if size actually changed and is valid
            if new_size != self.size() and new_size.isValid():
                self.resize(new_size)
                # Manual signal emission to ensure it fires
                self.position_changed.emit(self.element_id, self.pos(), new_size)
        
        else:
            # Update cursor based on position
            handle_rect = QRect(
                self.width() - self.resize_handle_size,
                self.height() - self.resize_handle_size,
                self.resize_handle_size,
                self.resize_handle_size
            )
            
            if handle_rect.contains(event.position().toPoint()):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            else:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_resizing:
                print(f"🔧 RESIZE END: {self.element_id} final size: {self.size()}")
            elif self.is_dragging:
                print(f"🔧 DRAG END: {self.element_id} final position: {self.pos()}")
                
            self.is_dragging = False
            self.is_resizing = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

class LayoutCanvas(QFrame):
    """Canvas for positioning FPS elements - UPDATED with new default positions"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Canvas dimensions (16:9 aspect ratio)
        self.canvas_width = 960  # 1920 / 2
        self.canvas_height = 540  # 1080 / 2
        self.setFixedSize(self.canvas_width, self.canvas_height)
        
        # Scaling factor for coordinates (canvas to real video)
        self.scale_factor = 2.0  # Canvas is half the size of actual video
        
        self.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border: 2px solid #555;
                border-radius: 8px;
            }
        """)
        
        # Snap settings
        self.snap_to_grid = True
        self.snap_to_edges = True
        self.snap_to_elements = True
        self.grid_size = 16
        self.snap_threshold = 10
        
        # Element storage
        self.elements = {}
        self.setup_default_elements()
    
    def setup_default_elements(self):
        """🔧 UPDATED: Setup default FPS elements with NEW POSITIONS from your coordinates"""
        
        # 🎯 NEW DEFAULT POSITIONS based on your canvas coordinates
        # Canvas positions (your provided coordinates) -> Real positions (×2)
        default_elements = [
            {
                'id': 'fps_number',
                'name': 'FPS Number\n60.0',
                'pos': QPoint(25, 16),       # Your coordinate: (25, 16)
                'size': QSize(45, 35)        # Canvas size (90x70 real / 2)
            },
            {
                'id': 'frame_time_graph',
                'name': 'Frame Time Graph\n⏱️ 420x160', 
                'pos': QPoint(25, 255),      # Your coordinate: (25, 255)
                'size': QSize(210, 80)       # Canvas size (420x160 real / 2)
            },
            {
                'id': 'frametime_statistics',
                'name': 'Frame Time Stats\nAVG MAX ms',
                'pos': QPoint(128, 245),     # Your coordinate: (128, 245)
                'size': QSize(115, 10)       # Canvas size (230x20 real / 2)
            },
            {
                'id': 'frame_rate_graph', 
                'name': 'Frame Rate Graph\n📊 1100x230',
                'pos': QPoint(25, 384),      # Your coordinate: (25, 384)
                'size': QSize(550, 115)      # Canvas size (1100x230 real / 2)
            },
            {
                'id': 'fps_statistics',
                'name': 'FPS Stats\nAVG MIN MAX',
                'pos': QPoint(25, 512),      # Your coordinate: (25, 512)
                'size': QSize(162, 10)       # Canvas size (325x20 real / 2)
            }
        ]
        
        print(f"🎯 CANVAS: Setting up {len(default_elements)} default elements with NEW POSITIONS")
        
        for elem_data in default_elements:
            element = DraggableElement(
                elem_data['id'],
                elem_data['name'], 
                elem_data['pos'],
                elem_data['size'],
                self
            )
            element.position_changed.connect(self.on_element_moved)
            self.elements[elem_data['id']] = element
            element.show()
            
            # Debug: Log the real-world coordinates
            real_x = elem_data['pos'].x() * self.scale_factor
            real_y = elem_data['pos'].y() * self.scale_factor
            real_w = elem_data['size'].width() * self.scale_factor
            real_h = elem_data['size'].height() * self.scale_factor
            print(f"   📊 {elem_data['id']}: Canvas({elem_data['pos'].x()}, {elem_data['pos'].y()}) -> Real({real_x}, {real_y}) Size: {real_w}x{real_h}")
    
    def get_element_default_position(self, element_id):
        """🔧 NEW: Get default position for an element"""
        defaults = {
            'fps_number': (QPoint(25, 16), QSize(45, 35)),
            'frame_time_graph': (QPoint(25, 255), QSize(210, 80)),
            'frametime_statistics': (QPoint(128, 245), QSize(115, 10)),
            'frame_rate_graph': (QPoint(25, 384), QSize(550, 115)),
            'fps_statistics': (QPoint(25, 512), QSize(162, 10))
        }
        return defaults.get(element_id, (QPoint(50, 50), QSize(100, 50)))
    
    def reset_element_to_default(self, element_id):
        """🔧 NEW: Reset specific element to default position and size"""
        if element_id in self.elements:
            element = self.elements[element_id]
            default_pos, default_size = self.get_element_default_position(element_id)
            
            element.move(default_pos)
            element.resize(default_size)
            
            print(f"📍 Reset {element_id} to default: pos({default_pos}) size({default_size})")
            return True
        return False
    
    def toggle_element_visibility(self, element_id, visible):
        """🔧 NEW: Toggle element visibility"""
        if element_id in self.elements:
            element = self.elements[element_id]
            element.setVisible(visible)
            print(f"👁️ {element_id} visibility: {visible}")
            return True
        return False
    
    def paintEvent(self, event):
        """Paint the canvas with grid and guides"""
        super().paintEvent(event)
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw 16:9 aspect ratio indicator
        painter.setPen(QPen(QColor(100, 255, 100), 2))
        painter.drawRect(2, 2, self.canvas_width - 4, self.canvas_height - 4)
        
        # Draw center lines
        painter.setPen(QPen(QColor(80, 80, 80), 1, Qt.PenStyle.DashLine))
        painter.drawLine(self.canvas_width // 2, 0, self.canvas_width // 2, self.canvas_height)
        painter.drawLine(0, self.canvas_height // 2, self.canvas_width, self.canvas_height // 2)
        
        # Draw grid if enabled
        if self.snap_to_grid:
            self.draw_grid(painter)
    
    def draw_grid(self, painter):
        """Draw snap grid"""
        painter.setPen(QPen(QColor(60, 60, 60), 1, Qt.PenStyle.DotLine))
        
        # Vertical lines
        for x in range(0, self.canvas_width, self.grid_size):
            painter.drawLine(x, 0, x, self.canvas_height)
        
        # Horizontal lines  
        for y in range(0, self.canvas_height, self.grid_size):
            painter.drawLine(0, y, self.canvas_width, y)
    
    def apply_snapping(self, position, size):
        """Apply snapping logic to a position"""
        snapped_pos = QPoint(position)
        
        # Grid snapping
        if self.snap_to_grid:
            snapped_pos = self.snap_to_grid_func(snapped_pos)
        
        # Edge snapping
        if self.snap_to_edges:
            snapped_pos = self.snap_to_edges_func(snapped_pos, size)
        
        # Element snapping
        if self.snap_to_elements:
            snapped_pos = self.snap_to_elements_func(snapped_pos, size)
        
        return snapped_pos
    
    def snap_to_grid_func(self, pos):
        """Snap position to grid"""
        x = round(pos.x() / self.grid_size) * self.grid_size
        y = round(pos.y() / self.grid_size) * self.grid_size
        return QPoint(x, y)
    
    def snap_to_edges_func(self, pos, size):
        """Snap to canvas edges"""
        x, y = pos.x(), pos.y()
        
        # Left edge
        if abs(x) < self.snap_threshold:
            x = 0
        
        # Right edge
        if abs(x + size.width() - self.canvas_width) < self.snap_threshold:
            x = self.canvas_width - size.width()
        
        # Top edge
        if abs(y) < self.snap_threshold:
            y = 0
            
        # Bottom edge
        if abs(y + size.height() - self.canvas_height) < self.snap_threshold:
            y = self.canvas_height - size.height()
        
        return QPoint(x, y)
    
    def snap_to_elements_func(self, pos, size):
        """Snap to other elements"""
        x, y = pos.x(), pos.y()
        
        for element in self.elements.values():
            if element.is_dragging or element.is_resizing:  # Don't snap to self
                continue
                
            elem_rect = element.geometry()
            
            # Horizontal alignment
            if abs(x - elem_rect.x()) < self.snap_threshold:
                x = elem_rect.x()
            elif abs(x - elem_rect.right()) < self.snap_threshold:
                x = elem_rect.right()
            elif abs(x + size.width() - elem_rect.x()) < self.snap_threshold:
                x = elem_rect.x() - size.width()
            
            # Vertical alignment  
            if abs(y - elem_rect.y()) < self.snap_threshold:
                y = elem_rect.y()
            elif abs(y - elem_rect.bottom()) < self.snap_threshold:
                y = elem_rect.bottom()
            elif abs(y + size.height() - elem_rect.y()) < self.snap_threshold:
                y = elem_rect.y() - size.height()
        
        return QPoint(x, y)
    
    def on_element_moved(self, element_id, position, size):
        """Handle element movement"""
        # Update internal state, trigger repaints for guides, etc.
        self.update()
        
        # Debug output for coordinate tracking
        real_x = position.x() * self.scale_factor
        real_y = position.y() * self.scale_factor
        real_w = size.width() * self.scale_factor
        real_h = size.height() * self.scale_factor
        print(f"🎯 Element {element_id}: Canvas({position.x()}, {position.y()}) -> Real({real_x:.0f}, {real_y:.0f}) Size: {real_w:.0f}x{real_h:.0f}")
    
    def get_layout_data(self):
        """Get current layout as dictionary - SCALED for real video coordinates"""
        layout_data = {}
        for elem_id, element in self.elements.items():
            # Only include visible elements or store visibility state
            # Scale up coordinates for real video (canvas * scale_factor)
            real_x = int(element.x() * self.scale_factor)
            real_y = int(element.y() * self.scale_factor)
            real_w = int(element.width() * self.scale_factor)
            real_h = int(element.height() * self.scale_factor)
            
            layout_data[elem_id] = {
                'position': (real_x, real_y),
                'size': (real_w, real_h),
                'anchor': 'top_left',
                'visible': element.isVisible()  # 🔧 NEW: Store visibility state
            }
            
            print(f"📊 Layout Export - {elem_id}: Real({real_x}, {real_y}) Size({real_w}x{real_h}) Visible({element.isVisible()})")
        
        return layout_data
    
    def set_layout_data(self, layout_data):
        """Apply layout from dictionary - SCALED down for canvas"""
        for elem_id, data in layout_data.items():
            if elem_id in self.elements:
                element = self.elements[elem_id]
                
                # Scale down coordinates for canvas (real / scale_factor)
                canvas_x = int(data['position'][0] / self.scale_factor)
                canvas_y = int(data['position'][1] / self.scale_factor)
                canvas_w = int(data['size'][0] / self.scale_factor)
                canvas_h = int(data['size'][1] / self.scale_factor)
                
                pos = QPoint(canvas_x, canvas_y)
                size = QSize(canvas_w, canvas_h)
                
                element.move(pos)
                element.resize(size)
                
                # 🔧 NEW: Apply visibility state
                element.setVisible(data.get('visible', True))
                
                print(f"📥 Layout Import - {elem_id}: Canvas({canvas_x}, {canvas_y}) from Real({data['position'][0]}, {data['position'][1]}) Visible({data.get('visible', True)})")

class ElementControlWidget(QFrame):
    """🔧 NEW: Individual control widget for each element"""
    
    element_visibility_changed = pyqtSignal(str, bool)  # element_id, visible
    element_reset_requested = pyqtSignal(str)  # element_id
    
    def __init__(self, element_id, element_name, parent=None):
        super().__init__(parent)
        self.element_id = element_id
        self.element_name = element_name
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Element name
        name_label = QLabel(self.element_name)
        name_label.setMinimumWidth(120)
        name_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(name_label)
        
        # Visibility toggle
        self.visibility_cb = QCheckBox("Show")
        self.visibility_cb.setChecked(True)
        self.visibility_cb.toggled.connect(self.on_visibility_changed)
        layout.addWidget(self.visibility_cb)
        
        # Reset button
        reset_btn = QPushButton("Reset")
        reset_btn.setMaximumWidth(60)
        reset_btn.clicked.connect(self.on_reset_clicked)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #66BB6A;
            }
        """)
        layout.addWidget(reset_btn)
        
        # Style the frame
        self.setStyleSheet("""
            QFrame {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 6px;
                margin: 2px;
            }
        """)
    
    def on_visibility_changed(self, checked):
        self.element_visibility_changed.emit(self.element_id, checked)
    
    def on_reset_clicked(self):
        self.element_reset_requested.emit(self.element_id)
    
    def set_visibility(self, visible):
        """Update visibility checkbox without triggering signal"""
        self.visibility_cb.blockSignals(True)
        self.visibility_cb.setChecked(visible)
        self.visibility_cb.blockSignals(False)

class LayoutEditorDialog(QDialog):
    """Main dialog for the layout editor - WITH INDIVIDUAL ELEMENT CONTROLS"""
    
    layout_changed = pyqtSignal(dict)  # Emit when layout changes
    
    def __init__(self, parent, current_layout=None):
        super().__init__(parent)
        self.parent_analyzer = parent
        self.setWindowTitle("🎯 FPS Layout Editor - Individual Element Controls")
        self.setModal(False)  # Allow interaction with main window
        self.resize(1400, 900)  # Slightly taller for controls
        
        # Element control widgets storage
        self.element_controls = {}
        
        self.setup_ui()
        self.apply_theme()
        
        # Load current layout if provided
        if current_layout:
            self.canvas.set_layout_data(current_layout)
            self.update_element_controls_visibility()
    
    def setup_ui(self):
        """Setup the user interface"""
        layout = QVBoxLayout(self)
        
        # Title and info
        title_label = QLabel("🎯 FPS Layout Editor - Individual Element Controls")
        title_label.setStyleSheet("font-weight: bold; color: #4CAF50; padding: 5px; font-size: 16px;")
        layout.addWidget(title_label)
        
        info_label = QLabel("💡 Drag elements • Drag WHITE CORNER HANDLE to resize • Use controls to hide/reset elements")
        info_label.setStyleSheet("color: #888; font-style: italic; padding: 0 5px 10px 5px;")
        layout.addWidget(info_label)
        
        # Main content area
        content_layout = QHBoxLayout()
        
        # Left side - Canvas
        canvas_group = QGroupBox("🎨 Layout Canvas (16:9 - 1920x1080 Preview)")
        canvas_layout = QVBoxLayout(canvas_group)
        
        self.canvas = LayoutCanvas()
        canvas_layout.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignCenter)
        
        content_layout.addWidget(canvas_group, 3)  # 60% width
        
        # Right side - Controls (made larger for element controls)
        controls_group = QGroupBox("⚙️ Layout Controls")
        controls_layout = QVBoxLayout(controls_group)
        
        # 🔧 NEW: Individual Element Controls Section
        self.setup_element_controls(controls_layout)
        
        # Snap settings
        self.setup_snap_settings(controls_layout)
        
        # Canvas info
        self.setup_canvas_info(controls_layout)
        
        # Layout presets (SIMPLIFIED)
        self.setup_layout_presets(controls_layout)
        
        # Quick actions
        self.setup_quick_actions(controls_layout)
        
        controls_layout.addStretch()
        content_layout.addWidget(controls_group, 2)  # 40% width
        
        layout.addLayout(content_layout)
        
        # Bottom buttons
        self.setup_bottom_buttons(layout)
    
    def setup_element_controls(self, parent_layout):
        """🔧 NEW: Setup individual element controls"""
        element_group = QGroupBox("🎛️ Individual Element Controls")
        element_layout = QVBoxLayout(element_group)
        
        # Scrollable area for element controls
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Create control widgets for each element
        element_names = {
            'fps_number': '🎯 FPS Number',
            'frame_rate_graph': '📊 Frame Rate Graph',
            'frame_time_graph': '⏱️ Frame Time Graph', 
            'fps_statistics': '📈 FPS Statistics',
            'frametime_statistics': '⏲️ Frame Time Stats'
        }
        
        for element_id, element_name in element_names.items():
            control_widget = ElementControlWidget(element_id, element_name)
            control_widget.element_visibility_changed.connect(self.on_element_visibility_changed)
            control_widget.element_reset_requested.connect(self.on_element_reset_requested)
            
            self.element_controls[element_id] = control_widget
            scroll_layout.addWidget(control_widget)
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setMaximumHeight(200)
        scroll_area.setWidgetResizable(True)
        
        element_layout.addWidget(scroll_area)
        
        # Global element actions
        global_actions_layout = QHBoxLayout()
        
        show_all_btn = QPushButton("👁️ Show All")
        show_all_btn.clicked.connect(self.show_all_elements)
        global_actions_layout.addWidget(show_all_btn)
        
        hide_all_btn = QPushButton("🚫 Hide All")
        hide_all_btn.clicked.connect(self.hide_all_elements)
        global_actions_layout.addWidget(hide_all_btn)
        
        reset_all_btn = QPushButton("↺ Reset All")
        reset_all_btn.clicked.connect(self.reset_all_elements)
        global_actions_layout.addWidget(reset_all_btn)
        
        element_layout.addLayout(global_actions_layout)
        parent_layout.addWidget(element_group)
    
    def setup_snap_settings(self, parent_layout):
        """Setup snap settings section"""
        snap_group = QGroupBox("📐 Snap Settings")
        snap_layout = QGridLayout(snap_group)
        
        self.snap_grid_cb = QCheckBox("Snap to Grid")
        self.snap_grid_cb.setChecked(True)
        self.snap_grid_cb.toggled.connect(self.update_snap_settings)
        snap_layout.addWidget(self.snap_grid_cb, 0, 0)
        
        self.snap_edges_cb = QCheckBox("Snap to Edges")
        self.snap_edges_cb.setChecked(True)
        self.snap_edges_cb.toggled.connect(self.update_snap_settings)
        snap_layout.addWidget(self.snap_edges_cb, 0, 1)
        
        self.snap_elements_cb = QCheckBox("Snap to Elements")
        self.snap_elements_cb.setChecked(True)
        self.snap_elements_cb.toggled.connect(self.update_snap_settings)
        snap_layout.addWidget(self.snap_elements_cb, 1, 0)
        
        snap_layout.addWidget(QLabel("Grid Size:"), 2, 0)
        self.grid_size_spin = QSpinBox()
        self.grid_size_spin.setRange(8, 64)
        self.grid_size_spin.setValue(16)
        self.grid_size_spin.valueChanged.connect(self.update_snap_settings)
        snap_layout.addWidget(self.grid_size_spin, 2, 1)
        
        parent_layout.addWidget(snap_group)
    
    def setup_canvas_info(self, parent_layout):
        """Setup canvas info section"""
        canvas_info_group = QGroupBox("📏 Canvas Info")
        canvas_info_layout = QVBoxLayout(canvas_info_group)
        
        self.canvas_info_label = QLabel(
            f"Canvas Size: {self.canvas.canvas_width}x{self.canvas.canvas_height}\n"
            f"Video Size: 1920x1080 (16:9)\n"
            f"Scale Factor: {self.canvas.scale_factor:.1f}x\n"
            f"NEW Default Positions Applied ✓"
        )
        self.canvas_info_label.setStyleSheet("color: #888; font-size: 10px;")
        canvas_info_layout.addWidget(self.canvas_info_label)
        
        parent_layout.addWidget(canvas_info_group)
    
    def setup_layout_presets(self, parent_layout):
        """🔧 UPDATED: Setup simplified layout presets"""
        preset_group = QGroupBox("📋 Layout Presets")
        preset_layout = QVBoxLayout(preset_group)
        
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "Default Layout",    # NEW: Your custom default
            "Minimal",          # Only FPS display
            "Medium"            # FPS + Frame Time Graph
        ])
        preset_layout.addWidget(self.preset_combo)
        
        preset_buttons_layout = QHBoxLayout()
        
        load_preset_btn = QPushButton("📥 Load Preset")
        load_preset_btn.clicked.connect(self.load_preset)
        preset_buttons_layout.addWidget(load_preset_btn)
        
        preset_layout.addLayout(preset_buttons_layout)
        
        # 🔧 NEW: Save/Load Current Layout
        current_layout_group = QGroupBox("💾 Current Layout")
        current_layout_layout = QVBoxLayout(current_layout_group)
        
        save_load_layout = QHBoxLayout()
        
        save_current_btn = QPushButton("💾 Save Current")
        save_current_btn.clicked.connect(self.save_current_layout)
        save_load_layout.addWidget(save_current_btn)
        
        load_file_btn = QPushButton("📂 Load File")
        load_file_btn.clicked.connect(self.load_layout_file)
        save_load_layout.addWidget(load_file_btn)
        
        current_layout_layout.addLayout(save_load_layout)
        preset_layout.addWidget(current_layout_group)
        
        parent_layout.addWidget(preset_group)
    
    def setup_quick_actions(self, parent_layout):
        """Setup quick actions section"""
        actions_group = QGroupBox("⚡ Quick Actions")
        actions_layout = QVBoxLayout(actions_group)
        
        center_all_btn = QPushButton("🎯 Center All Elements")
        center_all_btn.clicked.connect(self.center_all_elements)
        actions_layout.addWidget(center_all_btn)
        
        parent_layout.addWidget(actions_group)
    
    def setup_bottom_buttons(self, parent_layout):
        """Setup bottom control buttons"""
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        test_layout_btn = QPushButton("🎬 Test Layout")
        test_layout_btn.clicked.connect(self.test_layout)
        button_layout.addWidget(test_layout_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        apply_btn = QPushButton("✓ Apply Layout")
        apply_btn.clicked.connect(self.apply_layout)
        apply_btn.setDefault(True)
        apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #66BB6A;
            }
        """)
        button_layout.addWidget(apply_btn)
        
        parent_layout.addLayout(button_layout)
    
    # 🔧 NEW: Element control event handlers
    def on_element_visibility_changed(self, element_id, visible):
        """Handle element visibility change"""
        self.canvas.toggle_element_visibility(element_id, visible)
    
    def on_element_reset_requested(self, element_id):
        """Handle element reset request"""
        self.canvas.reset_element_to_default(element_id)
    
    def update_element_controls_visibility(self):
        """Update element control checkboxes based on canvas state"""
        for element_id, control_widget in self.element_controls.items():
            if element_id in self.canvas.elements:
                element = self.canvas.elements[element_id]
                control_widget.set_visibility(element.isVisible())
    
    def show_all_elements(self):
        """Show all elements"""
        for element_id in self.canvas.elements:
            self.canvas.toggle_element_visibility(element_id, True)
            if element_id in self.element_controls:
                self.element_controls[element_id].set_visibility(True)
    
    def hide_all_elements(self):
        """Hide all elements"""
        for element_id in self.canvas.elements:
            self.canvas.toggle_element_visibility(element_id, False)
            if element_id in self.element_controls:
                self.element_controls[element_id].set_visibility(False)
    
    def reset_all_elements(self):
        """Reset all elements to default positions"""
        for element_id in self.canvas.elements:
            self.canvas.reset_element_to_default(element_id)
    
    def update_snap_settings(self):
        """Update canvas snap settings"""
        self.canvas.snap_to_grid = self.snap_grid_cb.isChecked()
        self.canvas.snap_to_edges = self.snap_edges_cb.isChecked()
        self.canvas.snap_to_elements = self.snap_elements_cb.isChecked()
        self.canvas.grid_size = self.grid_size_spin.value()
        self.canvas.update()  # Redraw grid
    
    def load_preset(self):
        """🔧 UPDATED: Load simplified layout preset"""
        preset_name = self.preset_combo.currentText()
        
        # 🔧 UPDATED: Simplified presets with your default positions
        presets = {
            "Default Layout": {
                'fps_number': {'position': (50, 32), 'size': (90, 70), 'visible': True},
                'frame_time_graph': {'position': (50, 510), 'size': (420, 160), 'visible': True},
                'frametime_statistics': {'position': (256, 490), 'size': (230, 20), 'visible': True},
                'frame_rate_graph': {'position': (50, 768), 'size': (1100, 230), 'visible': True},
                'fps_statistics': {'position': (50, 1024), 'size': (325, 20), 'visible': True}
            },
            "Minimal": {
                'fps_number': {'position': (50, 50), 'size': (90, 70), 'visible': True},
                'frame_time_graph': {'position': (50, 510), 'size': (420, 160), 'visible': False},
                'frametime_statistics': {'position': (256, 490), 'size': (230, 20), 'visible': False},
                'frame_rate_graph': {'position': (50, 768), 'size': (1100, 230), 'visible': False},
                'fps_statistics': {'position': (50, 1024), 'size': (325, 20), 'visible': False}
            },
            "Medium": {
                'fps_number': {'position': (50, 50), 'size': (90, 70), 'visible': True},
                'frame_time_graph': {'position': (50, 300), 'size': (420, 160), 'visible': False},
                'frametime_statistics': {'position': (256, 280), 'size': (230, 20), 'visible': False},
                'frame_rate_graph': {'position': (50, 768), 'size': (1100, 230), 'visible': True},
                'fps_statistics': {'position': (50, 1024), 'size': (325, 20), 'visible': True}
            }
        }
        
        if preset_name in presets:
            self.canvas.set_layout_data(presets[preset_name])
            self.update_element_controls_visibility()
            print(f"📥 Loaded preset: {preset_name}")
    
    def save_current_layout(self):
        """🔧 NEW: Save current layout to file"""
        layout_data = self.canvas.get_layout_data()
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, 'Save Layout', '', 
            'JSON Files (*.json);;All Files (*)'
        )
        
        if file_path:
            try:
                import json
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'fps_analyzer_layout': layout_data,
                        'version': '2.0',
                        'elements': list(layout_data.keys()),
                        'description': 'FPS Analyzer Custom Layout'
                    }, f, indent=2, ensure_ascii=False)
                
                QMessageBox.information(self, 'Layout Saved', f'Layout saved successfully to:\n{file_path}')
                print(f"💾 Layout saved to: {file_path}")
                
            except Exception as e:
                QMessageBox.warning(self, 'Save Error', f'Could not save layout:\n{str(e)}')
    
    def load_layout_file(self):
        """🔧 NEW: Load layout from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Load Layout', '', 
            'JSON Files (*.json);;All Files (*)'
        )
        
        if file_path:
            try:
                import json
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Handle different file formats
                if 'fps_analyzer_layout' in data:
                    layout_data = data['fps_analyzer_layout']
                else:
                    layout_data = data  # Assume direct layout format
                
                self.canvas.set_layout_data(layout_data)
                self.update_element_controls_visibility()
                
                QMessageBox.information(self, 'Layout Loaded', f'Layout loaded successfully from:\n{file_path}')
                print(f"📂 Layout loaded from: {file_path}")
                
            except Exception as e:
                QMessageBox.warning(self, 'Load Error', f'Could not load layout:\n{str(e)}')
    
    def center_all_elements(self):
        """Center all elements on canvas"""
        canvas_center = QPoint(self.canvas.canvas_width // 2, self.canvas.canvas_height // 2)
        
        for element in self.canvas.elements.values():
            if element.isVisible():  # Only center visible elements
                element_center = QPoint(
                    canvas_center.x() - element.width() // 2,
                    canvas_center.y() - element.height() // 2
                )
                element.move(element_center)
    
    def test_layout(self):
        """Test current layout with live preview"""
        # This could open the font preview with current layout
        QMessageBox.information(self, "Test Layout", 
                               "Layout testing will be integrated with the font preview system!\n\n"
                               "Current layout will be applied when you click 'Apply Layout'.")
    
    def apply_layout(self):
        """Apply current layout and close dialog"""
        layout_data = self.canvas.get_layout_data()
        
        print(f"🚀 Applying layout with {len(layout_data)} elements:")
        for elem_id, data in layout_data.items():
            print(f"   {elem_id}: {data['position']} {data['size']} visible({data['visible']})")
        
        self.layout_changed.emit(layout_data)
        self.accept()
    
    def apply_theme(self):
        """Apply parent theme"""
        if hasattr(self.parent_analyzer, 'current_theme'):
            self.setStyleSheet(self.parent_analyzer.styleSheet())