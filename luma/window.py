"""The main Luma window: a frameless liquid-glass shell around a libVLC video surface.

Layout (top to bottom):  title bar · [ stage | playlist ] · control bar

The whole window is translucent and blurred by the OS (see glass.py). The stage
shows either the video (an opaque native surface libVLC draws on) or, when there
is no picture – idle, music, drop zone – a glass "now playing" card, so the
liquid glass is visible whenever video isn't covering it.

Widgets are laid out instead of floated over the video on purpose: libVLC renders
into a native child window, and ordinary Qt widgets can't be drawn on top of it
reliably. Only the toast is a separate floating window, which can.
"""
from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QCursor, QFont, QKeySequence, QLinearGradient, QPainter,
    QPainterPath, QPen, QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox,
    QStackedLayout, QVBoxLayout, QWidget,
)

from . import APP_NAME, glass, icons
from .controls import ControlBar, TitleBar
from .engine import ENDED, IDLE, PAUSED, PLAYING, STOPPED, Engine, EngineError
from .playlist import MEDIA_EXTS, Playlist, is_audio, is_media

RESIZE_MARGIN = 7
RADIUS = 16
BEZEL = 6          # glass rim around the video, so resize edges never sit on the video
# window glass strength: (top alpha, bottom alpha) with OS blur, and without it
GLASS_LEVELS = [
    ("Clear glass", (55, 85), (150, 170)),
    ("Frosted glass", (95, 130), (195, 212)),
    ("Solid", (230, 240), (238, 246)),
]


class VideoSurface(QFrame):
    """The opaque native widget libVLC draws onto."""

    doubleClicked = Signal()
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setStyleSheet("background:#000000;")
        self.setMouseTracking(True)
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(230)
        self._click_timer.timeout.connect(self.clicked.emit)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._click_timer.start()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self._click_timer.stop()
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


class NowPlaying(QWidget):
    """Glass card shown when there's no picture: drop zone, or music now playing."""

    doubleClicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(14)

        self.art = QLabel()
        self.art.setAlignment(Qt.AlignCenter)
        self.art.setPixmap(icons.logo_pixmap(132))

        self.headline = QLabel()
        self.headline.setAlignment(Qt.AlignCenter)
        self.headline.setWordWrap(True)
        f = QFont()
        f.setPointSize(17)
        f.setWeight(QFont.DemiBold)
        self.headline.setFont(f)
        self.headline.setStyleSheet("color:#f1f3fa;")

        self.sub = QLabel()
        self.sub.setAlignment(Qt.AlignCenter)
        self.sub.setWordWrap(True)
        self.sub.setStyleSheet("color: rgba(235,238,248,0.55); font-size: 13px;")

        lay.addWidget(self.art)
        lay.addWidget(self.headline)
        lay.addWidget(self.sub)
        self.show_drop_zone()

    def show_drop_zone(self) -> None:
        self.headline.setText("Drop a video or music file here")
        self.sub.setText("or press  O  to open  ·  Space  play / pause  ·  F  fullscreen  ·  Ctrl+L  playlist")

    def show_track(self, title: str, paused: bool) -> None:
        self.headline.setText(title or "Playing")
        self.sub.setText("Paused" if paused else "Now playing")

    def set_drag_highlight(self, on: bool) -> None:
        self.sub.setStyleSheet(
            f"color: rgba(235,238,248,{0.95 if on else 0.55}); font-size: 13px;")

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


class Toast(QLabel):
    """A small floating glass message. It's its own top-level window so it can
    appear over the video (normal child widgets can't)."""

    def __init__(self, owner: QWidget) -> None:
        super().__init__(None)
        self._owner = owner
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            "QLabel{background: rgba(18,20,28,0.86); color:#eef1f7; padding:10px 18px;"
            "border-radius:12px; border:1px solid rgba(255,255,255,0.12); font-size:13px;}")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def flash(self, text: str, msec: int = 2200) -> None:
        self.setText(text)
        self.adjustSize()
        owner = self._owner
        bottom_offset = 120 if owner.controls.isVisible() else 48
        pos = owner.mapToGlobal(QPoint((owner.width() - self.width()) // 2,
                                       owner.height() - bottom_offset - self.height()))
        self.move(pos)
        self.show()
        self.raise_()
        self._timer.start(msec)


class LumaWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.logo_icon())
        self.setMinimumSize(760, 460)
        self.resize(1120, 680)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # --- widgets ---------------------------------------------------
        self.title_bar = TitleBar(self)
        self.controls = ControlBar(self)
        self.playlist = Playlist(self)
        self.playlist.hide()
        self.video = VideoSurface()
        self.now_playing = NowPlaying()
        self.toast = Toast(self)

        # --- layout ----------------------------------------------------
        self.stage = QWidget()
        self.stage.setAttribute(Qt.WA_TranslucentBackground, True)
        self.stack = QStackedLayout(self.stage)
        self.stack.setStackingMode(QStackedLayout.StackOne)
        self.stack.addWidget(self.now_playing)   # index 0
        self.stack.addWidget(self.video)         # index 1
        self.stack.setCurrentIndex(0)

        middle = QHBoxLayout()
        middle.setContentsMargins(BEZEL, 0, BEZEL, 0)
        middle.setSpacing(0)
        middle.addWidget(self.stage, 1)
        middle.addWidget(self.playlist)

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)   # keeps the 1px glass rim visible
        root.setSpacing(0)
        root.addWidget(self.title_bar)
        root.addLayout(middle, 1)
        root.addWidget(self.controls)

        # --- state -----------------------------------------------------
        self.engine: Engine | None = None
        self._loop = False
        self._fullscreen = False
        self._backend = "paint"
        self._glass_level = 1
        self._last_cursor = QPoint()

        self._wire()
        self._install_shortcuts()

        # in fullscreen, hide the bars after a moment of no mouse movement
        self._idle = QTimer(self)
        self._idle.setInterval(2600)
        self._idle.setSingleShot(True)
        self._idle.timeout.connect(self._maybe_hide_bars)
        # libVLC's native window may swallow mouse-move events, so also watch the cursor
        self._cursor_watch = QTimer(self)
        self._cursor_watch.setInterval(250)
        self._cursor_watch.timeout.connect(self._watch_cursor)

        # Mouse events at the window edges land on child widgets, not on us, so
        # resizing is handled by an application-wide event filter.
        QApplication.instance().installEventFilter(self)

    # ================================================================ setup
    def start_engine(self) -> bool:
        try:
            self.engine = Engine(self)
        except EngineError as exc:
            QMessageBox.critical(self, f"{APP_NAME} – VLC not found", str(exc))
            return False
        self.engine.attach_to(self.video)
        self.engine.set_volume(80)
        e = self.engine
        e.positionChanged.connect(self.controls.set_position)
        e.timeChanged.connect(self.controls.set_time)
        e.volumeChanged.connect(self.controls.set_volume)
        e.mediaChanged.connect(self._on_media_changed)
        e.stateChanged.connect(self._on_state)
        e.endReached.connect(self._on_end)
        e.errorOccurred.connect(self.show_toast)
        e.videoPresenceChanged.connect(self._on_video_presence)
        return True

    def _wire(self) -> None:
        c = self.controls
        c.playToggled.connect(self.toggle_play)
        c.stopClicked.connect(self.stop)
        c.prevClicked.connect(self.play_prev)
        c.nextClicked.connect(self.play_next)
        c.openClicked.connect(self.open_files)
        c.seekStarted.connect(self._scrub_start)
        c.seekMoved.connect(self._scrub_preview)
        c.seekEnded.connect(self._scrub_end)
        c.volumeChanged.connect(self._set_volume)
        c.muteToggled.connect(self._toggle_mute)
        c.fullscreenToggled.connect(self.toggle_fullscreen)
        c.playlistToggled.connect(self.toggle_playlist)
        c.subtitlesClicked.connect(self.menu_subtitles)
        c.audioClicked.connect(self.menu_audio)
        c.speedClicked.connect(self.menu_speed)
        c.snapshotClicked.connect(self.take_snapshot)
        c.loopToggled.connect(self.toggle_loop)

        t = self.title_bar
        t.minimizeClicked.connect(self.showMinimized)
        t.maximizeClicked.connect(self.toggle_maximize)
        t.closeClicked.connect(self.close)
        t.dragStarted.connect(self._start_move)

        self.playlist.activated.connect(self._play_index)
        self.playlist.btn_add.clicked.connect(self.open_files)
        self.playlist.clearedAll.connect(self._on_playlist_cleared)

        self.video.doubleClicked.connect(self.toggle_fullscreen)
        self.video.clicked.connect(self.toggle_play)
        self.now_playing.doubleClicked.connect(self.toggle_fullscreen)

    def _install_shortcuts(self) -> None:
        def sc(seq, fn) -> None:
            s = QShortcut(QKeySequence(seq), self)
            s.setContext(Qt.WindowShortcut)
            s.activated.connect(fn)

        sc("Space", self.toggle_play)
        sc("K", self.toggle_play)
        sc("Right", lambda: self._seek_rel(5))
        sc("Left", lambda: self._seek_rel(-5))
        sc("Shift+Right", lambda: self._seek_rel(60))
        sc("Shift+Left", lambda: self._seek_rel(-60))
        sc("L", lambda: self._seek_rel(10))
        sc("J", lambda: self._seek_rel(-10))
        sc("Up", lambda: self._nudge_volume(5))
        sc("Down", lambda: self._nudge_volume(-5))
        sc("M", self._toggle_mute)
        sc("F", self.toggle_fullscreen)
        sc("Escape", self._escape)
        sc("S", self.stop)
        sc("N", self.play_next)
        sc("P", self.play_prev)
        sc("O", self.open_files)
        sc("Ctrl+O", self.open_files)
        sc("Ctrl+L", self.toggle_playlist)
        sc(".", lambda: self._bump_rate(0.1))
        sc(",", lambda: self._bump_rate(-0.1))
        sc("Ctrl+S", self.take_snapshot)
        sc("Ctrl+Q", self.close)
        sc("Ctrl+T", self.cycle_glass)
        for n in range(10):
            sc(str(n), lambda frac=n / 10.0: self.engine and self.engine.set_position(frac))

    # ================================================================ glass painting
    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._backend = glass.apply_blur(self)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        flat = self._fullscreen or self.isMaximized()
        radius = 0 if flat else RADIUS
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        # With a native blur behind us a light tint is enough; without one we paint
        # a denser frosted gradient so text stays readable over any desktop.
        _, with_blur, without_blur = GLASS_LEVELS[self._glass_level]
        a_top, a_bottom = with_blur if self._backend != "paint" else without_blur
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QColor(30, 33, 46, a_top))
        grad.setColorAt(0.55, QColor(18, 20, 30, a_bottom))
        grad.setColorAt(1.0, QColor(26, 18, 40, a_bottom))
        painter.fillPath(path, grad)

        # liquid sheen: a soft light band across the top
        sheen = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + 140))
        sheen.setColorAt(0.0, QColor(255, 255, 255, 26))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(path, sheen)

        if not flat:
            painter.strokePath(path, QPen(QColor(255, 255, 255, 40), 1.0))
        painter.end()

    # ================================================================ opening media
    def open_files(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(MEDIA_EXTS))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open media", os.path.expanduser("~"),
            f"Media files ({exts});;All files (*)")
        if paths:
            self.enqueue(paths, play=True)

    def open_paths(self, paths: list[str]) -> None:
        """Used for files given on the command line / 'Open with'."""
        files: list[str] = []
        for p in paths:
            if os.path.isdir(p):
                for root, _, names in os.walk(p):
                    files += [os.path.join(root, n) for n in sorted(names) if is_media(n)]
            else:
                files.append(p)
        if files:
            self.enqueue(files, play=True)

    def enqueue(self, paths: list[str], play: bool) -> None:
        first_new = self.playlist.count_items()
        added = self.playlist.add(paths)
        if not added:
            self.show_toast("No playable media in that selection.")
            return
        if play:
            self._play_index(first_new)
        if added > 1:
            self.show_toast(f"Added {added} items to the playlist")

    def _play_index(self, index: int) -> None:
        path = self.playlist.path_at(index)
        if path is None or self.engine is None:
            return
        self.playlist.set_current(index)
        # music shows the glass "now playing" card, everything else the video surface
        self.stack.setCurrentIndex(0 if is_audio(path) else 1)
        self.engine.open(path, play=True)

    # ================================================================ transport
    def toggle_play(self) -> None:
        if self.engine is None:
            return
        if self.engine.state in (IDLE, STOPPED, ENDED):
            if self.playlist.count_items():
                self._play_index(max(0, self.playlist.current_index()))
            else:
                self.open_files()
            return
        self.engine.toggle_pause()

    def stop(self) -> None:
        if self.engine:
            self.engine.stop()

    def play_next(self) -> None:
        nxt = self.playlist.next_index(self._loop)
        if nxt >= 0:
            self._play_index(nxt)
        else:
            self.stop()

    def play_prev(self) -> None:
        # like most players: restart the track if we're more than 3s in
        if self.engine and self.engine.state == PLAYING and self.controls.seek.fraction() * max(1, self.engine.duration) > 3000:
            self.engine.set_position(0.0)
            return
        prv = self.playlist.prev_index()
        if prv >= 0:
            self._play_index(prv)

    def _on_end(self) -> None:
        if self._loop and self.playlist.count_items() == 1:
            self._play_index(self.playlist.current_index())
        else:
            self.play_next()

    def _seek_rel(self, seconds: float) -> None:
        if self.engine:
            self.engine.step(seconds)
            self._wake_bars()

    def _scrub_start(self) -> None:
        if self.engine:
            self.engine.begin_scrub()

    def _scrub_preview(self, fraction: float) -> None:
        if self.engine and self.engine.duration:
            total = self.engine.duration
            self.controls.set_time(int(fraction * total), total)

    def _scrub_end(self, fraction: float) -> None:
        if self.engine:
            self.engine.end_scrub(fraction)

    # ================================================================ volume / rate / loop
    def _set_volume(self, value: int) -> None:
        if self.engine:
            self.engine.set_volume(value)

    def _toggle_mute(self) -> None:
        if self.engine:
            self.engine.toggle_mute()
            self.show_toast("Muted" if self.engine.is_muted() else f"Volume {self.engine.volume()}%")

    def _nudge_volume(self, delta: int) -> None:
        if self.engine:
            new = max(0, min(125, self.engine.volume() + delta))
            self.engine.set_volume(new)
            self.show_toast(f"Volume {new}%", 900)

    def _bump_rate(self, delta: float) -> None:
        if self.engine:
            new = round(max(0.25, min(4.0, self.engine.rate() + delta)), 2)
            self.engine.set_rate(new)
            self.show_toast(f"Speed {new:g}×")

    def toggle_loop(self) -> None:
        self._loop = not self._loop
        self.controls.set_loop(self._loop)
        self.show_toast("Loop on" if self._loop else "Loop off")

    # ================================================================ menus
    def _glass_menu(self) -> QMenu:
        m = QMenu(self)
        m.setStyleSheet(
            "QMenu{background:rgba(22,24,34,0.97);color:#e6eaf5;border:1px solid rgba(255,255,255,0.10);"
            "border-radius:10px;padding:6px;}"
            "QMenu::item{padding:7px 22px;border-radius:7px;}"
            "QMenu::item:selected{background:rgba(120,170,255,0.30);}"
            "QMenu::item:disabled{color:rgba(230,234,245,0.4);}"
            "QMenu::separator{height:1px;background:rgba(255,255,255,0.1);margin:5px 8px;}"
        )
        return m

    def _pop_menu(self, menu: QMenu, anchor: QWidget) -> None:
        pos = anchor.mapToGlobal(QPoint(0, 0))
        size = menu.sizeHint()
        menu.exec(QPoint(pos.x() + anchor.width() // 2 - size.width() // 2, pos.y() - size.height() - 8))

    def menu_audio(self) -> None:
        if not self.engine:
            return
        m = self._glass_menu()
        tracks = self.engine.audio_tracks()
        if not tracks:
            m.addAction("No audio tracks").setEnabled(False)
        for tid, name in tracks:
            m.addAction(name).triggered.connect(lambda _=False, t=tid: self.engine.set_audio_track(t))
        self._pop_menu(m, self.controls.btn_audio)

    def menu_subtitles(self) -> None:
        if not self.engine:
            return
        m = self._glass_menu()
        tracks = self.engine.subtitle_tracks()
        if not tracks:
            m.addAction("No subtitles in this file").setEnabled(False)
        for tid, name in tracks:
            m.addAction(name).triggered.connect(lambda _=False, t=tid: self.engine.set_subtitle_track(t))
        m.addSeparator()
        m.addAction("Load subtitle file…").triggered.connect(self._load_subtitle)
        self._pop_menu(m, self.controls.btn_subs)

    def _load_subtitle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load subtitles", os.path.expanduser("~"),
            "Subtitles (*.srt *.ass *.ssa *.sub *.vtt);;All files (*)")
        if path and self.engine and self.engine.add_subtitle_file(path):
            self.show_toast("Subtitles loaded")

    def menu_speed(self) -> None:
        if not self.engine:
            return
        m = self._glass_menu()
        current = self.engine.rate()
        for rate in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0):
            act = m.addAction(f"{rate:g}×" + ("   (normal)" if rate == 1.0 else ""))
            act.setCheckable(True)
            act.setChecked(abs(rate - current) < 0.01)
            act.triggered.connect(lambda _=False, r=rate: self._apply_rate(r))
        self._pop_menu(m, self.controls.btn_speed)

    def _apply_rate(self, rate: float) -> None:
        if self.engine:
            self.engine.set_rate(rate)
            self.show_toast(f"Speed {rate:g}×")

    def take_snapshot(self) -> None:
        if not self.engine or not self.engine.has_video:
            self.show_toast("Snapshots need a video playing.")
            return
        folder = os.path.join(os.path.expanduser("~"), "Pictures")
        if not os.path.isdir(folder):
            folder = os.path.expanduser("~")
        path = os.path.join(folder, f"luma-{datetime.now():%Y%m%d-%H%M%S}.png")
        if self.engine.snapshot(path):
            self.show_toast(f"Snapshot saved to {folder}")
        else:
            self.show_toast("Couldn't take a snapshot.")

    # ================================================================ playlist panel
    def toggle_playlist(self) -> None:
        self.playlist.setVisible(not self.playlist.isVisible())

    def _on_playlist_cleared(self) -> None:
        self.stop()
        self.title_bar.set_media_title("")
        self.now_playing.show_drop_zone()
        self.stack.setCurrentIndex(0)

    # ================================================================ fullscreen / maximize
    def toggle_fullscreen(self) -> None:
        self._fullscreen = not self._fullscreen
        self.controls.set_fullscreen(self._fullscreen)
        if self._fullscreen:
            self.showFullScreen()
            self._last_cursor = QCursor.pos()
            self._cursor_watch.start()
            self._idle.start()
        else:
            self._cursor_watch.stop()
            self._idle.stop()
            self._show_bars()
            self.showNormal()
        self.update()

    def toggle_maximize(self) -> None:
        if self._fullscreen:
            return
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _escape(self) -> None:
        if self._fullscreen:
            self.toggle_fullscreen()

    # bars auto-hide only in fullscreen while playing
    def _wake_bars(self) -> None:
        if self._fullscreen:
            self._show_bars()
            self._idle.start()

    def _show_bars(self) -> None:
        self.title_bar.show()
        self.controls.show()
        self.unsetCursor()

    def _maybe_hide_bars(self) -> None:
        if not self._fullscreen or not self.engine or self.engine.state != PLAYING:
            return
        if self.controls.underMouse() or self.title_bar.underMouse() or self.playlist.underMouse():
            self._idle.start()
            return
        self.title_bar.hide()
        self.controls.hide()
        self.setCursor(Qt.BlankCursor)

    def _watch_cursor(self) -> None:
        pos = QCursor.pos()
        if pos != self._last_cursor:
            self._last_cursor = pos
            self._wake_bars()

    # ================================================================ frameless move / resize
    def _start_move(self) -> None:
        handle = self.windowHandle()
        if handle and not self.isMaximized() and not self._fullscreen:
            handle.startSystemMove()

    def _edges_at(self, pos: QPoint) -> Qt.Edge:
        edges = Qt.Edge(0)
        if self.isMaximized() or self._fullscreen:
            return edges
        m = RESIZE_MARGIN
        if pos.x() <= m:
            edges |= Qt.LeftEdge
        if pos.x() >= self.width() - m:
            edges |= Qt.RightEdge
        if pos.y() <= m:
            edges |= Qt.TopEdge
        if pos.y() >= self.height() - m:
            edges |= Qt.BottomEdge
        return edges

    def _update_resize_cursor(self, pos: QPoint) -> None:
        e = self._edges_at(pos)
        if e in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeFDiagCursor)
        elif e in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
            self.setCursor(Qt.SizeBDiagCursor)
        elif e in (Qt.LeftEdge, Qt.RightEdge):
            self.setCursor(Qt.SizeHorCursor)
        elif e in (Qt.TopEdge, Qt.BottomEdge):
            self.setCursor(Qt.SizeVerCursor)
        elif not self._fullscreen:
            self.unsetCursor()

    def eventFilter(self, obj, event) -> bool:
        et = event.type()
        if et in (QEvent.MouseMove, QEvent.MouseButtonPress) and isinstance(obj, QWidget) \
                and obj.window() is self and not isinstance(obj, VideoSurface):
            pos = self.mapFromGlobal(event.globalPosition().toPoint())
            if et == QEvent.MouseMove:
                self._wake_bars()
                if not event.buttons():
                    self._update_resize_cursor(pos)
            elif event.button() == Qt.LeftButton:
                edges = self._edges_at(pos)
                handle = self.windowHandle()
                if edges and handle:
                    handle.startSystemResize(edges)
                    return True   # don't let the child (e.g. title bar drag) also react
        return super().eventFilter(obj, event)

    # ================================================================ drag & drop
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.now_playing.set_drag_highlight(True)

    def dragLeaveEvent(self, event) -> None:
        self.now_playing.set_drag_highlight(False)

    def dropEvent(self, event) -> None:
        self.now_playing.set_drag_highlight(False)
        paths: list[str] = []
        for url in event.mimeData().urls():
            paths.append(url.toLocalFile() if url.isLocalFile() else url.toString())
        if paths:
            self.open_paths(paths)
            self.activateWindow()

    # ================================================================ engine signals
    def _on_media_changed(self, title: str) -> None:
        self.title_bar.set_media_title(title)
        self.setWindowTitle(f"{title} — {APP_NAME}" if title else APP_NAME)
        self.now_playing.show_track(title, paused=False)

    def _on_state(self, state: str) -> None:
        self.controls.set_playing(state == PLAYING)
        if state in (PLAYING, PAUSED):
            self.now_playing.show_track(self.engine.title if self.engine else "", paused=(state == PAUSED))
        if state == PLAYING and self._fullscreen:
            self._idle.start()
        elif state != PLAYING:
            self._show_bars()
        if state in (STOPPED, IDLE) and not self.playlist.count_items():
            self.now_playing.show_drop_zone()

    def _on_video_presence(self, has_video: bool) -> None:
        # The file type picks the view when a track starts; this corrects it later,
        # e.g. a video with no picture, or playback ending.
        if has_video:
            self.stack.setCurrentIndex(1)
        elif self.engine and self.engine.state in (STOPPED, ENDED, IDLE):
            self.stack.setCurrentIndex(0)

    # ================================================================ misc
    def cycle_glass(self) -> None:
        self._glass_level = (self._glass_level + 1) % len(GLASS_LEVELS)
        self.update()
        self.show_toast(GLASS_LEVELS[self._glass_level][0])

    def show_toast(self, text: str, msec: int = 2200) -> None:
        self.toast.flash(text, msec)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.WindowStateChange:
            self.title_bar.set_maximized(self.isMaximized())
            self.update()
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        QApplication.instance().removeEventFilter(self)
        self.toast.close()
        if self.engine:
            self.engine.shutdown()
        super().closeEvent(event)
