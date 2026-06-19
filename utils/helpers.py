"""Miscellaneous helper functions."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient, QPainterPath
from PyQt6.QtCore import Qt, QRect


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_str() -> str:
    return utcnow().isoformat()


def format_score(score: int) -> str:
    return f"{score:,}"


def validate_display_name(name: str) -> tuple[bool, str]:
    name = name.strip()
    if len(name) < 2:
        return False, "Name must be at least 2 characters."
    if len(name) > 20:
        return False, "Name must be 20 characters or fewer."
    if not re.match(r"^[\w\s.\-']+$", name):
        return False, "Only letters, digits, spaces, and . - ' are allowed."
    return True, ""


def make_avatar_pixmap(initials: str, size: int = 64, bg_color: str = "#FE2C55") -> QPixmap:
    pixmap = QPixmap(size, size)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor(bg_color))
    dark = QColor(bg_color).darker(140)
    grad.setColorAt(1, dark)
    painter.fillRect(0, 0, size, size, grad)
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", size // 3, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, initials[:2].upper())
    painter.end()
    return pixmap


def round_pixmap(pix: QPixmap, size: int) -> QPixmap:
    """Clip a QPixmap to a circle."""
    scaled = pix.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    x_off = (scaled.width() - size) // 2
    y_off = (scaled.height() - size) // 2
    painter.drawPixmap(-x_off, -y_off, scaled)
    painter.end()
    return result


def avatar_color_for(name: str) -> str:
    from utils.config import AVATAR_COLORS
    return AVATAR_COLORS[abs(hash(name)) % len(AVATAR_COLORS)]


