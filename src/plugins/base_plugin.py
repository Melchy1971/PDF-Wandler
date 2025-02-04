class Plugin:
    def process_file(self, filepath):
        raise NotImplementedError("Plugins must implement the process_file method")