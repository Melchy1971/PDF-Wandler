# This file initializes the plugins package and may include code to load and register plugins.

from .base_plugin import Plugin

plugins = []

def register_plugin(plugin_class):
    if issubclass(plugin_class, Plugin):
        plugins.append(plugin_class())
    else:
        raise ValueError(f"{plugin_class} is not a valid Plugin subclass.")

def load_plugins():
    # This function can be expanded to dynamically load plugins from a directory or configuration.
    pass

def get_plugins():
    return plugins