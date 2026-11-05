"""Playback engine – a thin, Qt-friendly wrapper around libVLC (python-vlc).

All of libVLC's threading stays hidden behind this class. Position, length and
state are polled on a Qt timer and re-emitted as Qt signals, so the rest of the
app never touches a libVLC callback thread (which must not run Qt code).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

try:
    import vlc  # python-vlc, loads the system libVLC
except (ImportError, OSError) as exc:  # pragma: no cover - import guard
    vlc = None
    _VLC_IMPORT_ERROR = exc
else:
    _VLC_IMPORT_ERROR = None


class EngineError(RuntimeError):
    """Raised when libVLC is missing or a player could not be created."""


def vlc_available() -> bool:
    return vlc is not None


def vlc_import_hint() -> str:
    """A human-readable reason why the engine can't start, with a fix."""
    if vlc is not None:
        return ""
    base = "Luma needs VLC (libVLC) installed on this computer.\n"
    if sys.platform.startswith("win"):
        return base + "Install the 64-bit VLC from https://www.videolan.org/vlc/ and restart Luma."
    if sys.platform == "darwin":
        return base + "Install VLC from https://www.videolan.org/vlc/ (drag it to Applications), then restart Luma."
    return base + "Install it with your package manager, e.g.  sudo apt install vlc  (Debian/Ubuntu/BOBOS OS)."


# Playback states reported by the engine, mapped from vlc.State.
IDLE, OPENING, BUFFERING, PLAYING, PAUSED, STOPPED, ENDED, ERROR = (
    "idle", "opening", "buffering", "playing", "paused", "stopped", "ended", "error",
)

_STATE_MAP = {}
if vlc is not None:
    _STATE_MAP = {
        vlc.State.NothingSpecial: IDLE,
        vlc.State.Opening: OPENING,
        vlc.State.Buffering: BUFFERING,
        vlc.State.Playing: PLAYING,
        vlc.State.Paused: PAUSED,
        vlc.State.Stopped: STOPPED,
        vlc.State.Ended: ENDED,
        vlc.State.Error: ERROR,
    }


