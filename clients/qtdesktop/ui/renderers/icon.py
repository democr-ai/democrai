import qtawesome as qta
import os
import re
from urllib.parse import urlparse
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFontDatabase, QFont
from PySide6.QtWidgets import QLabel, QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt
import json
from ...utils.paths import resolve_resource
from ..theme.tokens import theme_token

# Defer initialization to avoid QApplication warnings
_initialized = False
GLYPH_MAP = {}
ICONS = {}
FAMILIES = []


def normalize_icon_name(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    if raw.startswith("ri-"):
        return f"ric.{raw[3:]}"
    if raw.startswith("ri."):
        return f"ric.{raw[3:]}"
    if not raw.startswith("ric."):
        return f"ric.{raw}"
    return raw


def _ensure_initialized():
    global _initialized, GLYPH_MAP, ICONS, FAMILIES
    if _initialized:
        return

    # Only initialize if a QApplication exists (GUI process)
    if not QApplication.instance():
        return

    # Use resolve_resource to find fonts in both dev and frozen modes
    customfont = resolve_resource("fonts/remixicon-custom.ttf")
    customfontchars = resolve_resource("fonts/remixicon-custom.json")

    try:
        qta.load_font("ric", customfont, customfontchars)
    except Exception as e:
        print(f"Error loading custom font: {e}")

    # Load glyph map
    try:
        if os.path.exists(customfontchars):
            with open(customfontchars, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in data.items():
                    if isinstance(v, str) and v.startswith("0x"):
                        try:
                            GLYPH_MAP[k] = chr(int(v, 16))
                        except ValueError:
                            pass
    except Exception as e:
        print(f"Error loading icon map: {e}")

    ICONS = {}

    try:
        font_id = QFontDatabase.addApplicationFont(customfont)
        FAMILIES = QFontDatabase.applicationFontFamilies(font_id)
    except Exception:
        pass

    _initialized = True


def identify_resource_type(s: str) -> str:
    """
    Identifica il tipo di risorsa passata come stringa.
    Ritorna: 'url', 'svg', 'path', o 'icon_name'.
    """
    s_trim = s.strip()

    # SVG check
    if s_trim.startswith("<svg") or "http://www.w3.org/2000/svg" in s_trim:
        return "svg"

    # URL check
    parsed = urlparse(s_trim)
    if parsed.scheme in ("http", "https"):
        if parsed.path.lower().endswith(".png"):
            return "png_url"
        return "url"

    # Path check
    if os.path.exists(s_trim):
        if s_trim.lower().endswith(".png"):
            return "png_path"
        if s_trim.lower().endswith(".svg"):
            return "svg_path"
        return "path"

    if s_trim.startswith("\\"):
        return "icon_font"

    return "icon_name"


from functools import lru_cache


@lru_cache(maxsize=512)
def _get_icon_cached(name, color, size):
    _ensure_initialized()
    res_type = identify_resource_type(name)

    if res_type == "icon_name":
        # Check ICONS cache first
        try:
            if isinstance(color, str):
                svg_data = qta.icon(name, options=[{"color": color}])
                if isinstance(svg_data, QIcon):
                    return svg_data
                if not svg_data:
                    return QIcon()
            else:
                i = 0
                ico = QIcon()
                styles = [QIcon.Normal, QIcon.Active, QIcon.Selected]
                for c in color:
                    pixmap = qta.icon(name, options=[{"color": c}]).pixmap(size)
                    ico.addPixmap(pixmap, styles[i], QIcon.Off)
                    i += 1
                return ico
        except Exception:
            return QIcon()
    elif res_type == "svg":
        svg_data = name
    elif res_type == "svg_path":
        try:
            with open(name, "r") as f:
                svg_data = f.read()
        except Exception:
            return QIcon(name)  # Fallback to direct QIcon if read fails
    elif res_type in ("path", "png_path"):
        return QIcon(name)
    elif res_type in ("url", "png_url"):
        return QIcon()
    else:
        return QIcon()

    # Simple color injection for SVG strings
    if isinstance(svg_data, str):
        svg_data = svg_data.replace('stroke="currentColor"', f'stroke="{color}"')
        svg_data = svg_data.replace('fill="currentColor"', f'fill="{color}"')

        try:
            renderer = QSvgRenderer(svg_data.encode("utf-8"))
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            try:
                renderer.render(painter)
            finally:
                if painter.isActive():
                    painter.end()
            return QIcon(pixmap)
        except Exception:
            pass

    return QIcon()


def get_icon(name, color=None, size=18):
    resolved_color = color if color is not None else theme_token("icon.default")
    return _get_icon_cached(name, resolved_color, size)


def get_icon_gliph(name):  # Slate-400
    _ensure_initialized()
    # Lookup glyph
    glyph = GLYPH_MAP.get(name, "?")
    if glyph == "?" and name.startswith("ric."):
        # Try without prefix if consistent naming isn't used
        short_name = name.replace("ric.", "")
        glyph = GLYPH_MAP.get(short_name, "?")

    icon_label = QLabel(glyph)
    if FAMILIES:
        icon_font = QFont(FAMILIES[0])
        icon_font.setPointSize(16)
        icon_label.setFont(icon_font)
    return icon_label
