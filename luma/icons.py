"""Vector icons drawn from inline SVG paths, recoloured on demand.

Keeping the icons as tiny SVG strings means no binary assets to ship and crisp
icons at any DPI. render(name, size, colour) returns a QIcon / QPixmap.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 24x24 viewBox path data (Material-ish, rounded). Stroke icons use fill via even-odd.
_PATHS: dict[str, str] = {
    "play": "M8 5.14v13.72c0 .78.86 1.26 1.54.84l10.8-6.86a1 1 0 0 0 0-1.68L9.54 4.3C8.86 3.88 8 4.36 8 5.14z",
    "pause": "M7 5h3.5v14H7zM13.5 5H17v14h-3.5z",
    "stop": "M7 7h10v10H7z",
    "prev": "M7 6h2.2v12H7zM19 6.2v11.6c0 .64-.72 1.02-1.25.66L9.2 13.1a.8.8 0 0 1 0-1.32l8.55-5.36c.53-.36 1.25.02 1.25.66z",
    "next": "M14.8 6h2.2v12h-2.2zM5 6.2v11.6c0 .64.72 1.02 1.25.66l8.55-5.36a.8.8 0 0 0 0-1.32L6.25 5.54C5.72 5.18 5 5.56 5 6.2z",
    "open": "M10 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2z",
    "playlist": "M3 6h12v2H3zM3 11h12v2H3zM3 16h8v2H3zM16 11l6 3.5-6 3.5z",
    "volume_high": "M4 9v6h4l5 5V4L8 9H4zm11.5 3a3.5 3.5 0 0 0-2-3.16v6.32A3.5 3.5 0 0 0 15.5 12zM16 4.2v2.06A6 6 0 0 1 16 17.74v2.06A8 8 0 0 0 16 4.2z",
    "volume_low": "M4 9v6h4l5 5V4L8 9H4zm11.5 3a3.5 3.5 0 0 0-2-3.16v6.32A3.5 3.5 0 0 0 15.5 12z",
    "volume_mute": "M4 9v6h4l5 5V4L8 9H4zm15.07-.07-1.41 1.41L19.25 12l-1.59 1.66 1.41 1.41L20.66 13.4l1.59 1.67 1.41-1.41L22.07 12l1.59-1.66-1.41-1.41L20.66 10.6z",
    "fullscreen": "M6 15H4v5h5v-2H6zM4 9h2V6h3V4H4zM18 18h-3v2h5v-5h-2zM15 4v2h3v3h2V4z",
    "fullscreen_exit": "M4 16h3v3h2v-5H4zM7 7H4v2h5V4H7zM15 19h2v-3h3v-2h-5zM17 7V4h-2v5h5V7z",
    "settings": "M19.14 12.94a7.8 7.8 0 0 0 0-1.88l2-1.56-2-3.46-2.4.96a7.3 7.3 0 0 0-1.62-.94L14.5 2.6h-4l-.62 2.46a7.3 7.3 0 0 0-1.62.94l-2.4-.96-2 3.46 2 1.56a7.8 7.8 0 0 0 0 1.88l-2 1.56 2 3.46 2.4-.96c.5.38 1.04.7 1.62.94l.62 2.46h4l.62-2.46c.58-.24 1.12-.56 1.62-.94l2.4.96 2-3.46-2-1.56zM12 15.6A3.6 3.6 0 1 1 12 8.4a3.6 3.6 0 0 1 0 7.2z",
    "minimize": "M5 11h14v2H5z",
    "maximize": "M5 5h14v14H5zm2 2v10h10V7z",
    "restore": "M7 7h10v10H7zm2 2v6h6V9z",
    "close": "M18.3 5.71 12 12l6.3 6.29-1.41 1.42L10.59 13.4 5.7 18.3 4.3 16.88 9.17 12 4.3 7.12 5.7 5.7l4.89 4.88 4.9-4.88z",
    "subtitles": "M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm2 10h6v2H6zm8 0h4v2h-4zM6 10h3v2H6zm5 0h7v2h-7z",
    "audio": "M12 3a9 9 0 0 0-9 9v5a3 3 0 0 0 3 3h1v-7H5v-1a7 7 0 0 1 14 0v1h-2v7h1a3 3 0 0 0 3-3v-5a9 9 0 0 0-9-9z",
    "speed": "M12 4a8 8 0 1 0 8 8h-2a6 6 0 1 1-6-6V4zm1 1v6h6a7 7 0 0 0-6-6z",
    "snapshot": "M9 4 7.2 6H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-3.2L15 4H9zm3 4.5A4.5 4.5 0 1 1 12 17.5 4.5 4.5 0 0 1 12 8.5z",
    "loop": "M7 7h8v2.5L19 6l-4-3.5V5H5v6h2V7zm10 10H9v-2.5L5 18l4 3.5V19h10v-6h-2v4z",
    "shuffle": "M14 4h6v6h-2V7.4l-4.3 4.3-1.4-1.42L16.6 6H14V4zM4 6h4.6l10.7 10.7V14h2v6h-6v-2h2.6L7.2 8H4V6z",
    "folder_add": "M10 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2zm3 7h3v2h-3v3h-2v-3H8v-2h3V8h2v3z",
}


def _svg(name: str, colour: str) -> bytes:
    path = _PATHS.get(name, "")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<path fill="{colour}" fill-rule="evenodd" d="{path}"/></svg>'
    ).encode("utf-8")


def pixmap(name: str, size: int = 24, colour: str = "#eef1f7") -> QPixmap:
    renderer = QSvgRenderer(QByteArray(_svg(name, colour)))
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pm


def icon(name: str, size: int = 24, colour: str = "#eef1f7") -> QIcon:
    ic = QIcon(pixmap(name, size, colour))
    return ic


def tint_color(hex_or_rgb) -> QColor:
    if isinstance(hex_or_rgb, QColor):
        return hex_or_rgb
    if isinstance(hex_or_rgb, (tuple, list)):
        return QColor(*hex_or_rgb)
    return QColor(hex_or_rgb)


# The Luma logo (multi-colour, so it is kept separate from the single-colour icons).
LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <defs>
    <linearGradient id="body" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#5EC8FF"/>
      <stop offset="0.5" stop-color="#6E7BFF"/>
      <stop offset="1" stop-color="#B36BFF"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.3" cy="0.25" r="0.8">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.55"/>
      <stop offset="0.45" stop-color="#FFFFFF" stop-opacity="0.08"/>
      <stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="gloss" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.65"/>
      <stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.9"/>
      <stop offset="0.5" stop-color="#FFFFFF" stop-opacity="0.15"/>
      <stop offset="1" stop-color="#FFFFFF" stop-opacity="0.55"/>
    </linearGradient>
  </defs>
  <rect x="16" y="16" width="224" height="224" rx="64" fill="url(#body)"/>
  <rect x="16" y="16" width="224" height="224" rx="64" fill="url(#glow)"/>
  <path d="M40 92 C 40 52, 70 32, 110 32 L 146 32 C 186 32, 216 52, 216 92 C 170 74, 90 74, 40 92 Z" fill="url(#gloss)"/>
  <rect x="17.5" y="17.5" width="221" height="221" rx="62.5" fill="none" stroke="url(#rim)" stroke-width="3"/>
  <circle cx="128" cy="136" r="58" fill="#FFFFFF" fill-opacity="0.16" stroke="#FFFFFF" stroke-opacity="0.55" stroke-width="4"/>
  <path d="M112 104 L 166 136 L 112 168 Z" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="10" stroke-linejoin="round"/>
</svg>"""


def logo_pixmap(size: int = 64) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(LOGO_SVG.encode("utf-8")))
    pm = QPixmap(QSize(size, size))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pm


def logo_icon() -> QIcon:
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(size))
    return ic
