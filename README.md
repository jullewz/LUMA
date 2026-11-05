<p align="center"><img src="assets/logo-256.png" width="128" alt="Luma logo"></p>

<h1 align="center">Luma</h1>
<p align="center"><b>A modern, liquid-glass media player.</b><br>
Frameless translucent window with real desktop blur, built on the libVLC engine – so it plays everything VLC plays.</p>

---

## Features

- **Liquid-glass window** – frameless, rounded and translucent, with real backdrop blur on
  Windows 10/11 (acrylic) and KDE Plasma (BOBOS OS included). Elsewhere it falls back to a painted frosted glass.
- **Three glass strengths** – press **Ctrl+T** to switch between *Clear glass*, *Frosted glass* and *Solid*.
- **Plays almost anything** – MP4, MKV, WebM, AVI, MOV, MP3, FLAC, WAV, OGG, Opus, network streams (`http://`, `rtsp://`…),
  because playback is done by libVLC, the engine inside VLC.
- **Glass "now playing" card** for music – the glass stays visible when there's no picture.
- **Playlist panel** with shuffle, loop, add files, and drag & drop of files or whole folders.
- **Audio track and subtitle menus**, loading external subtitles (`.srt`, `.ass`, `.vtt`…).
- **Playback speed** from 0.25× to 4×, **snapshots** saved to your Pictures folder.
- **Fullscreen** where the bars hide automatically and come back when you move the mouse.
- Custom-drawn controls: smooth seek bar with live time preview, animated buttons, glass menus and toasts.

## Install & run

Luma is a Python app. It needs **Python 3.9+**, **VLC** (for its playback engine) and two Python libraries
(PySide6 for the window, python-vlc to talk to VLC).

### Windows

1. Install **Python** from <https://www.python.org/downloads/> and tick **"Add python.exe to PATH"**.
2. Install **VLC (64-bit)** from <https://www.videolan.org/vlc/>.
3. Extract the zip and double-click **`Luma.bat`**.
   The first start installs the libraries (takes a minute), after that it opens right away.

### Linux (Debian / Ubuntu / BOBOS OS)

```bash
sudo apt install vlc python3-venv
./luma.sh
```

`luma.sh` makes its own virtual environment on the first run. To add Luma to your app menu, copy the folder to
`/opt/luma` and the `luma.desktop` file to `~/.local/share/applications/`.

### macOS

```bash
brew install --cask vlc      # or install VLC from videolan.org
./luma.sh
```

### Any system, by hand

```bash
python -m pip install -r requirements.txt
python luma.py  [optional files or folders to play]
```

## Keyboard shortcuts

| Key | Action |
|---|---|
| **Space** / **K** | Play / pause |
| **← / →** | Back / forward 5 s |
| **J / L** | Back / forward 10 s |
| **Shift + ← / →** | Back / forward 1 min |
| **↑ / ↓** | Volume up / down |
| **M** | Mute |
| **F** / double-click | Fullscreen (Esc to leave) |
| **0–9** | Jump to 0 %–90 % of the file |
| **N / P** | Next / previous in the playlist |
| **S** | Stop |
| **O** / **Ctrl+O** | Open files |
| **Ctrl+L** | Show / hide the playlist |
| **. / ,** | Speed up / slow down |
| **Ctrl+S** | Snapshot |
| **Ctrl+T** | Glass strength: clear / frosted / solid |
| **Ctrl+Q** | Quit |

Move the window by dragging the title bar, maximize by double-clicking it, and resize from any edge or corner.

## How it works

```
luma.py              entry point
luma/app.py          Qt application, dark palette, command-line files
luma/window.py       the frameless glass window, layout, shortcuts, menus, fullscreen, drag & drop
luma/engine.py       libVLC wrapper – exposes playback as Qt signals (no libVLC threads touch the UI)
luma/glass.py        native blur: Windows acrylic, KDE blur-behind, painted fallback
luma/controls.py     title bar and control bar
luma/playlist.py     playlist panel and queue logic
luma/widgets.py      hand-painted glass buttons and sliders
luma/icons.py        all icons as inline SVG (crisp at any DPI) + the logo
```

The video itself is drawn by libVLC into a native window. Normal widgets can't be drawn on top of that reliably,
so the title bar and controls sit **above and below** the video as glass bars instead of floating over it.
Only the small toast messages float, as their own windows.

## Notes

- **Glass on other systems:** GNOME and macOS don't let apps request blur in this way, so Luma uses its painted frosted
  glass there (still translucent, just not blurred).
- **VLC is required.** Luma uses VLC's engine, so VLC itself must be installed. If it's missing, Luma tells you
  how to install it instead of crashing.
- Luma is an independent player and isn't affiliated with VideoLAN or VLC.

## License

MIT – do what you like, keep the copyright notice.
