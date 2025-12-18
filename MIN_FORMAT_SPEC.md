# MIN Format Specification

## Overview
MIN (Minimum) is a custom binary file format designed for maximum compression of CSV and text files. It combines dictionary compression, variable-length integer encoding, and gzip compression to achieve minimal file sizes.

## File Structure

### Header (8 bytes)
- **Magic**: `MINFMT` (6 bytes) - Identifies MIN format files
- **Version**: 1 byte - Format version (currently 1)
- **File Type**: 1 byte
  - `0x00` = Text file (one line per entry)
  - `0x01` = CSV file (rows with multiple columns)

### Dictionary Section
- **Dictionary Size**: Variable-length integer - Number of dictionary entries
- **Dictionary Entries**: For each entry:
  - String length: Variable-length integer
  - String data: UTF-8 encoded bytes

### Data Section
- **Row Count**: Variable-length integer - Number of rows/lines
- **Rows**: For each row:
  - **CSV format**:
    - Column count: Variable-length integer
    - For each column:
      - Flag byte: `0xFF` = dictionary reference, `0x00` = raw string
      - If dictionary reference: Dictionary index (variable-length integer)
      - If raw string: String length (variable-length integer) + UTF-8 bytes
  - **Text format**:
    - Flag byte: `0xFF` = dictionary reference, `0x00` = raw string
    - If dictionary reference: Dictionary index (variable-length integer)
    - If raw string: String length (variable-length integer) + UTF-8 bytes

### Compression
The entire file structure (after header) is compressed using gzip with compression level 9.

## Variable-Length Integer Encoding

Integers are encoded using a variable-length format (varint):
- Each byte contains 7 bits of data and 1 continuation bit
- If MSB is set (0x80), more bytes follow
- Maximum value: 2^35 - 1 (5 bytes)

Example:
- `0x00` = 0
- `0x7F` = 127
- `0x80 0x01` = 128
- `0xFF 0xFF 0xFF 0xFF 0x0F` = 2^35 - 1

## Dictionary Reference Encoding

Dictionary references use a flag byte before each value:
- `0xFF`: Dictionary reference (followed by dictionary index as varint)
- `0x00`: Raw string (followed by string length as varint, then UTF-8 bytes)

## Dictionary Building

The dictionary contains strings that appear at least 2 times in the data. This provides compression for repeated values like:
- Common column headers
- Repeated cell values
- Frequently used strings

## Compression Techniques

1. **Deduplication**: Removes duplicate rows/lines
2. **Empty Column Removal**: Removes columns that are always empty (CSV only)
3. **Whitespace Stripping**: Removes leading/trailing whitespace
4. **Dictionary Compression**: Replaces repeated strings with short references
5. **Variable-Length Integers**: Uses minimal bytes for small numbers
6. **Gzip Compression**: Applies maximum compression (level 9) to the entire structure

## File Extensions

- Input: `.csv`, `.txt`
- Output: `.min`
- Decompressed: `_decompressed.csv` or `_decompressed.txt`

## Usage

### Compression
```bash
python dedupe_files.py
# Select CSV/TXT files to compress
```

### Decompression
```bash
python decompress_min.py
# Select .min files to decompress
```

## Example

### Input CSV
```csv
Name,Age,City
John,25,NYC
Jane,30,NYC
Bob,25,LA
```

### Processing
1. Deduplicate (no duplicates in this example)
2. Build dictionary: `{"NYC": 0, "25": 1}` (appears 2+ times)
3. Encode rows with dictionary references
4. Compress with gzip

### Output
Binary `.min` file with:
- Dictionary: `["NYC", "25"]`
- Rows encoded with dictionary references where possible
- Gzip compression applied

## Advantages

- **Maximum Compression**: Typically 60-95% size reduction
- **Preserves Data**: Lossless compression
- **Efficient**: Fast compression and decompression
- **Optimized**: Multiple compression techniques combined

## Limitations

- Dictionary only includes strings appearing 2+ times
- Empty rows are removed
- Empty columns are removed (CSV only)
- Whitespace is stripped

## Compatibility

- Python 3.x required
- Standard library only (no external dependencies)
- Cross-platform (Windows, Linux, macOS)

