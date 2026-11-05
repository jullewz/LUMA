"""The title bar and the bottom control bar – both frosted glass overlays."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

from . import icons
from .widgets import GlassSlider, IconButton, paint_divider


def _fmt_time(ms: int) -> str:
    if ms < 0:
        ms = 0
    s = ms // 1000
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class TitleBar(QWidget):
    """Draggable top bar with the app name, media title and window buttons."""

    minimizeClicked = Signal()
    maximizeClicked = Signal()
    closeClicked = Signal()
    dragStarted = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setAttribute(Qt.WA_StyledBackground, False)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 10, 0)
        lay.setSpacing(10)

        self._dot = QLabel()
        self._dot.setPixmap(icons.logo_pixmap(22))
        self.app_name = QLabel("Luma")
        f = QFont()
        f.setPointSize(11)
        f.setWeight(QFont.DemiBold)
        self.app_name.setFont(f)
        self.app_name.setStyleSheet("color: #eef1f7;")

        self.title = QLabel("")
        self.title.setStyleSheet("color: rgba(230,234,245,0.72);")
        self.title.setFont(QFont("", 10))
        self.title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.title.setAlignment(Qt.AlignCenter)

        self.btn_min = IconButton("minimize", 18, 34)
        self.btn_max = IconButton("maximize", 15, 34)
        self.btn_close = IconButton("close", 18, 34, colour="#ffd7d7")
        self.btn_min.clicked.connect(self.minimizeClicked)
        self.btn_max.clicked.connect(self.maximizeClicked)
        self.btn_close.clicked.connect(self.closeClicked)

        lay.addWidget(self._dot)
        lay.addWidget(self.app_name)
        lay.addSpacing(6)
        lay.addWidget(self.title, 1)
        lay.addSpacing(6)
        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_max)
        lay.addWidget(self.btn_close)

    def set_media_title(self, text: str) -> None:
        self.title.setText(text)

    def set_maximized(self, maximized: bool) -> None:
        self.btn_max.set_name("restore" if maximized else "maximize")

    # Start the system move only after a small drag, so double-click (maximize)
    # still reaches us – a move started on press would swallow it.
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        start = getattr(self, "_press_pos", None)
        if start is not None and event.buttons() & Qt.LeftButton:
            if (event.position().toPoint() - start).manhattanLength() > 4:
                self._press_pos = None
                self.dragStarted.emit()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.maximizeClicked.emit()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event) -> None:
        paint_divider(self, at_bottom=True)


class ControlBar(QWidget):
    """Bottom transport bar: seek, play, volume, time and extra actions."""

    playToggled = Signal()
    stopClicked = Signal()
    prevClicked = Signal()
    nextClicked = Signal()
    openClicked = Signal()
    seekStarted = Signal()
    seekMoved = Signal(float)
    seekEnded = Signal(float)
    volumeChanged = Signal(int)
    muteToggled = Signal()
    fullscreenToggled = Signal()
    playlistToggled = Signal()
    subtitlesClicked = Signal()
    audioClicked = Signal()
    speedClicked = Signal()
    snapshotClicked = Signal()
    loopToggled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(96)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        outer = QWidget(self)
        col = QVBoxLayout(outer)
        col.setContentsMargins(18, 8, 18, 12)
        col.setSpacing(4)

        # --- seek row (slider + times) ---
        seek_row = QHBoxLayout()
        seek_row.setSpacing(12)
        self.lbl_now = QLabel("0:00")
        self.lbl_now.setStyleSheet("color: rgba(230,234,245,0.85);")
        self.lbl_now.setFixedWidth(52)
        self.lbl_now.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.seek = GlassSlider()
        self.lbl_total = QLabel("0:00")
        self.lbl_total.setStyleSheet("color: rgba(230,234,245,0.6);")
        self.lbl_total.setFixedWidth(52)
        self.lbl_total.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        seek_row.addWidget(self.lbl_now)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.lbl_total)

        # --- button row ---
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.btn_open = IconButton("open", 20, 40)
        self.btn_prev = IconButton("prev", 20, 40)
        self.btn_play = IconButton("play", 24, 52)
        self.btn_stop = IconButton("stop", 18, 40)
        self.btn_next = IconButton("next", 20, 40)

        self.btn_loop = IconButton("loop", 19, 38)
        self.btn_vol = IconButton("volume_high", 20, 38)
        self.vol = GlassSlider()
        self.vol.setRange(0, 125)
        self.vol.setFixedWidth(110)
        self.vol.set_fraction_internal(0.8)

        self.btn_speed = IconButton("speed", 19, 38)
        self.btn_audio = IconButton("audio", 19, 38)
        self.btn_subs = IconButton("subtitles", 20, 38)
        self.btn_snap = IconButton("snapshot", 19, 38)
        self.btn_list = IconButton("playlist", 20, 38)
        self.btn_full = IconButton("fullscreen", 19, 40)

        left = QHBoxLayout()
        left.setSpacing(6)
        left.addWidget(self.btn_open)
        left.addWidget(self.btn_loop)

        centre = QHBoxLayout()
        centre.setSpacing(8)
        centre.addWidget(self.btn_prev)
        centre.addWidget(self.btn_play)
        centre.addWidget(self.btn_next)
        centre.addWidget(self.btn_stop)

        right = QHBoxLayout()
        right.setSpacing(6)
        right.addWidget(self.btn_vol)
        right.addWidget(self.vol)
        right.addSpacing(4)
        right.addWidget(self.btn_speed)
        right.addWidget(self.btn_audio)
        right.addWidget(self.btn_subs)
        right.addWidget(self.btn_snap)
        right.addWidget(self.btn_list)
        right.addWidget(self.btn_full)

        btn_row.addLayout(left)
        btn_row.addStretch(1)
        btn_row.addLayout(centre)
        btn_row.addStretch(1)
        btn_row.addLayout(right)

        col.addLayout(seek_row)
        col.addLayout(btn_row)
        root.addWidget(outer)

        self._wire()

    def _wire(self) -> None:
        self.btn_play.clicked.connect(self.playToggled)
        self.btn_stop.clicked.connect(self.stopClicked)
        self.btn_prev.clicked.connect(self.prevClicked)
        self.btn_next.clicked.connect(self.nextClicked)
        self.btn_open.clicked.connect(self.openClicked)
        self.btn_vol.clicked.connect(self.muteToggled)
        self.btn_full.clicked.connect(self.fullscreenToggled)
        self.btn_list.clicked.connect(self.playlistToggled)
        self.btn_subs.clicked.connect(self.subtitlesClicked)
        self.btn_audio.clicked.connect(self.audioClicked)
        self.btn_speed.clicked.connect(self.speedClicked)
        self.btn_snap.clicked.connect(self.snapshotClicked)
        self.btn_loop.clicked.connect(self.loopToggled)

        self.seek.scrubStarted.connect(self.seekStarted)
        self.seek.scrubMoved.connect(self.seekMoved)
        self.seek.scrubEnded.connect(self.seekEnded)
        self.vol.scrubMoved.connect(lambda f: self.volumeChanged.emit(int(f * 125)))
        self.vol.scrubEnded.connect(lambda f: self.volumeChanged.emit(int(f * 125)))

    # -- state updates from the player -----------------------------------
    def set_playing(self, playing: bool) -> None:
        self.btn_play.set_name("pause" if playing else "play")

    def set_time(self, now_ms: int, total_ms: int) -> None:
        self.lbl_now.setText(_fmt_time(now_ms))
        self.lbl_total.setText(_fmt_time(total_ms))

    def set_position(self, fraction: float) -> None:
        self.seek.set_fraction(fraction)

    def set_volume(self, value: int) -> None:
        self.vol.set_fraction_internal(min(1.0, value / 125))
        if value == 0:
            self.btn_vol.set_name("volume_mute")
        elif value < 60:
            self.btn_vol.set_name("volume_low")
        else:
            self.btn_vol.set_name("volume_high")

    def set_loop(self, on: bool) -> None:
        self.btn_loop.set_name("loop")
        self.btn_loop.setProperty("active", on)

    def set_fullscreen(self, on: bool) -> None:
        self.btn_full.set_name("fullscreen_exit" if on else "fullscreen")

    def paintEvent(self, event) -> None:
        paint_divider(self, at_bottom=False)
