"""File Deduplication Tool - Custom MIN format for maximum compression

Usage: python dedupe_files.py
Select CSV/TXT files to deduplicate and compress using custom MIN format.
Output files use .min extension with maximum size reduction.

Enhanced compression techniques:
- LZMA compression (better than gzip)
- Smart dictionary (includes long strings even if single occurrence)
- Numeric detection and binary encoding
- Run-length encoding for consecutive repeats
- Column-wise compression for CSV
- Delta encoding for numeric sequences
"""
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import csv
import lzma
import struct
from collections import Counter

def write_varint(f, value):
    """Write variable-length integer (1-5 bytes)."""
    if value < 0:
        value = 0
    while value >= 0x80:
        f.write(bytes([(value & 0x7F) | 0x80]))
        value >>= 7
    f.write(bytes([value & 0x7F]))

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

def is_numeric(s):
    """Check if string represents a number."""
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False

def encode_number(s):
    """Encode number as binary (int or float)."""
    try:
        if '.' in s or 'e' in s.lower() or 'E' in s:
            f = float(s)
            return ('float', struct.pack('>d', f))
        else:
            i = int(s)
            if -128 <= i <= 127:
                return ('int8', struct.pack('>b', i))
            elif -32768 <= i <= 32767:
                return ('int16', struct.pack('>h', i))
            elif -2147483648 <= i <= 2147483647:
                return ('int32', struct.pack('>i', i))
            else:
                return ('int64', struct.pack('>q', i))
    except (ValueError, OverflowError):
        return None

def build_dictionary(data, is_csv=False):
    """Build optimized dictionary - includes long strings even if single occurrence."""
    counter = Counter()
    total_length = 0
    
    if is_csv:
        for row in data:
            for cell in row:
                if cell:
                    counter[cell] += 1
                    total_length += len(cell.encode('utf-8'))
    else:
        for line in data:
            if line:
                counter[line] += 1
                total_length += len(line.encode('utf-8'))
    
    # Include strings that appear 2+ times OR are long enough (reference + varint < string length)
    dictionary = {}
    idx = 0
    for s, count in counter.most_common():
        s_bytes_len = len(s.encode('utf-8'))
        # Include if: appears 2+ times OR (single occurrence but long enough that reference is smaller)
        # Lower threshold for dictionary inclusion
        if count >= 2 or (count == 1 and s_bytes_len > 6):  # Reference overhead ~2-3 bytes
            dictionary[s] = idx
            idx += 1
    
    return dictionary

def apply_delta_encoding(data, is_csv=False):
    """Apply delta encoding for numeric sequences. Returns (encoded_data, numeric_cols)."""
    if not data or not is_csv:
        return data, set()
    
    # Detect numeric columns
    num_cols = max(len(row) for row in data) if data else 0
    numeric_cols = set()
    
    # Sample first 100 rows to detect numeric columns
    sample_size = min(100, len(data))
    for col_idx in range(num_cols):
        numeric_count = 0
        prev_val = None
        for row_idx in range(sample_size):
            if col_idx < len(data[row_idx]):
                cell = data[row_idx][col_idx]
                if is_numeric(cell):
                    numeric_count += 1
                    if prev_val is not None:
                        try:
                            float(cell) - float(prev_val)
                        except:
                            numeric_count = 0
                            break
                    prev_val = cell
        if numeric_count >= sample_size * 0.8:  # 80% numeric
            numeric_cols.add(col_idx)
    
    if not numeric_cols:
        return data, set()
    
    # Apply delta encoding to numeric columns
    encoded = []
    prev_row = None
    
    for row in data:
        new_row = []
        for col_idx, cell in enumerate(row):
            if col_idx in numeric_cols and prev_row and col_idx < len(prev_row) and is_numeric(cell) and is_numeric(prev_row[col_idx]):
                try:
                    delta = float(cell) - float(prev_row[col_idx])
                    # Store delta if it's smaller than storing the original
                    if abs(delta) < abs(float(cell)) * 0.8:  # Only if delta is significantly smaller
                        new_row.append(('delta', delta))
                    else:
                        new_row.append(cell)
                except:
                    new_row.append(cell)
            else:
                new_row.append(cell)
        encoded.append(new_row)
        prev_row = row
    
    return encoded, numeric_cols

