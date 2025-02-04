# gui.py

import tkinter as tk
from tkinter import filedialog, messagebox

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("File Processing Application")
        self.geometry("400x300")
        self.create_widgets()

    def create_widgets(self):
        self.label = tk.Label(self, text="Select a file to process:")
        self.label.pack(pady=10)

        self.select_button = tk.Button(self, text="Select File", command=self.select_file)
        self.select_button.pack(pady=10)

        self.process_button = tk.Button(self, text="Process File", command=self.process_file)
        self.process_button.pack(pady=10)

        self.result_text = tk.Text(self, height=10, width=50)
        self.result_text.pack(pady=10)

    def select_file(self):
        file_path = filedialog.askopenfilename()
        if file_path:
            self.result_text.insert(tk.END, f"Selected file: {file_path}\n")

    def process_file(self):
        # Placeholder for file processing logic
        messagebox.showinfo("Info", "File processing logic not implemented yet.")

if __name__ == "__main__":
    app = Application()
    app.mainloop()