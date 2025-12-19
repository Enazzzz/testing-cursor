# SwipeClean

**SwipeClean** is a simple Tkinter app to quickly browse and manage files in your Downloads folder.

## Features
- Default folder: user's Downloads directory
- Loads all files (not subfolders) into a queue
- Displays filename, size, last modified date
- If image, shows a preview thumbnail (requires Pillow)
- Keyboard controls:
  - Left  : delete (send to recycle bin if `send2trash` available)
  - Right : keep
  - Down  : skip (no action)
  - Up    : open with OS default program
- Handles missing files gracefully

## Requirements
- Python 3.9+
- Optional packages: `Pillow` for image preview, `send2trash` for safe deletion

## Installation
1. Install Python 3.9+ from [python.org](https://www.python.org/downloads/)
2. (Optional) Install dependencies:
```bash
pip install Pillow send2trash
