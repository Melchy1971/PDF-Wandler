class Plugin:
    def process_file(self, file_path):
        """
        Process the given file.

        Args:
            file_path (str): The path to the file to be processed.

        Raises:
            NotImplementedError: If the method is not implemented by a subclass.
        """
        raise NotImplementedError("Subclasses must implement this method.")