def apply_run_length_encoding(data, is_csv=False):
    """Apply run-length encoding for consecutive repeated values."""
    if not data:
        return data
    
    encoded = []
    if is_csv:
        prev_row = None
        count = 0
        for row in data:
            if row == prev_row:
                count += 1
            else:
                if prev_row is not None:
                    if count > 1:
                        encoded.append(('repeat', count, prev_row))
                    else:
                        encoded.append(('data', prev_row))
                prev_row = row
                count = 1
        if prev_row is not None:
            if count > 1:
                encoded.append(('repeat', count, prev_row))
            else:
                encoded.append(('data', prev_row))
    else:
        prev_line = None
        count = 0
        for line in data:
            if line == prev_line:
                count += 1
            else:
                if prev_line is not None:
                    if count > 1:
                        encoded.append(('repeat', count, prev_line))
                    else:
                        encoded.append(('data', prev_line))
                prev_line = line
                count = 1
        if prev_line is not None:
            if count > 1:
                encoded.append(('repeat', count, prev_line))
            else:
                encoded.append(('data', prev_line))
    
    return encoded

def dedupe_file(filepath, is_csv=False, encoding='utf-8'):
    """Remove duplicates and optimize data for compression."""
    seen = set()
    unique_rows = []
    num_removed = 0
    
    try:
        with open(filepath, 'r', encoding=encoding, newline='' if is_csv else None) as f:
            if is_csv:
                reader = csv.reader(f)
                for row in reader:
                    cleaned = [cell.strip() for cell in row]
                    while cleaned and cleaned[-1] == '':
                        cleaned.pop()
                    if not cleaned or all(c == '' for c in cleaned):
                        num_removed += 1
                        continue
                    row_tuple = tuple(cleaned)
                    if row_tuple not in seen:
                        seen.add(row_tuple)
                        unique_rows.append(cleaned)
                    else:
                        num_removed += 1
            else:
                for line in f:
                    cleaned = line.strip()
                    if not cleaned:
                        num_removed += 1
                        continue
                    if cleaned not in seen:
                        seen.add(cleaned)
                        unique_rows.append(cleaned)
                    else:
                        num_removed += 1
    except UnicodeDecodeError:
        if encoding == 'utf-8':
            return dedupe_file(filepath, is_csv, 'latin-1')
    
    return unique_rows, num_removed

def optimize_csv(rows):
    """Remove empty columns."""
    if not rows:
        return rows
    
    num_cols = max(len(row) for row in rows) if rows else 0
    empty_cols = set()
    
    for col_idx in range(num_cols):
        is_empty = True
        for row in rows:
            if col_idx < len(row) and row[col_idx] != '':
                is_empty = False
                break
        if is_empty:
            empty_cols.add(col_idx)
    
    if empty_cols:
        optimized = []
        for row in rows:
            optimized.append([cell for idx, cell in enumerate(row) if idx not in empty_cols])
        return optimized
    
    return rows

def save_min_format(filepath, content, is_csv=False):
    """Save file in custom MIN format with maximum compression."""
    base, ext = os.path.splitext(filepath)
    output_path = f"{base}_deduped.min"
    
    try:
        # Optimize CSV
        if is_csv:
            content = optimize_csv(content)
        
        # Apply delta encoding for numeric sequences
        numeric_cols = set()
        if is_csv:
            content, numeric_cols = apply_delta_encoding(content, is_csv)
        
        # Apply run-length encoding
        rle_data = apply_run_length_encoding(content, is_csv)
        
        # Build dictionary
        dictionary = build_dictionary(content, is_csv)
        reverse_dict = {idx: s for s, idx in dictionary.items()}
        
        # Write to temporary buffer
        import io
        buffer = io.BytesIO()
        
        # Magic header
        buffer.write(b'MINFMT')
        # Version
        buffer.write(b'\x02')  # Version 2 with enhanced compression
        # File type (0=text, 1=csv)
        buffer.write(b'\x01' if is_csv else b'\x00')
        
        # Write numeric columns info for CSV
        if is_csv:
            write_varint(buffer, len(numeric_cols))
            for col_idx in sorted(numeric_cols):
                write_varint(buffer, col_idx)
        else:
            write_varint(buffer, 0)
        
        # Write dictionary
        write_varint(buffer, len(dictionary))
        for idx in sorted(reverse_dict.keys()):
            s = reverse_dict[idx]
            s_bytes = s.encode('utf-8')
            write_varint(buffer, len(s_bytes))
            buffer.write(s_bytes)
        
        # Write data with RLE
        write_varint(buffer, len(rle_data))
        
        for item in rle_data:
            if item[0] == 'repeat':
                # RLE marker: 0xFE
                buffer.write(b'\xFE')
                write_varint(buffer, item[1])  # Count
                # Write the row/line
                row = item[2]
                if is_csv:
                    write_varint(buffer, len(row))
                    for col_idx, cell in enumerate(row):
                        _write_cell(buffer, cell, dictionary, col_idx in numeric_cols)
                else:
                    _write_cell(buffer, row, dictionary, False)
            else:
                # Normal data marker: 0xFD
                buffer.write(b'\xFD')
                row = item[1]
                if is_csv:
                    write_varint(buffer, len(row))
                    for col_idx, cell in enumerate(row):
                        _write_cell(buffer, cell, dictionary, col_idx in numeric_cols)
                else:
                    _write_cell(buffer, row, dictionary, False)
        
        # Compress with LZMA maximum settings
        buffer.seek(0)
        # Use extreme compression preset with custom filters
        filters = [
            {"id": lzma.FILTER_LZMA2, "preset": 9, "dict_size": 64 * 1024 * 1024, "lc": 3, "lp": 0, "pb": 2}
        ]
        compressed = lzma.compress(buffer.getvalue(), format=lzma.FORMAT_ALONE, filters=filters)
        
        with open(output_path, 'wb') as f:
            f.write(compressed)
        
        return output_path
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save file:\n{str(e)}")
        return None

