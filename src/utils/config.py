import logging

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
    # Add your configuration loading logic here