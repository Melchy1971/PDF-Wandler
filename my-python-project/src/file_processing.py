# FILE: /my-python-project/my-python-project/src/file_processing.py

import os
import shutil
import logging

def process_files(source_dir, target_dir, allowed_extensions):
    """
    Process files in the source directory and move them to the target directory.

    Args:
        source_dir (str): The directory to scan for files.
        target_dir (str): The directory to move processed files to.
        allowed_extensions (list): List of allowed file extensions.
    """
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    for filename in os.listdir(source_dir):
        if any(filename.endswith(ext) for ext in allowed_extensions):
            source_path = os.path.join(source_dir, filename)
            target_path = os.path.join(target_dir, filename)
            shutil.move(source_path, target_path)
            logging.info(f"Moved file: {filename} to {target_dir}")

def organize_files(target_dir):
    """
    Organize files in the target directory based on their extensions.

    Args:
        target_dir (str): The directory containing files to organize.
    """
    for filename in os.listdir(target_dir):
        ext = filename.split('.')[-1]
        ext_dir = os.path.join(target_dir, ext)

        if not os.path.exists(ext_dir):
            os.makedirs(ext_dir)

        shutil.move(os.path.join(target_dir, filename), os.path.join(ext_dir, filename))
        logging.info(f"Organized file: {filename} into {ext_dir}")

def backup_files(source_dir, backup_dir):
    """
    Backup files from the source directory to the backup directory.

    Args:
        source_dir (str): The directory to backup files from.
        backup_dir (str): The directory to store backup files.
    """
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    for filename in os.listdir(source_dir):
        source_path = os.path.join(source_dir, filename)
        backup_path = os.path.join(backup_dir, filename)
        shutil.copy2(source_path, backup_path)
        logging.info(f"Backed up file: {filename} to {backup_dir}")