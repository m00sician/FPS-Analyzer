"""
Font Diagnostic Script - To validate your font pipeline

INSTRUCTIONS:
1. Save this as font_diagnostic.py in your project directory
2. Run it with: python font_diagnostic.py
3. This will help diagnose font loading, initialization, and rendering issues
"""

import os
import sys
import cv2
import numpy as np

def enable_debug_mode():
    """Enable debug logging for font modules"""
    try:
        from font_manager import enable_debug_mode as fm_debug
        fm_debug(True)
        print("✅ Enabled debug mode for font_manager")
    except ImportError:
        print("⚠️ Could not enable debug mode for font_manager")
    
    try:
        from truetype_core import enable_debug_mode as ttc_debug
        ttc_debug(True)
        print("✅ Enabled debug mode for truetype_core")
    except ImportError:
        print("⚠️ Could not enable debug mode for truetype_core")

def check_font_system():
    """Check font system availability and configuration"""
    print("\n" + "="*70)
    print("🔍 FONT SYSTEM DIAGNOSTICS")
    print("="*70)
    
    # Check for Pillow
    try:
        from PIL import Image, ImageDraw, ImageFont
        print("✅ Pillow is available")
        
        # Try to load a system font
        try:
            # Check if we can load the default font
            default_font = ImageFont.load_default()
            print("✅ Pillow default font works")
            
            # Try to load Arial or a system font
            try:
                for font_name in ['arial.ttf', 'Arial.ttf', 'DejaVuSans.ttf', 'FreeSans.ttf']:
                    try:
                        font = ImageFont.truetype(font_name, 24)
                        print(f"✅ Successfully loaded Pillow font: {font_name}")
                        break
                    except IOError:
                        continue
            except Exception as e:
                print(f"⚠️ Pillow TrueType font loading issue: {e}")
        except Exception as e:
            print(f"⚠️ Pillow default font loading issue: {e}")
    except ImportError:
        print("❌ Pillow is not available")
    
    # Check for OpenCV FreeType support
    try:
        if hasattr(cv2, 'freetype'):
            print("✅ OpenCV FreeType module is available")
            try:
                ft = cv2.freetype.createFreeType2()
                print("✅ OpenCV FreeType creation works")
            except Exception as e:
                print(f"⚠️ OpenCV FreeType creation issue: {e}")
        else:
            print("❌ OpenCV FreeType module is not available")
    except Exception as e:
        print(f"❌ OpenCV FreeType check error: {e}")
    
    # Check OpenCV version
    print(f"ℹ️ OpenCV version: {cv2.__version__}")
    
    # Check for font_manager.py
    try:
        import font_manager
        print(f"✅ font_manager.py is available (version: {getattr(font_manager, '__version__', 'unknown')})")
        
        # Check if OpenCVFontSettings is available
        if hasattr(font_manager, 'OpenCVFontSettings'):
            print("✅ OpenCVFontSettings class is available")
            
            # Create a test instance
            test_font = font_manager.OpenCVFontSettings('HERSHEY_SIMPLEX', 24, 2, False)
            print(f"✅ Created test font: {test_font.font_name}, size: {test_font.size}")
            
            # Check if we can render text
            if hasattr(test_font, 'render_text'):
                print("✅ render_text method is available")
                
                # Try to render text
                try:
                    test_img = np.zeros((200, 400, 3), dtype=np.uint8)
                    result = test_font.render_text(test_img, "Test Text", (50, 50), 1.0)
                    print("✅ Text rendering works")
                    
                    # Check TrueType availability
                    if hasattr(test_font, 'is_freetype_available'):
                        ft_available = test_font.is_freetype_available()
                        print(f"ℹ️ TrueType/FreeType availability: {'✅ Yes' if ft_available else '❌ No'}")
                    
                except Exception as e:
                    print(f"❌ Text rendering failed: {e}")
            else:
                print("❌ render_text method is not available")
        else:
            print("❌ OpenCVFontSettings class is not available")
    except ImportError:
        print("❌ font_manager.py is not available")
    
    # Check for enhanced_overlay_renderer.py
    try:
        import enhanced_overlay_renderer
        print("✅ enhanced_overlay_renderer.py is available")
        
        # Check if necessary functions are available
        for func_name in ['draw_fps_overlay_with_layout', 'draw_fps_overlay_with_legacy_position']:
            if hasattr(enhanced_overlay_renderer, func_name):
                print(f"✅ {func_name} function is available")
            else:
                print(f"❌ {func_name} function is missing")
        
        # Check EnhancedFontSettings fallback
        if hasattr(enhanced_overlay_renderer, 'EnhancedFontSettings'):
            print("✅ EnhancedFontSettings class is available")
            
            # Create a test instance
            test_font = enhanced_overlay_renderer.EnhancedFontSettings('HERSHEY_SIMPLEX', 24, 2, False)
            print(f"✅ Created test font: {test_font.font_name}, size: {test_font.size}")
            
            # Check if we can render text
            if hasattr(test_font, 'render_text'):
                print("✅ render_text method is available in EnhancedFontSettings")
            else:
                print("❌ render_text method is missing in EnhancedFontSettings")
        else:
            print("❌ EnhancedFontSettings class is missing")
    except ImportError:
        print("❌ enhanced_overlay_renderer.py is not available")

