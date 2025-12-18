"""MIN Format Decompressor

Usage: python decompress_min.py
Select .min files to decompress back to original CSV/TXT format.

This script decompresses files created by dedupe_files.py
and restores them to their original format.
Supports both version 1 (gzip) and version 2 (LZMA + enhanced compression).
"""
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import csv
import gzip
import lzma
import struct

def read_varint(f):
    """Read variable-length integer."""
    result = 0
    shift = 0
    while True:
        byte = f.read(1)[0]
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
        if shift >= 35:
            raise ValueError("Varint too long")
    return result

def _read_cell(f, dictionary):
    """Read a single cell with all encoding types."""
    flag = f.read(1)[0]
    
    if flag == 0x00:
        # Raw string
        str_len = read_varint(f)
        str_bytes = f.read(str_len)
        return str_bytes.decode('utf-8')
    elif flag == 0x01:
        # Empty cell
        return ''
    elif flag == 0xFF:
        # Dictionary reference
        dict_idx = read_varint(f)
        return dictionary[dict_idx]
    elif flag == 0xF8:
        # int8
        return str(struct.unpack('>b', f.read(1))[0])
    elif flag == 0xF9:
        # int16
        return str(struct.unpack('>h', f.read(2))[0])
    elif flag == 0xFA:
        # int32
        return str(struct.unpack('>i', f.read(4))[0])
    elif flag == 0xFB:
        # int64
        return str(struct.unpack('>q', f.read(8))[0])
    elif flag == 0xFC:
        # float64
        val = struct.unpack('>d', f.read(8))[0]
        # Format to avoid unnecessary precision
        if val == int(val):
            return str(int(val))
        return str(val)
    else:
        raise ValueError(f"Unknown cell encoding flag: 0x{flag:02X}")

def decompress_min(filepath):
    """Decompress MIN format file back to original format."""
    try:
        # Try LZMA first (version 2), then gzip (version 1)
        try:
            with open(filepath, 'rb') as f:
                compressed_data = f.read()
            data = lzma.decompress(compressed_data)
        except (lzma.LZMAError, ValueError):
            # Try gzip for version 1 files
            with gzip.open(filepath, 'rb') as gz_file:
                data = gz_file.read()
        
        import io
        f = io.BytesIO(data)
        
        # Read magic header
        magic = f.read(6)
        if magic != b'MINFMT':
            raise ValueError("Invalid MIN format file")
        
        # Read version
        version = f.read(1)[0]
        if version not in (1, 2):
            raise ValueError(f"Unsupported MIN format version: {version}")
        
        # Read file type
        file_type = f.read(1)[0]
        is_csv = (file_type == 1)
        
        # Read dictionary
        dict_size = read_varint(f)
        dictionary = {}
        for idx in range(dict_size):
            str_len = read_varint(f)
            s = f.read(str_len).decode('utf-8')
            dictionary[idx] = s
        
        # Read data
        if version >= 2:
            # Version 2: RLE encoded
            item_count = read_varint(f)
            content = []
            
            for _ in range(item_count):
                marker = f.read(1)[0]
                
                if marker == 0xFE:
                    # RLE repeat
                    count = read_varint(f)
                    if is_csv:
                        col_count = read_varint(f)
                        row = []
                        for _ in range(col_count):
                            row.append(_read_cell(f, dictionary))
                        # Repeat the row
                        for _ in range(count):
                            content.append(row[:])
                    else:
                        line = _read_cell(f, dictionary)
                        # Repeat the line
                        for _ in range(count):
                            content.append(line)
                elif marker == 0xFD:
                    # Normal data
                    if is_csv:
                        col_count = read_varint(f)
                        row = []
                        for _ in range(col_count):
                            row.append(_read_cell(f, dictionary))
                        content.append(row)
                    else:
                        line = _read_cell(f, dictionary)
                        content.append(line)
                else:
                    raise ValueError(f"Unknown data marker: 0x{marker:02X}")
        else:
            # Version 1: No RLE
            row_count = read_varint(f)
            content = []
            
            for _ in range(row_count):
                if is_csv:
                    col_count = read_varint(f)
                    row = []
                    for _ in range(col_count):
                        flag = f.read(1)[0]
                        if flag == 0xFF:
                            dict_idx = read_varint(f)
                            row.append(dictionary[dict_idx])
                        else:
                            str_len = read_varint(f)
                            str_bytes = f.read(str_len)
                            row.append(str_bytes.decode('utf-8'))
                    content.append(row)
                else:
                    flag = f.read(1)[0]
                    if flag == 0xFF:
                        dict_idx = read_varint(f)
                        content.append(dictionary[dict_idx])
                    else:
                        str_len = read_varint(f)
                        str_bytes = f.read(str_len)
                        content.append(str_bytes.decode('utf-8'))
        
        return content, is_csv
    except Exception as e:
        raise Exception(f"Failed to decompress: {str(e)}")

def save_decompressed(filepath, content, is_csv=False):
    """Save decompressed content to file."""
    base = os.path.splitext(filepath)[0]
    # Remove _deduped if present
    if base.endswith('_deduped'):
        base = base[:-8]
    
    if is_csv:
        output_path = f"{base}_decompressed.csv"
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_MINIMAL, lineterminator='\n')
            writer.writerows(content)
    else:
        output_path = f"{base}_decompressed.txt"
        with open(output_path, 'w', encoding='utf-8') as f:
            for line in content:
                f.write(line)
                if not line.endswith('\n'):
                    f.write('\n')
    
    return output_path

def process_file(filepath):
    """Process a single .min file."""
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return False, None
    
    try:
        content, is_csv = decompress_min(filepath)
        output_path = save_decompressed(filepath, content, is_csv)
        return True, output_path
    except Exception as e:
        messagebox.showerror("Error", f"Failed to decompress '{os.path.basename(filepath)}':\n{str(e)}")
        return False, None

def main():
    """Main function."""
    root = tk.Tk()
    root.withdraw()
    
    filepaths = filedialog.askopenfilenames(
        title="Select .min files to decompress",
        filetypes=[
            ("MIN files", "*.min"),
            ("All files", "*.*")
        ]
    )
    
    if not filepaths:
        root.destroy()
        return
    
    results = []
    for filepath in filepaths:
        success, output_path = process_file(filepath)
        if success:
            results.append((os.path.basename(filepath), output_path))
    
    root.destroy()
    
    if results:
        summary_lines = []
        for filename, output_path in results:
            summary_lines.append(f"• {filename}")
            summary_lines.append(f"  Decompressed to: {os.path.basename(output_path)}")
        
        messagebox.showinfo("Decompression Complete", "\n".join(summary_lines))
    else:
        messagebox.showwarning("No files processed", "No files were successfully decompressed.")

if __name__ == "__main__":
    main()