class Engine(QObject):
    """Wraps one libVLC MediaPlayer and exposes Qt signals."""

    positionChanged = Signal(float)      # 0.0 .. 1.0
    timeChanged = Signal(int, int)       # current_ms, total_ms
    stateChanged = Signal(str)           # one of the state constants above
    mediaChanged = Signal(str)           # media title / file name
    volumeChanged = Signal(int)          # 0 .. 125
    endReached = Signal()
    errorOccurred = Signal(str)
    tracksChanged = Signal()             # audio / subtitle track list changed
    videoPresenceChanged = Signal(bool)  # True while the media is showing video

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        if vlc is None:
            raise EngineError(vlc_import_hint())

        # --no-xlib keeps libVLC from poking X11 itself; we give it a window handle.
        args = ["--no-video-title-show", "--quiet"]
        if not sys.platform.startswith("win") and sys.platform != "darwin":
            args.append("--no-xlib")
        try:
            self._instance = vlc.Instance(args)
            if self._instance is None:
                raise EngineError("libVLC could not be initialised.")
            self._player = self._instance.media_player_new()
        except Exception as exc:  # noqa: BLE001 - surface any libVLC failure cleanly
            raise EngineError(f"Could not start the VLC engine: {exc}") from exc

        self._state = IDLE
        self._title = ""
        self._duration = 0
        self._seeking = False
        self._has_video = False
        self._volume = 80          # libVLC ignores volume until audio starts, so we keep it

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # -- window embedding -------------------------------------------------
    def attach_to(self, widget) -> None:
        """Render video into the given Qt widget's native window."""
        handle = int(widget.winId())
        # let Qt (not libVLC) receive clicks and keys over the video
        self._player.video_set_mouse_input(False)
        self._player.video_set_key_input(False)
        if sys.platform.startswith("win"):
            self._player.set_hwnd(handle)
        elif sys.platform == "darwin":
            self._player.set_nsobject(handle)
        else:
            self._player.set_xwindow(handle)

    # -- media ------------------------------------------------------------
    def open(self, path: str, play: bool = True) -> None:
        media = self._instance.media_new(path) if "://" in path else self._instance.media_new_path(path)
        if media is None:
            self.errorOccurred.emit(f"Couldn't open: {path}")
            return
        media.parse_with_options(vlc.MediaParseFlag.local, 0)
        self._player.set_media(media)
        self._title = self._derive_title(media, path)
        self.mediaChanged.emit(self._title)
        media.release()
        if play:
            self.play()
        self.tracksChanged.emit()

    @staticmethod
    def _derive_title(media, path: str) -> str:
        try:
            meta = media.get_meta(vlc.Meta.Title)
            if meta:
                return meta
        except Exception:  # noqa: BLE001
            pass
        if "://" in path:
            return path
        return os.path.basename(path) or path

    # -- transport --------------------------------------------------------
    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.set_pause(1)

    def toggle_pause(self) -> None:
        if self._player.get_media() is None:
            return
        self._player.pause()  # libVLC toggles

    def stop(self) -> None:
        self._player.stop()
        self._duration = 0
        self._emit_state(STOPPED)
        self.positionChanged.emit(0.0)
        self.timeChanged.emit(0, 0)

    def is_playing(self) -> bool:
        return bool(self._player.is_playing())

    # -- seeking ----------------------------------------------------------
    def set_position(self, fraction: float) -> None:
        fraction = max(0.0, min(1.0, fraction))
        if self._player.is_seekable():
            self._player.set_position(fraction)
            self.positionChanged.emit(fraction)

    def step(self, seconds: float) -> None:
        total = self._player.get_length()
        if total <= 0:
            return
        now = self._player.get_time()
        target = max(0, min(total - 1, now + int(seconds * 1000)))
        self._player.set_time(target)
        self.positionChanged.emit(target / total)
        self.timeChanged.emit(target, total)

    def begin_scrub(self) -> None:
        self._seeking = True

    def end_scrub(self, fraction: float) -> None:
        self.set_position(fraction)
        self._seeking = False

    # -- volume -----------------------------------------------------------
    def volume(self) -> int:
        return self._volume

    def set_volume(self, value: int) -> None:
        value = max(0, min(125, int(value)))
        self._volume = value
        self._player.audio_set_volume(value)   # may be ignored before playback; re-applied on play
        self.volumeChanged.emit(value)

    def is_muted(self) -> bool:
        return bool(self._player.audio_get_mute())

    def toggle_mute(self) -> None:
        self._player.audio_toggle_mute()
        self.volumeChanged.emit(0 if self.is_muted() else self.volume())

    # -- speed ------------------------------------------------------------
    def rate(self) -> float:
        return float(self._player.get_rate() or 1.0)

    def set_rate(self, rate: float) -> None:
        self._player.set_rate(max(0.25, min(4.0, rate)))

    # -- tracks (audio / subtitles) --------------------------------------
    def audio_tracks(self) -> list[tuple[int, str]]:
        return self._track_list(self._player.audio_get_track_description,
                                self._player.audio_get_track)

    def set_audio_track(self, track_id: int) -> None:
        self._player.audio_set_track(track_id)

    def subtitle_tracks(self) -> list[tuple[int, str]]:
        return self._track_list(self._player.video_get_spu_description,
                                self._player.video_get_spu)

    def set_subtitle_track(self, track_id: int) -> None:
        self._player.video_set_spu(track_id)

    def add_subtitle_file(self, path: str) -> bool:
        # libVLC wants a URI with a scheme here (file:///...), not a plain path
        uri = path if "://" in path else Path(path).resolve().as_uri()
        try:
            ok = self._player.add_slave(vlc.MediaSlaveType.subtitle, uri, True) == 0
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            self.errorOccurred.emit("Couldn't load that subtitle file.")
        self.tracksChanged.emit()
        return ok

    @staticmethod
    def _track_list(describe, current) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        try:
            for item in (describe() or []):
                name = item[1].decode("utf-8", "replace") if isinstance(item[1], bytes) else str(item[1])
                out.append((item[0], name))
        except Exception:  # noqa: BLE001
            pass
        return out

    # -- snapshot ---------------------------------------------------------
    def snapshot(self, path: str) -> bool:
        return self._player.video_take_snapshot(0, path, 0, 0) == 0

    # -- internal polling -------------------------------------------------
    def _tick(self) -> None:
        if vlc is None:
            return
        try:
            state = _STATE_MAP.get(self._player.get_state(), IDLE)
        except Exception:  # noqa: BLE001
            return
        if state != self._state:
            if state == PLAYING:
                self._player.audio_set_volume(self._volume)
            self._emit_state(state)
            if state == ENDED:
                self.endReached.emit()
            elif state == ERROR:
                self.errorOccurred.emit("Playback error – the file may be unsupported or damaged.")

        try:
            has_video = self._player.has_vout() > 0
        except Exception:  # noqa: BLE001
            has_video = False
        if state in (STOPPED, ENDED, IDLE, ERROR):
            has_video = False
        if has_video != self._has_video:
            self._has_video = has_video
            self.videoPresenceChanged.emit(has_video)

        total = self._player.get_length()
        if total != self._duration and total > 0:
            self._duration = total
        if not self._seeking and self._duration > 0:
            now = self._player.get_time()
            if now >= 0:
                self.timeChanged.emit(now, self._duration)
                self.positionChanged.emit(now / self._duration)

    def _emit_state(self, state: str) -> None:
        self._state = state
        self.stateChanged.emit(state)

    @property
    def state(self) -> str:
        return self._state

    @property
    def duration(self) -> int:
        return self._duration

    @property
    def has_video(self) -> bool:
        return self._has_video

    @property
    def title(self) -> str:
        return self._title

    def shutdown(self) -> None:
        self._timer.stop()
        try:
            self._player.stop()
            self._player.release()
            self._instance.release()
        except Exception:  # noqa: BLE001
            pass
