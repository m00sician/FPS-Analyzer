"""
Debug Helper für FPS Analyzer
Überprüft, ob alle UI-Settings korrekt extrahiert werden
"""

def debug_widget_settings(fps_analyzer_instance):
    """Debug function to check all widget settings"""
    print("\n" + "="*50)
    print("🔍 DEBUG: Widget Settings Verification")
    print("="*50)
    
    try:
        # Test Bitrate Widget
        bitrate_widget = fps_analyzer_instance.bitrate_combo
        print(f"📊 Bitrate Widget Type: {type(bitrate_widget)}")
        
        if hasattr(bitrate_widget, 'currentText'):
            bitrate_text = bitrate_widget.currentText()
            print(f"📊 Bitrate Text: '{bitrate_text}'")
            try:
                bitrate_value = int(bitrate_text)
                print(f"📊 Bitrate Value: {bitrate_value}")
            except ValueError as e:
                print(f"❌ Bitrate Conversion Error: {e}")
        else:
            print("❌ Bitrate Widget has no currentText() method")
        
        # Test Resolution Widget
        resolution_widget = fps_analyzer_instance.resolution_combo
        print(f"📺 Resolution Widget Type: {type(resolution_widget)}")
        
        if hasattr(resolution_widget, 'currentData'):
            resolution = resolution_widget.currentData()
            print(f"📺 Resolution Data: {resolution}")
        else:
            print("❌ Resolution Widget has no currentData() method")
        
        # Test Sensitivity Widget
        sensitivity_widget = fps_analyzer_instance.sensitivity_combo
        print(f"🎯 Sensitivity Widget Type: {type(sensitivity_widget)}")
        
        if hasattr(sensitivity_widget, 'currentData'):
            sensitivity = sensitivity_widget.currentData()
            print(f"🎯 Sensitivity Data: {sensitivity}")
        else:
            print("❌ Sensitivity Widget has no currentData() method")
        
        # Test Frame Time Scale Widget
        frametime_widget = fps_analyzer_instance.frametime_scale_combo
        print(f"⏱️ Frame Time Widget Type: {type(frametime_widget)}")
        
        if hasattr(frametime_widget, 'currentData'):
            frametime_data = frametime_widget.currentData()
            print(f"⏱️ Frame Time Data: {frametime_data}")
        else:
            print("❌ Frame Time Widget has no currentData() method")
        
        # Test Full Settings Extraction
        print("\n🔧 Testing Full Settings Extraction:")
        settings = fps_analyzer_instance.get_current_settings()
        print(f"✅ Full Settings: {settings}")
        
    except Exception as e:
        print(f"❌ Debug Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("="*50)
    print("🔍 Debug Complete")
    print("="*50 + "\n")

def add_debug_button_to_analyzer(fps_analyzer_instance):
    """Add a debug button to the analyzer for testing"""
    from PyQt6.QtWidgets import QPushButton
    
    debug_button = QPushButton("🔍 Debug Settings")
    debug_button.clicked.connect(lambda: debug_widget_settings(fps_analyzer_instance))
    
    # Add to the playback controls layout
    if hasattr(fps_analyzer_instance, 'ui_manager'):
        # Find playback layout and add debug button
        try:
            # This is a bit hacky, but works for debugging
            debug_button.setParent(fps_analyzer_instance)
            debug_button.move(300, 10)  # Position it somewhere visible
            debug_button.show()
            print("✅ Debug button added - click to test settings extraction")
        except Exception as e:
            print(f"❌ Could not add debug button: {e}")

# Usage Instructions:
"""
Add this to your fps_analyzer_main.py at the end of setup_application():

from debug_helper import add_debug_button_to_analyzer
add_debug_button_to_analyzer(self)

Then click the "🔍 Debug Settings" button to see what's happening!
"""