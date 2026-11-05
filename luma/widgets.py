"""Custom, hand-painted glass controls: icon buttons, sliders, frosted panels."""
from __future__ import annotations

from PySide6.QtCore import (
    Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Signal,
)
from PySide6.QtGui import (
    QColor, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QSlider, QToolButton, QWidget

from . import glass, icons


def frosted_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def paint_glass_panel(widget: QWidget, radius: float = 18.0, alpha: int | None = None,
                      rim: bool = True) -> None:
    """Paint the standard frosted panel used by bars and popups."""
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
    path = frosted_path(rect, radius)

    a = glass.TINT_ALPHA if alpha is None else alpha
    grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    top = QColor(glass.TINT[0] + 14, glass.TINT[1] + 16, glass.TINT[2] + 22, a)
    bottom = QColor(glass.TINT[0], glass.TINT[1], glass.TINT[2], min(255, a + 24))
    grad.setColorAt(0.0, top)
    grad.setColorAt(1.0, bottom)
    painter.fillPath(path, grad)

    if rim:
        pen = QPen(QColor(255, 255, 255, glass.BORDER_ALPHA))
        pen.setWidthF(1.0)
        painter.strokePath(path, pen)
        # a brighter highlight along the very top edge
        hl = QPainterPath()
        hl.moveTo(rect.left() + radius, rect.top() + 0.75)
        hl.lineTo(rect.right() - radius, rect.top() + 0.75)
        painter.strokePath(hl, QPen(QColor(255, 255, 255, 40), 1.0))
    painter.end()


def paint_divider(widget: QWidget, at_bottom: bool) -> None:
    """A hairline separating a bar from the video area (bars themselves are clear glass)."""
    painter = QPainter(widget)
    y = widget.height() - 1 if at_bottom else 0
    painter.fillRect(0, y, widget.width(), 1, QColor(255, 255, 255, 22))
    painter.end()


class IconButton(QToolButton):
    """A flat, round icon button with a soft glass hover glow."""

    def __init__(self, name: str, size: int = 22, diameter: int = 40,
                 colour: str = "#eef1f7", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = name
        self._icon_size = size
        self._colour = colour
        self._hover = 0.0
        self._anim = QPropertyAnimation(self, b"hover", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        self.setIcon(icons.icon(self._name, self._icon_size, self._colour))
        self.setIconSize(QSize(self._icon_size, self._icon_size))

    def set_name(self, name: str) -> None:
        if name != self._name:
            self._name = name
            self._refresh_icon()

    def get_hover(self) -> float:
        return self._hover

    def set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    hover = Property(float, get_hover, set_hover)

    def enterEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        if self._hover > 0.01 or self.isDown():
            glow = 70 if self.isDown() else int(46 * self._hover)
            painter.setBrush(QColor(255, 255, 255, glow))
            painter.setPen(Qt.NoPen)
            inset = rect.adjusted(3, 3, -3, -3)
            painter.drawEllipse(inset)
        painter.end()
        # draw the icon on top via the default toolbutton mechanism
        opt_pm = self.icon().pixmap(QSize(self._icon_size, self._icon_size))
        p2 = QPainter(self)
        p2.setRenderHint(QPainter.SmoothPixmapTransform)
        x = (self.width() - opt_pm.width()) / 2
        y = (self.height() - opt_pm.height()) / 2
        p2.setOpacity(1.0 if self.isEnabled() else 0.4)
        p2.drawPixmap(int(x), int(y), opt_pm)
        p2.end()


class GlassSlider(QSlider):
    """A thin, rounded progress/volume slider with an accent fill and hover head.

    Clicking anywhere jumps there; dragging scrubs. Emits scrubStarted /
    scrubMoved(fraction) / scrubEnded(fraction) so the player can seek smoothly.
    """

    scrubStarted = Signal()
    scrubMoved = Signal(float)
    scrubEnded = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 1000)
        self.setFixedHeight(26)
        self.setCursor(Qt.PointingHandCursor)
        self._hovering = False
        self._dragging = False
        self._buffer = 0.0  # 0..1 reserved for future buffered display
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)

    def fraction(self) -> float:
        span = self.maximum() - self.minimum()
        return (self.value() - self.minimum()) / span if span else 0.0

    def set_fraction(self, value: float) -> None:
        if self._dragging:
            return
        value = max(0.0, min(1.0, value))
        self.setValue(int(self.minimum() + value * (self.maximum() - self.minimum())))

    def _pos_to_fraction(self, x: int) -> float:
        return max(0.0, min(1.0, x / max(1, self.width())))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            frac = self._pos_to_fraction(int(event.position().x()))
            self.set_fraction_internal(frac)
            self.scrubStarted.emit()
            self.scrubMoved.emit(frac)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._hovering = True
        if self._dragging:
            frac = self._pos_to_fraction(int(event.position().x()))
            self.set_fraction_internal(frac)
            self.scrubMoved.emit(frac)
            event.accept()
            return
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            frac = self._pos_to_fraction(int(event.position().x()))
            self.set_fraction_internal(frac)
            self.scrubEnded.emit(frac)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def set_fraction_internal(self, value: float) -> None:
        self.setValue(int(self.minimum() + value * (self.maximum() - self.minimum())))

    def enterEvent(self, event) -> None:
        self._hovering = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovering = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        h = 5.0 if not (self._hovering or self._dragging) else 7.0
        y = (self.height() - h) / 2
        full = QRectF(0, y, self.width(), h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 38))
        painter.drawRoundedRect(full, h / 2, h / 2)

        frac = self.fraction()
        fill_w = self.width() * frac
        if fill_w > 0:
            grad = QLinearGradient(0, 0, self.width(), 0)
            grad.setColorAt(0.0, QColor(*glass.ACCENT))
            grad.setColorAt(1.0, QColor(*glass.ACCENT2))
            painter.setBrush(grad)
            painter.drawRoundedRect(QRectF(0, y, fill_w, h), h / 2, h / 2)

        if self._hovering or self._dragging:
            r = 8.0 if self._dragging else 7.0
            cx = fill_w
            painter.setBrush(QColor(245, 247, 255))
            painter.drawEllipse(QRectF(cx - r / 2, self.height() / 2 - r / 2, r, r))
        painter.end()
