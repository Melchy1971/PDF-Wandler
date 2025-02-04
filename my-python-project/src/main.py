# FILE: /my-python-project/my-python-project/src/main.py

import logging
from text_extraction import extract_text_from_pdf, extract_text_from_image
from date_detection import detect_dates
from file_processing import process_files, organize_files, backup_files
from gui import create_gui

# Berichtsvariablen
processed_files = []
errors = []
processing_start_time = None

# Standardkonfiguration
default_config = {
    "DEFAULT_SOURCE_DIR": "",
    "BACKUP_DIR": "backup",
    "ALLOWED_EXTENSIONS": ["pdf", "png", "jpg", "jpeg"],
    "BATCH_SIZE": 10,
    "DATE_FORMATS": ["%Y.%m.%d", "%Y-%m-%d", "%d.%m.%Y"],
    "MAIN_TARGET_DIR": "",
    "LOG_LEVEL": "DEBUG"
}

config = default_config.copy()

def set_log_level(level):
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {level}')
    logging.getLogger().setLevel(numeric_level)
    logging.info(f"Log-Level gesetzt auf: {level}")

def load_config():
    # Funktion zum Laden der Konfiguration
    pass

def main():
    set_log_level(config["LOG_LEVEL"])
    create_gui()

if __name__ == "__main__":
    main()