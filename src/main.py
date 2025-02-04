# FILE: /my-python-project/my-python-project/src/main.py
import logging
import os
from plugins.base_plugin import Plugin

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
    "MAIN_TARGET_DIR": "",  # Hinzufügen
    "LOG_LEVEL": "DEBUG"  # Hinzufügen
}

config = default_config.copy()

def set_log_level(level):
    """
    Setzt das Log-Level.

    Args:
        level (str): Das Log-Level (z.B. DEBUG, INFO, WARNING, ERROR).
    """
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {level}')
    logging.getLogger().setLevel(numeric_level)
    logging.info(f"Log-Level gesetzt auf: {level}")

def load_config():
    """
    Funktion zum Laden der Konfiguration.
    """
    # Hier könnte der Code zum Laden der Konfiguration stehen
    pass

def register_plugins(plugin_directory):
    """
    Registriert alle Plugins im angegebenen Verzeichnis.

    Args:
        plugin_directory (str): Das Verzeichnis, in dem die Plugins gespeichert sind.
    """
    plugins = []
    for filename in os.listdir(plugin_directory):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            module = __import__(f'plugins.{module_name}', fromlist=[''])
            for attr in dir(module):
                plugin_class = getattr(module, attr)
                if isinstance(plugin_class, type) and issubclass(plugin_class, Plugin):
                    plugins.append(plugin_class())
    return plugins

def main():
    set_log_level(config["LOG_LEVEL"])
    plugins = register_plugins('plugins')
    # Hier könnte die Hauptverarbeitung der Dateien stattfinden
    pass

if __name__ == "__main__":
    main()