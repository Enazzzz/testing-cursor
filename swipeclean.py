"""
SwipeClean — simple Tkinter app to swipe through files in Downloads.

Features:
- Default folder: user's Downloads directory
- Loads all files (not subfolders) into a queue
- Displays filename, size, last modified date
- If image, shows a preview thumbnail (Pillow recommended)
- Keyboard controls:
    Left  : delete (send to recycle bin if send2trash available)
    Right : keep
    Down  : skip (no action)
    Up    : open with OS default program
- After action, moves to next file and updates progress
- Handles missing files gracefully
"""
import os
import sys
import time
import subprocess
import platform
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

# Optional dependencies
try:
    from send2trash import send2trash
except Exception:
    send2trash = None

try:
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None

DOWNLOADS = Path.home() / "Downloads"

def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0:
            return f"{n:3.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"

def open_with_default(path):
    if platform.system() == "Windows":
        os.startfile(str(path))
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])

class SwipeCleanApp:
    def __init__(self, root, folder=DOWNLOADS):
        self.root = root
        self.root.title("SwipeClean")
        self.folder = Path(folder).expanduser()
        self.files = self._load_files()
        self.idx = 0
        self.img_ref = None

        self._build_ui()
        self.root.bind("<Left>", lambda e: self.delete_current())
        self.root.bind("<Right>", lambda e: self.keep_current())
        self.root.bind("<Down>", lambda e: self.skip_current())
        self.root.bind("<Up>", lambda e: self.open_current())

        if not self.files:
            messagebox.showinfo("No files", f"No files found in {self.folder}")
        else:
            self.show_current()

    def _load_files(self):
        if not self.folder.exists() or not self.folder.is_dir():
            return []
        files = [p for p in sorted(self.folder.iterdir()) if p.is_file()]
        return files

    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=8)
        frm.pack(fill="both", expand=True)

        # Top: filename and info
        self.lbl_name = ttk.Label(frm, text="", font=("TkDefaultFont", 12, "bold"), wraplength=600)
        self.lbl_name.pack(anchor="w")

        self.lbl_info = ttk.Label(frm, text="", foreground="gray")
        self.lbl_info.pack(anchor="w", pady=(0,8))

        # Middle: image preview or placeholder
        self.canvas = tk.Canvas(frm, width=480, height=320, bg="#222", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Bottom: progress and instructions
        bottom = ttk.Frame(frm)
        bottom.pack(fill="x", pady=(8,0))
        self.lbl_progress = ttk.Label(bottom, text="0 / 0 files")
        self.lbl_progress.pack(side="left")

        instr = "← delete    → keep    ↓ skip    ↑ open"
        self.lbl_instr = ttk.Label(bottom, text=instr)
        self.lbl_instr.pack(side="right")

    def show_current(self):
        # Skip missing files until we find an existing one or reach end
        while self.idx < len(self.files) and not self.files[self.idx].exists():
            # remove missing file from queue and continue
            self.idx += 1

        if self.idx >= len(self.files):
            messagebox.showinfo("Done", "No more files.")
            self.root.quit()
            return

        p = self.files[self.idx]
        name = p.name
        try:
            size = human_size(p.stat().st_size)
            mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))
        except Exception:
            size = "N/A"
            mtime = "N/A"

        self.lbl_name.config(text=name)
        self.lbl_info.config(text=f"{size}    Modified: {mtime}")
        self.lbl_progress.config(text=f"{self.idx+1} / {len(self.files)} files")

        # Preview image if possible
        self.canvas.delete("all")
        self.img_ref = None
        if Image and self._is_image(p):
            try:
                img = Image.open(p)
                img.thumbnail((800, 600))
                # fit into canvas
                cw = self.canvas.winfo_width() or 480
                ch = self.canvas.winfo_height() or 320
                iw, ih = img.size
                # center
                x = (cw - iw)//2
                y = (ch - ih)//2
                tkimg = ImageTk.PhotoImage(img)
                self.img_ref = tkimg
                self.canvas.create_image(cw//2, ch//2, image=tkimg, anchor="center")
            except Exception:
                self._draw_placeholder(p)
        else:
            self._draw_placeholder(p)

    def _draw_placeholder(self, p):
        # Show file type placeholder text
        cw = self.canvas.winfo_width() or 480
        ch = self.canvas.winfo_height() or 320
        self.canvas.create_text(cw//2, ch//2, text=p.suffix or "FILE", fill="white", font=("TkDefaultFont", 36, "bold"))

    def _is_image(self, p: Path):
        ext = p.suffix.lower()
        return ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp")

    def _advance(self):
        self.idx += 1
        if self.idx >= len(self.files):
            messagebox.showinfo("Done", "No more files.")
            self.root.quit()
        else:
            self.show_current()

    def delete_current(self):
        if self.idx >= len(self.files):
            return
        p = self.files[self.idx]
        if not p.exists():
            self._advance()
            return
        try:
            if send2trash:
                send2trash(str(p))
            else:
                p.unlink()
        except Exception as e:
            messagebox.showerror("Delete failed", f"Could not delete {p.name}:\n{e}")
        finally:
            self._advance()

    def keep_current(self):
        # do nothing, just advance
        self._advance()

    def skip_current(self):
        # skip without any action
        self._advance()

    def open_current(self):
        if self.idx >= len(self.files):
            return
        p = self.files[self.idx]
        if not p.exists():
            self._advance()
            return
        try:
            open_with_default(p)
        except Exception as e:
            messagebox.showerror("Open failed", f"Could not open {p.name}:\n{e}")
        finally:
            # after opening, still move to next per spec
            self._advance()

def main():
    root = tk.Tk()
    # make window reasonably sized
    root.geometry("800x600")
    app = SwipeCleanApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
