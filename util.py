import os
from typing import List


def normalize_filename(file: str) -> str:
    """
    Gets the lowercase name of a file without extension.

    Args:
        file: Filename to normalize.

    Returns:
        Normalized filename.
    """
    file = os.path.basename(file)
    file = os.path.splitext(file)[0]
    return file.lower()


def get_file_by_name(files: List[str], filename: str):
    """
    Gets a file by name, insensitive of case or file extension.

    Args:
        files: List of files.
        filename: Filename to look for.

    Returns:
        An element of ``files`` if found, else ``None``.
    """
    norm_files = [normalize_filename(f) for f in files]
    filename = normalize_filename(filename)

    try:
        index = norm_files.index(filename)
    except ValueError:
        return None
    else:
        return files[index]
