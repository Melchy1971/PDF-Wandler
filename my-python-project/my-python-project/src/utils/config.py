# FILE: /my-python-project/my-python-project/src/utils/config.py

def load_config(file_path):
    """
    Lädt die Konfiguration aus einer Datei.

    Args:
        file_path (str): Der Pfad zur Konfigurationsdatei.

    Returns:
        dict: Die geladenen Konfigurationseinstellungen.
    """
    import json
    with open(file_path, 'r') as config_file:
        config = json.load(config_file)
    return config

def save_config(file_path, config):
    """
    Speichert die Konfiguration in einer Datei.

    Args:
        file_path (str): Der Pfad zur Konfigurationsdatei.
        config (dict): Die Konfigurationseinstellungen, die gespeichert werden sollen.
    """
    import json
    with open(file_path, 'w') as config_file:
        json.dump(config, config_file, indent=4)

def update_config(config, key, value):
    """
    Aktualisiert einen bestimmten Schlüssel in der Konfiguration.

    Args:
        config (dict): Die aktuelle Konfiguration.
        key (str): Der Schlüssel, der aktualisiert werden soll.
        value: Der neue Wert für den Schlüssel.
    """
    config[key] = value
    return config