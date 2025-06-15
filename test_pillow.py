import sys
print("Python version:", sys.version)

try:
    from PIL import Image, ImageDraw, ImageFont
    print("✅ Pillow is installed")
    print("Pillow version:", Image.__version__)
    
    # Test creating an image
    img = Image.new('RGB', (200, 100), color='black')
    draw = ImageDraw.Draw(img)
    
    # Try to load a default font
    try:
        font = ImageFont.load_default()
        draw.text((10, 10), "Test", fill='white', font=font)
        print("✅ Default font works")
    except Exception as e:
        print("❌ Default font error:", e)
    
    # Try to load a TrueType font
    import os
    if os.path.exists("C:/Windows/Fonts/arial.ttf"):
        try:
            ttf_font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 24)
            draw.text((10, 40), "TrueType Test", fill='white', font=ttf_font)
            print("✅ TrueType font loading works")
        except Exception as e:
            print("❌ TrueType font error:", e)
    else:
        print("⚠️ Arial.ttf not found in Windows fonts")
    
except ImportError as e:
    print("❌ Pillow is NOT installed")
    print("Error:", e)
    print("\nTo install Pillow, run:")
    print("pip install Pillow")

# Check OpenCV
try:
    import cv2
    print("\n✅ OpenCV is installed")
    print("OpenCV version:", cv2.__version__)
    
    # Check for FreeType
    try:
        ft = cv2.freetype.createFreeType2()
        print("✅ OpenCV has FreeType support")
    except:
        print("❌ OpenCV does NOT have FreeType support")
        print("Note: You need opencv-contrib-python for FreeType support")
        
except ImportError:
    print("\n❌ OpenCV is NOT installed")