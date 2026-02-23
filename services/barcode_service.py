"""
services.barcode_service - Code 128 barcode generation for labels.

Generates SVG barcode elements for DMTUIDs.
"""

# Code 128 encoding tables
CODE128_START_B = 104
CODE128_STOP = 106

# Code 128B character set (ASCII 32-127 maps to values 0-95)
CODE128_PATTERNS = [
    "11011001100", "11001101100", "11001100110", "10010011000", "10010001100",  # 0-4
    "10001001100", "10011001000", "10011000100", "10001100100", "11001001000",  # 5-9
    "11001000100", "11000100100", "10110011100", "10011011100", "10011001110",  # 10-14
    "10111001100", "10011101100", "10011100110", "11001110010", "11001011100",  # 15-19
    "11001001110", "11011100100", "11001110100", "11101101110", "11101001100",  # 20-24
    "11100101100", "11100100110", "11101100100", "11100110100", "11100110010",  # 25-29
    "11011011000", "11011000110", "11000110110", "10100011000", "10001011000",  # 30-34
    "10001000110", "10110001000", "10001101000", "10001100010", "11010001000",  # 35-39
    "11000101000", "11000100010", "10110111000", "10110001110", "10001101110",  # 40-44
    "10111011000", "10111000110", "10001110110", "11101110110", "11010001110",  # 45-49
    "11000101110", "11011101000", "11011100010", "11011101110", "11101011000",  # 50-54
    "11101000110", "11100010110", "11101101000", "11101100010", "11100011010",  # 55-59
    "11101111010", "11001000010", "11110001010", "10100110000", "10100001100",  # 60-64
    "10010110000", "10010000110", "10000101100", "10000100110", "10110010000",  # 65-69
    "10110000100", "10011010000", "10011000010", "10000110100", "10000110010",  # 70-74
    "11000010010", "11001010000", "11110111010", "11000010100", "10001111010",  # 75-79
    "10100111100", "10010111100", "10010011110", "10111100100", "10011110100",  # 80-84
    "10011110010", "11110100100", "11110010100", "11110010010", "11011011110",  # 85-89
    "11011110110", "11110110110", "10101111000", "10100011110", "10001011110",  # 90-94
    "10111101000", "10111100010", "11110101000", "11110100010", "10111011110",  # 95-99
    "10111101110", "11101011110", "11110101110", "11010000100", "11010010000",  # 100-104
    "11010011100", "1100011101011",  # 105 (START C), 106 (STOP)
]


def _encode_code128(text: str) -> str:
    """
    Encode text as Code 128B barcode pattern.
    Returns a string of 1s and 0s representing bars and spaces.
    """
    # Start with Code B
    values = [CODE128_START_B]
    
    # Encode each character
    for char in text:
        code = ord(char) - 32  # ASCII 32 = value 0 in Code 128B
        if 0 <= code <= 95:
            values.append(code)
        else:
            # Replace non-printable with space
            values.append(0)
    
    # Calculate checksum
    checksum = values[0]
    for i, val in enumerate(values[1:], 1):
        checksum += i * val
    checksum = checksum % 103
    values.append(checksum)
    
    # Add stop code
    values.append(CODE128_STOP)
    
    # Convert to pattern
    pattern = ""
    for val in values:
        pattern += CODE128_PATTERNS[val]
    
    return pattern


def generate_barcode_svg(text: str, width: float = 150, height: float = 50, 
                         bar_width: float = 1.0) -> str:
    """
    Generate SVG group element containing Code 128 barcode.
    
    Args:
        text: Text to encode
        width: Target width (barcode will be scaled to fit)
        height: Bar height in SVG units
        bar_width: Minimum bar width multiplier
    
    Returns:
        SVG <g> element string containing the barcode
    """
    pattern = _encode_code128(text)
    
    # Calculate actual width and scale factor
    pattern_width = len(pattern) * bar_width
    scale = width / pattern_width if pattern_width > 0 else 1
    
    bars = []
    x = 0
    in_bar = False
    bar_start = 0
    
    for i, bit in enumerate(pattern):
        if bit == '1' and not in_bar:
            in_bar = True
            bar_start = i
        elif bit == '0' and in_bar:
            in_bar = False
            bar_x = bar_start * bar_width * scale
            bar_w = (i - bar_start) * bar_width * scale
            bars.append(f'<rect x="{bar_x:.2f}" y="0" width="{bar_w:.2f}" height="{height}" fill="black"/>')
    
    # Handle final bar if pattern ends with 1
    if in_bar:
        bar_x = bar_start * bar_width * scale
        bar_w = (len(pattern) - bar_start) * bar_width * scale
        bars.append(f'<rect x="{bar_x:.2f}" y="0" width="{bar_w:.2f}" height="{height}" fill="black"/>')
    
    return f'<g>{"".join(bars)}</g>'


def generate_barcode_svg_centered(text: str, center_x: float, y: float,
                                   width: float = 150, height: float = 50) -> str:
    """
    Generate SVG barcode centered at a given x position.
    
    Args:
        text: Text to encode
        center_x: X coordinate for center of barcode
        y: Y coordinate for top of barcode
        width: Total barcode width
        height: Bar height
    
    Returns:
        SVG <g> element with transform for positioning
    """
    barcode = generate_barcode_svg(text, width, height)
    x = center_x - (width / 2)
    return f'<g transform="translate({x:.2f},{y})">{barcode}</g>'
