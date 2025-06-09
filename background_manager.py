"""
Background Manager für Font Preview
Simple gradient backgrounds instead of complex gaming scenes
"""
import cv2
import numpy as np

class BackgroundManager:
    """Manages different background styles for font preview"""
    
    def __init__(self):
        self.backgrounds = {
            "Dark Gradient": self.create_dark_gradient,
            "Blue Gradient": self.create_blue_gradient,
            "Green Gradient": self.create_green_gradient,
            "Purple Gaming": self.create_purple_gaming,
            "Orange Sunset": self.create_orange_sunset,
            "Cyberpunk": self.create_cyberpunk,
            "Minimal Gray": self.create_minimal_gray,
            "Black": self.create_solid_black
        }
    
    def get_available_backgrounds(self):
        """Get list of available background names"""
        return list(self.backgrounds.keys())
    
    def create_background(self, name, width=1920, height=1080):
        """Create background by name"""
        if name in self.backgrounds:
            return self.backgrounds[name](width, height)
        else:
            return self.create_dark_gradient(width, height)
    
    def create_dark_gradient(self, width, height):
        """Dark blue to black gradient - professional"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        for y in range(height):
            color_factor = y / height
            frame[y, :] = [
                int(20 + color_factor * 15),   # Blue
                int(15 + color_factor * 10),   # Green  
                int(5 + color_factor * 5)      # Red
            ]
        
        return frame
    
    def create_blue_gradient(self, width, height):
        """Classic blue gradient"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        for y in range(height):
            color_factor = y / height
            frame[y, :] = [
                int(100 + color_factor * 155),  # Blue
                int(20 + color_factor * 40),    # Green  
                int(10 + color_factor * 20)     # Red
            ]
        
        return frame
    
    def create_green_gradient(self, width, height):
        """Green gaming gradient"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        for y in range(height):
            color_factor = y / height
            frame[y, :] = [
                int(10 + color_factor * 20),    # Blue
                int(50 + color_factor * 100),   # Green  
                int(5 + color_factor * 15)      # Red
            ]
        
        return frame
    
    def create_purple_gaming(self, width, height):
        """Purple gaming aesthetic"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        for y in range(height):
            color_factor = y / height
            for x in range(width):
                x_factor = x / width
                frame[y, x] = [
                    int(80 + color_factor * 80 + x_factor * 20),   # Blue
                    int(20 + color_factor * 30),                   # Green  
                    int(60 + color_factor * 60 + x_factor * 30)    # Red
                ]
        
        return frame
    
    def create_orange_sunset(self, width, height):
        """Orange sunset gradient"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        for y in range(height):
            color_factor = y / height
            frame[y, :] = [
                int(20 + color_factor * 40),    # Blue
                int(60 + color_factor * 120),   # Green  
                int(100 + color_factor * 155)   # Red
            ]
        
        return frame
    
    def create_cyberpunk(self, width, height):
        """Cyberpunk neon style"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Base dark background
        frame[:, :] = [15, 25, 40]  # Dark blue-gray
        
        # Add some horizontal neon lines
        for i in range(0, height, 80):
            if i < height - 2:
                frame[i:i+2, :] = [255, 100, 150]  # Neon pink line
        
        # Add vertical accent
        center_x = width // 2
        frame[:, center_x-1:center_x+1] = [100, 255, 200]  # Neon cyan
        
        return frame
    
    def create_minimal_gray(self, width, height):
        """Minimal gray gradient"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        for y in range(height):
            color_factor = y / height
            gray_value = int(30 + color_factor * 50)
            frame[y, :] = [gray_value, gray_value, gray_value]
        
        return frame
    
    def create_solid_black(self, width, height):
        """Simple black background"""
        return np.zeros((height, width, 3), dtype=np.uint8)
    
    def add_simple_ui_elements(self, frame):
        """Add minimal UI elements for context"""
        height, width = frame.shape[:2]
        
        # Simple health bar (top left)
        cv2.rectangle(frame, (30, 30), (200, 55), (40, 40, 40), -1)
        cv2.rectangle(frame, (35, 35), (195, 50), (0, 120, 0), -1)
        cv2.putText(frame, "HEALTH", (40, 47), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        # Minimap placeholder (top right)
        cv2.rectangle(frame, (width-150, 30), (width-30, 150), (50, 50, 50), -1)
        cv2.rectangle(frame, (width-145, 35), (width-35, 145), (30, 30, 30), 2)
        cv2.putText(frame, "MAP", (width-115, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        
        # Center title
        title_text = "FONT PREVIEW DEMO"
        text_size = cv2.getTextSize(title_text, cv2.FONT_HERSHEY_COMPLEX, 1.2, 2)[0]
        text_x = (width - text_size[0]) // 2
        text_y = (height + text_size[1]) // 2
        
        cv2.putText(frame, title_text, (text_x, text_y), cv2.FONT_HERSHEY_COMPLEX, 1.2, (255, 255, 255), 2)
        cv2.putText(frame, "Background Preview Mode", (text_x, text_y + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (150, 255, 150), 1)
        
        return frame