def render_test_image():
    """Create a test image with different font rendering methods"""
    print("\n" + "="*70)
    print("🎨 GENERATING FONT RENDERING TEST IMAGE")
    print("="*70)
    
    # Create a test image
    width, height = 800, 600
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = (30, 30, 30)  # Dark gray background
    
    # Draw grid lines
    for x in range(0, width, 50):
        cv2.line(img, (x, 0), (x, height), (50, 50, 50), 1)
    for y in range(0, height, 50):
        cv2.line(img, (0, y), (width, y), (50, 50, 50), 1)
    
    # Add title
    cv2.putText(img, "Font Rendering Test", (20, 40), 
               cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2, cv2.LINE_AA)
    
    # Draw test text with OpenCV
    y_pos = 100
    cv2.putText(img, "OpenCV Standard: FPS 59.8", (50, y_pos), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2, cv2.LINE_AA)
    
    # Try to draw with font_manager if available
    y_pos += 50
    try:
        from font_manager import OpenCVFontSettings
        
        # Create OpenCV font settings
        opencv_font = OpenCVFontSettings('HERSHEY_SIMPLEX', 24, 2, True)
        
        # Render text
        opencv_font.text_color = (0, 200, 255)
        result = opencv_font.render_text(img, "font_manager: FPS 59.8", (50, y_pos), 0.7)
        img = result if result is not None else img
        
        # Try TrueType font if available
        y_pos += 50
        truetype_font = OpenCVFontSettings('Arial', 24, 2, True)
        truetype_font.text_color = (255, 255, 0)
        
        if truetype_font.is_freetype_available():
            result = truetype_font.render_text(img, "TrueType: FPS 59.8", (50, y_pos), 0.7)
            img = result if result is not None else img
            status = "✅ TrueType rendering works"
        else:
            cv2.putText(img, "TrueType not available", (50, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 255), 2, cv2.LINE_AA)
            status = "⚠️ TrueType not available"
        
        print(status)
        
    except ImportError:
        cv2.putText(img, "font_manager not available", (50, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 255), 2, cv2.LINE_AA)
        print("⚠️ font_manager not available")
    
    # Try to draw with enhanced_overlay_renderer if available
    y_pos += 50
    try:
        from enhanced_overlay_renderer import EnhancedFontSettings
        
        # Create enhanced font settings
        enhanced_font = EnhancedFontSettings('HERSHEY_SIMPLEX', 24, 2, True)
        
        # Render text
        if hasattr(enhanced_font, 'render_text'):
            enhanced_font.text_color = (255, 100, 255)
            result = enhanced_font.render_text(img, "enhanced_renderer: FPS 59.8", (50, y_pos), 0.7)
            img = result if result is not None else img
            print("✅ Enhanced renderer text rendering works")
        else:
            cv2.putText(img, "enhanced_renderer render_text missing", (50, y_pos), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 255), 2, cv2.LINE_AA)
            print("⚠️ enhanced_renderer render_text method missing")
            
    except ImportError:
        cv2.putText(img, "enhanced_overlay_renderer not available", (50, y_pos), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 255), 2, cv2.LINE_AA)
        print("⚠️ enhanced_overlay_renderer not available")
    
    # Special characters test
    y_pos += 50
    cv2.putText(img, "Special chars: !@#$%^&*()_+-=[]{}|;:'\",.<>/?", (50, y_pos), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
    
    # Add timestamp
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cv2.putText(img, f"Generated: {timestamp}", (50, height - 30), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
    
    # Save the image
    output_path = "font_test.png"
    cv2.imwrite(output_path, img)
    print(f"✅ Test image saved to: {output_path}")
    
    return img

def test_overlay_renderer():
    """Test the overlay renderer directly"""
    print("\n" + "="*70)
    print("🔧 TESTING OVERLAY RENDERER")
    print("="*70)
    
    try:
        import enhanced_overlay_renderer
        print("✅ enhanced_overlay_renderer imported successfully")
        
        # Create test image
        img = np.zeros((720, 1280, 3), dtype=np.uint8)
        img[:] = (30, 30, 40)  # Dark blue-gray background
        
        # Create mock data
        fps_history = [60, 59, 61, 58, 60, 59] * 30
        current_fps = 59.5
        frame_times = [16.7, 16.9, 16.5, 17.2, 16.7, 16.9] * 30
        
        # Create font settings
        try:
            from font_manager import OpenCVFontSettings
            font_settings = {
                'fps_font': OpenCVFontSettings('HERSHEY_SIMPLEX', 32, 3, True, border_thickness=3),
                'framerate_font': OpenCVFontSettings('HERSHEY_SIMPLEX', 16, 2, False, border_thickness=2),
                'frametime_font': OpenCVFontSettings('HERSHEY_SIMPLEX', 14, 1, False, border_thickness=1)
            }
            print("✅ Created font settings with OpenCVFontSettings")
        except ImportError:
            # Fallback
            try:
                from enhanced_overlay_renderer import EnhancedFontSettings
                font_settings = {
                    'fps_font': EnhancedFontSettings('HERSHEY_SIMPLEX', 32, 3, True, border_thickness=3),
                    'framerate_font': EnhancedFontSettings('HERSHEY_SIMPLEX', 16, 2, False, border_thickness=2),
                    'frametime_font': EnhancedFontSettings('HERSHEY_SIMPLEX', 14, 1, False, border_thickness=1)
                }
                print("✅ Created font settings with EnhancedFontSettings fallback")
            except Exception as e:
                print(f"❌ Could not create font settings: {e}")
                return
        
        # Create color settings
        color_settings = {
            'framerate_color': '#00FF00',
            'frametime_color': '#00FF00'
        }
        
        # Create mock layout
        layout_config = {
            'fps_display': {
                'x': 50, 'y': 50, 'width': 120, 'height': 80, 'visible': True
            },
            'frame_rate_graph': {
                'x': 50, 'y': 400, 'width': 800, 'height': 200, 'visible': True
            },
            'frame_time_graph': {
                'x': 900, 'y': 400, 'width': 300, 'height': 200, 'visible': True
            }
        }
        
        # Try to render with layout
        try:
            result = enhanced_overlay_renderer.draw_fps_overlay_with_layout(
                img, fps_history, current_fps, frame_times, True, 180,
                fps_history, frame_times,
                {'min': 16.7, 'mid': 33.3, 'max': 50.0, 'labels': ['16.7', '33.3', '50.0']},
                font_settings, color_settings, layout_config
            )
            cv2.imwrite("overlay_test_layout.png", result)
            print("✅ Successfully rendered overlay with layout")
        except Exception as e:
            print(f"❌ Overlay rendering with layout failed: {e}")
            import traceback
            traceback.print_exc()
        
        # Try to render with legacy position
        try:
            result = enhanced_overlay_renderer.draw_fps_overlay_with_legacy_position(
                img, fps_history, current_fps, frame_times, True, 180,
                fps_history, frame_times,
                {'min': 16.7, 'mid': 33.3, 'max': 50.0, 'labels': ['16.7', '33.3', '50.0']},
                font_settings, color_settings, 'bottom_right'
            )
            cv2.imwrite("overlay_test_legacy.png", result)
            print("✅ Successfully rendered overlay with legacy position")
        except Exception as e:
            print(f"❌ Overlay rendering with legacy position failed: {e}")
            import traceback
            traceback.print_exc()
            
    except ImportError:
        print("❌ enhanced_overlay_renderer could not be imported")

def main():
    """Run all font diagnostic tests"""
    print("\n" + "="*70)
    print("🔍 FONT DIAGNOSTICS TOOL")
    print("="*70)
    print("System:", sys.platform)
    print("Python:", sys.version)
    print("Working directory:", os.getcwd())
    print("="*70 + "\n")
    
    # Enable debug mode
    enable_debug_mode()
    
    # Run all tests
    check_font_system()
    render_test_image()
    test_overlay_renderer()
    
    print("\n" + "="*70)
    print("✅ DIAGNOSTICS COMPLETE")
    print("""
Next steps:
1. Check the generated test images (font_test.png, overlay_test_*.png)
2. Review the diagnostic output above for any errors
3. Fix any issues in the font rendering pipeline
4. Apply the patches from enhanced_renderer_fix.py and worker_font_fix.py
""")
    print("="*70)

if __name__ == "__main__":
    main()