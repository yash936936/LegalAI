"""
icons.py
────────
Centralised SVG icon library for Legal AI.

Every glyph in the product — nav marks, buttons, avatars, status badges —
is sourced from here. No emoji are used anywhere in the application;
this module is the single substitute for all of them.

Two access patterns are provided:

  icon(name, size=18, color="currentColor")
      Returns an inline <svg> string. Use inside any st.markdown(...,
      unsafe_allow_html=True) block. Inherits `color` via currentColor,
      so it can be themed with surrounding CSS.

  avatar_svg(name, bg, fg) / favicon_svg(bg, fg) + write_asset(...)
      Build a circular badge or favicon as raw SVG markup with colors
      baked in, then write it to disk. Use the resulting file path as
      the `avatar=` argument to st.chat_message(), or as `page_icon=`
      in st.set_page_config() — local file paths are the most reliably
      supported input for both across Streamlit versions.
"""

# Raw path data for each icon, on a 24x24 viewBox, stroke-based (Lucide-style).
_PATHS: dict[str, str] = {
    "scale": (
        '<path d="M12 3v18"/><path d="M5 7h14"/>'
        '<path d="M5 7l-3 7a4 4 0 0 0 8 0z"/>'
        '<path d="M19 7l-3 7a4 4 0 0 0 8 0z"/>'
        '<path d="M8 21h8"/>'
    ),
    "document": (
        '<path d="M7 3h7l4 4v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/>'
        '<path d="M14 3v4h4"/><path d="M9 12h6"/><path d="M9 16h6"/><path d="M9 8h2"/>'
    ),
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "trash": (
        '<path d="M4 7h16"/><path d="M9 7V4h6v3"/>'
        '<path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/>'
        '<path d="M10 11v6"/><path d="M14 11v6"/>'
    ),
    "download": '<path d="M12 3v12"/><path d="M7 11l5 5 5-5"/><path d="M5 21h14"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    "flag": '<path d="M5 21V4"/><path d="M5 4h13l-3 4 3 4H5"/>',
    "clipboard": (
        '<path d="M9 4h6a1 1 0 0 1 1 1v1H8V5a1 1 0 0 1 1-1z"/>'
        '<path d="M7 6h10v14a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V6z"/>'
        '<path d="M10 12h4"/><path d="M10 16h4"/>'
    ),
    "alert": (
        '<path d="M12 3l10 18H2z"/><path d="M12 10v4"/><path d="M12 17h.01"/>'
    ),
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/>',
    "bolt": '<path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z"/>',
    "user": (
        '<circle cx="12" cy="8" r="4"/>'
        '<path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>'
    ),
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v3"/><path d="M12 19v3"/><path d="M4.2 4.2l2.1 2.1"/>'
        '<path d="M17.7 17.7l2.1 2.1"/><path d="M2 12h3"/><path d="M19 12h3"/>'
        '<path d="M4.2 19.8l2.1-2.1"/><path d="M17.7 6.3l2.1-2.1"/>'
    ),
    "moon": '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "chevron-right": '<path d="M9 6l6 6-6 6"/>',
    "send": '<path d="M3 11l18-8-8 18-2-8-8-2z"/>',
    "shield": (
        '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>'
        '<path d="M9 12l2 2 4-4"/>'
    ),
}


def icon(name: str, size: int = 18, color: str = "currentColor", stroke_width: float = 1.8) -> str:
    """Return an inline <svg> tag string for the named icon."""
    path = _PATHS.get(name, _PATHS["alert"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round" class="lai-icon">{path}</svg>'
    )


def avatar_svg(name: str, bg: str, fg: str = "#ffffff", size: int = 64, glyph: int = 30) -> str:
    """Build a circular badge (background `bg`, icon `fg`) containing the
    requested glyph and return it as raw SVG markup."""
    offset = (size - glyph) / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">'
        f'<circle cx="{size/2}" cy="{size/2}" r="{size/2}" fill="{bg}"/>'
        f'<g transform="translate({offset},{offset}) scale({glyph/24})">'
        f'<path d="{_paths_only(name)}" fill="none" stroke="{fg}" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        "</g></svg>"
    )


def _paths_only(name: str) -> str:
    """Flatten the icon's path data into a single `d` attribute value."""
    import re

    raw = _PATHS.get(name, _PATHS["alert"])
    return " ".join(re.findall(r'd="([^"]+)"', raw))


def favicon_svg(bg: str = "#0064e0", fg: str = "#ffffff") -> str:
    """Square (rounded) favicon as raw SVG markup."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        f'<rect width="64" height="64" rx="14" fill="{bg}"/>'
        f'<g transform="translate(14,14) scale(1.5)">'
        f'<path d="{_paths_only("scale")}" fill="none" stroke="{fg}" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        "</g></svg>"
    )


def write_asset(svg_markup: str, path: str) -> str:
    """Write SVG markup to disk and return the path, creating parent dirs
    as needed. Used so Streamlit can reference icons as local image files
    (avatar=, page_icon=) — the most reliably-supported input type for
    those parameters across Streamlit versions."""
    import os

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg_markup)
    return path