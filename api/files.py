"""
File management: listing and serving output files.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import FileInfo


# Default output directory
MONTAGES_DIR = Path(__file__).parent.parent / "montages"

# Video file extensions
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov"}

# Playlist extensions
PLAYLIST_EXTENSIONS = {".m3u", ".m3u8"}

# All supported extensions
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS | PLAYLIST_EXTENSIONS | {".json", ".txt"}


def list_files(
    directory: Optional[Path] = None,
    extensions: Optional[set] = None,
    sort_by: str = "modified",
    descending: bool = True,
) -> List[FileInfo]:
    """
    List files in the output directory.

    Args:
        directory: Directory to list (default: montages/)
        extensions: Filter by extensions (default: all supported)
        sort_by: Sort field ("name", "modified", "size")
        descending: Sort direction

    Returns:
        List of FileInfo objects
    """
    dir_path = directory or MONTAGES_DIR

    if not dir_path.exists():
        return []

    exts = extensions or SUPPORTED_EXTENSIONS
    files: List[FileInfo] = []

    for path in dir_path.iterdir():
        if not path.is_file():
            continue

        # Skip hidden and temporary files
        if path.name.startswith(".") or path.name.startswith("_"):
            continue

        suffix = path.suffix.lower()
        if suffix not in exts:
            continue

        try:
            stat = path.stat()
            files.append(FileInfo(
                name=path.name,
                path=str(path.absolute()),
                size=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime),
                is_video=suffix in VIDEO_EXTENSIONS,
            ))
        except Exception:
            continue

    # Sort
    if sort_by == "name":
        files.sort(key=lambda f: f.name.lower(), reverse=descending)
    elif sort_by == "size":
        files.sort(key=lambda f: f.size, reverse=descending)
    else:  # modified
        files.sort(key=lambda f: f.modified, reverse=descending)

    return files


def get_file(filename: str, directory: Optional[Path] = None) -> Optional[FileInfo]:
    """Get info for a specific file."""
    dir_path = directory or MONTAGES_DIR
    path = dir_path / filename

    # Security: ensure file is within directory
    try:
        path = path.resolve()
        dir_path = dir_path.resolve()
        if not str(path).startswith(str(dir_path)):
            return None
    except Exception:
        return None

    if not path.exists() or not path.is_file():
        return None

    try:
        stat = path.stat()
        return FileInfo(
            name=path.name,
            path=str(path),
            size=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime),
            is_video=path.suffix.lower() in VIDEO_EXTENSIONS,
        )
    except Exception:
        return None


def delete_file(filename: str, directory: Optional[Path] = None) -> bool:
    """
    Delete a file from the output directory.

    Returns True if file was deleted, False otherwise.
    """
    dir_path = directory or MONTAGES_DIR
    path = dir_path / filename

    # Security: ensure file is within directory
    try:
        path = path.resolve()
        dir_path = dir_path.resolve()
        if not str(path).startswith(str(dir_path)):
            return False
    except Exception:
        return False

    if not path.exists() or not path.is_file():
        return False

    try:
        path.unlink()

        # Also try to delete associated files (e.g., .json, .txt for .mp4)
        base = path.stem
        for related_ext in [".segments.json", ".manifest.json", ".m3u", "-chapters.txt", ".debug.txt"]:
            related = dir_path / f"{base}{related_ext}"
            if related.exists():
                try:
                    related.unlink()
                except Exception:
                    pass

        return True
    except Exception:
        return False


def get_file_path(filename: str, directory: Optional[Path] = None) -> Optional[Path]:
    """
    Get the full path to a file, with security checks.

    Returns None if file doesn't exist or is outside directory.
    """
    dir_path = directory or MONTAGES_DIR
    path = dir_path / filename

    # Security: ensure file is within directory
    try:
        path = path.resolve()
        dir_path = dir_path.resolve()
        if not str(path).startswith(str(dir_path)):
            return None
    except Exception:
        return None

    if not path.exists() or not path.is_file():
        return None

    return path


def get_mime_type(filename: str) -> str:
    """Get MIME type for a file based on extension."""
    suffix = Path(filename).suffix.lower()

    mime_types = {
        ".mp4": "video/mp4",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".m3u": "audio/mpegurl",
        ".m3u8": "application/vnd.apple.mpegurl",
        ".json": "application/json",
        ".txt": "text/plain",
    }

    return mime_types.get(suffix, "application/octet-stream")


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