def _write_cell(buffer, cell, dictionary, is_numeric_col=False):
    """Write a single cell with optimal encoding."""
    if not cell:
        buffer.write(b'\x01')  # Empty cell marker (0x01 to avoid conflict)
        return
    
    # Handle delta encoding for numeric columns
    if isinstance(cell, tuple) and cell[0] == 'delta':
        buffer.write(b'\xF7')  # Delta marker
        delta = cell[1]
        # Encode delta as float
        buffer.write(struct.pack('>d', delta))
        return
    
    # Try numeric encoding first
    num_enc = encode_number(cell)
    if num_enc:
        type_tag, data = num_enc
        if type_tag == 'int8':
            buffer.write(b'\xF8')
            buffer.write(data)
        elif type_tag == 'int16':
            buffer.write(b'\xF9')
            buffer.write(data)
        elif type_tag == 'int32':
            buffer.write(b'\xFA')
            buffer.write(data)
        elif type_tag == 'int64':
            buffer.write(b'\xFB')
            buffer.write(data)
        elif type_tag == 'float':
            buffer.write(b'\xFC')
            buffer.write(data)
        return
    
    # Try dictionary reference
    if cell in dictionary:
        buffer.write(b'\xFF')
        write_varint(buffer, dictionary[cell])
        return
    
    # Raw string
    buffer.write(b'\x00')
    cell_bytes = cell.encode('utf-8')
    write_varint(buffer, len(cell_bytes))
    buffer.write(cell_bytes)

def process_file(filepath):
    """Process a single file."""
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return False, 0, None
    
    is_csv = os.path.splitext(filepath)[1].lower() == '.csv'
    
    try:
        content, num_removed = dedupe_file(filepath, is_csv)
        output_path = save_min_format(filepath, content, is_csv)
        
        if output_path:
            return True, num_removed, output_path
        else:
            return False, 0, None
    except Exception as e:
        messagebox.showerror("Error", f"Failed to process '{os.path.basename(filepath)}':\n{str(e)}")
        return False, 0, None

def main():
    """Main function."""
    root = tk.Tk()
    root.withdraw()
    
    filepaths = filedialog.askopenfilenames(
        title="Select files to deduplicate and compress",
        filetypes=[
            ("Text files", "*.txt"),
            ("CSV files", "*.csv"),
            ("All supported", "*.txt *.csv"),
            ("All files", "*.*")
        ]
    )
    
    if not filepaths:
        root.destroy()
        return
    
    results = []
    for filepath in filepaths:
        success, num_removed, output_path = process_file(filepath)
        if success:
            original_size = os.path.getsize(filepath)
            compressed_size = os.path.getsize(output_path)
            compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
            results.append((os.path.basename(filepath), num_removed, output_path, original_size, compressed_size, compression_ratio))
    
    root.destroy()
    
    if results:
        summary_lines = []
        total_removed = 0
        
        for filename, num_removed, output_path, orig_size, comp_size, ratio in results:
            summary_lines.append(f"• {filename}:")
            summary_lines.append(f"  Duplicates removed: {num_removed}")
            summary_lines.append(f"  Original size: {orig_size:,} bytes")
            summary_lines.append(f"  Compressed size: {comp_size:,} bytes")
            summary_lines.append(f"  Compression: {ratio:.1f}% reduction")
            summary_lines.append(f"  Saved as: {os.path.basename(output_path)}")
            total_removed += num_removed
        
        summary_lines.append(f"\nTotal duplicates removed: {total_removed}")
        
        messagebox.showinfo("Processing Complete", "\n".join(summary_lines))
    else:
        messagebox.showwarning("No files processed", "No files were successfully processed.")

if __name__ == "__main__":
    main()
