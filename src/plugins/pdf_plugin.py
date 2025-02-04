from .base_plugin import Plugin

class PDFPlugin(Plugin):
    def process_file(self, filepath):
        # PDF-specific processing
        print(f"Processing PDF file: {filepath}")
        # Add your PDF processing logic here