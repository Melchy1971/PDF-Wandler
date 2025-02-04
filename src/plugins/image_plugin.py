from .base_plugin import Plugin

class ImagePlugin(Plugin):
    def process_file(self, filepath):
        # Image-specific processing
        print(f"Processing image file: {filepath}")
        # Add your image processing logic here