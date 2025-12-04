def hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """
    Convert a hex color string to an RGBA string with the specified alpha transparency.
    """
    # Remove the leading #
    hex_color = hex_color.lstrip('#')
    
    # Parse each pair of characters as an RGB component
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    
    return f"rgba({r}, {g}, {b}, {alpha})"