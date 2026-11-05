"""The slide-in playlist panel (a frosted glass list on the right)."""
from __future__ import annotations

import os
import random

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)

from . import icons
from .widgets import IconButton

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg", ".ts", ".3gp", ".ogv"}
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aac", ".ogg", ".oga", ".m4a", ".opus", ".wma", ".aiff", ".alac"}
MEDIA_EXTS = VIDEO_EXTS | AUDIO_EXTS


def is_media(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in MEDIA_EXTS


def is_audio(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in AUDIO_EXTS


class Playlist(QWidget):
    """Holds the queue and emits which item to play."""

    activated = Signal(int)      # index chosen to play
    closeRequested = Signal()
    clearedAll = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(320)
        self._paths: list[str] = []
        self._current = -1
        self._shuffle = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Playlist")
        f = QFont()
        f.setPointSize(12)
        f.setWeight(QFont.DemiBold)
        title.setFont(f)
        title.setStyleSheet("color: #eef1f7;")
        self.count = QLabel("0 items")
        self.count.setStyleSheet("color: rgba(230,234,245,0.5);")
        self.btn_add = IconButton("folder_add", 18, 32)
        self.btn_shuffle = IconButton("shuffle", 17, 32)
        self.btn_clear = IconButton("close", 16, 32, colour="#ffd7d7")
        self.btn_add.setToolTip("Add files")
        self.btn_shuffle.setToolTip("Shuffle")
        self.btn_clear.setToolTip("Clear playlist")
        header.addWidget(title)
        header.addWidget(self.count)
        header.addStretch(1)
        header.addWidget(self.btn_add)
        header.addWidget(self.btn_shuffle)
        header.addWidget(self.btn_clear)

        self.list = QListWidget()
        self.list.setFrameShape(QListWidget.NoFrame)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setUniformItemSizes(False)
        self.list.setSpacing(2)
        self.list.setStyleSheet(
            "QListWidget{background:transparent;color:#e6eaf5;outline:none;}"
            "QListWidget::item{padding:9px 10px;border-radius:9px;}"
            "QListWidget::item:hover{background:rgba(255,255,255,0.07);}"
            "QListWidget::item:selected{background:rgba(120,170,255,0.28);color:#ffffff;}"
            "QScrollBar:vertical{background:transparent;width:8px;margin:2px;}"
            "QScrollBar::handle:vertical{background:rgba(255,255,255,0.18);border-radius:4px;min-height:30px;}"
            "QScrollBar::add-line,QScrollBar::sub-line{height:0;}"
        )
        self.list.itemActivated.connect(self._on_item)
        self.list.itemDoubleClicked.connect(self._on_item)

        root.addLayout(header)
        root.addWidget(self.list, 1)

        self.btn_clear.clicked.connect(self.clear)
        self.btn_shuffle.clicked.connect(self._toggle_shuffle)

    # -- queue management -------------------------------------------------
    def add(self, paths: list[str], play_first: bool = False) -> int:
        start = len(self._paths)
        added = 0
        for p in paths:
            if is_media(p) or "://" in p:
                self._paths.append(p)
                item = QListWidgetItem(self._label(p))
                item.setIcon(icons.icon("audio" if os.path.splitext(p)[1].lower() in AUDIO_EXTS else "play", 16))
                item.setSizeHint(QSize(0, 40))
                self.list.addItem(item)
                added += 1
        self._update_count()
        if added and play_first:
            self.set_current(start)
            self.activated.emit(start)
        return added

    @staticmethod
    def _label(path: str) -> str:
        if "://" in path:
            return path
        return os.path.basename(path) or path

    def clear(self) -> None:
        self._paths.clear()
        self.list.clear()
        self._current = -1
        self._update_count()
        self.clearedAll.emit()

    def _update_count(self) -> None:
        n = len(self._paths)
        self.count.setText(f"{n} item{'s' if n != 1 else ''}")

    def _toggle_shuffle(self) -> None:
        self._shuffle = not self._shuffle
        self.btn_shuffle.setProperty("active", self._shuffle)
        self.btn_shuffle.setToolTip("Shuffle: on" if self._shuffle else "Shuffle: off")

    # -- current item -----------------------------------------------------
    def path_at(self, index: int) -> str | None:
        if 0 <= index < len(self._paths):
            return self._paths[index]
        return None

    def set_current(self, index: int) -> None:
        self._current = index
        if 0 <= index < self.list.count():
            self.list.setCurrentRow(index)

    def current_index(self) -> int:
        return self._current

    def count_items(self) -> int:
        return len(self._paths)

    def next_index(self, loop: bool) -> int:
        if not self._paths:
            return -1
        if self._shuffle:
            if len(self._paths) == 1:
                return 0 if loop else -1
            choices = [i for i in range(len(self._paths)) if i != self._current]
            return random.choice(choices)
        nxt = self._current + 1
        if nxt >= len(self._paths):
            return 0 if loop else -1
        return nxt

    def prev_index(self) -> int:
        if not self._paths:
            return -1
        prv = self._current - 1
        return prv if prv >= 0 else len(self._paths) - 1

    def _on_item(self, item: QListWidgetItem) -> None:
        index = self.list.row(item)
        self.set_current(index)
        self.activated.emit(index)

    def paintEvent(self, event) -> None:
        # slightly darker glass than the window, plus a hairline where it meets the video
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 40))
        painter.fillRect(0, 0, 1, self.height(), QColor(255, 255, 255, 22))
        painter.end()
